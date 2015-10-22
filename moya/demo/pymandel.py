"""This is a raw python version of mandel.xml

The purpose of this code is to provide a speed comparison against moya code.

"""
from __future__ import print_function
from __future__ import division

import sys

PY2 = sys.version_info[0] == 2

if not PY2:
    xrange = range


def mandel(xsize=80, ysize=20, max_iteration=50):
    chars = " .,~:;+*%@##"
    for pixy in xrange(ysize):
        y0 = (pixy / ysize) * 2 - 1
        row = ""
        for pixx in xrange(xsize):
            x0 = (pixx / xsize) * 3 - 2
            x = 0
            y = 0
            iteration = 0
            while (x * x + y * y < 4) and iteration < max_iteration:
                xtemp = x * x - y * y + x0
                y = 2 * x * y + y0
                x = xtemp
                iteration += 1
            row += chars[iteration % 10]
        print(row)

if __name__ == "__main__":
    from moya.tools import timer
    with timer("Calculate mandelbrot set in raw python"):
        mandel()
