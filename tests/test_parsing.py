"""Test the parser.
"""

from textwrap import dedent
from pyparsing import ParseException
from nose.tools import assert_raises

from wsconfig.parsing import parse_string, Command, Selector, TagExpr, Or, And


def parse(text):
    result = parse_string(dedent(text))
    # Make sure to return a list, rather than a ``ParseResults`` object.
    print list(result)
    return list(result)


class TestParseBaseObjects(object):
    """Test parsing the basic syntax elements.
    """

    def test_command(self):
        """Test a simple command with arguments."""
        assert parse('command') == [Command(['command'])]
        assert parse('command arg') == [Command(['command', 'arg'])]
        assert parse('command "foo bar" arg') == (
            [Command(['command', 'foo bar', 'arg'])]
        )
        assert parse('''
          command1
          command2''') == [Command(['command1']), Command(['command2'])]

        # Quoted strings - actually this isn't want we want, but PyParsing
        # doesn't seem to unquote those strings properly.
        assert parse('command "foo\\"bar"') == (
            [Command(['command', 'foo\\"bar'])]
        )

    def test_tagexpr(self):
        """Test simple tag expressions."""
        assert parse('tag { } ') == [
            Selector(TagExpr(Or([And(['tag'])])), [])
        ]
        assert parse('tag { command } ') == [
            Selector(TagExpr(Or([And(['tag'])])),
                     [Command(['command'])])
        ]
        assert parse('foo { bar { command } } ') == [
            Selector(TagExpr(Or([And(['foo'])])),
                    [Selector(TagExpr(Or([And(['bar'])])), [
                        Command(['command'])])
                    ])
        ]

    def test_tagexpr_complex(self):
        """Test more complex tag expression."""
        assert parse('bar foo { } ') == [
            Selector(TagExpr(Or([And(['bar', 'foo'])])), [])
        ]
        assert parse('bar, foo { } ') == [
            Selector(TagExpr(Or([And(['bar']), And(['foo'])])), [])
        ]
        assert parse('bar, foo qux { } ') == [
            Selector(TagExpr(Or([And(['bar']), And(['foo', 'qux'])])), [])
        ]


class TestParseComments(object):

    def test_with_commands(self):
        assert parse('after cmd    # bla''') == [Command(['after', 'cmd'])]
        assert parse('''
       # before cmd
       cmd
        ''') == [Command(['cmd'])]

    def test_with_selectors(self):
        assert parse('''
       # before tag {}
       cmd
       ''') == [Command(['cmd'])]
        assert parse('''
       within { # }
       }
       ''') == [Selector(TagExpr(Or([And(['within'])])), [])]
        assert parse('''
       after { }  # x
       cmd
       ''') == [Selector(TagExpr(Or([And(['after'])])), []),
                 Command(['cmd'])]

    def test_eof(self):
        """Test comment at the end of the file - we had some trouble with this.
        """
        assert parse('# bla') == []
        assert parse('after { } # bla''') == [
            Selector(TagExpr(Or([And(['after'])])), [])]


class TestParseWhitespace(object):
    """Test parsing with respect to different whitespace usage (newlines
    before, after syntax elements etc).
    """

    def test_before_opening_braces(self):
        assert parse('bar{ }') == [
            Selector(TagExpr(Or([And(['bar'])])), [])
        ]
        assert parse('bar { }') == [
            Selector(TagExpr(Or([And(['bar'])])), [])
        ]
        # This is actually not supported.
        assert_raises(ParseException, parse, '''
       bar
       { } ''')

    def test_after_opening_braces(self):
        assert parse('bar {cmd }') == [
            Selector(TagExpr(Or([And(['bar'])])), [Command(['cmd'])])
        ]
        assert parse('bar { cmd }') == [
            Selector(TagExpr(Or([And(['bar'])])), [Command(['cmd'])])
        ]
        assert parse('''
       bar {
       cmd} ''') == [
            Selector(TagExpr(Or([And(['bar'])])), [Command(['cmd'])])
        ]

    def test_between_empty_braces(self):
        assert parse('bar {}') == [
            Selector(TagExpr(Or([And(['bar'])])), [])
        ]
        assert parse('bar { }') == [
            Selector(TagExpr(Or([And(['bar'])])), [])
        ]
        assert parse('''
       bar {
       }''') == [
            Selector(TagExpr(Or([And(['bar'])])), [])
        ]

    def test_before_closing_braces(self):
        assert parse('bar { cmd}') == [
            Selector(TagExpr(Or([And(['bar'])])), [Command(['cmd'])])
        ]
        assert parse('bar { cmd }') == [
            Selector(TagExpr(Or([And(['bar'])])), [Command(['cmd'])])
        ]
        assert parse('''
       bar { cmd
       } ''') == [
            Selector(TagExpr(Or([And(['bar'])])), [Command(['cmd'])])
        ]

    def test_after_closing_braces(self):
        assert parse('bar { }cmd') == [
            Selector(TagExpr(Or([And(['bar'])])), []), Command(['cmd'])
        ]
        assert parse('bar { } cmd') == [
            Selector(TagExpr(Or([And(['bar'])])), []), Command(['cmd'])
        ]
        assert parse('''
       bar { }
       cmd''') == [
            Selector(TagExpr(Or([And(['bar'])])), []), Command(['cmd'])
        ]

    def test_whitespace_in_command_args(self):
        assert parse('command     "  "        bla') == \
               [Command(['command', '  ', 'bla'])]
