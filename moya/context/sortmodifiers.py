"""Hacked up script to sort modifiers"""
# Couldn't find a tool for this

"""
import io
with io.open('modifiers.py', 'rt') as f:

    iter_lines = iter(f)

    while 1:
        line = next(iter_lines, None)
        if line.startswith('class ExpressionModifiers('):
            break

    defs = []
    while 1:
        line = next(iter_lines, None)
        if line is None:
            break
        if line.lstrip().startswith('def'):
            defs.append([])
        if defs:
            defs[-1].append(line)

    for d in sorted(defs, key=lambda m: m[0]):
        print ''.join(d),
"""
