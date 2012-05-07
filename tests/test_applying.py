"""Test that given a configuration, we do the right thing.
"""

from textwrap import dedent
from StringIO import StringIO
from nose.tools import assert_raises
from wsconfig.parsing import parse_string
from wsconfig.plugins import Plugin
from wsconfig.script import firstpass, apply_document, validate


class TestFirstPass(object):
    """Test the first pass, which will scour the document for tags that
    are exposed.

    While this does some matching, we are not extensively testing the tag
    matching facilities here. It is assumed that they are the same as those
    tested in other contexts.
    """

    def process(self, text, tags=None):
        document = parse_string(dedent(text))
        result = firstpass(document, tags or set())
        print result
        return result

    def test(self):
        # Tags generally do not need to match to be found, after all, we are
        # looking for them as to offer them to the user as an optional choice.
        assert self.process('foo {}') == {'foo'}
        assert self.process('foo bar {}') == {'foo', 'bar'}
        assert self.process('foo, bar {}') == {'foo', 'bar'}
        # Though Predefined tags are excluded
        assert self.process('foo {}', {'foo'}) == set()

        # Except sys:* tags, which do need to match, because they cannot be set
        # by the user anyway, so no need to offer tags that will never run.
        assert self.process('sys:test foo {}') == set()
        assert self.process('sys:test foo {}', {'sys:test'}) == {'foo'}
        # That works with complex expressions as well
        expr = 'sys:test foo bar, sys:osx { qux {} }'
        assert self.process(expr) == set()
        assert self.process(expr, {'sys:test'}) == {'foo', 'bar'}
        assert self.process(expr, {'sys:osx'}) == {'qux'}
        assert self.process(expr, {'sys:osx', 'sys:test'}) == \
               {'qux', 'bar', 'foo'}
        # Regression: Make sure that the ! operator works here as well
        assert self.process('!sys:test foo {}') == {'foo'}
        assert self.process('!sys:test foo {}', {'foo'}) == set()

        # However, tags do need to match to be followed.
        assert self.process('foo { bar {} }') == {'foo'}
        assert self.process('foo { bar {} }', {'foo'}) == {'bar'}

        # Which can be helped if they are defined, in the right order. Tags
        # that are defined internally in this way are not returned.
        assert self.process('define foo\nfoo { }') == set()
        assert self.process('define foo\nfoo { bar {} }') == {'bar'}
        assert self.process('foo { bar {} }\ndefine foo') == {'foo'}


class TestApply(object):
    """Test that the right commands run."""

    def apply(self, text, tags=None):
        # Dummy plugin
        class LogPlugin(Plugin):
            name = 'log'
            log = []
            def run(self, args, state):
                self.log.append(args)

        document = parse_string(dedent(text))
        validate(document, '', {'log': LogPlugin})
        apply_document(document, tags or set(), {})
        print LogPlugin.log
        return LogPlugin.log

    def test_simple(self):
        assert self.apply('log 42') == [['42']]
        # Conditions need to match
        assert self.apply('foo { log 42 }') == []
        assert self.apply('foo { log 42 }', {'foo'}) == [['42']]

    def test_and(self):
        assert self.apply('foo bar { log 42 }', set()) == []
        assert self.apply('foo bar { log 42 }', {'foo'}) == []
        assert self.apply('foo bar { log 42 }', {'bar'}) == []
        assert self.apply('foo bar { log 42 }', {'foo', 'bar'}) == [['42']]

    def test_or(self):
        assert self.apply('foo, bar { log 42 }', set()) == []
        assert self.apply('foo, bar { log 42 }', {'foo'}) == [['42']]
        assert self.apply('foo, bar { log 42 }', {'bar'}) == [['42']]
        assert self.apply('foo, bar { log 42 }', {'foo', 'bar'}) == [['42']]

    def test_and_or(self):
        assert self.apply('foo bar, qux { log 42 }', set()) == []
        assert self.apply('foo bar, qux { log 42 }', {'foo', 'qux'}) == [['42']]
        assert self.apply('foo bar, qux { log 42 }', {'bar', 'qux'}) == [['42']]
        assert self.apply('foo bar, qux { log 42 }', {'foo', 'bar'}) == [['42']]
        assert self.apply('foo bar, qux { log 42 }', {'qux'}) == [['42']]

    def test_negated_tags(self):
        assert self.apply('!foo { log 42 }', set()) == [['42']]
        assert self.apply('!foo { log 42 }', {'foo'}) == []

    def test_nesting(self):
        assert self.apply('foo { bar { log 42 }}', set()) == []
        assert self.apply('foo { bar { log 42 }}', {'foo'}) == []
        assert self.apply('foo { bar { log 42 }}', {'foo', 'bar'}) == [['42']]

    def test_define(self):
        assert self.apply('define foo\nfoo { log 42 }', set()) == [['42']]
        assert self.apply('foo { log 42 }\ndefine foo', set()) == []

