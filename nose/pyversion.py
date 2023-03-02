"""This module contains nose fixes for different versions of Python."""
import sys
import os
import traceback
import types
import inspect
import nose.util

__all__ = ['make_instancemethod', 'cmp_to_key', 'sort_list', 'ClassType',
           'TypeType', 'UNICODE_STRINGS', 'unbound_method', 'ismethod',
           'bytes_', 'is_base_exception', 'force_unicode', 'exc_to_unicode',
           'format_exception']
UNICODE_STRINGS = True


def force_unicode(s, encoding='UTF-8'):
    return str(s)


try:
    import new

    def make_instancemethod(function, instance):
        return new.instancemethod(
            function.__func__, instance, instance.__class__)
except ImportError:
    def make_instancemethod(function, instance):
        return function.__get__(instance, instance.__class__)


def cmp_to_key(mycmp):
    'Convert a cmp= function into a key= function'
    class Key(object):
        def __init__(self, obj):
            self.obj = obj

        def __lt__(self, other):
            return mycmp(self.obj, other.obj) < 0

        def __gt__(self, other):
            return mycmp(self.obj, other.obj) > 0

        def __eq__(self, other):
            return mycmp(self.obj, other.obj) == 0

    return Key


def sort_list(l, key, reverse=False):  # noqa: E741
    return l.sort(key=key, reverse=reverse)


if hasattr(types, 'ClassType'):
    ClassType = type
    TypeType = type
else:
    ClassType = type
    TypeType = type


class UnboundMethod:
    def __init__(self, cls, func):
        self.__dict__ = func.__dict__.copy()
        self._func = func
        self.__self__ = UnboundSelf(cls)
        self.__doc__ = getattr(func, '__doc__', None)

    def address(self):
        cls = self.__self__.cls
        modname = cls.__module__
        module = sys.modules[modname]
        filename = getattr(module, '__file__', None)
        if filename is not None:
            filename = os.path.abspath(filename)
        return (
            nose.util.src(filename),
            modname, "%s.%s" % (cls.__name__, self._func.__name__)
        )

    def __call__(self, *args, **kwargs):
        return self._func(*args, **kwargs)

    def __getattr__(self, attr):
        return getattr(self._func, attr)

    def __repr__(self):
        return '<unbound method %s.%s>' % (
            self.__self__.cls.__name__, self._func.__name__
        )


class UnboundSelf:
    def __init__(self, cls):
        self.cls = cls

    def __getattribute__(self, attr):
        if attr == '__class__':
            return self.cls
        else:
            return object.__getattribute__(self, attr)


def unbound_method(cls, func):
    if inspect.ismethod(func):
        return func
    if not inspect.isfunction(func):
        raise TypeError('%s is not a function' % (repr(func),))
    return UnboundMethod(cls, func)


def ismethod(obj):
    return inspect.ismethod(obj) or isinstance(obj, UnboundMethod)


def bytes_(s, encoding='utf8'):
    if isinstance(s, bytes):
        return s
    return bytes(s, encoding)


def isgenerator(o):
    if isinstance(o, UnboundMethod):
        o = o._func
    return inspect.isgeneratorfunction(o) or inspect.isgenerator(o)


def is_base_exception(exc):
    return isinstance(exc, BaseException)


def exc_to_unicode(ev, encoding='utf-8'):
    return str(ev)


def format_exception(exc_info, encoding='UTF-8'):
    ec, ev, tb = exc_info
    if not is_base_exception(ev):
        tb_data = force_unicode(''.join(traceback.format_tb(tb)), encoding)
        ev = exc_to_unicode(ev)
        return tb_data + ev
    else:
        return force_unicode(
            ''.join(traceback.format_exception(*exc_info)), encoding
        )
