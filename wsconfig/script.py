#!/usr/bin/env python

import sys, os
import platform
from os import path
import argparse

from .plugins import Plugin, ApplyError
from .parsing import parse_file, Selector, Command, Or, And


__version__ = ('0', '2', 'dev')


class ConfigError(Exception):
    pass


def init_env():
    """Return a list of tags that should automatically be set on this machine.

    There are a bunch of places to look for platform information, and what the
    information we find there looks like (in order Linux, Windows, Mac)

        sys.platform         -> linux2, win32
        os.name              -> posix, nt
        os.uname()           -> "ubuntu, kernelver, architecture"
        platform module
          platform.system()  -> Linux, Windows, Darwin or: CYGWIN_NT-5.1*
          platform.release() -> 2.6.22-15-generic, Vista, 8.11.1
          platform.linux_distribution()
                             -> ('Ubuntu', '11.04', 'natty')
          platform.mac_ver() -> ('10.5.8', ('', '', ''), 'i386')
          platform.win32_ver()
                             -> ('7', '6.1.7601', 'SP1', u'Multiprocessor Free')

    This tries to keep a close lid on the tags that are being defined. For
    example, sys.platform can return "linux" or "linux2", depending on
    Python version and linux kernel (see http://bugs.python.org/issue12326).
    Rather than dumping any values we can get our hands on into the tags, this
    carefully selects the values available.

    There is also the platinfo_ module. I chose not to use it: I had trouble
    with it (on Natty), and the benefit seems unclear.

    .. _platinfo: https://code.google.com/p/platinfo/
    """
    tags = set()

    # os.name has a limited number of defined values, we can add it as is.
    # Per the docs: 'posix', 'nt', 'os2', 'ce', 'java', 'riscos'
    tags.add(os.name)

    # The operating system, and version
    platform_system = platform.system()
    if platform_system == 'Windows':
        tags.add('windows')
        # Should be something like "7" or "Vista"
        version = platform.release().lower()
        if version: tags.add('windows:%s' % version)

    elif platform_system == 'Linux':
        tags.add('linux')
        # Should be something like ('Ubuntu', '11.04', 'natty'). Add
        # all three values as tag, i.e. sys:ubuntu or sys:ubuntu:natty
        distname, ver, id = platform.linux_distribution()
        if distname:
            tags.add(distname.lower())
            if ver: tags.add("%s:%s" % (distname.lower(), ver.lower()))
            if id: tags.add("%s:%s" % (distname.lower(), id.lower()))

    elif platform_system == 'Darwin':
        tags.add('darwin')
        tags.add('macos')
        release, info, machine = platform.mac_ver()
        if release:
            tags.add('macos:%s' % release.lower())
            # TODO: It would be cool to have Mac release names here: Lion etc.

    return set(map(lambda tag: "sys:%s" % tag, tags))


def validate(document, filename, plugins):
    """Validate ``document``, and resolve plugin references. This needs to
    run before a document can be applied.

    Raises errors if invalid plugins are referenced.
    """
    basedir = path.curdir \
        if not filename else path.abspath(path.dirname(filename))

    for item in document:
        if isinstance(item, Command):
            # define behavior is hardcoded
            if item.argv[0] in ('define',):
                item.plugin = None
                continue

            # Resolve a sudo in front of the command
            if item.argv[0] == 'sudo':
                item.command = item.argv[1]
                item.args = item.argv[2:]
                sudo = True
            else:
                item.command = item.argv[0]
                item.args = item.argv[1:]
                sudo = False

            try:
                plugin_class = plugins[item.command]
            except KeyError:
                raise ConfigError('"%s" not a valid plugin' % item.command)
            else:
                item.plugin = plugin_class(basedir, sudo=sudo)

        elif isinstance(item, Selector):
            validate(item.items, filename, plugins)


def test_match(expr, tags, sys_only=False):
    """Test if ``tagexpr`` succeeds given the list of tags.

    ``sys_only`` is a special mode in which only tags that start with
    ``sys:`` or checked, and all others are always assumed to match.
    """
    if isinstance(expr, And):
        for item in expr.items:
            result = test_match(item, tags, sys_only)
            if not result:
                return False
        return True
    elif isinstance(expr, Or):
        for item in expr.items:
            result = test_match(item, tags, sys_only)
            if result:
                return True
        return False
    else:
        assert isinstance(expr, basestring)
        if sys_only and not expr.startswith('sys:'):
            return True
        return expr in tags


def firstpass(document, init_tags):
    """Run the first pass over the ``document`` tree, as returned by the
    parser, assuming ``init_tags`` to be defined.

    It's sole purpose is to discover tags used in the document, so they may
    be offered to the user as a choice.

    It will find and return all tags used in selectors which are a) not
    yet in ``tags`` and b) loosely match what already is in ``tags``. Here
    is an explanation, by example, what we intend to return.

    In the simple case, collect all tags we run across::

        Foo {}                           [Foo]
        Foo Bar {}                       [Foo, Bar]
        Foo, Bar {}                      [Foo, Bar]
        foo bar qux {}                   [foo, bar, qux]

    ``sys:`` selectors are special-cased and if used, they must match for
    the tags to be collected. This is specifically so because it is assumed
    that they cannot be set by the user, thus it makes no sense to present
    the tag to the user::

        Bar sys:linux {}                 [Bar] or []
        sys:linux Foo, sys:macos Bar {}  [Foo] or [Bar] or []
        sys:linux sys:macos Foo {}       []

    Nested selectors are only traversed if the expression fully matches::

        sys:linux { Bar {} }             [Bar] or []
        Foo { Bar {} }                   [Foo]
        sys:linux Foo { Bar {} }         [Foo] or []

    If you give the user a choice based on the tags returned here, you will
    have to run this pass twice (or multiple times) on the same document.
    The second time you can include in the ``tags`` argument those the user
    selected.
    """
    discovered_tags = set()

    def search_items(items, tags):
        for item in items:
            # Look at all "define" commands
            if isinstance(item, Command):
                if item.argv[0] == 'define':
                    tags.update(item.argv)
                continue

            if not isinstance(item, Selector):
                continue

            # Find tags used in selectors, but not those that depend on a
            # ``sys:*`` tag that is not set.
            #
            # We know that a tag expression is an OR of many ANDs, and further
            # nesting is not possible. So simply check if any of the ANDs
            # passes a check of it's ``sys`` conditions.
            or_expr = item.tagexpr.expr
            for and_expr in or_expr.items:
                if test_match(and_expr, tags, sys_only=True):
                    discovered_tags.update(
                        {tag for tag in and_expr.items
                         if not tag.startswith('sys:') and not tag in tags})

            # Traverse if matching
            if test_match(item.tagexpr.expr, tags):
                search_items(item.items, tags)

    # Be sure we don't modify the incoming set of tags
    search_items(document, init_tags.copy())
    return discovered_tags


def apply_document(document, tags, state, dry_run=False):
    """Run all the commands in ``document``, filtered by ``tags``.

    As the document is processed, runtime state can be kept in ``state``.
    """
    for item in document:
        if isinstance(item, Command):
            # Hardcode the define behavior - add the newly defined tags
            # to the list, will have effect in subsequent code.
            if item.argv[0] == 'define':
                tags.update(item.argv)
                continue

            if dry_run:
                print item
                continue

            # Run the plugin
            try:
                result = item.plugin.run(item.args, state)
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

        elif isinstance(item, Selector):
            if test_match(item.tagexpr.expr, tags):
                apply_document(item.items, tags, state, dry_run)


def main(argv):
    """
    I would prefer a CLI that provides the following modes:

        wsconfig --defaults
        wsconfig config.ws
        wsconfig config.ws apply [tags [tags ...]]

    That seems really not possible with argparse, but we get something close
    by hacking the help text and using parse_known_args(). But it might just
    be easier to parse the command line manually in this case, or only enlist
    the help of argparse for stuff like --defaults (and others in the future).
    """

    usage_string = '''
  %(p)s --defaults
  %(p)s file
  %(p)s file apply [tags [tags ...]]''' % {'p': path.basename(argv[0])}

    parser = argparse.ArgumentParser(usage=usage_string)
    group = parser.add_argument_group(title='modes')
    group.add_argument('--defaults', action='store_true',
                        help='Show the system default tags')
    group.add_argument('file', help='The config file to use/run', default=1)
    subparsers = parser.add_subparsers(help=argparse.SUPPRESS)
    subparser = subparsers.add_parser('apply', usage=usage_string,
                               help='Apply the document')
    subparser.add_argument('tags', nargs='*', help=argparse.SUPPRESS)

    # XXX Actually, argparse will not allow --default to go through
    # even with parse_known_args()
    namespace, unparsed = parser.parse_known_args()
    if unparsed:
        print 'Unsupported arguments: %s' % ', '.join(unparsed)
        parser.print_help()
        return 1

    if namespace.defaults and namespace.file:
        print 'Error: Specify --defaults or a file to process.'
        parser.print_help()
        return 1

    # Get the tags that are defined by default
    tags = init_env()

    #namespace.defaults = True
    if namespace.defaults:
        for tag in sorted(tags):
            print tag
        return 0

    # Parse the configuration file
    document = parse_file(namespace.file)

    # Validate the document, add command implementations to the tree
    validate(document, namespace.file, Plugin.__class__.PLUGINS)

    # Add the tags the user specified to the list of defined tags
    tags.update(namespace.tags)

    # Run a first pass, to find tags that are defined via dependencies
    found_tags = firstpass(document, tags)

    # If the user is not yet running an apply, present him with the tags
    # that the firstpass discovered (only those which start with an uppercase
    # letter, per our convention).
    if not namespace.tags:
        print 'Optional tags for you to pass to apply:'
        for tag in found_tags:
            if tag[0].isupper():
                print '  %s' % tag
        return 0

    # Actually run all commands
    state = {'post_apply': []}
    apply_document(document, tags, state, dry_run=False)

    # Execute post apply handlers. Commands like ``remind`` set those up.
    for callable in state['post_apply']:
        callable(state)


def run():
    sys.exit(main(sys.argv) or 0)

if __name__ == '__main__':
    run()
