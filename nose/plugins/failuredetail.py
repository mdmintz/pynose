"""This plugin provides assert introspection. When the plugin is enabled
and a test failure occurs, the traceback is displayed with extra context
and debugging information around the line where the exception was raised."""
from nose.plugins import Plugin
from nose.pyversion import exc_to_unicode, force_unicode
from nose.inspector import inspect_traceback


class FailureDetail(Plugin):
    """Plugin that provides extra information in tracebacks of test failures"""
    score = 1600  # before capture

    def options(self, parser, env):
        """Register commandline options."""
        parser.add_option(
            "-d", "--detailed-errors", "--failure-detail", action="store_true",
            default=env.get('NOSE_DETAILED_ERRORS'), dest="detailedErrors",
            help="Add detail to error"
            " output by attempting to evaluate failed"
            " asserts [NOSE_DETAILED_ERRORS]"
        )

    def configure(self, options, conf):
        """Configure plugin."""
        if not self.can_configure:
            return
        self.enabled = options.detailedErrors
        self.conf = conf

    def formatFailure(self, test, err):
        """Add detail from traceback inspection to error message of failures"""
        ec, ev, tb = err
        tbinfo, str_ev = None, exc_to_unicode(ev)
        if tb:
            tbinfo = force_unicode(inspect_traceback(tb))
            str_ev = '\n'.join([str_ev, tbinfo])
        test.tbinfo = tbinfo
        return (ec, str_ev, tb)
