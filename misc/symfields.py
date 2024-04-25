#!/usr/bin/env python3

from enum import Enum
from collections import namedtuple
from dataclasses import dataclass, field


class Need(Enum):
    """Degree of necessity of the column

    OPT = 0 -- Optional: The symbol/Pin attribute is generated if a non empty
               value is applied. The headline entry is optional.
    MAN = 1 -- Madatory: The symbol/Pin attribute is always generated.
               The value may be empty. The headline entry is optional.
    VAL = 2 -- Value required: The symbol/Pin attribute is always generated.
               The value must not be empty. The headline entry is mandatory.
    """
    OPT = 0
    MAN = 1
    VAL = 2

Field = namedtuple('Field', 'name need')
avar = '---------'

SYM_NAME = 'Name'
SYM_VALUE = 'Value'
SYM_REFERENCE = 'Reference'
SYM_EXTENDS = 'extends'
SYM_PINS = 'pins'
SYM_TITLE = 'Title'

@dataclass
class Symbol:

    SYMBOL_FIELDS = [Field(SYM_NAME, Need.VAL),       Field(SYM_REFERENCE, Need.VAL),
                 Field(SYM_VALUE, Need.VAL),      Field('Footprint', Need.MAN),
                 Field('Datasheet', Need.MAN),    Field('Description', Need.MAN),
                 Field('ki_keywords', Need.MAN),  Field('ki_fp_filters', Need.OPT),
                 Field(SYM_EXTENDS, Need.OPT),    Field(SYM_TITLE, Need.OPT)]
    Props = namedtuple('Props', 'name header')

    PROPS1 = [Props('Datasheet', 'Datasheet'), Props('ki_keywords', 'ki_keywords')]

#    def __init__(self, xx):
    headlist = []
    xx:int

    def foo(self, y):
        x = bar()
        print("fooooo", x, y)



print(Symbol.SYMBOL_FIELDS)

#Symbol.headlist = []

#Symbol.headlist.append("22")
#Symbol.headlist.append(True)

def bar():
    print("bar")
    return 111

print(Symbol.SYMBOL_FIELDS)
print(Symbol.PROPS1)

p2 = Symbol.Props('Datasheet', 'Datasheetxx')
print(p2.name, p2.header)

s = Symbol(1)
print(s)
print(s.PROPS1)
print(s.headlist)
s2 = Symbol(2)
s.headlist.append("0000")
print(s)
print(s.headlist)

print(s2)
print(s2.headlist)

print("xx", fields(s))
s2.foo(avar)

exit(0)
