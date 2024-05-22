# KiCadSymbolUtil

A utility to generate a KiCad symbol library from a csv file.

This utility generates KiCad symbol libraries from symbol descriptions in CSV files.
The CSV files contain information about all the symbol attributes you need and all
the pin properties.

The script checks the validity of the input values, determines the required symbol
size, and outputs the KiCad library. The script supports the creation of symbols
with one functional unit.

## Requirements

This script requires python 3.

This utility requires the module kicad_sym
from the KiCad Library utilities with some corrections.
Thus clone:
[kicad-library-utils](https://gitlab.com/joergboe/kicad-library-utils.git)
Clone this repository and adapt the PYTHONPATH environment accordingly or adapt
an use the script *set_python_path.sh*
The required module is in path *kicad-library-utils/common*

## Usage

    csv_to_kicad.py --help
or

    python3 csv_to_kicad.py -h

prints the usual help.

    csv_to_kicad.py --info
or

    python3 csv_to_kicad.py -i

prints more information including a complete description of the csv file format.

## Samples

The directory *samples* contains samples of basic symbols and a comprehensive library of the classic Z80 microprocessor family.