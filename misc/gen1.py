#!/usr/bin/env python3

import sys
import os

from kicad_sym import Circle, KicadLibrary, KicadSymbol, Pin, Rectangle, Property

grid = 2.54     # 100 mills
w_padding = 1
h_padding = 1
pin_length = 1
font_w = 0.5 * grid
font_h = 0.5 * grid
text_offset = 0.5
#body_line_width = 0.1 * grid
#pin_offset = 1   # 100 mils

# the libname of the file and the symbol needs to be the same
libname = "A_New_Lib_Genrated"
print(f'Generate lib {libname}')
lib = KicadLibrary(libname + ".kicad_sym")


left_list = [('in1', '1'), '~', ('in2', '2')]
right_list = [('o1', '4'), ('o2', '5')]
vertical_max_pins = max(len(left_list), len(right_list))
vertical_pins_even = False
if (vertical_max_pins % 2) == 0:
    vertical_pins_even = True
h_pin_rec = vertical_max_pins // 2
if vertical_pins_even:
    h_pin_rec += 1
main_rect_h = h_pin_rec + h_padding
main_rect_w = w_padding

partname = "a_new_part"
print(f'Generate part {partname}')
new_symbol = KicadSymbol(partname, libname, libname)

# properties
new_symbol.add_default_properties()
ref = new_symbol.get_property("Reference")
ref.posy = (main_rect_h + text_offset) * grid

val = new_symbol.get_property("Value")
val.posy = (main_rect_h + text_offset) * grid * -1

datas = new_symbol.get_property("Datasheet")
datas.value = "https://example.com"

ki_kws = new_symbol.get_property("ki_keywords")
ki_kws.value = "gate cpu mcu"

desc = new_symbol.get_property("Description")
desc.value = "A description of a_new_part."

new_symbol.rectangles.append(
    Rectangle(
        main_rect_w * grid * -1, main_rect_h * grid * -1,
        main_rect_w * grid, main_rect_h * grid))

pin_length_mm = pin_length * grid
px = (main_rect_w + pin_length) * grid * -1
py = 0 - h_pin_rec
if vertical_pins_even:
    py += 1
for lpin in left_list:
    if lpin != '~':
        new_symbol.pins.append(
            Pin(
                number=lpin[1], name=lpin[0], etype="passive",
                posx=px, posy=(py * grid), length=pin_length_mm, rotation=0))
    py += 1

px = (main_rect_w + pin_length) * grid
py = 0 - h_pin_rec
if vertical_pins_even:
    py += 1
for lpin in right_list:
    if lpin != '~':
        new_symbol.pins.append(
            Pin(
                number=lpin[1], name=lpin[0], etype="passive",
                posx=px, posy=(py * grid), length=pin_length_mm, rotation=180))
    py += 1

lib.symbols.append(new_symbol)
print("Lib \n")
print(lib.get_sexpr())

print(f'Write lib {libname}')
lib.write()
