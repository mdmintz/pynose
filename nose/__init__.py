import sys
from nose.core import collector, main, run, run_exit, runmodule
from nose.exc import SkipTest, DeprecatedTest
from nose.tools import with_setup
from nose.__version__ import __version__
import collections

__author__ = 'Jason Pellerin (Original) / Michael Mintz (Update)'
version_list = [int(i) for i in __version__.split(".") if i.isdigit()]
__versioninfo__ = tuple(version_list)
__version__ = '.'.join(map(str, __versioninfo__))
__all__ = [
    'main', 'run', 'run_exit', 'runmodule', 'with_setup',
    'SkipTest', 'DeprecatedTest', 'collector'
]
if sys.version_info >= (3, 10):
    collections.Callable = collections.abc.Callable
