from __future__ import unicode_literals
from __future__ import print_function
from __future__ import absolute_import

import re
import weakref
from threading import local, Thread

from ..compat import implements_to_string, text_type, string_types, number_types
from . import dataindex
from .dataindex import parse, join, join_parsed, is_from_root
from .expression import Expression
from .errors import ContextKeyError, SubstitutionError
from .missing import Missing
from .tools import to_expression
from ..tools import lazystr
from ..moyaexceptions import MoyaException


@implements_to_string
class DynamicContextItem(object):
    """A proxy for a dynamic item"""

    def __init__(self, callable, *args, **kwargs):
        self.callable = callable
        self.args = args
        self.kwargs = kwargs
        super(DynamicContextItem, self).__init__()

    def __moyacontext__(self, context):
        return self.callable(context, *self.args, **self.kwargs)

    @property
    def obj(self):
        from moya import pilot
        return self.__moyacontext__(pilot.context)

    def __str__(self):
        return text_type(self.obj)

    def __repr__(self):
        return repr(self.obj)

    def __moyarepr__(self, context):
        return to_expression(context, self.obj)


class CounterContextItem(object):
    def __init__(self, start):
        self.value = start

    def __moyacontext__(self, context):
        ret = self.value
        self.value += 1
        return ret

    def __repr__(self):
        return text_type(self.value)

    def __moyarepr(self, context):
        return to_expression(context, self.value)


@implements_to_string
class LazyContextItem(object):
    """A proxy for a lazily evaluated object"""
    def __init__(self, callable, *args, **kwargs):
        self.callable = callable
        self.args = args
        self.kwargs = kwargs
        self.called = False
        self.result = None
        super(LazyContextItem, self).__init__()

    def __moyacontext__(self, context):
        if not self.called:
            self.result = self.callable(*self.args, **self.kwargs)
            self.called = True
        return self.result

    @property
    def obj(self):
        return self.__moyacontext__(None)

    def __str__(self):
        return text_type(self.obj)

    def __repr__(self):
        return repr(self.obj)

    def __moyarepr__(self, context):
        return to_expression(context, self.obj)


@implements_to_string
class AsyncContextItem(Thread):
    """A proxy for an asynchronously evaluated object"""
    def __init__(self, callable, *args, **kwargs):
        self.callable = callable
        self.args = args
        self.kwargs = kwargs
        self._obj = None
        super(AsyncContextItem, self).__init__()
        self.start()

    def will_block(self):
        """Check if accessing this object will block"""
        return self.is_alive()

    def run(self):
        self._obj = self.callable(*self.args, **self.kwargs)

    def __moyacontext__(self, context):
        self.join()
        return self._obj

    @property
    def obj(self):
        return self.__moyacontext__(None)

    def __str__(self):
        return text_type(self._obj)

    def __repr__(self):
        return repr(self._obj)

    def __moyarepr__(self, context):
        return to_expression(context, self._obj)


@implements_to_string
class _ThreadLocalItem(object):
    """A proxy for a thread local object"""
    def __init__(self, callable, *args, **kwargs):
        self.callable = callable
        self.args = args
        self.kwargs = kwargs
        self.local = local()

    def __moyacontext__(self, context):
        obj = getattr(self.local, 'obj', None)
        if not obj:
            obj = self.callable(*self.args, **self.kwargs)
            setattr(self.local, 'obj', obj)
        return obj

    @property
    def obj(self):
        return self.__moyacontext__(None)

    def __str__(self):
        return text_type(self.obj)

    def __repr__(self):
        return repr(self.obj)

    def __moyarepr__(self, context):
        return to_expression(context, self.obj)


class LinkItem(object):
    """Links on index to another, like a symbolic link"""
    def __init__(self, proxy_index):
        self.proxy_index = dataindex.parse(proxy_index)

    def __repr__(self):
        return "<link %s>" % self.proxy_index

    def __moyacontext__(self, context):
        return context[self.proxy_index]


class LastIndexItem(object):
    """Returns the last item of a sequence"""
    def __init__(self, sequence_index, name):
        self.sequence_index = dataindex.parse(sequence_index)
        self.name = name

    def __moyacontext__(self, context):
        if self.sequence_index in context:
            return context[self.sequence_index][-1]
        return None


@implements_to_string
class Scope(object):
    def __init__(self, stack, index, obj=None):
        self.stack = stack
        if obj is None:
            obj = self.stack.context.get(index)
            self.index = index
            self.obj = obj
        else:
            self.index = index
            self.obj = obj

    def __repr__(self):
        return "<Scope %s>" % self.index

    def __str__(self):
        return self.index


class Frame(object):
    def __init__(self, stack, index, obj=None):
        self.index = index
        self.stack = stack
        self.scopes = [Scope(stack, index, obj)]
        self._push = self.scopes.append
        self._pop = self.scopes.pop
        self._update()

    def _update(self):
        self.last_scope = self.scopes[-1]
        self.first_scope = self.scopes[0]

    def copy(self):
        frame = Frame.__new__(Frame)
        frame.index = self.index
        frame.stack = self.stack
        frame.scopes = self.scopes[:]
        frame._push = self.scopes.append
        frame._pop = self.scopes.pop
        frame._update()
        return frame

    def push_scope(self, index):
        self._push(Scope(self.stack, index))
        self._update()

    def pop_scope(self):
        self._pop()
        self._update()

    def __iter__(self):
        return reversed(self.scopes)

    def __len__(self):
        return len(self.scopes)

    def __repr__(self):
        return '<frame "%s">' % self.index


class Stack(object):
    def __init__(self, context, root_obj):
        self._context = weakref.ref(context)
        self.frames = [Frame(self, '.', root_obj)]
        self._push = self.frames.append
        self._pop = self.frames.pop
        self._current_frame = self.frames[-1]

    @property
    def context(self):
        return self._context()

    def push_frame(self, index_or_frame):
        if isinstance(index_or_frame, Frame):
            self._push(index_or_frame)
        else:
            self._push(Frame(self, parse(index_or_frame)))
        self._current_frame = self.frames[-1]

    def pop_frame(self):
        self._pop()
        self._current_frame = self.frames[-1]

    def clone_frame(self):
        return self._current_frame.copy()

    def reset(self):
        del self.frames[1:]
        self._current_frame = None

    @property
    def index(self):
        """Index of most recent scope"""
        return self._current_frame.last_scope.index

    @property
    def index_set(self):
        """Index of first scope"""
        return self._current_frame.first_scope.index

    @property
    def obj(self):
        """Most recent scope"""
        return self._current_frame.last_scope.obj

    @property
    def obj_set(self):
        """First scope in frame"""
        return self._current_frame.first_scope.obj

    @property
    def scope(self):
        return self._current_frame.last_scope

    @property
    def frame(self):
        return self._current_frame


@implements_to_string
class _FrameContext(object):
    def __init__(self, context, *index):
        self.context = context
        self.index = join_parsed(*index)

    def __enter__(self):
        self.context.push_frame(self.index)

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.context.pop_frame()

    def __str__(self):
        return self.index


class _ScopeContext(object):
    def __init__(self, context, *index):
        self.context = context
        self.index = join_parsed(*index)

    def __enter__(self):
        self.context.push_scope(self.index)

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.context.pop_scope()


class _TempScopeContext(_ScopeContext):
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.context.pop_scope()
        self.context.safe_delete(self.index)


class _DataScopeContext(object):
    def __init__(self, context, data):
        self.context = context
        self.data = data

    def __enter__(self):
        scope_index = self.context.push_thread_local_stack('datascope', self.data)
        self.context.push_scope(scope_index)

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.context.pop_scope()
        self.context.pop_stack('datascope')


class _DataFrameContext(object):
    def __init__(self, context, data):
        self.context = context
        self.data = data

    def __enter__(self):
        scope_index = self.context.push_thread_local_stack('dataframe', self.data)
        self.context.push_frame(scope_index)

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.context.pop_frame()
        self.context.pop_stack('dataframe')


class _StackContext(object):
    """This is a context manager for client stacks on the context"""
    def __init__(self, context, stack_name, value, stack_callable=list):
        self.context = context
        self.stack_name = stack_name
        self.value = value
        self.stack_callable = stack_callable

    def __enter__(self):
        index = self.context.push_stack(self.stack_name,
                                        self.value,
                                        stack_callable=self.stack_callable)
        self.context.push_frame(index)
        return index

    def __exit__(self, exc_type, exc_value, exc_tb):
        self.context.pop_frame()
        self.context.pop_stack(self.stack_name)


class _RootStackContext(object):
    def __init__(self, context, stack_name, value, stack_callable=list):
        self.context = context
        self.stack_name = stack_name
        self.value = value
        self.stack_callable = stack_callable

    def __enter__(self):
        stack = self.context.set_new_call('._{}_stack'.format(self.stack_name), list)
        stack.append(self.value)
        self.context['.' + self.stack_name] = self.value

    def __exit__(self, exc_type, exc_value, exc_tb):
        stack = self.context['._{}_stack'.format(self.stack_name)]
        stack.pop()
        try:
            self.context['.' + self.stack_name] = stack[-1]
        except IndexError:
            del self.context['.' + self.stack_name]


class DummyLock(object):
    """Replacement for real lock that does nothing"""
    def __enter__(self):
        pass

    def __exit__(self, *args, **kwargs):
        pass


def _get_key(obj, key):
    getitem = getattr(obj, "__getitem__")
    if getitem is not None:
        try:
            return getitem(key)
        except (TypeError, KeyError, IndexError):
            return Ellipsis
    else:
        return getattr(obj, key, Ellipsis)


def synchronize(f):
    f._synchronize = True
    return f


class _DummyLocal(object):
    def __init__(self, stack):
        self.stack = stack


@implements_to_string
class Context(object):
    """A meta data structure for indexing nested Python objects"""

    _re_substitute_context = re.compile(r'\$\{(.*?)\}')
    _sub = _re_substitute_context.sub

    def __init__(self, root=None, thread_safe=False, re_sub=None, name=None):
        if root is None:
            self.root = {}
        else:
            self.root = root
        self.lock = None
        if re_sub is not None:
            self._sub = re.compile(re_sub).sub
        self._stack = Stack(self, self.root)

        self.thread_safe = False
        if thread_safe:
            self._make_thread_safe()
        self.name = name

    def _make_thread_safe(self):
        if self.thread_safe:
            return
        for method_name in dir(self):
            method = getattr(self, method_name)
            if getattr(method, '_synchronize', False):
                def make_sync(context, method):
                    def _sync(*args, **kwargs):
                        with context.lock:
                            return method(*args, **kwargs)
                    return _sync
                setattr(self, method_name, make_sync(self, method))
        self.thread_safe = True

    @classmethod
    def escape(cls, v):
        return v.replace('.', '\\.')

    def __repr__(self):
        if self.name:
            return "<context '{}'>".format(self.name)
        else:
            return "<context>"

    def __str__(self):
        if self.name:
            return "<context '{}'>".format(self.name)
        else:
            return "<context>"

    def to_expr(self, obj, max_size=200):
        """Convert an object to a context expression, if possible"""
        return lazystr(to_expression, self, obj, max_size=max_size)

    @property
    def obj(self):
        return self._stack.obj

    def capture_scope(self):
        """Get an object that contains the data in the scope"""
        obj = {}
        for scope in reversed(self.current_frame.scopes):
            scope_obj = scope.obj
            if hasattr(scope_obj, '__getitem__') and hasattr(scope_obj, 'items'):
                for k, v in scope_obj.items():
                    if k not in obj:
                        obj[k] = v
            else:
                return scope_obj
        return obj

    @synchronize
    def clone(self):
        """Creates a context with a shallow copy of the data"""
        return Context(self.root.copy(),
                       thread_safe=self.thread_safe)

    @synchronize
    def reset(self):
        """Reset stack"""
        self._stack = Stack(self, self.root)

    def substitute(self, s, process=text_type):
        get_eval = Expression.get_eval

        def sub(match):
            try:
                return process(get_eval(match.group(1), self))
            except MoyaException:
                raise
            except Exception as e:
                start, end = match.span(1)
                raise SubstitutionError(match.group(1),
                                        start,
                                        end,
                                        original=e)

        return self._sub(sub, s)

    sub = substitute

    @classmethod
    def extract_expressions(cls, s):
        """Extract all expressions in substitution syntax"""
        expressions = set(match.group(1)
                          for match in cls._re_substitute_context.finditer(s))
        return expressions

    def push_frame(self, index):
        """Push an index frame, so all relative indices will reference data under this index."""
        stack = self._stack
        if isinstance(index, Frame):
            stack.push_frame(index)
        else:
            stack.push_frame(join_parsed(stack.index_set, index))

    def pop_frame(self):
        """Pop an index frame from the stack"""
        self._stack.pop_frame()

    def frame(self, *index):
        """Context manager to push/pop index frames"""
        return _FrameContext(self, *index)

    @property
    def current_frame(self):
        return self._stack._current_frame

    def _get_obj(self, index):
        index = parse(index)
        if is_from_root(index):
            return self.root, index
        return self._stack.obj, index

    def _get_scope(self, index):
        index = parse(index)
        if is_from_root(index):
            return [self.root], index
        return [scope.obj for scope in self._stack.frame], index

    def push_scope(self, index):
        stack = self._stack
        stack.frame.push_scope(join_parsed(stack.index, index))

    def pop_scope(self):
        self._stack.frame.pop_scope()

    def scope(self, *index):
        """Returns a context manager for a scope"""
        return _ScopeContext(self, *index)

    def temp_scope(self, index):
        """Returns a context manager for a temporary scope (deletes scope index on exit)"""
        return _TempScopeContext(self, index)

    def get_frame(self):
        """Get the current frame"""
        return text_type(self._stack.index)

    def data_scope(self, data=dict):
        """Make a context manager to create a scope from arbitrary mapping"""
        if callable(data):
            data = data()
        return _DataScopeContext(self, data)

    def data_frame(self, data):
        """Make a context manager to create a frame from arbitrary mapping"""
        return _DataFrameContext(self, data)

    def _set_lookup(self, index, _parse=parse):
        indices = _parse(index)
        if indices.from_root:
            obj = self.root
        else:
            obj = self._stack.obj
        try:
            final = indices.tokens[-1]
        except IndexError:
            raise
            raise ContextKeyError(self, index, message="Can't set root!")
        try:
            for name in indices.tokens[:-1]:
                obj = (getattr(obj, '__getitem__', None) or getattr(obj, '__getattribute__'))(name)
                __moyacontext__ = getattr(obj, '__moyacontext__', None)
                if __moyacontext__:
                    obj = __moyacontext__(self)
        except (KeyError, IndexError, AttributeError):
            raise ContextKeyError(self, index)

        return obj, final

    def update(self, map):
        """Update current scope with key/values from a mapping object"""
        for k, v in map.items():
            self[k] = v

    def update_base(self, map):
        """Update the base (first) scope"""
        obj = self.current_frame.scopes[0].obj
        for k, v in map.items():
            obj[k] = v

    @synchronize
    def set(self, index, value):
        """Set a value"""
        obj, final = self._set_lookup(index)
        try:
            (getattr(obj, '__setitem__', None) or getattr(obj, '__setattr__'))(final, value)
        except Exception:
            raise ContextKeyError(self, index)

    @synchronize
    def set_simple(self, index, value):
        """Set a single index"""
        obj = self._stack.obj
        try:
            (getattr(obj, '__setitem__', None) or getattr(obj, '__setattr__'))(index, value)
        except Exception:
            raise ContextKeyError(self, index)

    @synchronize
    def set_multiple(self, seq):
        """Set many index / value pairs"""
        _lookup = self._set_lookup
        for index, value in seq:
            obj, final = _lookup(index)
            try:
                (getattr(obj, '__setitem__', None) or getattr(obj, '__setattr__'))(final, value)
            except Exception:
                raise ContextKeyError(self, index)

    @synchronize
    def set_new(self, index, value):
        """Set a value if the index does not exist"""
        if index not in self:
            self[index] = value
            return value
        else:
            return self[index]

    @synchronize
    def set_new_call(self, index, value_callable):
        """Set a value from a callable if it does not exist"""
        if index not in self:
            self[index] = value = value_callable()
            return value
        return self[index]

    def set_dynamic(self, index, callable, *args, **kwargs):
        """Set a dynamic item (updates when references)"""
        self.set(index, DynamicContextItem(callable, *args, **kwargs))

    def set_counter(self, index, start=1):
        """Set a dynamic value that increments each time it is evaluated"""
        self.set(index, CounterContextItem(start))

    def set_lazy(self, index, callable, *args, **kwargs):
        """Associate a callable with an index. The callable is evaluated and the result
        returned when the index is first referenced. Subsequent references use the
        previously calculated result.

        """
        self.set(index, LazyContextItem(callable, *args, **kwargs))

    def set_async(self, index, callable, *args, **kwargs):
        """Associate a callable with an index, that runs concurrently, and will block if the
        index is references before the callable has completed

        """
        self.set(index, AsyncContextItem(callable, *args, **kwargs))

    def set_thread_local(self, index, callable, *args, **kwargs):
        """Associate callable with an index that will be used to create
        thread local data.

        """
        tlocal_item = _ThreadLocalItem(callable, *args, **kwargs)
        self.set(index, tlocal_item)
        return tlocal_item.obj

    @synchronize
    def set_new_thread_local(self, index, callable, *args, **kwargs):
        """Sets a new thread local callable, if the index doesn't yet exist"""
        if index not in self:
            return self.set_thread_local(index, callable, *args, **kwargs)
        else:
            return self[index]

    def link(self, index, proxy_index):
        self.set(index, LinkItem(proxy_index))

    @synchronize
    def __contains__(self, index, _parse=parse):
        indices = _parse(index)
        if indices.from_root:
            objs = [self.root]
        else:
            objs = [scope.obj for scope in self._stack._current_frame]
        if not indices:
            return objs[0]

        first, rest = indices.top_tail
        try:
            for obj in objs:
                try:
                    obj = (getattr(obj, '__getitem__', None) or getattr(obj, '__getattribute__'))(first)
                except (TypeError, KeyError, IndexError, AttributeError):
                    continue
                if not rest:
                    return True
                if hasattr(obj, '__moyacontext__'):
                    obj = obj.__moyacontext__(self)
                last = rest.pop()
                for name in rest:
                    obj = (getattr(obj, '__getitem__', None) or getattr(obj, '__getattribute__'))(name)
                    if hasattr(obj, '__moyacontext__'):
                        obj = obj.__moyacontext__(self)
                if hasattr(obj, '__getitem__'):
                    return last in obj
                else:
                    return hasattr(obj, last)
        except (TypeError, KeyError, IndexError, AttributeError):
            return False
        return False

    @synchronize
    def get(self, index, default=Ellipsis, _parse=parse):
        indices = _parse(index)
        if indices.from_root:
            objs = [self.root]
        else:
            objs = [scope.obj for scope in self._stack._current_frame]
        if not indices:
            obj = objs[0]
            if hasattr(obj, '__moyacontext__'):
                obj = obj.__moyacontext__(self)
            return obj

        first, rest = indices.top_tail
        try:
            for obj in objs:
                try:
                    obj = (getattr(obj, '__getitem__', None) or getattr(obj, '__getattribute__'))(first)
                except (TypeError, KeyError, IndexError, AttributeError):
                    continue
                if hasattr(obj, '__moyacontext__'):
                    obj = obj.__moyacontext__(self)
                for name in rest:
                    obj = (getattr(obj, '__getitem__', None) or getattr(obj, '__getattribute__'))(name)
                    if hasattr(obj, '__moyacontext__'):
                        obj = obj.__moyacontext__(self)
                return obj
        except (TypeError, KeyError, IndexError, AttributeError):
            return Missing(index)
        if default is not Ellipsis:
            return default
        return Missing(index)

    @synchronize
    def pop(self, index, default=Ellipsis):
        value = self.get(index, default=default)
        self.safe_delete(index)
        return value

    def get_simple(self, index):
        """Get a single index key"""
        objs = [scope.obj for scope in self._stack._current_frame]
        for obj in objs:
            try:
                val = (getattr(obj, '__getitem__', None) or getattr(obj, '__getattribute__'))(index)
            except (TypeError, KeyError, IndexError, AttributeError):
                continue
            if hasattr(val, '__moyacontext__'):
                return val.__moyacontext__(self)
            return val
        return Missing(index)

    def get_first(self, default=None, *indices):
        """Return the first index present, or return a default"""
        get = self.get
        for index in indices:
            value = get(index, Ellipsis)
            if value is not Ellipsis:
                return value
        return default

    def inc(self, index):
        """Increment an integer value and return it"""
        try:
            value = self.get(index, 0) + 1
        except ValueError:
            value = 0
        self.set(index, value)
        return value

    def dec(self, index):
        """Decrement an integer value and return it"""
        try:
            value = self.get(index, 0) - 1
        except ValueError:
            value = 0
        self.set(index, value)
        return value

    def get_first_true(self, default=None, *indices):
        """Return the first index that evaluates to true, or a default"""
        get = self.get
        for index in indices:
            value = get(index, None)
            if value:
                return value
        return default

    def get_sub(self, index, default=Ellipsis):
        return self.get(self.sub(index), default)

    @synchronize
    def copy(self, src, dst):
        self.set(dst, self.get(src))

    @synchronize
    def move(self, src, dst):
        self.set(dst, self.get(src))
        self.delete(src)

    @synchronize
    def delete(self, index):
        obj, final = self._set_lookup(index)
        if hasattr(obj, '__getitem__'):
            del obj[final]
        else:
            delattr(obj, final)

    @synchronize
    def safe_delete(self, *indices):
        """Deletes a value if it exists, or does nothing"""
        for index in indices:
            obj, final = self._set_lookup(index)
            if hasattr(obj, '__getitem__'):
                if final in obj:
                    del obj[final]
            else:
                if hasattr(obj, final):
                    delattr(obj, final)

    def eval(self, expression, _isinstance=isinstance, _string_types=string_types):
        """Evaluate an expression, can be either a string or an expression compiled with `compile`"""
        if _isinstance(expression, _string_types):
            return Expression(expression).eval(self)
        return expression.eval(self)

    def subeval(self, s):
        expression = self.sub(s)
        if isinstance(expression, string_types):
            return Expression(expression).eval(self)
        return expression.eval(self)

    @synchronize
    def keys(self, index=''):
        obj = self.get(index)
        if hasattr(obj, '__getitem__'):
            if hasattr(obj, 'keys'):
                return list(obj.keys())
            else:
                return [i for i, _v in enumerate(obj)]
        else:
            return [k for k in dir(obj) if not k.startswith('_')]

    @synchronize
    def values(self, index=''):
        obj, indices = self._get_obj(index)
        keys = self.keys(indices)
        return [self.get(join(indices, [k]), None) for k in keys]

    @synchronize
    def items(self, index=''):
        obj = self.get(index)
        if hasattr(obj, '__getitem__'):
            if hasattr(obj, 'items'):
                return list(obj.items())
            else:
                return list(enumerate(obj))
        else:
            return [(k, getattr(obj, k)) for k in dir(obj) if not k.startswith('_')]

    @synchronize
    def all_keys(self, max_depth=5):
        keys = []

        def recurse(index, depth=0):
            indices = parse(index)
            obj = self.get(indices)
            keys.append(dataindex.build(index))
            if max_depth is not None and depth >= max_depth:
                return
            if not isinstance(obj, (bool, slice) + number_types + string_types):
                for k, v in self.items(indices):
                    recurse(join(indices, [k]), depth + 1)
        recurse('')
        return keys

    def stack(self, stack_name, value, stack_callable=list):
        return _StackContext(self, stack_name, value, stack_callable=stack_callable)

    def root_stack(self, stack_name, value, stack_callable=list):
        return _RootStackContext(self, stack_name, value, stack_callable=stack_callable)

    @synchronize
    def push_stack(self, stack_name, value, stack_callable=list):
        """Create a stack in the root of the context"""
        stack_index = '_{}_stack'.format(stack_name)
        if stack_index not in self.root:
            stack = self.root[stack_index] = stack_callable()
        else:
            stack = self.root[stack_index]
        stack.append(value)
        self.set(stack_name, LastIndexItem(stack_index, '.' + stack_name))
        value_index = ".{}.{}".format(stack_index, len(stack) - 1)
        return value_index

    @synchronize
    def pop_stack(self, stack_name):
        """Pop a value from an existing stack"""
        stack_index = '._{}_stack'.format(stack_name)
        stack = self[stack_index]
        value = stack.pop()
        if not stack:
            del self[stack_index]
        return value

    def get_stack_top(self, stack_name, default=None):
        stack = self.get('._{}_stack'.format(stack_name), None)
        if not stack:
            return default
        return stack[-1]

    @synchronize
    def push_thread_local_stack(self, stack_name, value, stack_callable=list):
        """Push a value on to a thread local stack"""
        stack_index = '._{}_stack'.format(stack_name)
        stack = self.set_new_thread_local(stack_index, stack_callable)
        stack.append(value)
        value_index = "{}.{}".format(stack_index, len(stack) - 1)
        return value_index

    # Pop thread local stack is the same as the non-local version
    pop_thread_local_stack = pop_stack

    __setitem__ = set
    __getitem__ = get
    __delitem__ = delete

if __name__ == "__main__":

    c = Context()

    c['foo'] = dict(bar={}, baz={})
    c['foo.bar.fruits'] = ['apples', 'oranges', 'pears']
    c['foo.baz.td'] = dict(posts=[1, 2, 3, 4])
    c['whooo'] = "wah"

    with c.scope('foo'):
        with c.scope('bar'):
            print(c['fruits'])
            print(c['td'])
            print(c['.whooo'])


#        c = Context()
#        c['foo'] = {}
#        c.push_frame('foo')
#        self.assertEqual(c.get_frame(), 'foo')
#        c['bar'] = 1
#        self.assertEqual(c.root['foo']['bar'], 1)
#        c.pop_frame()
#        self.assertEqual(c.get_frame(), '')
#        c['baz'] = 2
#        self.assertEqual(c.root['baz'], 2)


#    c = Context()
#    c['foo'] = {}
#    c['fruit'] = "apple"
#    c['foo.bar'] = {}
#    c.push_scope('foo.bar')
#    c['ilike'] = c['fruit']
#    c.push_scope('.foo')
#    c['f'] = 4
#    print c.root
