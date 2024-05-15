#!/usr/bin/env bash

rm -f samples.kicad_sym

./csv_to_kicad.py -o samples samples/simple_symbols.csv samples/alternative_pin_functions.csv samples/bus.csv samples/derived_symbols.csv
