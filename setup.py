from setuptools import setup, find_packages
import distutils.dir_util


distutils.dir_util.remove_tree("dist")
setup(
    name='tokenization',
    version='1.0.7',
    packages=find_packages(),
    install_requires=[
        "regex"
    ],
    url='https://github.com/Ro5bert/tokenization',
    license='MIT',
    author='Robert Russell',
    author_email='robertrussell.72001@gmail.com',
    description='A general purpose text tokenizing module for python.',
    classifiers=(
        "Topic :: Text Processing",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Operating System :: OS Independent"
    )
)
