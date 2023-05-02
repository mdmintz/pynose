"""
Test Result
-----------
Provides a TextTestResult that extends unittest's _TextTestResult to
provide support for error classes (such as the builtin skip and deprecated
classes), and hooks for plugins to take over or extend reporting."""
import logging
from unittest import TextTestResult as _TextTestResult
from nose.config import Config
from nose.util import isclass, ln as _ln

log = logging.getLogger('nose.result')


def _exception_detail(exc):
    try:
        return str(exc)
    except Exception:
        return '<unprintable %s object>' % type(exc).__name__


class TextTestResult(_TextTestResult):
    """Text test result that extends unittest's default test result
    support for a configurable set of errorClasses (eg, Skip,
    Deprecated, TODO) that extend the errors/failures/success triad."""
    def __init__(self, stream, descriptions, verbosity, config=None,
                 errorClasses=None):
        if errorClasses is None:
            errorClasses = {}
        self.errorClasses = errorClasses
        if config is None:
            config = Config()
        self.config = config
        _TextTestResult.__init__(self, stream, descriptions, verbosity)
        _TextTestResult.addDuration = None

    def addSkip(self, test, reason):
        from nose.plugins.skip import SkipTest
        if SkipTest in self.errorClasses:
            storage, label, isfail = self.errorClasses[SkipTest]
            storage.append((test, reason))
            self.printLabel(label, (SkipTest, reason, None))

    def addError(self, test, err):
        """Overrides normal addError to add support for errorClasses."""
        ec, ev, tb = err
        try:
            exc_info = self._exc_info_to_string(err, test)
        except TypeError:
            exc_info = self._exc_info_to_string(err)
        for cls, (storage, label, isfail) in list(self.errorClasses.items()):
            if isclass(ec) and issubclass(ec, cls):
                if isfail:
                    test.passed = False
                storage.append((test, exc_info))
                self.printLabel(label, err)
                return
        self.errors.append((test, exc_info))
        test.passed = False
        self.printLabel('ERROR')

    def getDescription(self, test):
        if self.descriptions:
            return test.shortDescription() or str(test)
        else:
            return str(test)

    def printLabel(self, label, err=None):
        stream = getattr(self, 'stream', None)
        if stream is not None:
            if self.showAll:
                message = [label]
                if err:
                    detail = _exception_detail(err[1])
                    if detail:
                        message.append(detail)
                stream.writeln(": ".join(message))
            elif self.dots:
                stream.write(label[:1])

    def printErrors(self):
        """Overrides to print all errorClasses errors as well."""
        _TextTestResult.printErrors(self)
        for cls in list(self.errorClasses.keys()):
            storage, label, isfail = self.errorClasses[cls]
            if isfail:
                self.printErrorList(label, storage)
        if hasattr(self, 'config'):
            self.config.plugins.report(self.stream)

    def printSummary(self, start, stop):
        """Called by the test runner to print the final results summary."""
        write = self.stream.write
        writeln = self.stream.writeln
        taken = float(stop - start)
        run = self.testsRun
        plural = run != 1 and "s" or ""
        writeln(self.separator2)
        writeln("Ran %s test%s in %.3fs" % (run, plural, taken))
        writeln()
        summary = {}
        eckeys = list(self.errorClasses.keys())
        for cls in eckeys:
            storage, label, isfail = self.errorClasses[cls]
            count = len(storage)
            if not count:
                continue
            summary[label] = count
        if len(self.failures):
            summary['failures'] = len(self.failures)
        if len(self.errors):
            summary['errors'] = len(self.errors)
        if not self.wasSuccessful():
            write("FAILED")
        else:
            write("OK")
        items = list(summary.items())
        if items:
            items.sort()
            write(" (")
            write(", ".join(["%s=%s" % (label, count) for
                             label, count in items]))
            writeln(")")
        else:
            writeln()

    def wasSuccessful(self):
        if self.errors or self.failures:
            return False
        for cls in list(self.errorClasses.keys()):
            storage, label, isfail = self.errorClasses[cls]
            if not isfail:
                continue
            if storage:
                return False
        return True

    def _addError(self, test, err):
        try:
            exc_info = self._exc_info_to_string(err, test)
        except TypeError:
            exc_info = self._exc_info_to_string(err)
        self.errors.append((test, exc_info))
        if self.showAll:
            self.stream.write('ERROR')
        elif self.dots:
            self.stream.write('E')

    def _exc_info_to_string(self, err, test=None):
        from nose.plugins.skip import SkipTest
        if isclass(err[0]) and issubclass(err[0], SkipTest):
            return str(err[1])
        try:
            return _TextTestResult._exc_info_to_string(self, err, test)
        except TypeError:
            return _TextTestResult._exc_info_to_string(self, err)


def ln(*arg, **kw):
    from warnings import warn
    warn("ln() has moved to nose.util from nose.result and will be removed "
         "from nose.result in a future release. Please update your imports ",
         DeprecationWarning)
    return _ln(*arg, **kw)
