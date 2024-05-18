#!/usr/bin/env bash

rm -f samples.kicad_sym

./csv_to_kicad.py -o samples samples/*.csv
