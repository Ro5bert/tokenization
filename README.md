# tokenization
A general purpose text tokenizing module for python.
Create application-specific tokenizers while writing little code.

Most tokenizing libraries require one to subclass a tokenizing
class to achieve one's desired functionality, but `tokenization`
merely takes a variety of simple arguments to fit nearly any use
case. (With that said, it is always better to use a library suited
specifically for one's needs, if it exists.)

## Features
- Choose which characters should be included in tokens and which
characters should mark the end of a token
- Input data either from a string or a stream (e.g. a file)
- Specify how "unknown" characters (characters not given an
explicit classification) should be handled
- Specify types of "containers," which are pairs of characters
which treat everything between them as one token (e.g. useful
containers might be parentheses "(...)" or square brackets "[...]")
- Customizable escape sequence handling
- Highly documented/commented source code 

## Install
`pip install tokenization`

## Examples
##### Parentheses Container
```python
>>>from tokenization import Tokenizer
>>>input_str = "hello 123 (this is a container) #comment"
>>>container = {"(": (")", True, False, True)}
>>>tokenizer = Tokenizer(input_str, containers=container)
>>>tokenizer.get_all_tokens()
['hello', '123', '(this is a container)']
```

##### Parentheses Container with Internal Tokenization
```python
>>>from tokenization import Tokenizer
>>>input_str = "hello 123 (this is a container) #comment"
>>>container = {"(": (")", True, True, True)}
>>>tokenizer = Tokenizer(input_str, containers=container)
>>>tokenizer.get_all_tokens()
['hello', '123', ['(', 'this', 'is', 'a', 'container', ')']]
```

##### Escaping Containers
```python
>>>from tokenization import Tokenizer
>>>input_str = "hello 123 \\(this is a container) #comment"
>>>container = {"(": (")", True, True, True)}
>>>tokenizer = Tokenizer(input_str, containers=container)
>>>tokenizer.get_all_tokens()
['hello', '123', '(', 'this', 'is', 'a', 'container', ')']
```
