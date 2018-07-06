
"""
A general purpose tokenizing module.

This module strives to achieve powerful tokenizing options without having to write much code. That is, one should not
need to subclass Tokenizer; Tokenizer provides plenty of customizability simply through parameters.
"""


from collections import deque
import io
import itertools
from string import ascii_lowercase, ascii_uppercase, digits, punctuation, whitespace
import regex as re


# this may be edited to change what is considered eof
eof = None
# this may be edited to change what is considered an escape character
escape = "\\"


def search_unescaped_pattern(seq, escape=escape):
    """
    Return a regex pattern string (warning: NOT a compiled regex object) which can be used to find a given sequence
    which is not escaped (i.e. not preceded by the given escape sequence).
    :param seq: the sequence to search for
    :param escape: the sequence which is treated as escaping anything that follows it
    :return:
    """
    return r"(?<=([^{escape}]|^)({escape}{{2}})*(?!{escape})){seq}".format(seq=re.escape(seq), escape=re.escape(escape))


class Tokenizer:
    """
    The Tokenizer class uses a set of rules specified as arguments to __init__ and a given input stream/string to
    yield a token complying to the aforementioned rules. Note that more than one input stream/string can be specified
    by placing them in a list when passed to __init__ or by using add_source.

    This class determines how to handle each character in the input stream/string by determining it's "type". The type
    can be "token character", "split character", "unknown character", or "container character" (these terms will be used
    frequently throughout the documentation below). No character can be classified explicitly as more than one type. A
    token character is one that is allowed to be present inside a token. A split character is one that acts as a
    delimiter between tokens. A container character is one which signifies the start of a container (see below for more
    details on what constitutes a "container"). An unknown character is one which does not fall into any of the previous
    categories. Unknown characters cannot be explicitly chosen; they are simply any character not explicitly put into
    any other group. Token chars and split chars are passed in as parameters to __init__.

    How Tokenizer should handle unknown characters can be specified as a argument to __init__. The options--which can be
    found as class variables--are to return the unknown character as an individual token, strip (remove) the unknown
    character entirely, or treat the unknown character as a split character.

    Containers are a special kind of token which are contained between two predefined characters. This allows one to
    define a container opening character and a container closing character and treat everything in-between them as one
    token, despite any other rules regarding what constitutes a token. Particularly useful containers one might want to
    define are quotes--"..."--or parentheses--(...)--, for example. Also, options exist for specifying whether or not to
    slice off the bounding (opening/closing) characters, recursively tokenize inside the container, or allow for nesting
    of multiple instances of the containers. When recursively tokenizing inside a container, the same rules for the
    master tokenizer are used and the inside tokens are returned as a python list. If both recursive tokenization of
    containers and keeping the bounds of containers are selected as options, the bounding characters of the container
    will be individual elements of the returned list. Refer to __init__ for how to specify the details of each
    container.

    One can specify a sequence to be treated as the identifier for a comment, in which case everything after (up to the
    next new line) and including the comment-indicating sequence will be ignored.

    Finally, one can also escape characters by placing the escaping character (by default and convention the backslash)
    before the character to be escaped. How this escaped character is handled depends on its type and what characters of
    this type should be treated as when they are escaped. For example, one might specify that a split character be
    treated as a token character when escaped (i.e. an escaped split character could be included in a token). How each
    character type is handled when escaped is specified by four arguments--one for each type--to __init__.

    For convenience, Tokenizer objects are iterable. Also, the get_all_tokens method is provided to quickly and easily
    get all remaining tokens as a list.

    If the customizability offered by simple arguments upon instantiation of a Tokenizer is not enough, consider
    subclassing Tokenizer and implementing the three offered hooks new_line_hook, char_hook_pre_escape,
    and char_hook_post_escape.
    """

    # the three possible values for unknown_char_handling
    RETURN_UNKNOWN = 1
    STRIP_UNKNOWN = 2
    SPLIT_AT_UNKNOWN = 3

    # the four character types which determine how each character is handled
    TOKEN_CHAR_TYPE = 1
    SPLIT_CHAR_TYPE = 2
    UNKNOWN_CHAR_TYPE = 3
    CONTAINER_CHAR_TYPE = 4

    def __init__(self, stream,
                 token_chars=ascii_lowercase+ascii_uppercase+digits+"_",
                 containers=None,
                 comment_seq="#",
                 split_chars=whitespace,
                 unknown_char_handling=RETURN_UNKNOWN,
                 escaped_token_handling=TOKEN_CHAR_TYPE,
                 escaped_split_handling=TOKEN_CHAR_TYPE,
                 escaped_unknown_handling=UNKNOWN_CHAR_TYPE,
                 escaped_container_handling=UNKNOWN_CHAR_TYPE):
        """
        :param stream: the input stream or string, or a list of them, to read lines from
        :param token_chars: a string of characters to be treated as of TOKEN_CHAR_TYPE
        :param containers: a dictionary defining the characteristics of containers in the following format:
            containers = {<str: cont1_opening_char>: (<str: closing_char>, <bool: keep_bounds?>,
                                                      <bool: tokenize_inside?>, <bool: nesting_allowed?>), ...}
        :param comment_seq: a sequence of characters which will be ignored along with everything after it until the next
        newline character; None means no comments should be looked for and removed
        :param split_chars: a string of characters to be treated as of SPLIT_CHAR_TYPE
        :param unknown_char_handling: how to handle characters of UNKNOWN_CHAR_TYPE; one of the three constants
        RETURN_UNKNOWN, STRIP_UNKNOWN, or SPLIT_AT_UNKNOWN
        :param escaped_token_handling: how to handle escaped characters of type TOKEN_CHAR_TYPE; this should simply be
        another type which escaped token chars will be considered as when parsed
        :param escaped_split_handling: how to handle escaped characters of type SPLIT_CHAR_TYPE; this should simply be
        another type which escaped split chars will be considered as when parsed
        :param escaped_unknown_handling: how to handle escaped characters of type UNKNOWN_CHAR_TYPE; this should simply
        be another type which escaped unknown chars will be considered as when parsed
        :param escaped_container_handling: how to handle escaped characters of type CONTAINER_CHAR_TYPE; this should
        simply be another type which escaped container chars will be considered as when parsed
        """
        if isinstance(stream, str):
            self.stream = io.StringIO(stream)
            self._stream_queue = deque()
        elif isinstance(stream, io.IOBase):
            self.stream = stream
            self._stream_queue = deque()
        else:
            self.stream = io.StringIO(stream[0]) if isinstance(stream[0], str) else stream[0]
            self._stream_queue = deque((io.StringIO(x) if isinstance(x, str) else x for x in stream[1:]))

        self.comment_seq = comment_seq

        self.token_chars = token_chars
        self.split_chars = split_chars
        # make sure no characters are both token and split chars as this would make no sense (even though the behaviour
        # is predictable)
        token_and_split_chars = set(self.token_chars).intersection(self.split_chars)
        if token_and_split_chars:
            raise ValueError("characters cannot be token and split characters: {}".format(token_and_split_chars))

        if unknown_char_handling not in (Tokenizer.RETURN_UNKNOWN, Tokenizer.STRIP_UNKNOWN, Tokenizer.SPLIT_AT_UNKNOWN):
            raise ValueError("invalid unknown_char_handling specification: {} (must be Tokenizer.<RETURN_UNKNOWN | "
                             "STRIP_UNKNOWN | SPLIT_AT_UNKNOWN>)".format(unknown_char_handling))
        self.unknown_char_handling = unknown_char_handling

        self.containers = containers or {}
        for c in self.containers:
            if c == self.containers[c][0] and self.containers[c][3]:
                raise ValueError("nesting on containers with identical left and right bounds is unsupported")
            if c in token_chars or self.containers[c][0] in token_chars:
                raise ValueError("container open/close cannot be in token_chars")
            if c in split_chars or self.containers[c][0] in split_chars:
                raise ValueError("container open/close cannot be in split_chars")

        self.escape_handling = {Tokenizer.TOKEN_CHAR_TYPE: escaped_token_handling,
                                Tokenizer.SPLIT_CHAR_TYPE: escaped_split_handling,
                                Tokenizer.UNKNOWN_CHAR_TYPE: escaped_unknown_handling,
                                Tokenizer.CONTAINER_CHAR_TYPE: escaped_container_handling}
        # this works because the keys of the above dict are the valid types and the values of the above dict are the
        # inputted types; if there are more than the 4 valid and unique types, something must be wrong
        if len(set(self.escape_handling.values()).union(set(self.escape_handling.keys()))) > 4:
            raise ValueError("escaped character handling must be one of Tokenizer.<TOKEN_CHAR_TYPE | SPLIT_CHAR_TYPE | "
                             "UNKNOWN_CHAR_TYPE | CONTAINER_CHAR_TYPE>")

        self._curr_line = ""
        self._token_stack = deque()

    def get_token(self):
        """
        Fetch the next token using the following source priority:
            _token_stack > _curr_line > _fetch_next_line (i.e. next line from the stream)
        Firstly, the token stack is checked for any tokens. Tokens end up on the token stack if
            1. they were manually placed there by the user (for whatever reason);
            2. parsing a container yielded extra container opening chars in front of it which need to be returned first
               so the parsed container (in order to avoid wastefully re-parsing it later), and any tokens in front of it
               (except for the very first one), was placed on the stack;
            3. an unknown char was parsed with unknown_char_handling == RETURN_UNKNOWN and so (once again, to avoid
               having to re-parse it later) the unknown char gets placed on the stack.
        Next new lines are continuously fetched zero or more times so that line is not empty. Also, any comments and any
        split_chars on the new line stripped.
        If the first character of this line is a container opening character, then the container parsing if block is
        entered, which, to summarize (refer to the source for greater detail), parses the container according to the
        predefined specifications in containers. This is by far the most complex part of the parsing process.
        Finally, the last parsing stage is reached, which, in short, iterates through the current line, classifying
        each character it reaches as a token char, split char, container char, or unknown char, and acts upon said
        character appropriately.
        :return: the next token or EOF
        """
        tok = ""

        # nearly the entire function must be placing in a loop because, even after all the processing below, tok may end
        # up being empty
        # e.g. If we start with a line consisting of a bunch unknown chars, for example, and
        # unknown_char_handling == Tokenizer.STRIP_UNKNOWN. We would strip all the unknowns then be left with nothing
        # to return.
        while tok == "":
            # check if preprocessed tokens from previous calls are waiting to be popped from the token stack
            try:
                tok = self._token_stack.pop()
                return tok
            except IndexError:
                # if the deque/stack is empty, IndexError is raised
                pass

            # left strip only, otherwise containers which aren't internally tokenized will be incorrect
            self._curr_line = (self._curr_line or "").lstrip(self.split_chars)
            while not self._curr_line:
                # continually fetch new lines and strip off split chars until either something remains to be parsed or
                # we reach EOF
                self._curr_line = self._fetch_next_line()
                if self._curr_line == eof:
                    return eof
                self._curr_line = self._curr_line.lstrip(self.split_chars)

            # first check if the next token is a container
            if self._curr_line[0] in self.containers:
                # make renamed copies of these for readability
                container_spec = self.containers[self._curr_line[0]]
                container_open, container_close = self._curr_line[0], container_spec[0]
                # these regular expressions are used to find unescaped container open or close chars within the line
                search_close_re = re.compile(search_unescaped_pattern(container_close))
                search_open_re = re.compile(search_unescaped_pattern(container_open))
                # if we manage to isolate a container token it will place it in here while any other potential chars in
                # front of it will be in "tok"
                container_tok = ""
                # if nesting allowed
                if container_spec[3]:
                    # counters for how many opening and closing container chars have been found
                    # one of three things will happen with these counters:
                    #   1. we achieve n_opening_matches == n_closing_matches: i.e. nesting was perfect; no problems.
                    #   2. n_opening_matches < n_closing_matches: i.e. we have too many closing chars. This is also no
                    #      problem as we just strip the extra ones off the right side and take care of them when the
                    #      next token is requested.
                    #   3. n_opening_matches > n_closing_matches: i.e. we have too many opening chars and the stream is
                    #      exhausted. This is a little more tricky. We will slice the token at an opening char such the
                    #      right-hand-side string slice has an equal number of opening and closing chars. This resulting
                    #      right-hand-side slice will then be sliced at the last closing char (making it a string whose
                    #      bounding characters are opening and closing chars, respectively) and the piece sliced off
                    #      without any opening/closing chars will be set as the _curr_line to be parsed later. The
                    #      container string will be parsed and added to the token stack. The left-hand-side slice from
                    #      earlier (with excess opening chars) will be tokenized completely; the first token will be
                    #      returned and the others appended to the token stack. Note the reason for tokenizing the
                    #      container string in advance and appending it to the stack is so it doesn't have to be parsed
                    #      again (this means the tokenizing process will be slowed down in the short-run but sped up in
                    #      the long-run because we needn't re-isolate the container string).
                    n_opening_matches, n_closing_matches = 0, 0
                    # continually loop until we reach one of the three states discussed above
                    while True:
                        # first we count the opening chars upto the first closing char
                        try:
                            # this line will raise AttributeError if no closing char is found
                            next_close_idx = search_close_re.search(self._curr_line).start()
                            # slice up to the found closing char and append this to the token
                            cut = self._curr_line[:next_close_idx]
                            tok += cut
                            # add the number of opening chars found in the cut to the running sum
                            n_opening_matches += len(search_open_re.findall(cut))
                            # slice off this cut from the current line
                            self._curr_line = self._curr_line[next_close_idx:]
                        except AttributeError:  # if no closing chars were found
                            # increase the running sum of opening chars found appropriately
                            n_opening_matches += len(search_open_re.findall(self._curr_line))
                            # add the entire line to the token
                            tok += self._curr_line
                            # set the line to an empty string to signify we need to fetch the next line from the stream
                            self._curr_line = ""

                        # now, count the closing chars upto the next opening char
                        try:
                            # this line will raise AttributeError if no opening char is found
                            next_open_idx = search_open_re.search(self._curr_line).start()
                            # if at least one opening char was found
                            # slice up to the found opening char and append this to the token
                            cut = self._curr_line[:next_open_idx]
                            tok += cut
                            # add the number of closing chars found in the cut to the running sum
                            n_closing_matches += len(search_close_re.findall(cut))
                            # slice off this cut from the current line
                            self._curr_line = self._curr_line[next_open_idx:]
                        except AttributeError:  # if no opening chars were found
                            # note this except clause is always ran if the except clause from the previous try block
                            # also ran but nothing will happen here because the line is already empty

                            # increase the running sum of opening chars found appropriately
                            n_closing_matches += len(search_close_re.findall(self._curr_line))
                            # add the entire line to the token
                            tok += self._curr_line
                            # set the line to an empty string to signify we need to fetch the next line from the stream
                            self._curr_line = ""

                        # break out of the loop if we've found enough or too many closing chars (cases 1 and 2 above)
                        if n_opening_matches - n_closing_matches <= 0:
                            break
                        # fetch the next line if the current line is empty
                        if self._curr_line == "":
                            self._curr_line = self._fetch_next_line()
                            # if we've reached EOF, also break out of the loop (case 3 above)
                            if self._curr_line == eof:
                                break
                    # cases 1 and 2 above
                    if n_opening_matches <= n_closing_matches:
                        # find where the last desired closing char is
                        cut_idx = next(itertools.islice(search_close_re.finditer(tok), n_opening_matches-1, None))\
                            .start()
                        # add right-hand-side string slice to the front of the line to be parsed later
                        self._curr_line = tok[cut_idx+1:] + self._curr_line
                        # the remaining left-hand-side slice is now our desired token with an equal number of opening
                        # and closing chars
                        container_tok = tok[:cut_idx+1]
                        # there is no excess in front of the container token to be parsed, thus make tok empty
                        tok = ""
                    # case 3 above
                    else:
                        # find where the first desired opening char is
                        # (tbh no idea why the "or 1" is necessary but it doesn't work sometimes without it)
                        left_cut_idx = next(itertools.islice(search_open_re.finditer(tok),
                                                             n_opening_matches-(n_closing_matches or 1), None)).start()
                        try:
                            # find where the last closing char is
                            last_match = None
                            for last_match in search_close_re.finditer(tok):
                                pass
                            # this line will raise AttributeError if no closing char is found
                            right_cut_idx = last_match.start()
                            # if there was at least one closing char and thus at least one container,
                            # set the line to everything after the last closing char to be parsed later
                            self._curr_line = tok[right_cut_idx+1:]
                            # isolated container token
                            container_tok = tok[left_cut_idx:right_cut_idx+1]
                            # any other characters in front of the container token
                            tok = tok[:left_cut_idx]
                        except AttributeError:
                            # if there wasn't at least one closing char we needn't move any variables around as tok
                            # already contains "misc. chars" and container_tok is empty
                            # all we'll do is change _curr_line to "" from None
                            self._curr_line = ""

                # if nesting is not allowed (instead we just look for the first occurrence of the closing char)
                else:
                    next_close_idx = None
                    # if the container open/close are the same, make sure we don't simply match the same char!
                    if container_open == container_close:
                        search_in = self._curr_line[1:]
                        add_one = True
                    else:
                        search_in = self._curr_line
                        add_one = False
                    while True:
                        try:
                            # attempt to find closing char withing the current line
                            next_close_idx = search_close_re.search(search_in).start() + add_one
                            break
                        except AttributeError:
                            # repeatedly add the line to the token and fetch a new line until we either exhaust the
                            # stream or find a closing char
                            tok += self._curr_line
                            self._curr_line = self._fetch_next_line()
                            # if we've reached EOF, break out of the loop
                            if self._curr_line == eof:
                                break
                    # if we managed to find a closing char
                    if next_close_idx is not None:
                        # set container_tok to the tok and everything upto and including the closing char in the line
                        container_tok = tok + self._curr_line[:next_close_idx+1]
                        # set line to everything after the closing char to be parsed later
                        self._curr_line = self._curr_line[next_close_idx+1:]
                        # there is no excess in front of the container token to be parsed, thus make tok empty
                        tok = ""
                    # otherwise, no closing char is found and hence no closed containers were found
                    else:
                        # if there wasn't at least one closing char we needn't move any variables around as tok already
                        # contains "misc. chars" and container_tok is empty
                        # all we'll do is change _curr_line to "" from None
                        self._curr_line = ""
                # if we isolated a container token
                if container_tok:
                    # if this type of container should itself be tokenized
                    if container_spec[2]:
                        # if this type of container should keep its bounds
                        if container_spec[1]:
                            # to make things simple, we will create a copy of this Tokenizer using the container token
                            # as the input stream and fetch all its tokens recursively
                            container_tok = [container_tok[0]] + \
                                            self.copy(container_tok[1:-1]).get_all_tokens() + \
                                            [container_tok[-1]]
                        # if this type of container should not keep its bounds
                        else:
                            # same as above: make a copy of this Tokenizer and fetch all the container token's tokens
                            # only without the bounds included this time
                            container_tok = self.copy(container_tok[1:-1]).get_all_tokens()
                    # if this type of container should not itself be tokenized
                    else:
                        # if this type of container should not keep its bounds
                        if not container_spec[1]:
                            container_tok = container_tok[1:-1]
                    # if this is the next token in queue
                    if tok == "":
                        return container_tok
                    # otherwise we must append the container token to the stack to be popped off later
                    else:
                        self._token_stack.append(container_tok)

            # if we've reached this point and tok is empty, then there ought to be something in line which we will read
            # from to determine the next token to send
            # if tok has something in it though (implying the massive if block above did something) then line might or
            # might have not something in it, but either way we mustn't access line because there ought to be something
            # of higher priority in the token stack which will be sent on the next token request
            escape_hit = False
            parsing_curr_line = tok == ""
            toks = []  # stores all the tokens being built
            curr_tok = ""  # stores the token currently being built
            idx = 0
            for idx, char in enumerate(self._curr_line if parsing_curr_line else tok):
                char = self.char_hook_pre_escape(char)
                if escape_hit:
                    # reset flag
                    escape_hit = False
                    # exchange what type this char actually is for what it should be treated as when escaped
                    char_type = self.escape_handling[self._get_char_type(char)]
                elif char == escape:
                    # silently ignoring this escape char effectively strips it from the line but we still set a flag so
                    # that we process the next character as escaped
                    escape_hit = True
                    continue
                else:
                    char_type = self._get_char_type(char)
                char, char_type = self.char_hook_post_escape(char, char_type)

                # special handling for container types
                if char_type == Tokenizer.CONTAINER_CHAR_TYPE:
                    if not parsing_curr_line:
                        # this only happens if we parsed a container above and thus any found container chars are
                        # "excess" open container chars, which should be treated as unknown
                        char_type = Tokenizer.UNKNOWN_CHAR_TYPE
                    else:
                        # this only happens if we did NOT parse a container above
                        idx -= 1
                        break

                if char_type == Tokenizer.TOKEN_CHAR_TYPE:
                    curr_tok += char
                elif char_type == Tokenizer.SPLIT_CHAR_TYPE:
                    # only break from encountering a split char if tok is not empty
                    if curr_tok:
                        toks.append(curr_tok)
                        curr_tok = ""
                elif char_type == Tokenizer.UNKNOWN_CHAR_TYPE:
                    if self.unknown_char_handling == Tokenizer.RETURN_UNKNOWN:
                        if curr_tok:
                            toks.append(curr_tok)
                            curr_tok = ""
                        toks.append(char)
                    elif self.unknown_char_handling == Tokenizer.SPLIT_AT_UNKNOWN:
                        if curr_tok:
                            toks.append(curr_tok)
                            curr_tok = ""
                    else:  # self.unknown_char_handling == Tokenizer.STRIP_UNKNOWN
                        # silently ignoring this character effectively strips it from the line
                        pass
            if parsing_curr_line:
                self._curr_line = self._curr_line[idx+1:]
            if curr_tok:
                # make sure the token that was being built as the loop broke doesn't get ignored
                toks.append(curr_tok)
            # tok must be cleared because it might contain only chars which were supposed to be stripped, in which case
            # this loop, conditioned on tok being empty, should be ran again
            tok = ""
            # the first token must be returned, should it exist
            try:
                tok = toks[0]
            except IndexError:
                continue
            # the remaining tokens in the list are appended to the stack in reverse order so that the leftmost list
            # elements are popped off first, as they should be
            self._token_stack.extend(toks[1:][::-1])

        return tok

    def _fetch_next_line(self):
        """
        Fetch the next line from the stream and strip the comments from it.
        If the current stream is exhausted, attempt to fetch a new stream from the stream queue and read from it.
        :return: the next line with comments stripped or EOF
        """
        line = self.stream.readline()
        while line == "":  # i.e. while current stream is exhausted
            # try to get a new stream from the stream queue
            try:
                # must pop from left side so queue is in FIFO order
                self.stream = self._stream_queue.popleft()
            except IndexError:
                # this means the stream queue is empty
                break
            # read a line from the new stream
            line = self.stream.readline()
        line = self._strip_comments(line) if line != "" else eof
        return self.new_line_hook(line)

    def _strip_comments(self, line):
        """
        Strip comments from the given line.
        :param line: the line to strip comments from
        :return: the line with comments stripped
        """
        if self.comment_seq:
            comment = line.find(self.comment_seq)
            if comment != -1:
                return line[:comment]
        return line

    def _get_char_type(self, char):
        """
        Get the type of the given character. "Type" refers to one of the four unique types used in determining how to
        parse each character.
        :param char: a character to retrieve the type of
        :return: the type of char
        """
        if char in self.containers:
            return Tokenizer.CONTAINER_CHAR_TYPE
        elif char in self.token_chars:
            return Tokenizer.TOKEN_CHAR_TYPE
        elif char in self.split_chars:
            return Tokenizer.SPLIT_CHAR_TYPE
        else:
            return Tokenizer.UNKNOWN_CHAR_TYPE

    def get_all_tokens(self):
        """
        A convenient way to retrieve all the remaining tokens as a list.
        This function is used in get_token when tokenizing inside containers.
        :return: the list of all the remaining tokens
        """
        return [tok for tok in self]

    def __iter__(self):
        return self

    def __next__(self):
        tok = self.get_token()
        if tok == eof:
            raise StopIteration
        return tok

    def copy(self, stream):
        """
        Create a new Tokenizer with the same parameters as this one but with new data.
        :param stream: the new stream (or string) to read tokens from
        :return: the new Tokenizer copy
        """
        return Tokenizer(stream, self.token_chars, self.containers, self.comment_seq,
                         self.split_chars, self.unknown_char_handling,
                         self.escape_handling[Tokenizer.TOKEN_CHAR_TYPE],
                         self.escape_handling[Tokenizer.SPLIT_CHAR_TYPE],
                         self.escape_handling[Tokenizer.UNKNOWN_CHAR_TYPE],
                         self.escape_handling[Tokenizer.CONTAINER_CHAR_TYPE])

    def add_source(self, stream):
        """
        Add a new stream (or string) to the stream queue to be read from once the current stream is exhausted.
        :param stream: the new stream or string
        :return: None
        """
        self._stream_queue.append(io.StringIO(stream) if isinstance(stream, str) else stream)

    # noinspection PyMethodMayBeStatic
    def new_line_hook(self, line):
        """
        A hook that can be optionally implemented to augment each line when they are fetched.
        This hook is called in _fetch_next_line after the line is read from the stream, the comments are stripped, and
        the line is converted to eof (defaults to None) if it equals "" (empty string).
        It is recommended one should attempt to achieve their desired functionality by adjusting the parameters of the
        Tokenizer class before resorting to implementing any hooks.
        By default just return the inputted line (i.e. no change).
        :param line: the input line before hook is applied (either a string or eof)
        :return: the output line after the hook is applied (either a string or eof)
        """
        return line

    # noinspection PyMethodMayBeStatic
    def char_hook_pre_escape(self, char):
        """
        A hook that can be optionally implemented to augment each character as they are processed.
        This hook is called in get_token while looping through the current line BEFORE any character escaping occurs
        (and hence this character may actually be an escape character, which defaults to backslash) or the character
        type is determined.
        It is recommended one should attempt to achieve their desired functionality by adjusting the parameters of the
        Tokenizer class before resorting to implementing any hooks.
        By default just return the inputted character (i.e. no change).
        :param char: the input character before hook is applied (as a string)
        :return: the output character after hook is applied (as a string)
        """
        return char

    # noinspection PyMethodMayBeStatic
    def char_hook_post_escape(self, char, char_type):
        """
        A hook that can be optionally implemented to augment each character as they are processed.
        This hook is called in get_token while looping through the current line AFTER any character escaping occurs
        (and hence this character will never be an escape character, which defaults to backslash) and the character
        type is determined.
        Be sure to check out the get_token method to see exactly how a change to this character's type will effect the
        outcome of the get_token call.
        It is recommended one should attempt to achieve their desired functionality by adjusting the parameters of the
        Tokenizer class before resorting to implementing any hooks.
        By default just return the inputted character and character type (i.e. no change).
        :param char: the input character before hook is applied (as a string)
        :param char_type: one of the four character types: Tokenizer.<TOKEN_CHAR_TYPE | SPLIT_CHAR_TYPE |
        UNKNOWN_CHAR_TYPE | CONTAINER_CHAR_TYPE>
        :return: the output character after hook is applied (as a string) and one of the four character types
        """
        return char, char_type


if __name__ == '__main__':
    import sys
    tokenizer = Tokenizer(sys.stdin, containers={"(": (")", True, True, True)})
    print(tokenizer.get_all_tokens())
