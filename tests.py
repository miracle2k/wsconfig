from textwrap import dedent
from StringIO import StringIO
from nose.tools import assert_raises
from wsconfig import load_yaml, ConfigError, Plugin


def mkplugin(name):
    return type('%sPlugin' % name.upper(), (Plugin,), {'name': name})


class BaseTest(object):

    plugins = []

    def __init__(self):
        self.plugins = dict([(p, mkplugin(p)) for p in self.plugins])

    def load(self, text):
        return load_yaml(StringIO(dedent(text)), self.plugins)


class TestLoad(BaseTest):

    plugins = ['test', 'test2']

    def test_basic(self):
        r = self.load("""
        pkg1:
            - test
            - test
        pkg2:
            - test
        """)
        assert len(r) == 2
        assert len(r['pkg1']) == 2
        assert len(r['pkg2']) == 1

    def test_no_arg_plugins(self):
        """Plugins can be specified with and without arguments.
        """
        r = self.load("""
        pkg1:
            - test
            - test: foobar
        """)
        assert r['pkg1'][0][0].name == 'test'
        assert r['pkg1'][1][0].name == 'test'

    def test_required_reference(self):
        r = self.load("""
        foo:
            - test
        pkg:
            - <foo>
        """)
        package, is_optional = r['pkg'][0]
        assert is_optional == False
        assert len(package) == 1

    def test_optional_reference(self):
        r = self.load("""
        foo:
            - test
        pkg:
            - <foo?>
        """)
        package, is_optional = r['pkg'][0]
        assert is_optional == True
        assert len(package) == 1

    def test_unexported_packages(self):
        r = self.load("""
        _foo:
            - test
        pkg:
            - <foo>
            - <_foo>
        """)
        # _foo is not included in output
        assert len(r) == 1
        # Both "foo" and "__foo" work for referencing
        assert r['pkg'][0][0] == r['pkg'][1][0]

    def test_invalid_reference(self):
        assert_raises(ConfigError, self.load, """
        pkg:
            - <foo>
        """)

    def test_invalid_plugin(self):
        assert_raises(ConfigError, self.load, """
        pkg:
            - foo
        """)

    def test_multi_instruction_array(self):
        assert_raises(AssertionError, self.load, """
        pkg:
            - test: foo
              test2: bar
        """)


class TestRun(BaseTest):

    def __init__(self):
        class LogPlugin(Plugin):
            name = 'log'
            log = []
            def run(self, args, raw, state):
                self.log.append((args, raw))
        self.log = LogPlugin.log
        self.plugins = {'log': LogPlugin}

    def test_base(self):
        r = self.load("""
        pkg:
            - log: foo   bar
            - log: 12
        """)
        r['pkg'].run([], {})

        assert self.log == [
            (['foo', 'bar'], 'foo   bar'),
            ([12], 12),
        ]

    def test_with_dependency(self):
        r = self.load("""
        _foo:
            - log: foo
        pkg:
            - <foo>
            - log: bar
        """)
        r['pkg'].run([], {})

        assert self.log == [
            (['foo'], 'foo'),
            (['bar'], 'bar'),
        ]


    def test_with_optional_dependencies(self):
        r = self.load("""
        _foo:
            - log: foo
        pkg:
            - <foo?>
            - log: bar
        """)

        # foo not included by default
        r['pkg'].run([], {})
        assert self.log == [
            (['bar'], 'bar'),
        ]

        # but is when configured via optional
        del self.log[:]
        r['pkg'].run(['foo'], {})
        assert self.log == [
            (['foo'], 'foo'),
            (['bar'], 'bar'),
        ]
