from __future__ import unicode_literals
from __future__ import print_function

from ..compat import implements_to_string, text_type, string_types, implements_bool

from operator import truth


@implements_bool
@implements_to_string
class ParseResult(object):
    """An immutable list like object that stores the results of a parsed index"""
    def __init__(self, tokens, from_root):
        self.tokens = tokens
        self.from_root = from_root
        self.index = None

    def __str__(self):
        if self.index is None:
            if self.from_root:
                self.index = '.' + build(self.tokens)
            else:
                self.index = build(self.tokens)
        return self.index

    def __repr__(self):
        return "ParseResult(%r)" % (text_type(self))

    @property
    def top_tail(self):
        return self.tokens[0], self.tokens[1:]

    def __moyarepr__(self, context):
        return text_type(self)

    def get(self, index, default=None):
        return self.tokens.get(index, default)

    def as_list(self):
        return self.tokens[:]

    def __iter__(self):
        return iter(self.tokens)

    def __len__(self):
        return len(self.tokens)

    def __getitem__(self, i):
        return self.tokens[i]

    def __eq__(self, other):
        return self.tokens == other

    def __ne__(self, other):
        return self.tokens != other

    def __bool__(self):
        return truth(self.tokens)


def parse(s, parse_cache={}):
    """Parse a string containing a dotted notation data index in to a list of indices"""
    if isinstance(s, ParseResult):
        return s
    cached_result = parse_cache.get(s, None)
    if cached_result is not None:
        return cached_result
    from_root = s.startswith('.')
    iter_chars = iter(s)
    tokens = []     # Token accumulator
    token = []      # Current token
    append_token = tokens.append
    append_char = token.append

    def pop():
        c = next(iter_chars, None)
        if c is None:
            return None, None
        if c == '\\':
            c = next(iter_chars, None)
            if c is None:
                return None, None
            return True, c
        if c == '.':
            return True, None
        else:
            return False, c

    def pop2():
        c = next(iter_chars, None)
        if c is None:
            return None, None
        return False, c

    def asint(s):
        return int(s) if s.isdigit() else s

    join = ''.join

    while 1:
        literal, c = pop()
        if literal is None:
            break
        if c is None:
            continue
        if not literal and c == '"':
            while 1:
                literal, c = pop2()
                if c is None:
                    break
                elif not literal and c == '"':
                    append_token(join(token))
                    del token[:]
                    break
                else:
                    append_char(c)
        else:
            append_char(c)
            while 1:
                literal, c = pop()
                if c is None:
                    append_token(asint(join(token)))
                    del token[:]
                    break
                else:
                    append_char(c)
    if token:
        append_token(asint(join(token)))
    tokens = ParseResult(tokens, from_root)
    parse_cache[s] = tokens
    return tokens


def build(indices, absolute=False):
    """Combines a sequence of indices in to a data index string"""
    if isinstance(indices, string_types):
        return indices

    def escape(s):
        if isinstance(s, string_types):
            if ' ' in s or '.' in s:
                s = '"%s"' % s.replace('"', '\\"')
            return s
        else:
            return text_type(s)
    if absolute:
        return '.' + '.'.join(escape(s) for s in indices)
    else:
        return '.'.join(escape(s) for s in indices)


def is_from_root(indices):
    """Test a string index is from the root"""
    # Mainly here for self documentation purposes
    if hasattr(indices, 'from_root'):
        return indices.from_root
    return indices.startswith('.')


def normalise(s):
    """Normalizes a data index"""
    return build(parse(s))
normalize = normalise  # For Americans


def iter_index(index):
    index_accumulator = []
    push = index_accumulator.append
    join = '.'.join
    for name in parse(index):
        push(name)
        yield name, join(text_type(s) for s in index_accumulator)


def join(*indices):
    """Joins 2 or more inidices in to one"""
    absolute = False
    joined = []
    append = joined.append
    for index in indices:
        if isinstance(index, string_types):
            if index.startswith('.'):
                absolute = True
                del joined[:]
                append(parse(index[1:]))
            else:
                append(parse(index))
        else:
            if getattr(index, 'from_root', False):
                absolute = True
                del joined[:]
            append(index)
    new_indices = []
    for index in joined:
        new_indices.extend(index)
    return build(new_indices, absolute)
indexjoin = join


def makeindex(*subindices):
    """Make an index from sub indexes"""
    return '.'.join(text_type(i) for i in subindices)


def join_parsed(*indices):
    absolute = False
    joined = []
    append = joined.append
    for index in indices:
        if isinstance(index, string_types):
            if index.startswith('.'):
                absolute = True
                del joined[:]
                append(parse(index[1:]))
            else:
                append(parse(index))
        else:
            if getattr(index, 'from_root', False):
                absolute = True
                del joined[:]
            append(index)
    new_indices = []
    for index in joined:
        new_indices.extend(index)
    return ParseResult(new_indices, absolute)


def make_absolute(index):
    """Make an index absolute (preceded by a '.')"""
    if not isinstance(index, string_types):
        index = build(index)
    return '.' + text_type(index).lstrip('.')


if __name__ == "__main__":
    test = 'foo.1.2."3"."sdsd.sdsd".1:2.1:.2:.file\.txt.3'
    print(test)
    print(parse(test))
    print(normalize(test))
    print(parse(normalize(test)))
    print(join('call', 'param1', ('a', 'b', 'c')))

    print(join(["callstack", 1], 'foo'))
