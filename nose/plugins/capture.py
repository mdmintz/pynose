"""This plugin captures stdout during test execution. If a test fails
or raises an error, the captured output will be appended to the error
or failure output. It is disabled by default, but can be enabled with
the options: ``--capture-output`` or ``--capture_output``.
Or enable it by setting os.environ["NOSE_CAPTURE"] to "1".

:Options:
  ``--capture-output`` or ``--capture_output``
    Capture stdout (stdout output will not be printed) """
import logging
import os
import sys
from nose.plugins.base import Plugin
from nose.pyversion import exc_to_unicode, force_unicode
from nose.util import ln
from io import StringIO

log = logging.getLogger(__name__)


class Capture(Plugin):
    """Output-capturing plugin. Now disabled by default.
    Can be enabled with ``--capture-output`` or ``--capture_output``.
    Or enable it with os.environ["NOSE_CAPTURE"]="1" before tests."""
    enabled = True
    name = "capture"
    score = 1600

    def __init__(self):
        self.stdout = []
        self._buf = None

    def options(self, parser, env):
        """Register commandline options"""
        parser.add_option(
            "-s", "--nocapture", action="store_false",
            default=False, dest="capture",
            help="Don't capture stdout (any stdout output "
            "will be printed immediately) [NOSE_NOCAPTURE]"
        )
        parser.add_option(
            "--capture-output", "--capture_output", action="store_true",
            default=False, dest="capture_output",
            help="Capture stdout (stdout output "
            "will not be printed) [NOSE_CAPTURE]"
        )

    def configure(self, options, conf):
        """Configure plugin. Plugin is enabled by default."""
        self.conf = conf
        if (
            "NOSE_CAPTURE" in os.environ
            and os.environ["NOSE_CAPTURE"] == "1"
        ) or options.capture_output:
            self.enabled = True
        elif not options.capture:
            self.enabled = False

    def afterTest(self, test):
        """Clear capture buffer."""
        self.end()
        self._buf = None

    def begin(self):
        """Replace sys.stdout with capture buffer."""
        self.start()  # get an early handle on sys.stdout

    def beforeTest(self, test):
        """Flush capture buffer."""
        self.start()

    def formatError(self, test, err):
        """Add captured output to error report."""
        test.capturedOutput = output = self.buffer
        self._buf = None
        if not output:
            # Don't return None as that will prevent other
            # formatters from formatting and remove earlier formatters
            # formats, instead return the err we got
            return err
        ec, ev, tb = err
        return (ec, self.addCaptureToErr(ev, output), tb)

    def formatFailure(self, test, err):
        """Add captured output to failure report."""
        return self.formatError(test, err)

    def addCaptureToErr(self, ev, output):
        ev = exc_to_unicode(ev)
        output = force_unicode(output)
        return '\n'.join(
            [
                ev,
                ln('>> begin captured stdout <<'),
                output,
                ln('>> end captured stdout <<')
            ]
        )

    def start(self):
        self.stdout.append(sys.stdout)
        self._buf = StringIO()
        sys.stdout = self._buf

    def end(self):
        if self.stdout:
            sys.stdout = self.stdout.pop()

    def finalize(self, result):
        """Restore stdout."""
        while self.stdout:
            self.end()

    def _get_buffer(self):
        if self._buf is not None:
            return self._buf.getvalue()
        return None

    buffer = property(_get_buffer, None, None, """Captured stdout output.""")
