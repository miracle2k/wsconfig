"""Parse our DLS into a tree.

Currently uses PyParsing. I'm not happy with the error messages it produces.
"""

from pyparsing import *


__all__ = ('parse_file', 'parse_string', 'print_document',
           'Command', 'And', 'Or', 'TagExpr', 'Selector')


################################################################################
###### Constructing the Grammar
######
###### Note: Using - instead of + to concatenate expressions means "no
###### backtrack" and makes error messages a lot more readable. See
###### http://pyparsing.wikispaces.com/message/view/home/40296440
################################################################################

def minIndentBlock(blockStatementExpr):
    """Adapted from ``pyparsing.indentedBlock``.

    From the current column, tries to parse ``blockStatementExpr`` on all
    following lines, so long as they have an indent larger than that initial
    position. If a line has a indent smaller or equal to the column position
    where parsing the block first started, then the block stops consuming.
    """

    # Only a list so that nested scopes can modify it
    initial = []

    # Use an dummy token to have a function run when we start parsing. It
    # determines and stores the column of the current parsing position.
    def capture_initial_indent(s, location, t):
        # -1 is required, or the col() function might already refer to the
        # next line (and return 0).
        initial.append(col(location-1, s))
    # Be sure to leaveWhitespace(), or the parser will already skip ahead
    # and the action will not get to know the original start column.
    MARK_INITIAL = Empty().setParseAction(capture_initial_indent).leaveWhitespace()

    # Use a dummy token to check the indent, on every line. If this dummy token
    # fails, then the expressions that use it will fail, the block will end,
    # and the parser can continue with other expressions.
    def checkPeerIndent(s,l,t):
        curCol = col(l,s)
        # TO keep the block going, the indentation needs to be larger than
        # the original position where we started.
        if curCol <= initial[0]:
            # Note: Because below we use OneOrMore(), if there is not a single
            # correct indent, the user will get to see this message.
            raise ParseException(
                s, l, 'Indentation must be at least %d' % (initial[0]+1))
    CHECK_INDENT = Empty().setParseAction(checkPeerIndent)

    # Define LineEnd with custom whitespace chars. This is how
    # pyparsing.indentedBlock does it, so I kept it.
    #
    # If .suppress() is added, the whitespace used for indentation and at eol
    # will be removed. We'll keep it for now, to get the shell code just as
    # the user specified it. If the whitespace is removed, then you'll want
    # to change the join in the shell_command parseAction to use a \n instead.
    NL = OneOrMore(LineEnd().setWhitespaceChars("\t "))

    # Build the block parser
    return (
        # Mark the initial position, then optionally consume a newline,
        # if there is any (or blockStatementExpr may begin on the same line).
        MARK_INITIAL + Optional(NL) +
        # Parse any number of block statements, always check indent
        (OneOrMore(CHECK_INDENT + blockStatementExpr + Optional(NL))))


items = Forward()

# Characters allowed in commands - all but your syntax elements
commandchars = "".join([c for c in printables if c not in '{}'])

# List of characters allowed in tags, commands...
tagchars = alphanums + ':._-'

# A command that will be executed.
#
# This is essentially everything until the end of the line, but we split it
# into multiple words by whitespace, and support quoting. The NotAny() is
# required, because PyParsing does not backtrack, it seems.
#
# The first word needs to start with an alphanumeric character only.
internal_command = \
        Word(alphas, alphanums+'_') + \
        ZeroOrMore(NotAny(lineEnd) + (quotedString | Word(commandchars))) + \
        (Suppress(lineEnd) | FollowedBy('}'))

# Provide a special syntax for shell commands
shell_command =\
    (Suppress(Literal('$:')) - minIndentBlock(SkipTo(lineEnd))) |\
    (Suppress(Literal('$')) + SkipTo(lineEnd | Literal('}')))

command = shell_command | internal_command

# A selector restricts the commands in it's body to the given tags.
# I.e. this is the ``tag { commands... }`` syntax structure.
#
# The tag expression allows multiple tags separated by whitespace (AND), as
# well as usage of commas (OR). Brackets for complex expressions are currently
# not supported. AND takes preference, so: ``tag1, tag2 tag3`` is
# ``tag1 OR (tag2 AND tag3)``.
tagexprAnd = OneOrMore(Combine(Optional('!') + Word(alphas, tagchars)))
tagexprOr = delimitedList(tagexprAnd)
tagexpr = tagexprOr
selector = tagexpr - Suppress('{') - items - Suppress('}')

# An item is either a selector or a command
item = command | selector
items << ZeroOrMore(item)

# A full document.
root = items + StringEnd()

# Support comments
root.ignore(pythonStyleComment)


################################################################################
###### Constructing the AST
######
###### Attach parser actions to parse into a tree.
################################################################################


class Node(object):
    def __eq__(self, other):
        if type(other) is type(self):
            return self.__dict__ == other.__dict__
        return False
    def __ne__(self, other):
        return not self.__eq__(other)

class Command(Node):
    def __init__(self, argv):
        self.argv = argv
    def __str__(self):
        return 'exec(%s)' % " ".join(self.argv)
    def __repr__(self):
        return '<%s %s>' % (
            self.__class__.__name__, self.argv
        )

class And(Node):
    def __init__(self, items):
        self.items = items
    def __str__(self):
        return '%s' % " and ".join(map(str, self.items))
    def __repr__(self):
        return '<%s %s>' % (self.__class__.__name__, self.items)

class Or(Node):
    def __init__(self, items):
        self.items = items
    def __str__(self):
        return '%s' % " or ".join(map(
            # Wrap nested ``And``s in brackets if they have more than one item
            lambda i: "(%s)" % i
                if (isinstance(i, And) and len(i.items) > 1)
                else str(i),
            self.items))
    def __repr__(self):
        return '<%s %s>' % (
            self.__class__.__name__, ' '.join(map(repr, self.items)))

class TagExpr(Node):
    def __init__(self, expr):
        self.expr = expr
    def __str__(self):
        return 'if(%s)' % self.expr
    def __repr__(self):
        return '<%s %s>' % (self.__class__.__name__, repr(self.expr))

class Selector(Node):
    def __init__(self, tagexpr, items):
        self.tagexpr = tagexpr
        self.items = items
    def __str__(self):
        return '%s -> %s' % (self.tagexpr, self.items)
    def __repr__(self):
        return '<%s %s items=%s>' % (
            self.__class__.__name__, repr(self.tagexpr), map(repr, self.items))


# Restore $, which we have the parser suppress, to indicate shell command
shell_command.setParseAction(lambda _,__,toks: ['$'] + [''.join(toks[:])])
# Create nodes for other tokens
command.setParseAction(lambda _,__,toks: Command(toks[0:]))
tagexprAnd.setParseAction(lambda _,__,toks: And(toks[0:]))
tagexpr.setParseAction(lambda _,__,toks: TagExpr(Or(toks[0:])))
selector.setParseAction(lambda _,__,toks: Selector(toks[0], toks[1:]))
quotedString.setParseAction(removeQuotes)


def print_document(doc, level=0):
    indent = '   '*level
    for item in doc:
        if isinstance(item, Selector):
            print "%s%s %s" % (indent, item.tagexpr, '->')
            print_document(item.items, level=level+1)
        else:
            print '%s%s' % (indent, item)


parse_string = root.parseString
parse_file = root.parseFile
