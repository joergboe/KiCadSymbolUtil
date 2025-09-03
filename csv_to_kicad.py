#!/usr/bin/env python3
"""Generate a kicat symbol library from lib.csv files."""

__author__ = "joergboe"
__version__ = "1.3.0"

from io import TextIOWrapper
import sys
import argparse
import csv
import re
from enum import Enum
from collections import namedtuple
from dataclasses import dataclass, field
from typing import Optional, Tuple, Union, TypeAlias

import kicad_sym as kicad


class Const:
    """Class with all required constant values"""

    EOT = "\x04"  # ascii 'End of Text'
    # kicad needs
    # see: https://klc.kicad.org/symbol/
    GRID = 2.54  # 100 mills - the pin grid for KiCat symbols
    BODY_LINE_WIDTH = 10.0  # 10 mills
    HIDDEN_TEXT_GAP = 1.0  # in pin grid units
    TEXT_GAP = 0.5  # text gap for small symbols
    TEXT_GAP_BIG_SYM = 2.5  # text gap for big symbols
    TEXT_GAP_VERY_BIG_SYM = 5.5
    PIN_COUNT_BIG_SYM = 5  # min pin count for big symbols
    PIN_COUNT_VERY_BIG_SYM = 15

    DOC = """This utility generates KiCad symbol libraries from symbol descriptions in CSV
files. The CSV files contain information about all the symbol attributes you need
and all the pin properties. The script checks the validity of the input values,
determines the required symbol size, and outputs the KiCad library. The script
supports the creation of symbols with one functional unit.
Symbols may be derived from precedent symbols. The derived symbol inherits all
attributes and pins from the precedent symbol and may override them."""

    @classmethod
    def more_doc(cls) -> str:
        return "\n" + cls.DOC


class Need(Enum):
    """Degree of necessity of a column

    OPT -- Optional: The symbol/Pin attribute is generated if a non empty
           value is applied. The column is optional.
    MAN -- Mandatory: The symbol/Pin attribute is always generated.
           The value may be empty. The column is mandatory.
    VAL -- Value required: The symbol/Pin attribute is always generated.
           The value must not be empty. The column is mandatory.
    """

    OPT = 0
    MAN = 1
    VAL = 2


NEED_DESCR = ["Optional", "Mandatory", "Value required"]

ColumnProp = namedtuple("ColumnProp", "name need")


class SymHead:
    """Class contains information of the symbol columns."""

    # The possible column header entries
    NAME = "symbol name"
    REFERENCE = "reference"
    FOOTPRINT = "footprint"
    DATASHEET = "datasheet"
    DESCRIPTION = "description"
    KEYWORDS = "keywords"
    FP_FILTERS = "fp filters"
    KICAD_EXTENDS = "kicad extends"
    TEXT = "text"  # TEXT - The TEXT field in the symbol
    IN_BOM = "in bom"
    ON_BOARD = "on board"
    PIN_NUMBERS_HIDE = "hide pin numbers"
    PIN_NAME_OFFSET = "pin name offset"
    PIN_NAMES_HIDE = "hide pin names"
    MIN_W = (
        "min width"  # min width of the pin shape rect. in pin grid units (must be even)
    )
    MIN_H = "min height"  # min height ...
    W_PADDING = "w padding"  # padding of the body rectangle in pin grid units
    H_PADDING = "h padding"  # fractions possible
    TEXT_FONT_SIZE = "text font size"  # Font size for text boxes 50 mills
    TEXT_GAP = "text gap"
    H_REF_VALUE_GAP = "h r/v gap"
    W_REF_VALUE_PIN_GAP = "w r/v gap"
    DERIVE_FROM = "derive from"

    # internally used
    VALUE = "symbol value"

    # this is a list because the order matters during symbol parsing
    COLUMNS_NEED = [
        ColumnProp(NAME, Need.VAL),
        ColumnProp(DERIVE_FROM, Need.OPT),
        ColumnProp(KICAD_EXTENDS, Need.OPT),
        ColumnProp(FOOTPRINT, Need.MAN),
        ColumnProp(DATASHEET, Need.MAN),
        ColumnProp(DESCRIPTION, Need.MAN),
        ColumnProp(KEYWORDS, Need.MAN),
        ColumnProp(FP_FILTERS, Need.OPT),
        ColumnProp(REFERENCE, Need.OPT),
        ColumnProp(TEXT, Need.OPT),
        ColumnProp(IN_BOM, Need.OPT),
        ColumnProp(ON_BOARD, Need.OPT),
        ColumnProp(PIN_NUMBERS_HIDE, Need.OPT),
        ColumnProp(PIN_NAME_OFFSET, Need.OPT),
        ColumnProp(PIN_NAMES_HIDE, Need.OPT),
        ColumnProp(MIN_W, Need.OPT),
        ColumnProp(MIN_H, Need.OPT),
        ColumnProp(W_PADDING, Need.OPT),
        ColumnProp(H_PADDING, Need.OPT),
        ColumnProp(TEXT_FONT_SIZE, Need.OPT),
        ColumnProp(TEXT_GAP, Need.OPT),
        ColumnProp(H_REF_VALUE_GAP, Need.OPT),
        ColumnProp(W_REF_VALUE_PIN_GAP, Need.OPT),
    ]

    BOOL_FIELDS = {IN_BOM, ON_BOARD, PIN_NUMBERS_HIDE, PIN_NAMES_HIDE}
    FLOAT_FIELDS = {
        W_PADDING,
        H_PADDING,
        TEXT_GAP,
        H_REF_VALUE_GAP,
        W_REF_VALUE_PIN_GAP,
    }
    INT_FIELDS = {PIN_NAME_OFFSET, MIN_W, MIN_H, TEXT_FONT_SIZE}

    DEFAULTS = {
        REFERENCE: "U",
        IN_BOM: "yes",
        ON_BOARD: "yes",
        PIN_NUMBERS_HIDE: "no",
        PIN_NAME_OFFSET: "20",  # mills
        PIN_NAMES_HIDE: "no",
        MIN_W: "2",
        MIN_H: "2",
        W_PADDING: "1.0",
        H_PADDING: "1.0",
        TEXT_FONT_SIZE: "50",
        H_REF_VALUE_GAP: "0.5",
        W_REF_VALUE_PIN_GAP: "0.75",
    }

    # The property names used in KiCad
    KICAD_PROPERTY_NAMES = {
        REFERENCE: "Reference",
        VALUE: "Value",
        FOOTPRINT: "Footprint",
        DATASHEET: "Datasheet",
        KEYWORDS: "ki_keywords",
        DESCRIPTION: "Description",
        FP_FILTERS: "ki_fp_filters",
    }
    MAN_PROPS = [REFERENCE, VALUE, DESCRIPTION, DATASHEET, FOOTPRINT, KEYWORDS]
    OPT_PROPS = [FP_FILTERS]
    # Hidden text fields to shift away from 0, 0
    HIDDEN_PROPS_TO_SHIFT = {DESCRIPTION, DATASHEET, FOOTPRINT}
    # Properties valid for extension symbols (except name & extends)
    EXTENSION_PROPS = {
        REFERENCE,
        FOOTPRINT,
        DATASHEET,
        DESCRIPTION,
        KEYWORDS,
        FP_FILTERS,
    }

    INFO = {
        TEXT: "The text field in the main symbol rectangle",
        MIN_W: "The minimum width of the pin shape rectangle in pin grid units (must be even)",
        MIN_H: "The minimum height of the pin shape rectangle in pin grid units (must be even)",
        W_PADDING: "Vertical padding of the body rectangle in pin grid units.\n"
        "Additional space from the minimum pin rectangle to the main symbol rectangle.\n"
        "Fractions (0.5, 0.25) are possible.",
        H_PADDING: "Horizontal padding of the body rectangle in pin grid units.\n"
        "Additional space from the minimum pin rectangle to the main symbol rectangle.\n"
        "Fractions (0.5, 0.25) are possible.",
        PIN_NAME_OFFSET: "KiCad Symbol Attribute: The pin name offset in mills.",
        TEXT_FONT_SIZE: "Font size for text box in mills.",
        TEXT_GAP: "Gap between the top of the minimum pin rectangle and the center of the text box\n"
        "in pin grid units. Fractions and negative values are possible.\n"
        f"The default text gap is determined depending on the vertical pin count:\n"
        f"IF pin_count > {Const.PIN_COUNT_VERY_BIG_SYM} THEN {Const.TEXT_GAP_VERY_BIG_SYM}\n"
        f"IF pin_count > {Const.PIN_COUNT_BIG_SYM} THEN {Const.TEXT_GAP_BIG_SYM}\n"
        f"ELSE {Const.TEXT_GAP}\n"
        f"The text box is always in the upper half of the symbol rectangle.",
        H_REF_VALUE_GAP: "Vertical distance from symbol body to Reference and Value "
        "in pin grid units.",
        W_REF_VALUE_PIN_GAP: "Horizontal distance from pin to Reference and Value "
        "in pin grid units.",
        KICAD_EXTENDS: "KiCad Symbol Attribute: The attribute for an extension symbol. (Derived in KiCad!)",
        DERIVE_FROM: "Build a new symbol and derive attributes and pins from symbol.\n"
        "Given symbol attributes overwrite the original values. Pins can be deleted\n"
        "or inserted. New pins can be inserted or appended.",
    }

    @classmethod
    def more_doc(cls) -> str:
        res = """\n
Symbol Description
==================
The first line in the symbol csv file is the headline for the symbol description.
The first column of the first line must be not empty. It must be a mandatory symbol
attribute like "symbol name". Header entries are case insensitive. Each column head
is associated with an "Need". The needs are:\n\n"""
        res += Need.__doc__
        res += "\n\nThe following columns are defined for the symbol description:\n\n"
        for item in cls.COLUMNS_NEED:
            if item.name in cls.BOOL_FIELDS:
                the_type = "boolean"
            elif item.name in cls.FLOAT_FIELDS:
                the_type = "float"
            elif item.name in cls.INT_FIELDS:
                the_type = "integer"
            else:
                the_type = "string"
            if item.name in cls.DEFAULTS:
                default = cls.DEFAULTS[item.name]
            else:
                default = "no default"
            res += (
                f"{item.name.title():<20} -- {NEED_DESCR[item.need.value]};  "
                f"Type:{the_type};  Default: {default}\n"
            )
            if item.name in cls.INFO:
                res += cls.INFO[item.name] + "\n"
            else:
                res += "KiCad Symbol Attribute\n"
            res += "\n"
        res += f"A pin grid unit is {Const.GRID} mm\n"
        res += """\n
Symbol Body
===========
The size of the symbol body rectangle depends on the effective vertical and effective
horizontal pin count and vertical and horizontal padding. The pin count determines the size of
the 'pin shape rectangle'. The 'pin shape rectangle' is the smallest rectangle which is required
to place all pins to the symbol.
If the v/h pin count is even, the height/width is pin count * pin grid unit.
If the v/h pin count is odd, the height/width is (pin count - 1) * pin grid unit.
This ensures that the body rectangle is always symmetrical to the point (0,0).
The minimum height and width of the 'pin shape rectangle' is always maintained.
The symbol body rectangle is the 'pin shape rectangle' with added padding.
The effective pin count is the count of the pins on a side of the symbol minus number
of alternative functions. Stacked pins are counted as one. Separators and gaps are counted
like real pins.
"""
        return res


class PinHead:
    """Class describing the pin columns."""

    GAP = "---"  # special number for single gap in the pin row
    GAP_REX_ANY = r"---+.*"
    GAP_REX_N1 = r"---+$"
    GAP_REX_N = r"---+\s*(\d+)$"

    def is_gap(value: str) -> bool:
        the_match = re.match(PinHead.GAP_REX_ANY, value)
        if the_match:
            return True
        else:
            return False

    def get_gap_count(value: str) -> Optional[int]:
        res = None
        the_match = re.match(PinHead.GAP_REX_N, value)
        if the_match:
            res = int(the_match.group(1))
            if res < 1:
                res = None
        else:
            the_match = re.match(PinHead.GAP_REX_N1, value)
            if the_match:
                res = 1
        vpr(f"get_gap_count({value}) returns: {res}", level=Verbosity.VERY_VERB)
        return res

    CAT = "pin category"
    NAME = "pin name"
    NUMBER = "pin number"
    GR_TYPE = "pin gr type"
    EL_TYPE = "pin el type"
    LEN = "pin length"
    STACKED = "pin stacked"
    HIDDEN = "pin hidden"
    NAME_FONT_SIZE = "name font size"
    NUMBER_FONT_SIZE = "number font size"

    # this is a list because the order matters during pin parsing
    COLUMNS_NEED = [
        ColumnProp(CAT, Need.VAL),
        ColumnProp(NUMBER, Need.VAL),
        ColumnProp(NAME, Need.MAN),
        ColumnProp(GR_TYPE, Need.MAN),
        ColumnProp(EL_TYPE, Need.VAL),
        ColumnProp(STACKED, Need.OPT),
        ColumnProp(HIDDEN, Need.OPT),
        ColumnProp(LEN, Need.OPT),
        ColumnProp(NAME_FONT_SIZE, Need.OPT),
        ColumnProp(NUMBER_FONT_SIZE, Need.OPT),
    ]

    STICKY_FIELDS = frozenset(
        {CAT, GR_TYPE, EL_TYPE, LEN, NAME_FONT_SIZE, NUMBER_FONT_SIZE}
    )

    BOOL_FIELDS = {STACKED, HIDDEN}
    FLOAT_FIELDS = {LEN, NAME_FONT_SIZE, NUMBER_FONT_SIZE}
    INT_FIELDS = {}

    DEFAULTS = {
        GR_TYPE: "line",
        LEN: "1.0",  # in grid multiples of 1/4
        NAME_FONT_SIZE: "50.0",  # 20, 30, 40 or 50 mills
        NUMBER_FONT_SIZE: "50.0",  # 20, 30, 40 or 50 mills
    }

    SIDE_TO_ANGLE = {"left": 0, "right": 180, "bottom": 90, "top": 270}

    DELETE = "delete"
    BEFORE = "before"
    AFTER = "after"
    OVERLOAD = "overload"
    CATS_FOR_DERIVED = {DELETE, BEFORE, AFTER, OVERLOAD}

    VALID_DATA = {
        CAT: CATS_FOR_DERIVED | set(SIDE_TO_ANGLE.keys()),
        GR_TYPE: {
            "line",  # ----
            "inverted",  # ----o
            "clock",  # ----|>
            "inverted_clock",  # ----o>
            "input_low",  # ----|\
            "clock_low",  # --|\|>
            "output_low",  # ---/|
            "edge_clock_high",  # --|\|>
            "non_logic",
        },  # ----x
        EL_TYPE: {
            "input",
            "output",
            "bidirectional",
            "tri_state",
            "open_collector",
            "open_emitter",
            "passive",
            "free",
            "unspecified",
            "no_connect",
            "power_in",
            "power_out",
        },
    }
    INFO = {
        CAT: 'The category of a pin. For base symbols, the "Category" refers to the side \n'
        'on which the pin is located: "left", "right", "top" and "bottom"\n'
        'For derived symbols, the categories "delete", "before" and "after" are allowed\n'
        "and denote pseudo-pins.\n"
        "A pin of a derived symbol overwrites the pin of the parent symbol with the\n"
        "matching number. The same applies to a pin list (bus). A pin list of the\n"
        "derived symbol must be a exact match to one of the pin lists of the parent\n"
        "symbol. The overwrite pin replaces the complete parent pin including all\n"
        "alternative functions.\n"
        'The category "delete" removes an inherited pin or pin list including all\n'
        "alternative functions from and sets the insertion point.\n"
        'Subsequent "real" pins are inserted in place of the deleted pin.\n'
        'The categories "before" and "after" put the insertion marker in place of\n'
        'the pin number. Subsequent "real" pins are inserted at this insertion mark.\n'
        'Inserted pins are not deleted in a subsequent "delete" and they are ignored\n'
        'in "before" and "after" searches.'
        'A pseudo-pin with category "overload" removes the insertion mark and\n'
        'subsequent pins overwrite parent pins. A pseudo-pin with category "overload"\n'
        "must not have a pin number.",
        LEN: "The length of the pin in pin grid units. Fractions (0.5, 0.25) are possible.\n"
        "The pin length should be from 1.0 (100mil) 3.0 (300mil) in steps of 1/2 grid\n"
        "padding + pin len must be an integer.",
        NAME_FONT_SIZE: "Pin name font size in mills.",
        NUMBER_FONT_SIZE: "Pin number font size in mills.",
    }

    @classmethod
    def more_doc(cls) -> str:
        res = """
Pin Description
===============
The second line in the symbol csv file is the headline for the pin description.
The first column of this line must be empty.\n\n"""
        for item in cls.COLUMNS_NEED:
            if item.name in cls.BOOL_FIELDS:
                the_type = "boolean"
            elif item.name in cls.FLOAT_FIELDS:
                the_type = "float"
            elif item.name in cls.INT_FIELDS:
                the_type = "integer"
            else:
                the_type = "string"
            if item.name in cls.DEFAULTS:
                default = cls.DEFAULTS[item.name]
            else:
                default = "no default"
            is_sticky = item.name in cls.STICKY_FIELDS
            res += (
                f"{item.name.title():<20} -- {NEED_DESCR[item.need.value]};  "
                f"Type: {the_type};  Is sticky: {is_sticky};  Default: {default}\n"
            )
            if item.name in cls.VALID_DATA:
                vd = ""
                for val in cls.VALID_DATA[item.name]:
                    vd += val + ", "
                res += f"    Valid values: {vd}\n"
            if item.name in cls.INFO:
                res += cls.INFO[item.name]
                res += "\n"
            res += "\n"
        res += f"""
More about Pins
===============
Pin numbers must be unique in one symbol. If the pin number has a value {cls.GAP!r}
or '{cls.GAP} n' no pin is generated at n positions. You can use gaps to group pins
into sections.
Sticky fields are copied from the previous line within a symbol.

Alternative pin functions are identified by the same pin number and must follow one another.

If the 'pin number' column contains a comma-separated list, a function group (bus)
is defined. In this case, the symbol '$' in the pin name is replaced by a serial
number starting with 0 and incrementing by 1.
The symbol '$(4)' is replaced by a serial number starting with 4 and incrementing by 1.
The symbol '$(4+2)' is replaced by a serial number starting with 4 and incrementing by 2.
The symbol '$(16-1)' is replaced by a serial number starting with 16 and decrementing by 1.

A function group (bus) can also define alternative functions. In this case the
alternative function must follow immediately and the 'pin number' list must be a
subset of the main 'pin number' list. The generation of the serial number works
independently for each alternative function.
"""
        return res


@dataclass
class Location:
    """Instances store the location of an csv record."""

    file: str
    line: int
    record: int

    def __str__(self) -> str:
        return f"File: {self.file!r} Record: {self.record} Line: {self.line}."


class CsvToKicadError(Exception):
    """Superclass for all thrown errors"""

    def __init__(self, message: str, loc: Location):
        super().__init__(f"{message} - {loc}")


class HeaderError(CsvToKicadError):
    """Signals an error in the csv file header rows 1 and 2."""

    pass


class SymbolError(CsvToKicadError):
    """Signals invalid or insufficient symbol data."""

    pass


class PinError(CsvToKicadError):
    """Signals invalid or insufficient pin data."""

    pass


class ValidationError(CsvToKicadError):
    """Thrown if a field value is not valid."""

    pass


class LogicError(CsvToKicadError):
    """Signals an severe logic error."""

    pass


CSVRecord = namedtuple("CSVRecord", "columns location")


class MyCSVReader:
    """Special csv reader returns stripped line items, skips comment-lines and
    empty lines and generates 'Location'."""

    def __init__(
        self, filename: str, csvfile: TextIOWrapper, dialect: csv.Dialect, strict: bool
    ) -> None:
        self.file = filename
        self.csvreader = csv.reader(csvfile, dialect=dialect, strict=strict)
        self.record = 0
        self.skipped_empty = 0

    def get_location(self) -> Location:
        return Location(self.file, self.csvreader.line_num, self.record)

    def get_record(self) -> CSVRecord:
        """Get the next csv record with stripped entries
        Throws: StopFileIteration
        """
        res = [item.strip() for item in next(self.csvreader)]
        self.record += 1
        loc = Location(self.file, self.csvreader.line_num, self.record)
        return CSVRecord(res, loc)

    def get_nonempty_line(self) -> CSVRecord:
        """Get the next non empty and non comment csv record, strip values and return.

        Throws: csv.Error, LogicError
        Returns the next csv record. Empty lines and comments are skipped.
        EOT is returned at the end of the file.
        """
        while True:
            line = next(self.csvreader, Const.EOT)
            if line != Const.EOT:
                self.record += 1
            loc = Location(self.file, self.csvreader.line_num, self.record)
            if line == Const.EOT:
                return CSVRecord(line, loc)
            elif isinstance(line, list):
                res = [item.strip() for item in line]
                for item in res:
                    if item:
                        if item.startswith("#"):
                            break
                        return CSVRecord(res, loc)
            else:
                raise LogicError(f"Wrong type in get_nonempty_line(): {line!r}", loc)
            self.skipped_empty += 1


Attrib: TypeAlias = Union[str, int, float, bool]


@dataclass
class Pin:
    """Internal representation of a pin."""

    loc: Location
    protected: bool = field(default=False, init=False)
    attribs: dict[str, Attrib] = field(default_factory=dict)

    def __post_init__(self):
        vpr("Pin created:", self.__dict__, level=Verbosity.VERY_VERB)

    def is_protected(self) -> bool:
        return self.protected

    def set_protected(self, val: bool) -> None:
        self.protected = val

    def add_attr(self, name: str, value: Attrib) -> None:
        self.attribs[name] = value

    def get_attr(self, name: str) -> Attrib:
        if name not in self.attribs:
            raise LogicError(f"No attribute {name!r}", self.loc)
        return self.attribs[name]

    def has_attr(self, name: str) -> bool:
        return name in self.attribs

    def set_gap(self, value: str) -> None:
        self.attribs[PinHead.NUMBER] = value

    def is_gap(self) -> bool:
        if PinHead.NUMBER not in self.attribs:
            raise LogicError("in is_separator_or_gap()", self.loc)
        return PinHead.is_gap(self.attribs[PinHead.NUMBER])

    def get_gap_count(self) -> int:
        if PinHead.NUMBER not in self.attribs:
            raise LogicError("in is_separator_or_gap()", self.loc)
        value = self.attribs[PinHead.NUMBER]
        res = PinHead.get_gap_count(value)
        if res is None:
            raise PinError(f"No valid get_gap_count: value: {value!r}", self.loc)
        return res

    def is_hidden(self) -> bool:
        return PinHead.HIDDEN in self.attribs and self.attribs[PinHead.HIDDEN]

    def is_stacked(self) -> bool:
        return PinHead.STACKED in self.attribs and self.attribs[PinHead.STACKED]

    def is_pseudo_pin(self) -> bool:
        if PinHead.CAT in self.attribs:
            return self.attribs[PinHead.CAT] in PinHead.CATS_FOR_DERIVED
        else:
            return False

    def get_cat(self) -> str:
        if PinHead.CAT not in self.attribs:
            raise LogicError(f"No attribute {PinHead.CAT!r}", self.loc)
        return self.attribs[PinHead.CAT]

    def get_number(self) -> str:
        if PinHead.NUMBER not in self.attribs:
            raise LogicError(f"No attribute {PinHead.NUMBER!r}", self.loc)
        return self.attribs[PinHead.NUMBER]

    def get_name(self) -> str:
        if PinHead.NAME not in self.attribs:
            raise LogicError(f"No attribute {PinHead.NAME!r}", self.loc)
        return self.attribs[PinHead.NAME]

    def is_bus(self) -> bool:
        return "," in self.get_number()

    def get_checked_bus_pin_list(self) -> list[str]:
        """Get the bus pin list and check against duplicate elements"""
        elems = [item.strip() for item in self.get_number().split(",")]
        check = set()
        for item in elems:
            if item in check:
                raise PinError(f"Duplicate pin: {item!r} in bus: {elems}", self.loc)
            check.add(item)
        return elems

    def is_alt_func_pin(self, next_pin) -> bool:
        if self.is_gap() or next_pin.is_gap():
            return False
        if self.is_bus():
            my_pin_numbers = set(self.get_checked_bus_pin_list())
            new_pin_list = set(next_pin.get_checked_bus_pin_list())
            return new_pin_list <= my_pin_numbers
        else:
            return self.get_number() == next_pin.get_number()


def convert_to_bool(val: str, column_name: str, loc: Location) -> bool:
    """Get the boolean value from a yes/no field entry and return"""
    if val:
        temp = val
        val = temp.lower()
        if val in {"y", "yes", "true"}:
            return True
        elif val in {"n", "no", "false"}:
            return False
        else:
            raise ValidationError(
                f"Wrong value {val!r} in {column_name} "
                f' Valid values: "yes" or "no".',
                loc,
            )
    else:
        return False


def convert_inp(
    value: str,
    name: str,
    bool_fields: set[str],
    int_fields: set[str],
    float_fields: set[str],
    loc: Location,
) -> Attrib:
    res = None
    try:
        if name in bool_fields:
            res = convert_to_bool(value, name, loc)
        elif name in int_fields:
            res = int(value)
        elif name in float_fields:
            res = float(value)
        else:
            res = value
    except ValueError as error:
        raise ValidationError(
            f"Error during conversation of column: {name} "
            f"value: {value!r}! Message {error}",
            loc,
        )
    return res


def validate_value(
    value: str, valid_values: set[str], column_name: str, loc: Location
) -> None:
    """Validate symbol/pin value and throw ValidationError if invalid.

    Arguments:
      value        -- value to check
      valid_values -- set with valid values
      column_name  -- column name
      loc          -- the current location info
    Globals:
      vpr       -- the log printer
    Throws: ValidationError
    """
    if value in valid_values:
        vpr(
            f"validate_value: Column {column_name} value {value!r} validated.",
            level=Verbosity.VERY_VERB,
        )
        return
    else:
        raise ValidationError(
            f"Column {column_name} value {value!r} is invalid!\n"
            f"Valid values: {valid_values}",
            loc,
        )


def clone_bus_pin(pin: Pin, number: str, rex: str, serial: int) -> Pin:
    """Clone bus pin to a physical pin number and convert bus pin name"""
    bus_pin = Pin(pin.loc)
    for pin_attr_name in pin.attribs.keys():
        if pin_attr_name == PinHead.NUMBER:
            bus_pin.attribs[pin_attr_name] = number
        elif pin_attr_name == PinHead.NAME:
            if rex:
                bus_pin.attribs[pin_attr_name] = re.sub(
                    rex, str(serial), pin.get_name()
                )
            else:
                bus_pin.attribs[pin_attr_name] = pin.get_name()
        else:
            bus_pin.attribs[pin_attr_name] = pin.attribs[pin_attr_name]
    return bus_pin


@dataclass
class PinProcessor:
    """Stores pin column information and parses pin lines.

    The instance of this class contains the results of the second
    line header analysis of the current csv-file:
        head_list -- a copy of the head line as list[str]
        head_cols -- the assignement title -> column number as dict[int]
    """

    reader: MyCSVReader
    head_list: list = field(init=False)
    head_cols: dict[str:int] = field(init=False)

    def __post_init__(self):
        self.head_list, self.head_cols = parse_header(
            PinHead.COLUMNS_NEED, self.reader, False
        )

    def parse_pin(self, inp: CSVRecord, previous_pin: Pin, previous_cat: str) -> Pin:
        """Process one pin record and return a validated pin-dict.

        Arguments:
        inp          -- csv record and location to process
        previous_pin -- previous pin or None
        previous_cat -- previous pin category or empty
        Globals:
        PinHead      -- class attributes
        vpr          -- the log printer
        Returns: validated pin as as dictionary.
        Throws: LogicError, PinError

        Pin is a dictionary like:
        {'pin category':'aSide', 'pin number':'aNumber', 'pin name', 'aName', 'stacked':True}
        Alternative pin functions follow as entry in pin list with same 'number'
        If name or number is '---' or '--- n', it is or a gap or n gaps.
        A separator/gap takes the space of one pin but does not generate a pin-symbol
        """
        vpr(f"parse_pin inp: {inp.columns}", level=Verbosity.VERBOSE)

        if not isinstance(inp.columns, list):
            raise LogicError("Wrong type in parse_pin()!", inp.location)
        # In pin records the first column must be empty
        if inp.columns[0]:
            raise LogicError(f"Wrong record {inp.columns} in parse_pin!", inp.location)
        # check surplus data fields and data values with no header entry
        i = 0
        while i < len(inp.columns):
            if i >= len(self.head_list):
                raise PinError(f"Surplus pin data fields: {inp.columns}", inp.location)
            if not self.head_list[i] and inp.columns[i]:
                raise PinError(
                    f"Surplus pin data field {inp.columns[i]!r}", inp.location
                )
            i += 1
        # build pin object and check values
        pin = Pin(inp.location)
        # expected order: category, number, name, ...
        break_condition = ""
        for item in PinHead.COLUMNS_NEED:
            check_fields = break_condition == ""
            # get column and value
            column = None
            value = ""
            if item.name in self.head_cols:
                column = self.head_cols[item.name]
                value = inp.columns[column]
            vpr(
                f"parse_pin: item: {item!r} column: {column} value: {value!r}",
                level=Verbosity.VERY_VERB,
            )
            # check separator or gap
            if (item.name == PinHead.NUMBER) and PinHead.is_gap(value):
                pin.set_gap(value)
                break_condition = "pin gap"
            # check pseudo pin
            if item.name == PinHead.NAME:
                if pin.is_pseudo_pin():
                    break_condition = "pseudo pin"
                    if (pin.get_cat() == PinHead.OVERLOAD) and pin.get_number():
                        raise PinError(
                            "Pin number is not allowed for overload!", inp.location
                        )
            if check_fields:
                # propagate sticky fields if necessary and possible
                if (not value) and (item.name in PinHead.STICKY_FIELDS):
                    if item.name == PinHead.CAT:
                        if previous_cat:
                            value = previous_cat
                    else:
                        if previous_pin and previous_pin.has_attr(item.name):
                            v_str = str(previous_pin.get_attr(item.name))
                            if v_str:
                                value = v_str
                # check need
                if not value:
                    if item.need == Need.VAL:
                        if not pin.get_cat() == PinHead.OVERLOAD:
                            raise PinError(
                                f"Value is required for {item.name!r}", inp.location
                            )
                # add defaults
                if not value and (item.name in PinHead.DEFAULTS):
                    value = PinHead.DEFAULTS[item.name]
                # check valid entries
                if item.name in PinHead.VALID_DATA:
                    validate_value(
                        value, PinHead.VALID_DATA[item.name], item.name, inp.location
                    )
                # add name:value to pin
                if value or (item.need != Need.OPT):
                    # Need.MAN and Need.VAL are always put
                    va = convert_inp(
                        value,
                        item.name,
                        PinHead.BOOL_FIELDS,
                        PinHead.INT_FIELDS,
                        PinHead.FLOAT_FIELDS,
                        inp.location,
                    )
                    pin.add_attr(item.name, va)
            else:
                if value:
                    print(
                        f"WARNING: Ignored value: {value!r} in {break_condition} column: {item.name!r}",
                        inp.location,
                        file=sys.stderr,
                    )
        vpr(f"parse_pin returns: {pin}", level=Verbosity.VERBOSE)
        return pin


BusBuildSchema = namedtuple("BusBuildSchema", "rex start increment")

BUS_BUILD_REX = [r"\$\((\d+)([+-])?(\d+)?\)", r"\$"]


def get_bus_build_schema(name: str, loc: Location) -> BusBuildSchema:
    vpr(f"get_bus_build_schema() : name: {name}", level=Verbosity.VERY_VERB)
    operation = "+"
    inc = 1
    start = 0
    rex = BUS_BUILD_REX[0]
    the_match = re.search(rex, name)
    if the_match:
        if not the_match.group(3) is None:
            inc = int(the_match.group(3))
        if not the_match.group(2) is None:
            operation = the_match.group(2)
        start = int(the_match.group(1))
    else:
        rex = BUS_BUILD_REX[1]
        the_match = re.search(rex, name)
    if the_match:
        vpr(
            f"get_bus_build_schema() : rex: {rex} group(): {the_match.group()} groups: "
            f"{the_match.groups()}",
            level=Verbosity.VERY_VERB,
        )
        if operation == "+":
            pass
        elif operation == "-":
            inc = inc * -1
        else:
            raise LogicError(
                f"Error in get_bus_build_schema name:{name!r} "
                f"rex: {rex!r} operation: {operation!r}",
                loc,
            )
    else:
        vpr("get_bus_build_schema() : no match!", level=Verbosity.VERY_VERB)
        rex = ""
    res = BusBuildSchema(rex, start, inc)
    vpr(f"get_bus_build_schema returns: {res}", level=Verbosity.VERBOSE)
    return res


PinShapeProps = namedtuple(
    "PinShapeProps",
    "width_h height_h pin_count_l pin_count_r pin_count_t pin_count_b "
    "len_l, len_r, len_t, len_b",
)


@dataclass
class Symbol:
    """Internal representation of a symbol.

    All symbol attributes are stored in the 'attribs'.
    The name is additionally stored in 'name'.
    The symbol pins are stored in a list of pins.
    """

    loc: Location
    attribs: dict[str, Attrib] = field(default_factory=dict)
    pins: list[Pin] = field(default_factory=list)
    extends = None

    def __post_init__(self):
        vpr("Symbol created:", self.__dict__, level=Verbosity.VERY_VERB)

    def add_attr(self, name: str, value: Attrib) -> None:
        if name in [SymHead.KICAD_EXTENDS, SymHead.DERIVE_FROM]:
            raise LogicError(
                f"Use set_derived() or set_extends() to set {name!r}", self.loc
            )
        if name == SymHead.NAME:
            # KiCad requires: symbol name and value are always equal
            self.attribs[SymHead.VALUE] = value
        self.attribs[name] = value

    def get_attr(self, name: str) -> Optional[Attrib]:
        if name in self.attribs:
            return self.attribs[name]
        else:
            return None

    def get_name(self) -> str:
        if SymHead.NAME not in self.attribs:
            raise LogicError("get_name() called but no name in self.attribs", self.loc)
        return self.attribs[SymHead.NAME]

    def add_pin(self, pin: Pin) -> None:
        self.pins.append(pin)

    def is_extension(self) -> bool:
        return self.extends is not None

    def set_extends(self, value) -> None:
        self.attribs[SymHead.KICAD_EXTENDS] = value.get_name()
        self.extends = value

    def get_extension_root_symbol(self):
        if self.extends is None:
            raise LogicError(
                "get_extension_root_symbol() called but no extension set!", self.loc
            )
        if self.extends.is_extension():
            return self.extends.get_extension_root_symbol()
        else:
            return self.extends

    def is_derived(self) -> bool:
        return (SymHead.DERIVE_FROM in self.attribs) and self.attribs[
            SymHead.DERIVE_FROM
        ]

    def set_derived(self, value: str) -> None:
        self.attribs[SymHead.DERIVE_FROM] = value

    def get_derived(self) -> str:
        return self.attribs[SymHead.DERIVE_FROM]

    def get_max_pin_len(self, side: str) -> float:
        res = 0.0
        for pin in self.pins:
            if pin.get_cat() == side and not pin.is_gap() and not pin.is_pseudo_pin():
                res = max(res, pin.get_attr(PinHead.LEN))
        vpr(side, "get_max_pin_len returns:", res, level=Verbosity.VERY_VERB)
        return res

    def get_effective_pin_count(self, side: str) -> int:
        """Get the count of the effective pin count of one side and check conditions

        The effective pin count is the count of the pins in list pins minus number
        of alternative functions. Stacked pins are counted as 1.
        Separators and gaps are counted."""
        count = 0
        main_pin: Pin = None
        for pin in self.pins:
            if pin.get_cat() == side:
                if pin.is_pseudo_pin():
                    raise LogicError(
                        "get_effective_pin_count(): No pseudo pins " "allowed here!",
                        pin.loc,
                    )
                if pin.is_stacked():
                    if main_pin and main_pin.is_alt_func_pin(pin):
                        raise PinError(
                            f"get_effective_pin_count(): alternative "
                            f"function must not be stacked: {pin}",
                            pin.loc,
                        )
                    main_pin = None
                elif pin.is_gap():
                    count += pin.get_gap_count()
                    main_pin = None
                elif main_pin is None:
                    count += len(pin.get_checked_bus_pin_list())
                    main_pin = pin
                else:
                    if main_pin.is_alt_func_pin(pin):
                        if pin.is_hidden() != main_pin.is_hidden():
                            raise PinError(
                                f"get_effective_pin_count(): alternative "
                                f"function hidden: {pin.is_hidden()} Main pin hidden: "
                                f"{main_pin.is_hidden()} combination not allowed!",
                                pin.loc,
                            )
                    else:
                        count += len(pin.get_checked_bus_pin_list())
                        main_pin = pin
        vpr(side, "get_effective_pin_count returns:", count, level=Verbosity.VERBOSE)
        return count

    def get_pin_shape(self) -> PinShapeProps:
        """Get the minimal rectangle depending on the pin count. Return 1/2 height
        and 1/2 width in multiples of the pin grid len.

        l - edge length; p - pin count; g - pin grid
        l >= (p - 1) * g
        """
        pin_count_l = self.get_effective_pin_count("left")
        pin_count_r = self.get_effective_pin_count("right")
        pin_count_t = self.get_effective_pin_count("top")
        pin_count_b = self.get_effective_pin_count("bottom")
        width_half = get_half_len(max(pin_count_t, pin_count_b))
        height_half = get_half_len(max(pin_count_l, pin_count_r))
        m_w_h = self.attribs[SymHead.MIN_W] // 2
        m_h_h = self.attribs[SymHead.MIN_H] // 2
        if width_half < m_w_h:
            vpr(
                f"Pin Shape Width: {width_half} is below minimum. Set: {m_w_h} "
                f"Symbol name: {self.get_name()} {self.loc}",
                level=Verbosity.VERBOSE,
            )
            width_half = m_w_h
        if height_half < m_h_h:
            vpr(
                f"Pin Shape Height: {height_half} is below minimum. Set: {m_h_h} "
                f"Symbol name: {self.get_name()} {self.loc}",
                level=Verbosity.VERBOSE,
            )
            height_half = m_h_h
        psp = PinShapeProps(
            width_half,
            height_half,
            pin_count_l,
            pin_count_r,
            pin_count_t,
            pin_count_b,
            self.get_max_pin_len("left"),
            self.get_max_pin_len("right"),
            self.get_max_pin_len("top"),
            self.get_max_pin_len("bottom"),
        )

        vpr(
            f"get_pin_shape: psp.width_h={psp.width_h} psp.height_h={psp.height_h} "
            f"count_l={pin_count_l} count_r={pin_count_r} count_t={pin_count_t} "
            f"count_b={pin_count_b}",
            level=Verbosity.VERBOSE,
        )
        return psp

    def build_symbol(self, filename: str, libname: str) -> kicad.KicadSymbol:
        """Build and return the Kicad new_symbol"""
        # real width is 2 * w, real heigth is 2 * h
        if self.is_extension():
            psp = self.get_extension_root_symbol().get_pin_shape()
        else:
            psp = self.get_pin_shape()
        new_symbol = kicad.KicadSymbol(self.get_name(), libname, filename)
        # add text properties
        py = (
            psp.height_h
            + psp.len_b
            + self.get_attr(SymHead.H_PADDING)
            + Const.HIDDEN_TEXT_GAP
        )
        py = py * -1
        for p in SymHead.MAN_PROPS:
            prop = kicad.Property(SymHead.KICAD_PROPERTY_NAMES[p], self.attribs[p])
            prop.effects.is_hidden = True
            if p in SymHead.HIDDEN_PROPS_TO_SHIFT:
                prop.posy = py * Const.GRID
                py -= Const.HIDDEN_TEXT_GAP
            new_symbol.properties.append(prop)
        for p in SymHead.OPT_PROPS:
            if p in self.attribs and self.attribs[p]:
                prop = kicad.Property(SymHead.KICAD_PROPERTY_NAMES[p], self.attribs[p])
                prop.effects.is_hidden = True
                new_symbol.properties.append(prop)
        # place reference and value on top and below bottom
        pyref = (
            psp.height_h
            + self.attribs[SymHead.H_PADDING]
            + self.attribs[SymHead.H_REF_VALUE_GAP]
        ) * Const.GRID
        pyval = pyref * -1.0
        pxref = 0
        pxval = 0
        justifyref = "center"
        justifyval = "center"
        # place reference and value on top if bottom pins are present
        if psp.pin_count_b or psp.pin_count_t:
            pyval = pyref
            if psp.pin_count_t:
                px_first_top_pin = (
                    psp.width_h - center_pins(psp.width_h, psp.pin_count_t)
                ) * -1
                px_last_top_pin = px_first_top_pin + psp.pin_count_t - 1
            else:
                px_first_top_pin = 0
                px_last_top_pin = 0
            pxref = (
                px_first_top_pin - self.attribs[SymHead.W_REF_VALUE_PIN_GAP]
            ) * Const.GRID
            pxval = (
                px_last_top_pin + self.attribs[SymHead.W_REF_VALUE_PIN_GAP]
            ) * Const.GRID
            justifyref = "right"
            justifyval = "left"
        prop = new_symbol.get_property(SymHead.KICAD_PROPERTY_NAMES[SymHead.REFERENCE])
        prop.effects.is_hidden = False
        prop.effects.h_justify = justifyref
        prop.posx = pxref
        prop.posy = pyref
        prop.rotation = 0.0
        prop = new_symbol.get_property(SymHead.KICAD_PROPERTY_NAMES[SymHead.VALUE])
        prop.effects.is_hidden = False
        prop.effects.h_justify = justifyval
        prop.posx = pxval
        prop.posy = pyval
        prop.rotation = 0.0

        if self.is_extension():
            new_symbol.extends = self.attribs[SymHead.KICAD_EXTENDS]
            return new_symbol
        # place the body rectangle
        body_w = (psp.width_h + self.attribs[SymHead.W_PADDING]) * Const.GRID
        body_h = (psp.height_h + self.attribs[SymHead.H_PADDING]) * Const.GRID
        body = kicad.Rectangle(body_w * -1, body_h * -1, body_w, body_h)
        body.stroke_width = kicad.mil_to_mm(Const.BODY_LINE_WIDTH)
        new_symbol.rectangles.append(body)
        # place symbol text
        if (SymHead.TEXT in self.attribs) and self.attribs[SymHead.TEXT]:
            title = self.attribs[SymHead.TEXT]
            # if no special text gap is given, the value depends on symbol size
            if SymHead.TEXT_GAP in self.attribs:
                my_text_gap = self.attribs[SymHead.TEXT_GAP]
            else:
                pin_max = max(psp.pin_count_l, psp.pin_count_r)
                if pin_max > Const.PIN_COUNT_VERY_BIG_SYM:
                    my_text_gap = Const.TEXT_GAP_VERY_BIG_SYM
                elif pin_max > Const.PIN_COUNT_BIG_SYM:
                    my_text_gap = Const.TEXT_GAP_BIG_SYM
                else:
                    my_text_gap = Const.TEXT_GAP
            vpr(
                f"build_symbol: text gap result: {my_text_gap}", level=Verbosity.VERBOSE
            )
            posy = psp.height_h - my_text_gap
            if posy < 0.0:
                posy = 0.0
            posy_mm = posy * Const.GRID
            fs_mm = kicad.mil_to_mm(self.attribs[SymHead.TEXT_FONT_SIZE])
            text_eff = kicad.TextEffect(fs_mm, fs_mm)
            text = kicad.Text(title, 0.0, posy_mm, 0.0, text_eff)
            new_symbol.texts.append(text)
        # other optionale attributes
        new_symbol.in_bom = self.attribs[SymHead.IN_BOM]
        new_symbol.on_board = self.attribs[SymHead.ON_BOARD]
        new_symbol.hide_pin_numbers = self.attribs[SymHead.PIN_NUMBERS_HIDE]
        new_symbol.pin_names_offset = kicad.mil_to_mm(
            self.attribs[SymHead.PIN_NAME_OFFSET]
        )
        new_symbol.hide_pin_names = self.attribs[SymHead.PIN_NAMES_HIDE]

        self.build_all_pins(new_symbol, psp)
        return new_symbol

    def build_all_pins(self, kicad_sym: kicad.KicadSymbol, psp: PinShapeProps) -> None:
        """Build all pins of an symbol from pins and append to symbol

        Goes through all 4 sides left, right, top and bottom
        """

        pin_number_set = set()

        def collect_alt_functions(side_pin_list: list[Pin], shift_pos) -> None:
            """Collect all associated alternative functions of one pin in alt_func_list

            Goes through side_pin_list, collects the alternative functions of a pin
            in alt_func_list, shifts position and calls build_bus for each pin
            """
            alt_func_list: list[Pin] = []

            def build_bus() -> None:
                """Gets the alt_func_list and calls the build_pin for each pin number

                Clear alt_func_list after pin creation
                """
                alt_func_list_single: list[Pin] = []

                def build_pin() -> kicad.Pin:
                    """Build a KiCad Pin object from alt_func_list_single and return
                    Check valid pin len
                    Clear alt_func_list after pin creation
                    """
                    vpr(
                        f"build_pin(): alt_func_list_single={alt_func_list_single}",
                        level=Verbosity.VERY_VERB,
                    )
                    if not alt_func_list_single:
                        raise LogicError(
                            "build_pin(): with empty alt_func_list_single!", self.loc
                        )
                    # check pin number uniqueness
                    p_n = alt_func_list_single[0].get_number()
                    if p_n in pin_number_set:
                        raise PinError(
                            f"duplicate pin number {p_n}", alt_func_list_single[0].loc
                        )
                    pin_number_set.add(p_n)
                    # check if pin len + padding is a integer multiple of grid
                    p_len = alt_func_list_single[0].get_attr(PinHead.LEN)
                    if (rot == 0) or (rot == 180):
                        padding = self.attribs[SymHead.W_PADDING]
                    else:
                        padding = self.attribs[SymHead.H_PADDING]
                    pin_pos = padding + p_len
                    pin_pos_i = int(pin_pos)
                    if pin_pos != pin_pos_i:
                        raise SymbolError(
                            f"Invalid pin_len: {p_len} padding: "
                            f"{padding} combination in pin: "
                            f"{alt_func_list_single[0].get_number()} Symbol {self.get_name()}",
                            alt_func_list_single[0].loc,
                        )
                    # shift pos
                    nonlocal do_shift
                    if do_shift:
                        if not alt_func_list_single[0].is_stacked():
                            shift_pos()
                    do_shift = True
                    # build kicad pin
                    new_pin = build_kicad_pin(alt_func_list_single, posx, posy, rot)
                    kicad_sym.pins.append(new_pin)
                    return new_pin

                # build_bus
                vpr(
                    f"build_bus(): alt_func_list={alt_func_list}",
                    level=Verbosity.VERY_VERB,
                )
                if not alt_func_list:
                    raise LogicError("build_bus(): with empty alt_func_list!", self.loc)
                pin_num_list = alt_func_list[0].get_checked_bus_pin_list()
                alt_funcs_name_schemas = []
                alt_funcs_name_serial = []
                for alt_func in alt_func_list:
                    bbs = get_bus_build_schema(alt_func.get_name(), alt_func.loc)
                    alt_funcs_name_schemas.append(bbs)
                    alt_funcs_name_serial.append(bbs.start)

                for pin_number in pin_num_list:
                    alt_func_list_single.clear()
                    i = 0
                    for alt_func in alt_func_list:
                        alt_func_pin_num_list = set(alt_func.get_checked_bus_pin_list())
                        if pin_number in alt_func_pin_num_list:
                            bus_pin = clone_bus_pin(
                                alt_func,
                                pin_number,
                                alt_funcs_name_schemas[i].rex,
                                alt_funcs_name_serial[i],
                            )
                            vpr(
                                f"append to alt_func_list_single - Pin:{bus_pin}",
                                level=Verbosity.VERY_VERB,
                            )
                            alt_func_list_single.append(bus_pin)
                            alt_funcs_name_serial[i] += alt_funcs_name_schemas[
                                i
                            ].increment
                        i += 1
                    build_pin()
                alt_func_list.clear()

            # collect_alt_functions
            vpr(f"collect_alt_functions(): {side_pin_list}", level=Verbosity.VERY_VERB)
            for pin in side_pin_list:
                vpr(
                    f"collect_alt_functions: number: {pin.get_number()}",
                    level=Verbosity.VERY_VERB,
                )
                if pin.is_gap():
                    if alt_func_list:
                        build_bus()
                    count = pin.get_gap_count()
                    while count > 0:
                        shift_pos()  # a sepatator or gap must shift the position
                        count -= 1
                else:
                    if not alt_func_list:
                        alt_func_list.append(pin)
                    else:
                        pin0 = alt_func_list[0]
                        if not pin0.is_alt_func_pin(pin):
                            # next physical pin
                            build_bus()
                            alt_func_list.append(pin)
                        else:
                            # alternative function - check for changes in other fields
                            if pin.get_cat() != pin0.get_cat():
                                raise LogicError(
                                    f"collect_alt_functions(): "
                                    f"Alternative list changes side!\n"
                                    f"pin: {pin} alt_func_list[-1]: {alt_func_list[-1]}",
                                    pin.loc,
                                )
                            # finally append alternative function
                            alt_func_list.append(pin)
            # end side_pin_list
            if alt_func_list:
                build_bus()
            return None

        def inc_posx():
            nonlocal posx
            posx += 1

        def dec_posy():
            nonlocal posy
            posy -= 1

        # add_pins()
        # left pins
        posx = (psp.width_h + self.attribs[SymHead.W_PADDING]) * -1
        posy = psp.height_h - center_pins(psp.height_h, psp.pin_count_l)
        rot = PinHead.SIDE_TO_ANGLE["left"]
        do_shift = False
        the_side_list = [
            pin_item for pin_item in self.pins if pin_item.get_cat() == "left"
        ]
        collect_alt_functions(the_side_list, dec_posy)

        # right pins
        posx = psp.width_h + self.attribs[SymHead.W_PADDING]
        posy = psp.height_h - center_pins(psp.height_h, psp.pin_count_r)
        rot = PinHead.SIDE_TO_ANGLE["right"]
        do_shift = False
        the_side_list = [
            pin_item for pin_item in self.pins if pin_item.get_cat() == "right"
        ]
        collect_alt_functions(the_side_list, dec_posy)

        # top pins
        posx = (psp.width_h - center_pins(psp.width_h, psp.pin_count_t)) * -1
        posy = psp.height_h + self.attribs[SymHead.H_PADDING]
        rot = PinHead.SIDE_TO_ANGLE["top"]
        do_shift = False
        the_side_list = [
            pin_item for pin_item in self.pins if pin_item.get_cat() == "top"
        ]
        collect_alt_functions(the_side_list, inc_posx)

        # bottom pins
        # adjust = ((psp.width_h * 2) + 1 - psp.pin_count_b) // 2
        posx = (psp.width_h - center_pins(psp.width_h, psp.pin_count_b)) * -1
        posy = (psp.height_h + self.attribs[SymHead.H_PADDING]) * -1
        rot = PinHead.SIDE_TO_ANGLE["bottom"]
        do_shift = False
        the_side_list = [
            pin_item for pin_item in self.pins if pin_item.get_cat() == "bottom"
        ]
        collect_alt_functions(the_side_list, inc_posx)


@dataclass
class SymbolProcessor:
    """Class contains information of the symbol columns and parses symbol colunms.

    The instance of this class contains the results of the first
    line header analysis of the current csv-file:

        reader -- the reader object for the current csv-file
        head_list -- a copy of the head line as list[str]
        head_cols -- the assignement title -> column number as dict[int]"""

    reader: MyCSVReader
    head_list: list = field(init=False)
    head_cols: dict[str:int] = field(init=False)
    pin_processor: PinProcessor = field(init=False)

    def __post_init__(self):
        self.head_list, self.head_cols = parse_header(
            SymHead.COLUMNS_NEED, self.reader, True
        )
        self.pin_processor = PinProcessor(self.reader)

    def parse_symbol(
        self, inp: CSVRecord, all_symbols: dict[str, Symbol]
    ) -> Tuple[CSVRecord, Optional[Symbol]]:
        """Generate one symbol from csv records and return the next record and symbol.

        Arguments:
        inp        -- csv column and location to process
        all_symbols -- all symbols processed so far as dict name -> Symbol
        Globals:
        SymHead    -- class attributes
        vpr        -- the log printer
        Returns: Tuple [ next CSVRecord, Symbol|None ]
        Throws: LogicError, SymbolError, ValidationError, PinError, csv.Error
        """
        vpr(f"parse_symbol inp: {inp.columns!r}", level=Verbosity.VERBOSE)
        if inp.columns == Const.EOT:
            return inp, None

        if not isinstance(inp.columns, list):
            raise LogicError("Wrong type in parse_symbol()!", inp.location)

        # check surplus data fields and data values with no header entry
        i = 0
        while i < len(inp.columns):
            if i >= len(self.head_list):
                raise SymbolError(
                    f"Surplus symbol data fields: {inp.columns}", inp.location
                )
            if not self.head_list[i] and inp.columns[i]:
                raise SymbolError(
                    f"Surplus symbol data field {inp.columns[i]!r}", inp.location
                )
            i += 1

        symbol: Symbol = Symbol(inp.location)
        derived_from: Optional[Symbol] = None
        # parse all symbol columns in specific order:
        #    name, derived from, extends... h ref value gap, w ref value gap
        for item in SymHead.COLUMNS_NEED:
            column = None
            value: str = ""
            # Get value from csv if column symbol header is present
            if item.name in self.head_cols:
                column = self.head_cols[item.name]
                value = inp.columns[column]
            vpr(
                f"parse_symbol: item: {item} column: {column} value: {value!r}",
                level=Verbosity.VERY_VERB,
            )

            if (item.name == SymHead.KICAD_EXTENDS) and value:
                # Extends column is processed after derived from -> check
                if symbol.is_derived():
                    raise SymbolError(
                        f"Cannot extend and derive from another symbol {symbol.get_name()!r}",
                        inp.location,
                    )
                if value not in all_symbols:
                    raise SymbolError(
                        f"Symbol to extend {value!r} not found!", inp.location
                    )
                symbol.set_extends(all_symbols[value])
                continue

            if (item.name == SymHead.DERIVE_FROM) and value:
                # Derived column is processed before column extends -> no check
                if value not in all_symbols:
                    raise SymbolError(
                        f"Derived from symbol {value!r} not found!", inp.location
                    )
                derived_from = all_symbols[value]
                symbol.set_derived(value)
                continue

            # try to get attribute from parent for derived symbols
            if derived_from and not value:
                derived_attr = derived_from.get_attr(item.name)
                if derived_attr is not None:
                    # derived attributes are taken unchecked
                    symbol.add_attr(item.name, derived_attr)
                    continue

            # attribute check - value required?
            if not value:
                if item.need == Need.VAL:
                    raise SymbolError(
                        f"Value is required for {item.name!r}", inp.location
                    )

            # check extension props
            if symbol.is_extension():
                if value and item.name not in SymHead.EXTENSION_PROPS:
                    raise SymbolError(
                        f"{item.name!r} is not allowed for extension "
                        f"symbols in symbol: {symbol.get_name()!r}",
                        inp.location,
                    )

            # add defaults
            if not value and (item.name in SymHead.DEFAULTS):
                value = SymHead.DEFAULTS[item.name]

            # add value to symbol
            if value or (item.need != Need.OPT):
                # Need.MAN and Need.VAL are always put
                va = convert_inp(
                    value,
                    item.name,
                    SymHead.BOOL_FIELDS,
                    SymHead.INT_FIELDS,
                    SymHead.FLOAT_FIELDS,
                    inp.location,
                )
                if (item.name in {SymHead.MIN_H, SymHead.MIN_W}) and value:
                    if va % 2:
                        raise SymbolError(
                            f"{item.name} must be even. Value "
                            f"is: {va} in symbol: {symbol.get_name()!r}",
                            inp.location,
                        )

                symbol.add_attr(item.name, va)

        # get pins
        previous_pin = None
        previous_cat = ""
        ov_pins = []
        while True:
            new_inp = self.reader.get_nonempty_line()
            if (new_inp.columns == Const.EOT) or new_inp.columns[0]:
                # symbol end or EOT
                if derived_from:
                    overload_pins(symbol, derived_from.pins, ov_pins)
                vpr(f"parse_symbol returns: {symbol!r}", level=Verbosity.VERBOSE)
                return new_inp, symbol
            # (more) pin(s) encountered
            if symbol.is_extension():
                raise SymbolError(
                    f"No pin definition allowed for a Derived symbol: "
                    f"{symbol.get_name()!r}",
                    new_inp.location,
                )
            # get pin
            pin = self.pin_processor.parse_pin(new_inp, previous_pin, previous_cat)
            # handle derived from
            if derived_from:
                ov_pins.append(pin)
            else:
                if pin.is_pseudo_pin():
                    raise PinError(
                        f"Pin Category: {pin.get_cat()!r} is not allowed "
                        f"for base symbols!",
                        new_inp.location,
                    )
                symbol.add_pin(pin)
            # keep previous pin when gap or pseudo-pin is encountered
            if not pin.is_gap() and not pin.is_pseudo_pin():
                previous_pin = pin
            # save previous cat in any case
            previous_cat = pin.get_cat()


def overload_pins(
    symbol: Symbol, base_pins: list[Pin], derived_sym_pins: list[Pin]
) -> None:
    ins_index = None
    current_ovl_pin: Pin = None
    ovl_index = None
    new_pins: list[Pin] = base_pins.copy()

    def clear_index():
        nonlocal ins_index, current_ovl_pin, ovl_index
        ins_index = None
        current_ovl_pin = None
        ovl_index = None

    def get_clear_list(derived_pin: Pin) -> list[int]:
        my_list = []
        idx = 0
        alt_functs = False
        for pn in new_pins:
            if not alt_functs:
                if (
                    derived_pin.get_checked_bus_pin_list()
                    == pn.get_checked_bus_pin_list()
                ):
                    if not pn.is_protected():
                        my_list.append(idx)
                        alt_functs = True
            else:
                if derived_pin.is_alt_func_pin(pn):
                    my_list.append(idx)
                else:
                    alt_functs = False
            idx += 1
        return my_list

    for pin in derived_sym_pins:
        p_num = pin.get_number()
        if pin.is_pseudo_pin():
            category = pin.get_cat()
            if category == PinHead.OVERLOAD:
                clear_index()
            elif category == PinHead.DELETE:
                clear_index()
                del_list = get_clear_list(pin)
                if not del_list:
                    raise PinError(
                        f"Pin number to delete not found! Number: {p_num!r}", pin.loc
                    )
                ins_index = del_list[0]
                del_list.reverse()
                vpr(
                    f"overload_pins(): Delete pins {del_list} Insert marker at {ins_index}",
                    level=Verbosity.VERY_VERB,
                )
                for x in del_list:
                    del new_pins[x]
            elif (category == PinHead.BEFORE) or (category == PinHead.AFTER):
                clear_index()
                p_list = []
                idx = 0
                alt_functs = False
                for pn in new_pins:
                    if not alt_functs:
                        if (
                            pin.get_checked_bus_pin_list()
                            == pn.get_checked_bus_pin_list()
                        ):
                            if not pn.is_protected():
                                p_list.append(idx)
                                alt_functs = True
                    else:
                        if pin.is_alt_func_pin(pn):
                            p_list.append(idx)
                        else:
                            alt_functs = False
                    idx += 1
                if not p_list:
                    raise PinError(
                        f"Pin number to insert not found! Number: {p_num!r}", pin.loc
                    )
                if category == PinHead.BEFORE:
                    ins_index = p_list[0]
                else:
                    ins_index = p_list[-1] + 1
                vpr(
                    f"overload_pins(): Insert marker at {ins_index}",
                    level=Verbosity.VERY_VERB,
                )
            else:
                raise LogicError(f"Invalide overwrite operation: {category!r}", pin.loc)
        else:
            if ins_index is not None:
                vpr(
                    f"overload_pins(): Insert pin {p_num!r} at index {ins_index}",
                    level=Verbosity.VERY_VERB,
                )
                pin.set_protected(True)
                new_pins.insert(ins_index, pin)
                ins_index += 1
            else:
                done = False
                if ovl_index is not None:
                    if current_ovl_pin.is_alt_func_pin(pin):
                        vpr(
                            f"overload_pins(): Overload: insert pin {p_num!r} at index {ovl_index}",
                            level=Verbosity.VERY_VERB,
                        )
                        new_pins.insert(ovl_index, pin)
                        ovl_index += 1
                        done = True
                    else:
                        vpr(
                            f"overload_pins(): Overload: end alt func list. New pin {p_num!r}",
                            level=Verbosity.VERY_VERB,
                        )
                        clear_index()
                if not done:
                    del_list = get_clear_list(pin)
                    if not del_list:
                        raise PinError(
                            f"Pin number to overload not found! Number: {p_num!r}",
                            pin.loc,
                        )
                    ovl_index = del_list[0]
                    current_ovl_pin = pin
                    del_list.reverse()
                    vpr(
                        f"overload_pins(): Overload: delete pins {del_list}",
                        level=Verbosity.VERY_VERB,
                    )
                    for x in del_list:
                        del new_pins[x]
                    vpr(
                        f"overload_pins(): Overload: insert pin {p_num!r} at index {ovl_index}",
                        level=Verbosity.VERY_VERB,
                    )
                    new_pins.insert(ovl_index, pin)
                    ovl_index += 1
    for np in new_pins:
        np.set_protected(False)
    symbol.pins = new_pins


def parse_header(
    head_prop: list[ColumnProp], reader: MyCSVReader, is_first_line: bool
) -> Tuple[list[str], dict[str:int]]:
    """Get one record from csvreader and return valid header list and name-column-dict.

    The headlines are case insensitive and the items are stripped.
    Arguments:
      head_prop -- header property list for the current header
      reader    -- reader object for the current file
      is_first_line -- is it the first line to parse?
    Globals:
      vpr       -- the log printer
    Returns: The header as list (empty entries are preserved) and as
             name-column-dict {name:column}
    Throws: HeaderError, csv.Error, StopIteration
    """
    csv_record = reader.get_record()
    l_record = [item.lower() for item in csv_record.columns]
    vpr(f"parse_header: inp: {csv_record.columns}", level=Verbosity.VERBOSE)
    # fieldset: set of non empty fields
    fieldset = set([item for item in l_record if item])
    vpr(f"field_set: {fieldset}", level=Verbosity.VERBOSE)
    # check the first column
    if is_first_line:
        if not l_record[0]:
            raise HeaderError(
                "Column 0 in the first line header must contain a " "mandatory field!",
                csv_record.location,
            )
    else:
        if l_record[0]:
            raise HeaderError(
                "Column 0 in the second line header must be empty!", csv_record.location
            )
    # check double entries
    for val in fieldset:
        count = l_record.count(val)
        if count > 1:
            raise HeaderError(
                f"Column: {val!r} exists more than once in header:\n"
                f"{csv_record.columns}",
                csv_record.location,
            )
    # check presence of all required fields
    required_header_fields = {
        item.name
        for item in head_prop
        if (item.need == Need.VAL) or (item.need == Need.MAN)
    }
    vpr(f"required_header_fields: {required_header_fields}", level=Verbosity.VERY_VERB)
    if not fieldset >= required_header_fields:
        missing_header_fields = required_header_fields - fieldset
        raise HeaderError(
            f"Headline: {csv_record.columns}\n"
            f"misses required fields: {[item for item in missing_header_fields]}",
            csv_record.location,
        )
    # check presence of surplus fields
    all_header_field_set = {item for item, need in head_prop}
    vpr(f"all_header_field_set: {all_header_field_set}", level=Verbosity.VERY_VERB)
    surplus_header_field_set = fieldset - all_header_field_set
    if surplus_header_field_set:
        raise HeaderError(
            f"Headline: {csv_record.columns}\n"
            f"has surplus fields: {[item for item in surplus_header_field_set]}",
            csv_record.location,
        )
    # build return values
    heading_cols = {}
    for col_index, col_name in enumerate(l_record):
        if col_name:
            heading_cols[col_name] = col_index
    vpr(f"parse_header: return l_record: {l_record}", level=Verbosity.VERBOSE)
    vpr(f"parse_header: return head_cols: {heading_cols}", level=Verbosity.VERBOSE)
    return l_record, heading_cols


def get_half_len(pin_count: int) -> int:
    """Return half len of a pin shape rect
    lgh = (p - 1) / 2 if p is odd
    lgh = P / 2 if p is even
    """
    if pin_count % 2:
        return (pin_count - 1) // 2
    else:
        return pin_count // 2


def center_pins(half_len: int, pin_count: int) -> int:
    """center pins and return start pos for the first pin

    Arguments:
      half_len  -- the half of the length of the edge in pin grid multiples
      pin_count -- the actual pin count of the edge

    The max pin count of the edge is:
        pin_count_max = half_len * 2 + 1
    Start pos is:
        st =  (pin_count_max - pin_count) / 2
    Round up for even pin counts
    """
    res = ((half_len * 2) + 1 - pin_count) // 2
    if not pin_count % 2:
        res += 1
    return res


def build_kicad_pin(
    alt_func_list: list[Pin], posx: float, posy: float, rot: float
) -> kicad.Pin:
    """Build a KiCad Pin object from alt_func_list and return"""
    vpr(f"build_pin: alt_func_list: {alt_func_list}", level=Verbosity.VERY_VERB)
    pin0 = alt_func_list[0]
    loc = pin0.loc
    hidden = pin0.is_hidden()
    pin_len = pin0.get_attr(PinHead.LEN)
    pin_len_mm = kicad.mil_to_mm(pin_len)
    if hidden:
        pin_len = 0
    posx_mm = posx * Const.GRID
    posy_mm = posy * Const.GRID
    pin_len_mm = pin_len * Const.GRID
    # TODO: check valid pin pos
    if rot == 0:
        posx_mm -= pin_len_mm
    elif rot == 180:
        posx_mm += pin_len_mm
    elif rot == 270:
        posy_mm += pin_len_mm
    elif rot == 90:
        posy_mm -= pin_len_mm
    else:
        raise LogicError(f"Wrong rot: {rot} in pin: {pin0}", loc)
    vpr(
        f"build_pin: number: {pin0.get_number()} "
        f"name={pin0.get_name()} posx: {posx} posy: {posy} "
        f"pin_len: {pin_len_mm} rot: {rot}",
        level=Verbosity.VERBOSE,
    )
    new_pin = kicad.Pin(
        number=pin0.get_number(),
        name=pin0.get_name(),
        etype=pin0.get_attr(PinHead.EL_TYPE),
        shape=pin0.get_attr(PinHead.GR_TYPE),
        posx=posx_mm,
        posy=posy_mm,
        length=pin_len_mm,
        rotation=rot,
        is_hidden=hidden,
    )
    number_font_size = pin0.get_attr(PinHead.NUMBER_FONT_SIZE)  # mils
    n_mm = kicad.mil_to_mm(number_font_size)
    new_pin.number_effect.sizex = n_mm
    new_pin.number_effect.sizey = n_mm
    name_font_size = pin0.get_attr(PinHead.NAME_FONT_SIZE)  # mils
    n_mm = kicad.mil_to_mm(name_font_size)
    new_pin.name_effect.sizex = n_mm
    new_pin.name_effect.sizey = n_mm
    # append alternative functions
    i = 1
    while i < len(alt_func_list):
        new_alt_func = kicad.AltFunction(
            name=alt_func_list[i].get_name(),
            etype=alt_func_list[i].get_attr(PinHead.EL_TYPE),
            shape=alt_func_list[i].get_attr(PinHead.GR_TYPE),
        )
        new_pin.altfuncs.append(new_alt_func)
        i += 1
    return new_pin


@dataclass
class KicadLibWrapper:
    """A wrapper for the KiCad lib"""

    libname: str
    lib: kicad.KicadLibrary = field(init=False)

    def __post_init__(self):
        self.lib = kicad.KicadLibrary(self.get_filename())

    def get_filename(self) -> str:
        return self.libname + ".kicad_sym"

    def add_symbol(self, sym: kicad.KicadSymbol) -> None:
        self.lib.symbols.append(sym)

    def generate(self) -> None:
        self.lib.write()


vpr = None


def main():
    """Parse csv input files and produce one kicat symbolfile"""
    arguments = parse_arguments()
    global vpr
    vpr = verbose_print_fact(arguments.verbose, arguments.silent)
    vpr(f"arguments: {arguments}", level=Verbosity.VERBOSE)

    inp_file_errors = 0
    inp_files_processed = 0
    all_failures = 0
    all_skipped_pins = 0
    all_symbols: dict[str, Symbol] = {}

    # the libname of the file and the library object needs to be the same
    if isinstance(arguments.output, str):
        libname = arguments.output
    else:
        libname = arguments.output[0]
    kicad_lib = KicadLibWrapper(libname)
    vpr(f"Create kicad_lib: {kicad_lib.get_filename()}")

    for inputfile in arguments.inputfiles:
        inp_files_processed += 1
        try:
            vpr(f"Open: {inputfile!r}")
            with open(inputfile, mode="rt", newline="") as csvfile:
                reader = MyCSVReader(
                    inputfile, csvfile, dialect=arguments.csv_dialect[0], strict=True
                )

                sym_proc = SymbolProcessor(reader)

                csv_rec = CSVRecord(None, reader.get_location())
                skipped_pins = 0
                failures = 0
                symbol_count = 0
                while (csv_rec.columns is None) or (csv_rec.columns != Const.EOT):
                    new_csv_rec = None
                    try:
                        if csv_rec.columns is None:
                            csv_rec = reader.get_nonempty_line()
                        # skip pin lines
                        while (csv_rec.columns != Const.EOT) and (
                            not csv_rec.columns[0]
                        ):
                            skipped_pins += 1
                            csv_rec = reader.get_nonempty_line()
                            vpr(
                                f"main loop skip line inp: {csv_rec.columns}",
                                level=Verbosity.VERY_VERB,
                            )
                        new_csv_rec, symbol = sym_proc.parse_symbol(
                            csv_rec, all_symbols
                        )
                        if symbol:
                            if symbol.get_name() in all_symbols:
                                raise SymbolError(
                                    f"Symbol with name {symbol.get_name()!r} already exists!",
                                    symbol.loc,
                                )
                            kicad_symbol = symbol.build_symbol(
                                kicad_lib.get_filename(), kicad_lib.lib
                            )
                            all_symbols[symbol.get_name()] = symbol
                            kicad_lib.add_symbol(kicad_symbol)
                            symbol_count += 1
                    except (PinError, SymbolError, ValidationError) as error:
                        failures += 1
                        print(error.__class__.__name__, error, file=sys.stderr)
                        if new_csv_rec is None:
                            new_csv_rec = CSVRecord(None, reader.get_location())
                    if new_csv_rec is None:
                        raise LogicError("main: new_csv_rec is None!", csv_rec.location)
                    csv_rec = new_csv_rec

                vpr(
                    f"End file: {inputfile!r} ",
                    f"{symbol_count} symbol(s) generated. "
                    f"{failures} failure(s) occurred. "
                    f"{csv_rec.location.line} line(s) processed. ",
                    f"{csv_rec.location.record} record(s) processed. "
                    f"{reader.skipped_empty} empty/comment record(s) skipped. "
                    f"{skipped_pins} pin record(s) skipped.",
                )
                all_failures += failures
                all_skipped_pins += skipped_pins

        except StopIteration:
            inp_file_errors += 1
            print(
                "StopIteration: Premature file end! ",
                reader.get_location(),
                file=sys.stderr,
            )
        except csv.Error as error:
            inp_file_errors += 1
            print("csv.Error ", error, reader.get_location(), file=sys.stderr)
        except (FileNotFoundError, HeaderError) as error:
            inp_file_errors += 1
            print(error.__class__.__name__, error, file=sys.stderr)

    # generate output lib
    vpr(f"Write to kicad_lib: {kicad_lib.get_filename()}")
    kicad_lib.generate()

    if not inp_file_errors and not all_skipped_pins and not all_failures:
        vpr(
            f"Success all done. {inp_files_processed} input file(s) processed.\n"
            f"{len(all_symbols)} symbols in library "
            f"{kicad_lib.get_filename()} generated."
        )
        vpr(f"Symbols: {list(all_symbols.keys())}", level=Verbosity.VERBOSE)
        exit(0)
    else:
        print(
            f"Errors occured! {inp_files_processed} input file(s) processed.\n"
            f"{inp_file_errors} input file(s) failed! Skipped pins: {all_skipped_pins} "
            f"Failures: {all_failures}",
            file=sys.stderr,
        )
        vpr(
            f"{len(all_symbols)} symbols in library "
            f"{kicad_lib.get_filename()} generated."
        )
        vpr(f"Symbols: {list(all_symbols.keys())}", level=Verbosity.VERBOSE)
        exit(3)


EPILOG = """
Return values:
0 - Success
1 - Severe error occurred.
2 - Wrong or missing arguments.
3 - Library generated but some failures occurred
"""


def parse_arguments():
    """Parse command line arguments an return command line argument class."""
    # get the list of available csv dialects and get the default dialect
    csv_dialects_available = csv.list_dialects()
    csv_dialect_default = None
    csv_dialect_required = True
    if "unix" in csv_dialects_available:
        csv_dialect_default = "unix"
        csv_dialect_required = False

    parser = argparse.ArgumentParser(
        description="Generate a kicat symbol library from csv-files.", epilog=EPILOG
    )
    parser.add_argument(
        "--output",
        "-o",
        nargs=1,
        default="a",
        metavar="FILE",
        help="Set output libname. The output filename is libname.kicad_sym. (Default: a)",
    )
    # With nargs=1 a list of len 1 is returned. The default is returned as is.
    parser.add_argument(
        "--csv_dialect",
        "-d",
        nargs=1,
        choices=csv_dialects_available,
        default=[csv_dialect_default],
        required=csv_dialect_required,
        help=f"The dialect to be used from the csv reader. See option --csv_info."
        f" Default: {csv_dialect_default}",
    )
    parser.add_argument(
        "--csv_info",
        "-c",
        nargs=0,
        action=DialectInfoAction,
        help="Print csv-parser dialect information.",
    )
    parser.add_argument(
        "--info", "-i", nargs=0, action=MoreInfoAction, help="Print more information."
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s v{__version__}"
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="count",
        default=1,
        help="Verbose output of debug information. Repeat argument for "
        "very verbose output.",
    )
    parser.add_argument(
        "--silent",
        "-s",
        action="store_true",
        help="Silent mode. Forces verbosity level to zero.",
    )
    parser.add_argument(
        "inputfiles",
        nargs="+",
        metavar="INPUTFILE",
        help="Input file with element definitions in csv format.",
    )

    return parser.parse_args()


class MoreInfoAction(argparse.Action):
    """The argparse action class to print more information."""

    def __init__(self, option_strings, dest, nargs=None, **kwargs):
        if nargs != 0:
            raise ValueError(f"nargs={nargs} not allowed")
        super().__init__(option_strings, dest, nargs, **kwargs)

    def __call__(self, parser, namespace, values, option_string=None):
        """Print available more info and exit(0)."""
        setattr(namespace, self.dest, True)
        print(Const.more_doc())
        print(SymHead.more_doc())
        print(PinHead.more_doc())
        exit(0)


class DialectInfoAction(argparse.Action):
    """The argparse action class to print the csv dialect information."""

    def __init__(self, option_strings, dest, nargs=None, **kwargs):
        if nargs != 0:
            raise ValueError(f"nargs={nargs} not allowed")
        super().__init__(option_strings, dest, nargs, **kwargs)

    def __call__(self, parser, namespace, values, option_string=None):
        """Print available csv parser dialect info and exit(0)."""
        setattr(namespace, self.dest, True)
        info_dialects()
        exit(0)


def info_dialects():
    """Print info about the available csv reader dialect."""
    QUOTE_CONST_LIST = {}
    for item in csv.__dict__.keys():
        if item.startswith("QUOTE_"):
            i = csv.__dict__[item]
            QUOTE_CONST_LIST[i] = item

    dialects = csv.list_dialects()
    print(f"Supported csv dialects: {dialects!s}", end="\n\n")

    for dialect in dialects:
        print(f"dialect:          {dialect}")
        di = csv.get_dialect(dialect)
        print(f"delimiter:        {di.delimiter!r}")
        print(f"doublequote:      {di.doublequote}")
        print(f"escapechar:       {di.escapechar!r}")
        print(f"lineterminator:   {di.lineterminator!r}")
        print(f"quotechar:        {di.quotechar!r}")
        print(f"quoting:          {QUOTE_CONST_LIST[di.quoting]}={di.quoting}")
        print(f"skipinitialspace: {di.skipinitialspace}")
        print(f"strict:           {di.strict}", end="\n\n")


class Verbosity(Enum):
    """Verbosity of the output during runtime."""

    SILENT = 0
    NORMAL = 1
    VERBOSE = 2
    VERY_VERB = 3


def verbose_print_fact(verbosity: int, silent: bool):
    """Produce closure for verbose printing and return it."""
    if silent:
        vb = Verbosity.SILENT
    else:
        try:
            vb = Verbosity(verbosity)
        except ValueError:
            print(
                f"Verbosity level: {verbosity} is not allowed!\n" f"Valid levels:\n",
                file=sys.stderr,
            )
            for e in Verbosity:
                print(f"{e.value} - {e.name}", file=sys.stderr)
            exit(2)

    def verbose_print(*args, level: Verbosity = Verbosity.NORMAL):
        """Print args for messages with appropriate level."""
        if level.value <= vb.value:
            print(*args)

    verbose_print(vb, level=Verbosity.VERBOSE)
    return verbose_print


if __name__ == "__main__":
    main()
