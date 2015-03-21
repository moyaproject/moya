from __future__ import unicode_literals
from __future__ import print_function

from threading import Thread
import logging

log = logging.getLogger('moya.thread')

from ..context import Context
from ..compat import iteritems
from ..elements.elementbase import Attribute
from ..tags.context import DataSetter


class MoyaThread(Thread):

    def __init__(self, element, app, name, context, data, join_timeout=None):
        super(MoyaThread, self).__init__(name=name)
        self.element = element
        self.app = app
        self.context = context
        self.data = data
        self.join_timeout = join_timeout
        self.libid = element.libid
        self._result = None
        self._error = None

    def __repr__(self):
        return "<thread {} '{}'>".format(self.libid, self.name)

    def run(self):
        try:
            self._result = self.element.archive.call(self.element.libid, self.context, self.app)
        except Exception as e:
            self.context['.console'].obj(self.context, e)
            self._error = e

    def __moyacontext__(self, context):

        self.join(self.join_timeout)
        if self.join_timeout:
            if self.is_alive():
                self.element.throw('thread.timeout',
                                   'the thread failed to complete within timeout',
                                   thread=self)

        if self._error:
            self.element.throw('thread.fail',
                               'exception occurred in thread',
                               diagnosis="{!r} raised exception '{}'".format(self, self._error),
                               original=self._error,
                               thread=self)
        return self._result


class ThreadElement(DataSetter):
    """
    Run enclosed block in a thread.

    The thread


    """

    class Help:
        synopsis = "run a thread"

    class Meta:
        tag_name = "thread"

    name = Attribute("Name of thread", required=False, default=None)
    timeout = Attribute("Maximum time to wait for thread to complete", type="timespan", default=None)

    def logic(self, context):
        params = self.get_parameters(context)

        thread_context = Context({k: v for k, v in iteritems(context.root) if not k.startswith('_')})
        data = self.get_let_map(context)

        moya_thread = MoyaThread(self,
                                 context.get('.app', None),
                                 params.name or self.docname,
                                 thread_context,
                                 data=data,
                                 join_timeout=params.timeout)
        moya_thread.start()
        self.set_context(context, params.dst, moya_thread)
