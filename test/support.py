"""Support functions for inspect tests. Copied from various places in CPython."""

import collections
import contextlib
import importlib
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
import sysconfig
import tempfile
import unittest
import warnings

@contextlib.contextmanager
def maybe_subtest(test_case, **kwargs):
    """Uses test_case.subTest if available."""
    if hasattr(test_case, 'subTest'):
        with test_case.subTest(**kwargs):
            yield
    else:
        try:
            yield
        except Exception:
            # poor man's subtest support
            print('failed in subtest: {}'.format(kwargs))
            raise

@contextlib.contextmanager
def override(obj, attribute, new_value):
    """Temporarily replaces an attribute on an object."""
    old_value = getattr(obj, attribute)
    try:
        setattr(obj, attribute, new_value)
        yield
    finally:
        setattr(obj, attribute, old_value)

# Copied from subprocess._optim_args_from_interpreter_flags in 3.6
def optim_args_from_interpreter_flags():
    """Return a list of command-line arguments reproducing the current
    optimization settings in sys.flags."""
    args = []
    value = sys.flags.optimize
    if value > 0:
        args.append('-' + 'O' * value)
    return args

# Copied from test_import/__init__.py in 3.6
@contextlib.contextmanager
def ready_to_import(name=None, source=""):
    # sets up a temporary directory and removes it
    # creates the module file
    # temporarily clears the module from sys.modules (if any)
    # reverts or removes the module when cleaning up
    name = name or "spam"
    with temp_dir() as tempdir:
        path = make_script(tempdir, name, source)
        old_module = sys.modules.pop(name, None)
        try:
            sys.path.insert(0, tempdir)
            yield name, path
            sys.path.remove(tempdir)
        finally:
            if old_module is not None:
                sys.modules[name] = old_module
            elif name in sys.modules:
                del sys.modules[name]

# Copied from test/support/__init__.py in 3.6

# Filename used for testing
if os.name == 'java':
    # Jython disallows @ in module names
    TESTFN = '$test'
else:
    TESTFN = '@test'

# Disambiguate TESTFN for parallel testing, while letting it remain a valid
# module name.
TESTFN = "{}_{}_tmp".format(TESTFN, os.getpid())

class TestFailed(Exception):
    """Test failed."""

def _run_suite(suite):
    """Run tests from a unittest.TestSuite-derived class."""
    runner = unittest.TextTestRunner(sys.stdout, verbosity=2,
                                     failfast=False)

    result = runner.run(suite)
    if not result.wasSuccessful():
        if len(result.errors) == 1 and not result.failures:
            err = result.errors[0][1]
        elif len(result.failures) == 1 and not result.errors:
            err = result.failures[0][1]
        else:
            err = "multiple errors occurred"
        raise TestFailed(err)

def run_unittest(*classes):
    """Run tests from unittest.TestCase-derived classes."""
    valid_types = (unittest.TestSuite, unittest.TestCase)
    suite = unittest.TestSuite()
    for cls in classes:
        if isinstance(cls, str):
            if cls in sys.modules:
                suite.addTest(unittest.findTestCases(sys.modules[cls]))
            else:
                raise ValueError("str arguments must be keys in sys.modules")
        elif isinstance(cls, valid_types):
            suite.addTest(cls)
        else:
            suite.addTest(unittest.makeSuite(cls))
    _run_suite(suite)

@contextlib.contextmanager
def temp_dir(path=None, quiet=False):
    """Return a context manager that creates a temporary directory.

    Arguments:

      path: the directory to create temporarily.  If omitted or None,
        defaults to creating a temporary directory using tempfile.mkdtemp.

      quiet: if False (the default), the context manager raises an exception
        on error.  Otherwise, if the path is specified and cannot be
        created, only a warning is issued.

    """
    dir_created = False
    if path is None:
        path = tempfile.mkdtemp()
        dir_created = True
        path = os.path.realpath(path)
    else:
        try:
            os.mkdir(path)
            dir_created = True
        except OSError:
            if not quiet:
                raise
            warnings.warn('tests may fail, unable to create temp dir: ' + path,
                          RuntimeWarning, stacklevel=3)
    try:
        yield path
    finally:
        if dir_created:
            rmtree(path)

def _force_run(path, func, *args):
    try:
        return func(*args)
    except OSError:
        os.chmod(path, stat.S_IRWXU)
        return func(*args)

if sys.platform.startswith("win"):
    def _waitfor(func, pathname, waitall=False):
        # Perform the operation
        func(pathname)
        # Now setup the wait loop
        if waitall:
            dirname = pathname
        else:
            dirname, name = os.path.split(pathname)
            dirname = dirname or '.'
        # Check for `pathname` to be removed from the filesystem.
        # The exponential backoff of the timeout amounts to a total
        # of ~1 second after which the deletion is probably an error
        # anyway.
        # Testing on an i7@4.3GHz shows that usually only 1 iteration is
        # required when contention occurs.
        timeout = 0.001
        while timeout < 1.0:
            # Note we are only testing for the existence of the file(s) in
            # the contents of the directory regardless of any security or
            # access rights.  If we have made it this far, we have sufficient
            # permissions to do that much using Python's equivalent of the
            # Windows API FindFirstFile.
            # Other Windows APIs can fail or give incorrect results when
            # dealing with files that are pending deletion.
            L = os.listdir(dirname)
            if not (L if waitall else name in L):
                return
            # Increase the timeout and try again
            time.sleep(timeout)
            timeout *= 2
        warnings.warn('tests may fail, delete still pending for ' + pathname,
                      RuntimeWarning, stacklevel=4)

    def _unlink(filename):
        _waitfor(os.unlink, filename)

    def _rmdir(dirname):
        _waitfor(os.rmdir, dirname)

    def _rmtree(path):
        def _rmtree_inner(path):
            for name in _force_run(path, os.listdir, path):
                fullname = os.path.join(path, name)
                try:
                    mode = os.lstat(fullname).st_mode
                except OSError as exc:
                    print("support.rmtree(): os.lstat(%r) failed with %s" % (fullname, exc),
                          file=sys.__stderr__)
                    mode = 0
                if stat.S_ISDIR(mode):
                    _waitfor(_rmtree_inner, fullname, waitall=True)
                    _force_run(fullname, os.rmdir, fullname)
                else:
                    _force_run(fullname, os.unlink, fullname)
        _waitfor(_rmtree_inner, path, waitall=True)
        _waitfor(lambda p: _force_run(p, os.rmdir, p), path)
else:
    _unlink = os.unlink
    _rmdir = os.rmdir

    def _rmtree(path):
        try:
            shutil.rmtree(path)
            return
        except OSError:
            pass

        def _rmtree_inner(path):
            for name in _force_run(path, os.listdir, path):
                fullname = os.path.join(path, name)
                try:
                    mode = os.lstat(fullname).st_mode
                except OSError:
                    mode = 0
                if stat.S_ISDIR(mode):
                    _rmtree_inner(fullname)
                    _force_run(path, os.rmdir, fullname)
                else:
                    _force_run(path, os.unlink, fullname)
        _rmtree_inner(path)
        os.rmdir(path)

def unlink(filename):
    try:
        _unlink(filename)
    except (FileNotFoundError, NotADirectoryError):
        pass

def rmdir(dirname):
    try:
        _rmdir(dirname)
    except FileNotFoundError:
        pass

def rmtree(path):
    try:
        _rmtree(path)
    except FileNotFoundError:
        pass

class DirsOnSysPath(object):
    """Context manager to temporarily add directories to sys.path.

    This makes a copy of sys.path, appends any directories given
    as positional arguments, then reverts sys.path to the copied
    settings when the context ends.

    Note that *all* sys.path modifications in the body of the
    context manager, including replacement of the object,
    will be reverted at the end of the block.
    """

    def __init__(self, *paths):
        self.original_value = sys.path[:]
        self.original_object = sys.path
        sys.path.extend(paths)

    def __enter__(self):
        return self

    def __exit__(self, *ignore_exc):
        sys.path = self.original_object
        sys.path[:] = self.original_value

def _parse_guards(guards):
    # Returns a tuple ({platform_name: run_me}, default_value)
    if not guards:
        return ({'cpython': True}, False)
    is_true = list(guards.values())[0]
    assert list(guards.values()) == [is_true] * len(guards)   # all True or all False
    return (guards, not is_true)

# Use the following check to guard CPython's implementation-specific tests --
# or to run them only on the implementation(s) guarded by the arguments.
def check_impl_detail(**guards):
    """This function returns True or False depending on the host platform.
       Examples:
          if check_impl_detail():               # only on CPython (default)
          if check_impl_detail(jython=True):    # only on Jython
          if check_impl_detail(cpython=False):  # everywhere except on CPython
    """
    guards, default = _parse_guards(guards)
    return guards.get(platform.python_implementation().lower(), default)

MISSING_C_DOCSTRINGS = (check_impl_detail() and
                        sys.platform != 'win32' and
                        not sysconfig.get_config_var('WITH_DOC_STRINGS'))

def _id(obj):
    return obj

def cpython_only(test):
    """
    Decorator for tests only applicable on CPython.
    """
    return impl_detail(cpython=True)(test)

def impl_detail(msg=None, **guards):
    if check_impl_detail(**guards):
        return _id
    if msg is None:
        guardnames, default = _parse_guards(guards)
        if default:
            msg = "implementation detail not available on {0}"
        else:
            msg = "implementation detail specific to {0}"
        guardnames = sorted(guardnames.keys())
        msg = msg.format(' or '.join(guardnames))
    return unittest.skip(msg)

# Copied from test/support/script_helper.py in 3.6
def make_script(script_dir, script_basename, source, omit_suffix=False):
    script_filename = script_basename
    if not omit_suffix:
        script_filename += os.extsep + 'py'
    script_name = os.path.join(script_dir, script_filename)
    # The script should be encoded to UTF-8, the default string encoding
    script_file = open(script_name, 'w', encoding='utf-8')
    script_file.write(source)
    script_file.close()
    importlib.invalidate_caches()
    return script_name

# Cached result of the expensive test performed in the function below.
__cached_interp_requires_environment = None

def interpreter_requires_environment():
    """
    Returns True if our sys.executable interpreter requires environment
    variables in order to be able to run at all.

    This is designed to be used with @unittest.skipIf() to annotate tests
    that need to use an assert_python*() function to launch an isolated
    mode (-I) or no environment mode (-E) sub-interpreter process.

    A normal build & test does not run into this situation but it can happen
    when trying to run the standard library test suite from an interpreter that
    doesn't have an obvious home with Python's current home finding logic.

    Setting PYTHONHOME is one way to get most of the testsuite to run in that
    situation.  PYTHONPATH or PYTHONUSERSITE are other common environment
    variables that might impact whether or not the interpreter can start.
    """
    global __cached_interp_requires_environment
    if __cached_interp_requires_environment is None:
        # Try running an interpreter with -E to see if it works or not.
        try:
            subprocess.check_call([sys.executable, '-E',
                                   '-c', 'import inspect2, sys; sys.exit(0)'])
        except subprocess.CalledProcessError:
            __cached_interp_requires_environment = True
        else:
            __cached_interp_requires_environment = False

    return __cached_interp_requires_environment


_PythonRunResult = collections.namedtuple("_PythonRunResult",
                                          ("rc", "out", "err"))

def strip_python_stderr(stderr):
    """Strip the stderr of a Python process from potential debug output
    emitted by the interpreter.

    This will typically be run on the result of the communicate() method
    of a subprocess.Popen object.
    """
    stderr = re.sub(br"\[\d+ refs, \d+ blocks\]\r?\n?", b"", stderr).strip()
    return stderr

# Executing the interpreter in a subprocess
__cached_has_isolated_mode = None

def has_isolated_mode():
    global __cached_has_isolated_mode
    if __cached_has_isolated_mode is not None:
        return __cached_has_isolated_mode
    cmdline = [sys.executable, '-I', '-c', 'import inspect2']
    try:
        subprocess.check_call(cmdline)
    except subprocess.CalledProcessError:
        __cached_has_isolated_mode = False
    else:
        __cached_has_isolated_mode = True
    return __cached_has_isolated_mode


def run_python_until_end(*args, **env_vars):
    env_required = interpreter_requires_environment()
    if '__isolated' in env_vars:
        isolated = env_vars.pop('__isolated')
    else:
        isolated = not env_vars and not env_required
    cmd_line = [sys.executable, '-X', 'faulthandler']
    if isolated and has_isolated_mode():
        # isolated mode: ignore Python environment variables, ignore user
        # site-packages, and don't add the current directory to sys.path
        cmd_line.append('-I')
    elif not env_vars and not env_required:
        # ignore Python environment variables
        cmd_line.append('-E')
    # Need to preserve the original environment, for in-place testing of
    # shared library builds.
    env = os.environ.copy()
    # set TERM='' unless the TERM environment variable is passed explicitly
    # see issues #11390 and #18300
    if 'TERM' not in env_vars:
        env['TERM'] = ''
    # But a special flag that can be set to override -- in this case, the
    # caller is responsible to pass the full environment.
    if env_vars.pop('__cleanenv', None):
        env = {}
    env.update(env_vars)
    cmd_line.extend(args)
    proc = subprocess.Popen(cmd_line, stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         env=env)
    with proc:
        try:
            out, err = proc.communicate()
        finally:
            try:
                proc.kill()
            except ProcessLookupError:
                pass  # process may have already exited
            subprocess._cleanup()
    rc = proc.returncode
    err = strip_python_stderr(err)
    return _PythonRunResult(rc, out, err), cmd_line

def _assert_python(expected_success, *args, **env_vars):
    res, cmd_line = run_python_until_end(*args, **env_vars)
    if (res.rc and expected_success) or (not res.rc and not expected_success):
        # Limit to 80 lines to ASCII characters
        maxlen = 80 * 100
        out, err = res.out, res.err
        if len(out) > maxlen:
            out = b'(... truncated stdout ...)' + out[-maxlen:]
        if len(err) > maxlen:
            err = b'(... truncated stderr ...)' + err[-maxlen:]
        out = out.decode('ascii', 'replace').rstrip()
        err = err.decode('ascii', 'replace').rstrip()
        raise AssertionError("Process return code is %d\n"
                             "command line: %r\n"
                             "\n"
                             "stdout:\n"
                             "---\n"
                             "%s\n"
                             "---\n"
                             "\n"
                             "stderr:\n"
                             "---\n"
                             "%s\n"
                             "---"
                             % (res.rc, cmd_line,
                                out,
                                err))
    return res

def assert_python_ok(*args, **env_vars):
    """
    Assert that running the interpreter with `args` and optional environment
    variables `env_vars` succeeds (rc == 0) and return a (return code, stdout,
    stderr) tuple.

    If the __cleanenv keyword is set, env_vars is used as a fresh environment.

    Python is started in isolated mode (command line option -I),
    except if the __isolated keyword is set to False.
    """
    return _assert_python(True, *args, **env_vars)

def assert_python_failure(*args, **env_vars):
    """
    Assert that running the interpreter with `args` and optional environment
    variables `env_vars` fails (rc != 0) and return a (return code, stdout,
    stderr) tuple.

    See assert_python_ok() for more options.
    """
    return _assert_python(False, *args, **env_vars)
