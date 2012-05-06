import os
from os import path
from subprocess import Popen, list2cmdline


class ApplyError(Exception):
    pass


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

    def log(self, str):
        print ""
        print "====>", str

    def pexecute(self, cmdline, *a, **kw):
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
            raise ApplyError('Process returns non-zero code: %s' % process.returncode)


class DpkgPlugin(Plugin):
    """Debian package installation.
    """

    name = 'dpkg'
    sudo = True

    def run(self, arguments, state):
        for package in arguments:
            self.pexecute(['apt-get', 'install', '-y', package])


class PipPlugin(Plugin):
    """Pip python package installation.
    """

    name = 'pip'
    sudo = True

    def run(self, arguments, state):
        for package in arguments:
            self.pexecute(['pip', 'install', package])


class ShellPlugin(Plugin):
    """Shell command execution
    """

    name = '$'

    def run(self, arguments, state):
        assert len(arguments) == 1
        old_pwd = os.getcwdu()
        os.chdir(self.basedir)
        try:
            self.pexecute(arguments[0], shell=True)
        finally:
            os.chdir(old_pwd)


class LinkPlugin(Plugin):
    """Create a symbolic link.
    """

    name = 'link'

    def run(self, arguments, state):
        force = False
        if arguments[0] == '-f':
            force = True
            arguments = arguments[1:]

        src, dst = arguments
        src, dst = path.join(self.basedir, path.expanduser(src)),\
                   path.join(self.basedir, path.expanduser(dst))
        link = path.relpath(src, path.dirname(dst))
        self.log('link %s -> %s' % (link, dst))
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


class MkdirPlugin(Plugin):
    """Create one or more directories.
    """

    name = 'mkdir'

    def run(self, arguments, state):
        for dir in arguments:
            abspath = path.join(self.basedir, path.expanduser(dir))
            if not path.exists(abspath):
                self.log('mkdir %s' % abspath)
                os.makedirs(abspath)
            else:
                self.log('%s exists' % abspath)


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
