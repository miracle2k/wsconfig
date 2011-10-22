#!/usr/bin/env python

import sys, os
from os import path
import yaml
from subprocess import Popen, list2cmdline


class ConfigError(Exception):
    pass

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

    def __init__(self, basedir):
        self.basedir = basedir

    def run(self, arguments, raw_value, state):
        raise NotImplementedError()

    def log(self, str):
        print ""
        print "====>", str

    def pexecute(self, cmdline, *a, **kw):
        self.log("$ %s" % (list2cmdline(cmdline)
                           if isinstance(cmdline, list) else cmdline))
        process = Popen(cmdline, *a, **kw)
        process.wait()
        if process.returncode != 0:
            raise ApplyError('Process returns non-zero code: %s' % process.returncode)


class DpkgPlugin(Plugin):
    """Debian package installation.
    """
    name = 'dpkg'

    def run(self, arguments, raw_value, state):
        for package in arguments:
            self.pexecute(['apt-get', 'install', '-y', package])


class PipPlugin(Plugin):
    """Pip python package installation.
    """
    name = 'pip'

    def run(self, arguments, raw_value, state):
        for package in arguments:
            self.pexecute(['pip', 'install', package])


class ShellPlugin(Plugin):
    """Shell command execution
    """
    name = 'shell'

    def run(self, arguments, raw_value, state):
        self.pexecute(raw_value, shell=True)


class LinkPlugin(Plugin):
    """Create a symbolic link.
    """
    name = 'link'

    def run(self, arguments, raw_value, state):
        src, dst = arguments
        src, dst = path.join(self.basedir, path.expanduser(src)), \
                   path.join(self.basedir, path.expanduser(dst))
        link = path.relpath(src, path.dirname(dst))
        self.log('link %s -> %s' % (link, dst))
        try:
            os.symlink(link, dst)
        except OSError, e:
            print e
            return 1


class MkdirPlugin(Plugin):
    """Create one or more directories.
    """
    name = 'mkdir'

    def run(self, arguments, raw_value, state):
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

    def run(self, arguments, raw_value, state):
        state.setdefault(self.__class__, {'reminders': []})
        state[self.__class__]['reminders'].append(raw_value)
        if not RemindPlugin.post_apply_handler in state['post_apply']:
            state['post_apply'].append(RemindPlugin.post_apply_handler)


PLUGIN = object()
REFERENCE = object()
def instruction_type(instruction):
    """Helper to return the type of an instruction, as held by a ``Package``
    instance. in it's ``instructions`` list.

    When the internal format changes, we only need to update here.
    """
    if len(instruction) == 2:
        return REFERENCE
    return PLUGIN


class Package(object):
    """Represents a package as defined in the YAML config file.
    """

    def __init__(self, name):
        self.name = name[1:] if name.startswith('_') else name
        self.exported = not name.startswith('_')
        self.instructions = []

    def append(self, plugin_instance):
        self.instructions.append(plugin_instance)

    def run(self, optionals, state):
        """Run the instructions in this package.

        ``optionals`` is a list of optional packages which should also be run.

        ``state`` is a dictionary which stores execution state across the run.
        """
        for i in self.instructions:
            if instruction_type(i) == REFERENCE:
                package, is_optional = i
                if not is_optional or package.name in optionals:
                    package.run(optionals, state)
            else:
                plugin, arguments, raw_value = i
                try:
                    result = plugin.run(arguments, raw_value, state)
                    if result:
                        raise ApplyError('Plugin failed.')
                except ApplyError, e:
                    print "%s" % e
                    while True:
                        yn = raw_input('Do you want to continue (y/n)? [y] ')
                        if not yn in ('y', 'n', ''):
                            continue
                        if yn == 'n':
                            sys.exit(1)
                        break

    def get_optionals(self):
        """Recursively return all the possible optional packages.
        """
        result = []
        for item in self:
            if instruction_type(item) == REFERENCE:
                reference, is_optional = item
                if is_optional:
                    result.append(reference.name)
                result.extend(reference.get_optionals())
        return result

    def __len__(self):
        return len(self.instructions)

    def __getitem__(self, item):
        return self.instructions[item]

    def __iter__(self):
        return iter(self.instructions)


def load_yaml(file, plugins):
    """Parse the given YAML configuration file into a dict of ``Package`` instances.

    Packages prefixed with _ will not be included.

    ``plugins`` is a dict of available plugin classes.
    """
    input = yaml.load(file if hasattr(file, 'read') else open(file, 'r'))
    assert isinstance(input, dict), "root must be a an associative array"

    filename = None
    if hasattr(file, 'name'):
        filename = file.name
    elif isinstance(file, basestring):
        filename = file
    basedir = path.curdir if not filename \
        else path.abspath(path.dirname(filename))

    packages = {}
    for pkg_name, instructions in input.items():
        p = Package(pkg_name)
        for instruction in instructions:
            # Parse instruction
            if isinstance(instruction, dict):
                assert len(instruction) == 1, 'instruction array must have only item'
                raw_value = instruction.values()[0]
                instruction = instruction.keys()[0]
            else:
                raw_value = ""

            # Parse the value
            if isinstance(raw_value, basestring):
                # Consider using the shlex module
                arguments = filter(lambda s: bool(s),
                    [s.strip() for s in raw_value.split(' ')])
            else:
                arguments = [raw_value]

            # Resolve a potential include
            if instruction.startswith('<') and instruction.endswith('>'):
                reference = instruction[1:-1]
                is_optional = False
                if reference.endswith('?'):
                    reference = reference[:-1]
                    is_optional = True
                p.append((reference, is_optional))
                continue

            try:
                plugin_class = plugins[instruction]
            except KeyError:
                raise ConfigError('"%s" not a valid plugin' % instruction)
            else:
                p.append((plugin_class(basedir), arguments, raw_value))
        packages[p.name] = p

    # Resolve package references
    for package in packages.values():
        for index, instruction in enumerate(package.instructions):
            if instruction_type(instruction) == REFERENCE:
                reference, is_optional = instruction
                try:
                    package.instructions[index] = (
                        packages[reference[1:]
                            if reference.startswith('_') else reference],
                        is_optional)
                except KeyError:
                    raise ConfigError('"%s" is an invalid reference' % reference)

    # Return all  exported packages
    return dict([(n, p) for n, p in packages.items() if p.exported])


def query_package(packages):
    """Ask the user which package to install.
    """
    print "There are %d package(s) available: " % len(packages)
    package_names = packages.keys()
    for index, name in enumerate(package_names):
        print "  %d. %s" % (index+1, name)
    to_install = False
    while not to_install:
        index = raw_input("Type the number of the package you wish to apply: ")
        if index in ('q', 'exit', 'quit', 'bye', ''):
            break
        try:
            to_install = packages[package_names[int(index)-1]]
        except (IndexError, ValueError):
            print "Invalid input."

    if not to_install:
        return None, None

    # Query optional components
    # XXX recursive dependencies are not well dealt with here. If you select
    # an optional component which is a child of another, unselected component,
    # then your selection will have no effect. One solution might be to repeat to
    # have get_optionals() only descend into nodes that have already been
    # selected, and repeat this call until no new optionals are found.
    available_optionals = to_install.get_optionals()
    selected_optionals = []
    if available_optionals:
        print ""
        print "Some optional packages are possible:"
        for index, name in enumerate(available_optionals):
            print "  %d. %s" % (index+1, name)

        input = raw_input("Type the numbers you wish to apply (space separated): ")
        while input:
            for num in [s.strip() for s in input.split(' ')]:
                try:
                    optional = available_optionals[int(num)-1]
                except (ValueError, IndexError):
                    print "Not a valid number: %s" % num
                else:
                    if not optional in selected_optionals:
                        selected_optionals.append(optional)

            print "Selected optional packages: ", ", ".join(selected_optionals)
            input = raw_input("Enter more numbers, or empty when done: ")

    return to_install, selected_optionals

def main():
    if len(sys.argv) != 2:
        print "Usage: %s YAML_CONFIG_FILE" % path.basename(__file__)
        return 1
    
    # Parse the configuration file
    filename = sys.argv[1]
    packages = load_yaml(filename, Plugin.__class__.PLUGINS)

    # Query the user
    to_apply, optionals = query_package(packages)
    if not to_apply:
        return 1

    # Actually run the package
    print 'Applying package "%s"' % to_apply.name
    state = {'post_apply': []}
    to_apply.run(optionals, state)

    # Execute post apply handlers
    for callable in state['post_apply']:
        callable(state)


if __name__ == '__main__':
    sys.exit(main() or 0)