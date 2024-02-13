"""
Overview
========
The multiprocess plugin enables you to distribute your test run among a set of
worker processes that run tests in parallel. This can speed up CPU-bound test
runs (as long as the number of work processeses is around the number of
processors or cores available), but is mainly useful for IO-bound tests that
spend most of their time waiting for data to arrive from someplace else.
.. _multiprocessing : http://code.google.com/p/python-multiprocessing/

How tests are distributed
=========================
The ideal case would be to dispatch each test to a worker process separately.
This ideal is not attainable in all cases, however, because many test suites
depend on context (class, module, or package) fixtures.
The plugin can't know (unless you tell it -- see below!) if a context fixture
can be called many times concurrently (is re-entrant), or if it can be shared
among tests running in different processes. Therefore, if a context has
fixtures, the default behavior is to dispatch the suite to a worker as a unit.

Controlling distribution
========================
There are two context-level variables to control this default behavior:
* If a context's fixtures are re-entrant, set `_multiprocess_can_split_ = True`
in the context, and the plugin will dispatch tests in suites bound to that
context as if the context had no fixtures. This means that the fixtures will
execute concurrently and multiple times, typically once per test.
* If a context's fixtures can be shared by tests running in different processes
(such as a package-level fixture that starts an external http server or
initializes a shared database) then set ``_multiprocess_shared_ = True`` in
the context. These fixtures will then execute in the primary nose process,
and tests in those contexts will be individually dispatched to run in parallel.

How results are collected and reported
======================================
As each test or suite executes in a worker process, results (failures, errors,
and specially handled exceptions like SkipTest) are collected in that process.
When the worker process finishes, it returns results to the main nose process.
There, any progress output is printed (dots!), and the results from the
test run are combined into a consolidated result set.
When results have been received for all dispatched tests,
or all workers have died, the result summary is output as normal.

Beware!
=======
Not all test suites will benefit from, or even operate correctly using this
plugin. For example, CPU-bound tests will run more slowly if you don't have
multiple processors. There are also some differences in plugin interactions
and behaviors due to the way in which tests are dispatched and loaded.
In general, tests loaded under this plugin operate as if they were always in
directed mode instead of discovered mode. For instance, doctests in test
modules will always be found when using this plugin with the doctest plugin.
But the biggest issue you will face is probably concurrency. Unless you
have kept your tests as religiously pure unit tests, with no side-effects, no
ordering issues, and no external dependencies, chances are you will experience
odd, intermittent and unexplainable failures and errors when using this
plugin. This doesn't necessarily mean the plugin is broken;
it may mean that your test suite is not safe for concurrency."""
import logging
import os
import sys
import time
import unittest
import pickle
import signal
import nose.case
from nose.core import TextTestRunner
from nose import failure
from nose import loader
from nose.plugins.base import Plugin
from nose.pyversion import bytes_
from nose.suite import ContextSuite
from nose.util import test_address
from unittest.runner import _WritelnDecorator
from queue import Empty
from warnings import warn
from io import StringIO

_instantiate_plugins = None
log = logging.getLogger(__name__)
Process = Queue = Pool = Event = Value = Array = None


class TimedOutException(KeyboardInterrupt):

    def __init__(self, value="Timed Out"):
        self.value = value

    def __str__(self):
        return repr(self.value)


def _import_mp():
    global Process, Queue, Pool, Event, Value, Array
    try:
        from multiprocessing import Manager, Process
        old = signal.signal(signal.SIGINT, signal.SIG_IGN)
        m = Manager()
        signal.signal(signal.SIGINT, old)
        Queue, Pool, Event, Value, Array = (
                m.Queue, m.Pool, m.Event, m.Value, m.Array
        )
    except ImportError:
        warn("multiprocessing module is not available, multiprocess plugin "
             "cannot be used", RuntimeWarning)


class TestLet:
    def __init__(self, case):
        try:
            self._id = case.id()
        except AttributeError:
            pass
        self._short_description = case.shortDescription()
        self._str = str(case)

    def id(self):
        return self._id

    def shortDescription(self):
        return self._short_description

    def __str__(self):
        return self._str


class MultiProcess(Plugin):
    """Run tests in multiple processes. Requires processing module."""
    score = 1000
    status = {}

    def options(self, parser, env):
        """Register command-line options."""
        parser.add_option(
            "--processes", action="store",
            default=env.get('NOSE_PROCESSES', 0),
            dest="multiprocess_workers", metavar="NUM",
            help="Spread test run among this many processes. "
            "Set a number equal to the number of processors "
            "or cores in your machine for best results. "
            "Pass a negative number to have the number of "
            "processes automatically set to the number of cores. "
            "Passing 0 means to disable parallel testing. "
            "Default is 0 unless NOSE_PROCESSES is set. [NOSE_PROCESSES]")
        parser.add_option(
            "--process-timeout", action="store",
            default=env.get('NOSE_PROCESS_TIMEOUT', 10),
            dest="multiprocess_timeout", metavar="SECONDS",
            help="Set timeout for return of results from each "
            "test runner process. Default is 10. [NOSE_PROCESS_TIMEOUT]")
        parser.add_option(
            "--process-restartworker", action="store_true",
            default=env.get('NOSE_PROCESS_RESTARTWORKER', False),
            dest="multiprocess_restartworker",
            help="If set, will restart each worker process once"
            " their tests are done, this helps control memory "
            "leaks from killing the system. [NOSE_PROCESS_RESTARTWORKER]")

    def configure(self, options, config):
        """Configure plugin."""
        try:
            self.status.pop('active')
        except KeyError:
            pass
        if not hasattr(options, 'multiprocess_workers'):
            self.enabled = False
            return
        if config.worker:
            return  # Don't start inside of a worker process
        self.config = config
        try:
            workers = int(options.multiprocess_workers)
        except (TypeError, ValueError):
            workers = 0
        if workers:
            _import_mp()
            if Process is None:
                self.enabled = False
                return
            if workers < 0:
                import multiprocessing
                workers = multiprocessing.cpu_count()
            self.enabled = True
            self.config.multiprocess_workers = workers
            t = float(options.multiprocess_timeout)
            self.config.multiprocess_timeout = t
            r = int(options.multiprocess_restartworker)
            self.config.multiprocess_restartworker = r
            self.status['active'] = True

    def prepareTestLoader(self, loader):
        """Remember loader class so MultiProcessTestRunner can instantiate
        the right loader."""
        self.loaderClass = loader.__class__

    def prepareTestRunner(self, runner):
        """Replace test runner with MultiProcessTestRunner."""
        return MultiProcessTestRunner(
            stream=runner.stream, verbosity=self.config.verbosity,
            config=self.config, loaderClass=self.loaderClass)


def signalhandler(sig, frame):
    raise TimedOutException()


class MultiProcessTestRunner(TextTestRunner):
    # Max time to wait to terminate a process that does not respond to SIGILL.
    waitkilltime = 5.0

    def __init__(self, **kw):
        self.loaderClass = kw.pop('loaderClass', loader.defaultTestLoader)
        super(MultiProcessTestRunner, self).__init__(**kw)

    def collect(self, test, testQueue, tasks, to_teardown, result):
        for case in self.nextBatch(test):
            log.debug("Next batch %s (%s)", case, type(case))
            if (
                isinstance(case, nose.case.Test)
                and isinstance(case.test, failure.Failure)
            ):
                log.debug("Case is a Failure")
                case(result)
                continue
            if isinstance(
                case, ContextSuite
            ) and case.context is failure.Failure:
                log.debug("Case is a Failure")
                case(result)
                continue
            elif isinstance(case, ContextSuite) and self.sharedFixtures(case):
                log.debug("%s has shared fixtures", case)
                try:
                    case.setUp()
                except (KeyboardInterrupt, SystemExit):
                    raise
                except Exception:
                    log.debug("%s setup failed", sys.exc_info())
                    result.addError(case, sys.exc_info())
                else:
                    to_teardown.append(case)
                    if case.factory:
                        ancestors = case.factory.context.get(case, [])
                        for an in ancestors[:2]:
                            if getattr(an, '_multiprocess_shared_', False):
                                an._multiprocess_can_split_ = True
                    self.collect(case, testQueue, tasks, to_teardown, result)
            else:
                test_addr = self.addtask(testQueue, tasks, case)
                log.debug(
                    "Queued test %s (%s) to %s",
                    len(tasks), test_addr, testQueue,
                )

    def startProcess(
        self, iworker, testQueue, resultQueue, shouldStop, result
    ):
        currentaddr = Value('c', bytes_(''))
        currentstart = Value('d', time.time())
        keyboardCaught = Event()
        p = Process(
            target=runner,
            args=(
                iworker,
                testQueue,
                resultQueue,
                currentaddr,
                currentstart,
                keyboardCaught,
                shouldStop,
                self.loaderClass,
                result.__class__,
                pickle.dumps(self.config),
            )
        )
        p.currentaddr = currentaddr
        p.currentstart = currentstart
        p.keyboardCaught = keyboardCaught
        old = signal.signal(signal.SIGILL, signalhandler)
        p.start()
        signal.signal(signal.SIGILL, old)
        return p

    def run(self, test):
        """Execute the test (which may be a suite). If the test is a suite,
        distribute it out among as many processes as have been configured, at
        as fine a level as is possible given the context fixtures defined in
        the suite or any sub-suites."""
        log.debug("%s.run(%s) (%s)", self, test, os.getpid())
        wrapper = self.config.plugins.prepareTest(test)
        if wrapper is not None:
            test = wrapper
        wrapped = self.config.plugins.setOutputStream(self.stream)
        if wrapped is not None:
            self.stream = wrapped
        testQueue = Queue()
        resultQueue = Queue()
        tasks = []
        completed = []
        workers = []
        to_teardown = []
        shouldStop = Event()
        result = self._makeResult()
        start = time.time()
        self.collect(test, testQueue, tasks, to_teardown, result)
        log.debug("Starting %s workers", self.config.multiprocess_workers)
        for i in range(self.config.multiprocess_workers):
            p = self.startProcess(
                i, testQueue, resultQueue, shouldStop, result
            )
            workers.append(p)
            log.debug("Started worker process %s", i+1)
        total_tasks = len(tasks)
        nexttimeout = self.config.multiprocess_timeout
        thrownError = None
        try:
            while tasks:
                log.debug(
                    "Waiting for results (%s/%s tasks), next timeout=%.3fs",
                    len(completed), total_tasks, nexttimeout,
                )
                try:
                    iworker, addr, newtask_addrs, batch_result = (
                        resultQueue.get(timeout=nexttimeout)
                    )
                    log.debug(
                        'Results received for worker %d, %s, new tasks: %d',
                        iworker, addr, len(newtask_addrs),
                    )
                    try:
                        try:
                            tasks.remove(addr)
                        except ValueError:
                            log.warning(
                                'worker %s failed to remove from tasks: %s',
                                iworker, addr,
                            )
                        total_tasks += len(newtask_addrs)
                        tasks.extend(newtask_addrs)
                    except KeyError:
                        log.debug("Got result for unknown task? %s", addr)
                        log.debug("current: %s", str(list(tasks)[0]))
                    else:
                        completed.append([addr, batch_result])
                    self.consolidate(result, batch_result)
                    if (
                        self.config.stopOnError and not result.wasSuccessful()
                    ):
                        shouldStop.set()
                        break
                    if self.config.multiprocess_restartworker:
                        log.debug('joining worker %s', iworker)
                        workers[iworker].join(timeout=1)
                        if not shouldStop.is_set() and not testQueue.empty():
                            log.debug(
                                'starting new process on worker %s', iworker
                            )
                            workers[iworker] = self.startProcess(
                                iworker,
                                testQueue,
                                resultQueue,
                                shouldStop,
                                result,
                            )
                except Empty:
                    msg = "Timeout - %s tasks pending (empty testQueue=%r): %s"
                    log.debug(msg, len(tasks), testQueue.empty(), str(tasks))
                    any_alive = False
                    for iworker, w in enumerate(workers):
                        if w.is_alive():
                            worker_addr = bytes_(w.currentaddr.value, 'ascii')
                            timeprocessing = time.time() - w.currentstart.value
                            if (
                                len(worker_addr) == 0
                                and timeprocessing
                                > self.config.multiprocess_timeout - 0.1
                            ):
                                log.debug(
                                    'Worker %d finished its work item, but is '
                                    'not exiting. Do we wait for it?', iworker,
                                )
                            else:
                                any_alive = True
                            if (
                                len(worker_addr) > 0
                                and timeprocessing
                                > self.config.multiprocess_timeout - 0.1
                            ):
                                msg = 'Timed out worker %s: %s'
                                log.debug(msg, iworker, worker_addr)
                                w.currentaddr.value = bytes_('')
                                w.keyboardCaught.clear()
                                startkilltime = time.time()
                                while (
                                    not w.keyboardCaught.is_set()
                                    and w.is_alive()
                                ):
                                    if (
                                        time.time() - startkilltime
                                        > self.waitkilltime
                                    ):
                                        msg = "terminating worker %s"
                                        log.error(msg, iworker)
                                        w.terminate()
                                        workers[iworker] = w = (
                                            self.startProcess(
                                                iworker,
                                                testQueue,
                                                resultQueue,
                                                shouldStop,
                                                result,
                                            )
                                        )
                                        break
                                    os.kill(w.pid, signal.SIGILL)
                                    time.sleep(0.1)
                    if not any_alive and testQueue.empty():
                        log.debug("All workers are dead")
                        break
                nexttimeout = self.config.multiprocess_timeout
                for w in workers:
                    if w.is_alive() and len(w.currentaddr.value) > 0:
                        timeprocessing = time.time() - w.currentstart.value
                        if timeprocessing <= self.config.multiprocess_timeout:
                            nexttimeout = min(
                                nexttimeout,
                                self.config.multiprocess_timeout
                                - timeprocessing,
                            )
            log.debug(
                "Completed %s tasks (%s remain)", len(completed), len(tasks)
            )
        except (KeyboardInterrupt, SystemExit) as e:
            log.info('parent received ctrl-c when waiting for test results')
            thrownError = e
            result.addError(test, sys.exc_info())
        try:
            for case in to_teardown:
                log.debug("Tearing down shared fixtures for %s", case)
                try:
                    case.tearDown()
                except (KeyboardInterrupt, SystemExit):
                    raise
                except Exception:
                    result.addError(case, sys.exc_info())
            stop = time.time()
            result.printErrors()
            result.printSummary(start, stop)
            self.config.plugins.finalize(result)
            if thrownError is None:
                log.debug("Tell all workers to stop")
                for w in workers:
                    if w.is_alive():
                        testQueue.put('STOP', block=False)
            for iworker, worker in enumerate(workers):
                if worker.is_alive():
                    log.debug('joining worker %s', iworker)
                    worker.join()
                    if worker.is_alive():
                        log.debug('failed to join worker %s', iworker)
        except (KeyboardInterrupt, SystemExit):
            log.info(
                'parent received ctrl-c when shutting down: stop all processes'
            )
            for worker in workers:
                if worker.is_alive():
                    worker.terminate()
            if thrownError:
                raise thrownError
            else:
                raise
        return result

    def addtask(testQueue, tasks, case):
        arg = None
        if isinstance(case, nose.case.Test) and hasattr(case.test, 'arg'):
            case.test.descriptor = None
            arg = case.test.arg
        test_addr = MultiProcessTestRunner.address(case)
        testQueue.put((test_addr, arg), block=False)
        if arg is not None:
            test_addr += str(arg)
        if tasks is not None:
            tasks.append(test_addr)
        return test_addr
    addtask = staticmethod(addtask)

    def address(case):
        if hasattr(case, 'address'):
            file, mod, call = case.address()
        elif hasattr(case, 'context'):
            file, mod, call = test_address(case.context)
        else:
            raise Exception("Unable to convert %s to address" % case)
        parts = []
        if file is None:
            if mod is None:
                raise Exception("Unaddressable case %s" % case)
            else:
                parts.append(mod)
        else:
            dirname, basename = os.path.split(file)
            if basename.startswith('__init__'):
                file = dirname
            parts.append(file)
        if call is not None:
            parts.append(call)
        return ':'.join(map(str, parts))
    address = staticmethod(address)

    def nextBatch(self, test):
        # Tests can mark themselves as not safe for multiprocess execution.
        if hasattr(test, 'context'):
            if not getattr(test.context, '_multiprocess_', True):
                return
        if (
            (
                isinstance(test, ContextSuite)
                and test.hasFixtures(self.checkCanSplit)
            )
            or not getattr(test, 'can_split', True)
            or not isinstance(test, unittest.TestSuite)
        ):
            if isinstance(test, ContextSuite):
                contained = list(test)
                if (
                    len(contained) == 1
                    and getattr(contained[0], 'context', None) == test.context
                ):
                    test = contained[0]
            yield test
        else:
            for case in test:
                yield from self.nextBatch(case)

    def checkCanSplit(context, fixt):
        """Callback to check whether the fixtures found in a context or
        ancestor are ones we care about. Contexts can tell us that their
        fixtures are reentrant by setting _multiprocess_can_split_."""
        if not fixt:
            return False
        if getattr(context, '_multiprocess_can_split_', False):
            return False
        return True
    checkCanSplit = staticmethod(checkCanSplit)

    def sharedFixtures(self, case):
        context = getattr(case, 'context', None)
        if not context:
            return False
        return getattr(context, '_multiprocess_shared_', False)

    def consolidate(self, result, batch_result):
        log.debug("batch result is %s", batch_result)
        try:
            output, testsRun, failures, errors, errorClasses = batch_result
        except ValueError:
            log.debug("result in unexpected format %s", batch_result)
            failure.Failure(*sys.exc_info())(result)
            return
        self.stream.write(output)
        result.testsRun += testsRun
        result.failures.extend(failures)
        result.errors.extend(errors)
        for key, (storage, label, isfail) in list(errorClasses.items()):
            if key not in result.errorClasses:
                result.errorClasses[key] = ([], label, isfail)
            mystorage, _junk, _junk = result.errorClasses[key]
            mystorage.extend(storage)
        log.debug("Ran %s tests (total: %s)", testsRun, result.testsRun)


def runner(
    ix, testQueue, resultQueue, currentaddr, currentstart,
    keyboardCaught, shouldStop, loaderClass, resultClass, config
):
    try:
        try:
            return __runner(
                ix, testQueue, resultQueue, currentaddr, currentstart,
                keyboardCaught, shouldStop, loaderClass, resultClass, config
            )
        except KeyboardInterrupt:
            log.debug('Worker %s keyboard interrupt, stopping', ix)
    except Empty:
        log.debug("Worker %s timed out waiting for tasks", ix)


def __runner(
    ix, testQueue, resultQueue, currentaddr, currentstart,
    keyboardCaught, shouldStop, loaderClass, resultClass, config
):
    config = pickle.loads(config)
    dummy_parser = config.parserClass()
    if _instantiate_plugins is not None:
        for pluginclass in _instantiate_plugins:
            plugin = pluginclass()
            plugin.addOptions(dummy_parser, {})
            config.plugins.addPlugin(plugin)
    config.plugins.configure(config.options, config)
    config.plugins.begin()
    log.debug("Worker %s executing, pid=%d", ix, os.getpid())
    loader = loaderClass(config=config)
    loader.suiteClass.suiteClass = NoSharedFixtureContextSuite

    def get():
        return testQueue.get(timeout=config.multiprocess_timeout)

    def makeResult():
        stream = _WritelnDecorator(StringIO())
        result = resultClass(
            stream, descriptions=1, verbosity=config.verbosity, config=config
        )
        plug_result = config.plugins.prepareTestResult(result)
        if plug_result:
            return plug_result
        return result

    def batch(result):
        failures = [(TestLet(c), err) for c, err in result.failures]
        errors = [(TestLet(c), err) for c, err in result.errors]
        errorClasses = {}
        for key, (storage, label, isfail) in list(result.errorClasses.items()):
            errorClasses[key] = (
                [(TestLet(c), err) for c, err in storage], label, isfail
            )
        return (
            result.stream.getvalue(),
            result.testsRun,
            failures,
            errors,
            errorClasses
        )
    for test_addr, arg in iter(get, 'STOP'):
        if shouldStop.is_set():
            log.exception('Worker %d STOPPED', ix)
            break
        result = makeResult()
        test = loader.loadTestsFromNames([test_addr])
        test.testQueue = testQueue
        test.tasks = []
        test.arg = arg
        log.debug("Worker %s Test is %s (%s)", ix, test_addr, test)
        try:
            if arg is not None:
                test_addr = test_addr + str(arg)
            currentaddr.value = bytes_(test_addr)
            currentstart.value = time.time()
            test(result)
            currentaddr.value = bytes_('')
            resultQueue.put((ix, test_addr, test.tasks, batch(result)))
        except KeyboardInterrupt as e:
            timeout = isinstance(e, TimedOutException)
            if timeout:
                keyboardCaught.set()
            if len(currentaddr.value):
                if timeout:
                    msg = 'Worker %s timed out, failing current test %s'
                else:
                    msg = (
                        'Worker %s keyboard interrupt, failing current test %s'
                    )
                log.exception(msg, ix, test_addr)
                currentaddr.value = bytes_('')
                failure.Failure(*sys.exc_info())(result)
                resultQueue.put((ix, test_addr, test.tasks, batch(result)))
            else:
                if timeout:
                    msg = 'Worker %s test %s timed out'
                else:
                    msg = 'Worker %s test %s keyboard interrupt'
                log.debug(msg, ix, test_addr)
                resultQueue.put((ix, test_addr, test.tasks, batch(result)))
            if not timeout:
                raise
        except SystemExit:
            currentaddr.value = bytes_('')
            log.exception('Worker %s system exit', ix)
            raise
        except Exception:
            currentaddr.value = bytes_('')
            log.exception(
                "Worker %s error running test or returning results", ix
            )
            failure.Failure(*sys.exc_info())(result)
            resultQueue.put((ix, test_addr, test.tasks, batch(result)))
        if config.multiprocess_restartworker:
            break
    log.debug("Worker %s ending", ix)


class NoSharedFixtureContextSuite(ContextSuite):
    """Context suite that never fires shared fixtures.
    When a context sets _multiprocess_shared_, fixtures in that context
    are executed by the main process. Using this class prevents them
    from executing in the runner process as well."""
    testQueue = None
    tasks = None
    arg = None

    def setupContext(self, context):
        if getattr(context, '_multiprocess_shared_', False):
            return
        super(NoSharedFixtureContextSuite, self).setupContext(context)

    def teardownContext(self, context):
        if getattr(context, '_multiprocess_shared_', False):
            return
        super(NoSharedFixtureContextSuite, self).teardownContext(context)

    def run(self, result):
        """Run tests in suite inside of suite fixtures."""
        log.debug(
            "suite %s (%s) run called, tests: %s", id(self), self, self._tests
        )
        if self.resultProxy:
            result, orig = self.resultProxy(result, self), result
        else:
            result, orig = result, result
        try:
            # log.debug('setUp for %s', id(self));
            self.setUp()
        except KeyboardInterrupt:
            raise
        except Exception:
            self.error_context = 'setup'
            result.addError(self, self._exc_info())
            return
        try:
            for test in self._tests:
                if isinstance(test, nose.case.Test) and self.arg is not None:
                    test.test.arg = self.arg
                else:
                    test.arg = self.arg
                test.testQueue = self.testQueue
                test.tasks = self.tasks
                if result.shouldStop:
                    log.debug("stopping")
                    break
                try:
                    test(orig)
                except KeyboardInterrupt as e:
                    timeout = isinstance(e, TimedOutException)
                    if timeout:
                        msg = 'Timeout when running test %s in suite %s'
                    else:
                        msg = (
                            'KeyboardInterrupt '
                            'when running test %s in suite %s'
                        )
                    log.debug(msg, test, self)
                    err = (
                        TimedOutException,
                        TimedOutException(str(test)),
                        sys.exc_info()[2],
                    )
                    test.config.plugins.addError(test, err)
                    orig.addError(test, err)
                    if not timeout:
                        raise
        finally:
            self.has_run = True
            try:
                # log.debug('tearDown for %s', id(self))
                self.tearDown()
            except KeyboardInterrupt:
                raise
            except Exception:
                self.error_context = 'teardown'
                result.addError(self, self._exc_info())
