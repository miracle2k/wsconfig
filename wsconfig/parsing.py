"""Parse our DLS into a tree.

Currently uses PyParsing. I'm not happy with the error messages it produces.
"""

from pyparsing import *


__all__ = ('parse_file', 'parse_string', 'print_document',
           'Command', 'And', 'Or', 'TagExpr', 'Selector')


################################################################################
###### Constructing the Grammar
################################################################################


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
        Word(alphas, alphanums) + \
        ZeroOrMore(NotAny(lineEnd) + (quotedString | Word(commandchars))) + \
        (Suppress(lineEnd) | FollowedBy('}'))

# Provide a special syntax for shell commands
shell_command = Literal('$') + SkipTo(lineEnd)

command = shell_command | internal_command

# A selector restricts the commands in it's body to the given tags.
# I.e. this is the ``tag { commands... }`` syntax structure.
#
# The tag expression allows multiple tags separated by whitespace (AND), as
# well as usage of commas (OR). Brackets for complex expressions are currently
# not supported. AND takes preference, so: ``tag1, tag2 tag3`` is
# ``tag1 OR (tag2 AND tag3)``.
tagexprAnd = OneOrMore(Word(alphas, tagchars))
tagexprOr = delimitedList(tagexprAnd)
tagexpr = tagexprOr
selector = tagexpr + Suppress('{') + items + Suppress('}')

# An item is either a selector or a command
item = command | selector
items << ZeroOrMore(item)

# A full document.
root = items + StringEnd()


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
        self.command = argv[0]
        self.argv = argv[1:]
    def __str__(self):
        return 'exec(%s:%s)' % (self.command, " ".join(self.argv))
    def __repr__(self):
        return '<%s cmd=%s argv=%s>' % (
            self.__class__.__name__, self.command, self.argv
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
