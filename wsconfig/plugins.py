import os
from os import path
from subprocess import Popen, list2cmdline
import subprocess
import sys


class ApplyError(Exception):
    def __init__(self, message, process=None):
        Exception.__init__(self, message)
        self.returncode = process.returncode if process else None
        self.process = process


class Plugin(object):
    """Base class for a plugin, implementing a metaclass registry.
    """

    class __metaclass__(type):
        PLUGINS = {}
        def __new__(cls, name, bases, attrs):
            clazz = type.__new__(cls, name, bases, attrs)
            try:
                Plugin
            except NameError:
                pass
            else:
                cls.PLUGINS[clazz.name] = clazz
            return clazz

    # Can be overwritten on a per-plugin or per-instance base
    sudo = False

    def __init__(self, basedir, sudo=None):
        self.basedir = basedir
        if sudo is not None:
            self.sudo = sudo

    def run(self, arguments, state):
        raise NotImplementedError()

    @classmethod
    def log(cls, str):
        print ""
        print "====>", str

    def execute_proc(self, cmdline, *a, **kw):
        """Subclasses should use this to run an external command."""
        if self.sudo:
            cmdline = ['sudo'] + cmdline[:]

        self.log("$ %s" % (list2cmdline(cmdline)
                           if isinstance(cmdline, list) else cmdline))
        try:
            process = Popen(cmdline, *a, **kw)
        except OSError, e:
            raise ApplyError('Failed to run: %s' % e)
        process.wait()
        if process.returncode != 0:
            raise ApplyError(
                'Process returns non-zero code: %s' % process.returncode,
                process)
        return process

    def execute_impl(self, arguments):
        """Subclasses should use this to run their own ``impl`` methods.

        If necessary, will run these methods via sudo.
        """
        if not self.sudo:
            return self.impl(arguments)
        else:
            # It would be pretty to use an environment variable as an indicator
            # that the script should execute a plugin, but those would be lost
            # by sudo.
            try:
                cmdline = ['sudo', sys.executable, '%s' % sys.argv[0],
                             'WSCONFIG_CALL_PLUGIN', self.name] + arguments
                process = Popen(cmdline)
            except OSError, e:
                raise ApplyError('Failed to run %s: %s' % (
                    list2cmdline(cmdline), e))
            process.wait()
            if process.returncode != 0:
                raise ApplyError('Process returns non-zero code: %s' % process.returncode)


class DpkgPlugin(Plugin):
    """Debian package installation.
    """

    name = 'dpkg'
    sudo = True

    def run(self, arguments, state):
        for package in arguments:
            self.execute_proc(['apt-get', 'install', '-y', package])


class Homebrew(Plugin):
    """Homebrew formula installation.

    A command is required for this, because the ``brew`` executable
    returns an error code if the package is already installed.
    """

    name = 'brew'

    def run(self, arguments, state):
        try:
            # In order to check the output, we need to capture it,
            # meaning it won't appear in the console. XXX Possible
            # we can fix this via a wrapper that writes to multiple
            # streams: http://stackoverflow.com/a/9130786
            process = self.execute_proc(['brew', 'install'] + arguments,
                stdout=subprocess.PIPE)
        except ApplyError, e:
            # If the package is already installed, brew returns
            # a specific error code and message. Check for this,
            # and ignore such errors, raise all others.
            stdout = e.process.stdout.read()
            if e.returncode != 1 or (
               not 'already installed' in stdout):
                raise
            print stdout

        else:
            # Output what we captured, though this might be too late
            # (if there was an error).
            print process.stdout.read()


class PipPlugin(Plugin):
    """Pip python package installation.
    """

    name = 'pip'
    sudo = True

    def run(self, arguments, state):
        for package in arguments:
            self.execute_proc(['pip', 'install', package])


class ShellPlugin(Plugin):
    """Shell command execution
    """

    name = '$'

    def run(self, arguments, state):
        assert len(arguments) == 1
        old_pwd = os.getcwdu()
        os.chdir(self.basedir)
        try:
            self.execute_proc(arguments[0], shell=True)
        finally:
            os.chdir(old_pwd)


class LinkPlugin(Plugin):
    """Create a symbolic link.
    """

    name = 'link'

    def run(self, arguments, state):
        return self.execute_impl([self.basedir] + arguments)

    @classmethod
    def impl(cls, arguments):
        basedir = arguments.pop(0)

        force = False
        if arguments[0] == '-f':
            force = True
            arguments = arguments[1:]

        src, dst = arguments
        src, dst = path.join(basedir, path.expanduser(src)),\
                   path.join(basedir, path.expanduser(dst))
        link = path.relpath(src, path.dirname(dst))
        cls.log('link %s -> %s' % (link, dst))
        # Maybe delete an existing target
        if path.exists(dst):
            if force:
                os.unlink(dst)
            else:
                # If the link already exists and points to the correct file, just move on
                if path.islink(dst) and path.normpath(
                    path.join(path.dirname(dst), os.readlink(dst))) ==\
                                        path.normpath(src):
                    return
            # Create directories as necessary
        if not path.exists(path.dirname(dst)):
            os.makedirs(path.dirname(dst))

        try:
            os.symlink(link, dst)
        except OSError, e:
            print e
            return 1


class EnsureLinePlugin(Plugin):
    """Ensure that a file contains a certain line.
    """

    name = 'ensure_line'

    def run(self, arguments, state):
        if len(arguments) != 2:
            raise ValueError('Need exactly two arguments')

        filename, line =  arguments
        self.execute_impl([path.join(self.basedir, path.expanduser(filename)), line])

    @classmethod
    def impl(cls, arguments):
        filename, line =  arguments
        with open(filename, 'a+') as f:
            f.seek(0)
            if not line in map(lambda s: s.rstrip('\n\r'), f.readlines()):
                f.write('%s\n' % line)


class MkdirPlugin(Plugin):
    """Create one or more directories.
    """

    name = 'mkdir'

    def run(self, arguments, state):
        for dir in arguments:
            abspath = path.join(self.basedir, path.expanduser(dir))
            if not path.exists(abspath):
                self.log('mkdir %s' % abspath)
                self.execute_impl([abspath])
            else:
                self.log('%s exists' % abspath)

    @classmethod
    def impl(cls, arguments):
        assert len(arguments) == 1
        os.makedirs(arguments[0])


class RemindPlugin(Plugin):
    """Remind about manual installation steps
    """

    name = 'remind'

    @classmethod
    def post_apply_handler(cls, state):
        print ""
        print "ATTENTION! Do not forget to: "
        for reminder in state[cls]['reminders']:
            print " *", reminder
        print ""

    def run(self, arguments, state):
        state.setdefault(self.__class__, {'reminders': []})
        state[self.__class__]['reminders'].append(' '.join(arguments))
        if not RemindPlugin.post_apply_handler in state['post_apply']:
            state['post_apply'].append(RemindPlugin.post_apply_handler)
