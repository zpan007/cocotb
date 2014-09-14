"""
Coverage-related functionality
"""
from functools import wraps
import inspect



class CoverItem(object):
    """
    Ever-expanding dot-scoped coverage counters
    """
    def __init__(self, name, parent=None, filename=None, line_number=None):
        self._name = name
        self._children = {}
        self._parent = parent
        self._count = None
        self._filename = filename
        self._line_number = line_number

    def __getattr__(self, name):
        hier = name.split(".")
        cov = CoverItem(hier[0], parent=self)
        setattr(self, hier[0], cov)
        self._children[hier[0]] = cov
        if len(hier) > 1:
            return getattr(cov, ".".join(hier[1:]))
        return cov

    def __iadd__(self, value):
        if self._count is None:
            self._count = 0
        self._count += value
        return self

    def _dump(self, pstring=""):
        me = "%s.%s" % (pstring, self._name) if pstring else self._name
        rs = ""
        if self._filename is not None:
            rs += "%s is from %s:%d\n" % (me, self._filename, self._line_number)
        if self._count is not None:
            rs += "%s %d\n" % (me.ljust(50), self._count)
        for child in self._children.itervalues():
            rs += child._dump(me)
        return rs

_root = CoverItem("cocotb")

class bins(object):

    """
    Decorator to histogram bin values

    TODO: Use numpy.histogram if available?
    """

    def __init__(self, name, fn=None, bins=None):
        self._name = name
        self._fn = fn
        self._bins = bins
        self._method = None     # Moves to true/false after test

        (frame, filename, line_number, function_name, lines, index) = \
            inspect.getouterframes(inspect.currentframe())[1]

        self._covergroup = getattr(_root, name)
        self._covergroup._filename = filename
        self._covergroup._line_number = line_number
        self._cgs = []

        if bins:
            for index, left in enumerate(bins[:-1]):
                right = bins[index+1]
                self._cgs.append(getattr(self._covergroup, "%d_to_%d" % (left, right-1)))
                self._cgs[-1] += 0
            self._cgs.append(getattr(self._covergroup, "%d_to_infinity" % (right)))
            self._cgs[-1] += 0

    def __call__(self, f):

        @wraps(f)
        def _wrapped_function(*args, **kwargs):

            # This is rather horrible but no reliable way to determine if a
            # decorated function is a bound method...
            if self._method is None:
                arg_spec = inspect.getargspec(f)
                self._method = "self" in arg_spec.args

            call_args = args[1:] if self._method else args
            if self._fn:
                value = self._fn(*call_args)
            else:
                value = call_args[0]
            self._covergroup.hits += 1

            if self._bins is None:
                b = getattr(self._covergroup, "%d" % value)
                b += 1
            else:
                for index, edge in enumerate(self._bins):
                    if value < edge:
                        break
                if index < 0:
                    raise Exception("Illegal value: %d" % value)
                self._cgs[index-1] += 1

            return f(*args, **kwargs)
        return _wrapped_function


    def __get__(self, obj, type=None):
        """
        Permit the decorator to be used on class methods and standalone functions
        """
        return self.__class__(self._func.__get__(obj, type))


class count(object):
    """
    Decorator to count occurrences.

    Optional test function to decide whether to increment or not
    """
    def __init__(self, name, test=None):
        raise NotImplementedError

def dump():
    return _root._dump()
