from __future__ import print_function
from __future__ import unicode_literals

from . import pilot
from .console import ConsoleHighlighter

import logging


class LogHighlighter(ConsoleHighlighter):
    styles = {
        None: "cyan",
        "tag": "yellow not bold",
        "debug": "dim green",
        "info": "green",
        "warning": "red",
        "error": "bold red",
        "critical": "bold red reverse",
        "logdate": "blue",
        "string_single": "green",
        "string_double": "green",
        "get": "bold magenta",
        "post": "bold blue",
        "errorresponse": "bold red",
        "responsecode": "not dim",
        "path": "bold blue",
        #"dim": "dim",
        "url": "underline",
        #"parenthesis": "dim"
    }

    highlights = [
        r'(?P<path>\s\/[-_\.\w\/]*)',
        r'(?P<tag>\<.*?\>)',

        r'^(?P<logdate>\[.*?\])',
        r'(?P<string_single>\".*?\")|(?P<string_double>\'.*?\')',

        r'^\[.*\](?P<info>:.*?:INFO:)',
        r'^\[.*\](?P<debug>:.*?:DEBUG:)',
        r'^\[.*\](?P<warning>:.*?:WARNING:)',
        r'^\[.*\](?P<error>:.*?:ERROR:)',
        r'^\[.*\](?P<critical>:.*?:CRITICAL:)',

        r'(?P<request>\".*?\") (?:(?P<errorresponse>[45]\S+)|(?P<responsecode>\S+))',

        r'(?P<get>\"GET .*?\")',
        r'(?P<post>\"POST .*?\")',
        r'(?P<url>https{0,1}://\S*)',
        r'(?P<parenthesis>\(.*?\))'

    ]


class MoyaConsoleHandler(logging.StreamHandler):

    def emit(self, record):
        text = self.format(record)
        htext = LogHighlighter.highlight(text)
        pilot.console(htext).nl()


class LoggerFile(object):
    """A file-like object that writes to a log"""

    def __init__(self, logger):
        self._logger = logger
        self._log = logging.getLogger(logger)
        self._text = []

    def __repr__(self):
        return "<loggerfile '{}'>".format(self._logger)

    def write(self, text):
        self._text.append(text)
        if '\n' in text:
            lines = ''.join(self._text).splitlines(True)
            for i, line in enumerate(lines):
                if line.endswith('\n'):
                    self._log.info(line[:-1])
                else:
                    self._text[:] = lines[i:]
                    break
            else:
                del self._text[:]

    def flush(self):
        pass

    def isatty(self):
        return False
