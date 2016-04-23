from __future__ import unicode_literals
from __future__ import print_function

from ...command import SubCommand

import os


MOYA_TEMPLATE_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<moya xmlns="http://moyaproject.com"
    xmlns:m="http://moyaproject.com"
    xmlns:let="http://moyaproject.com/let"
    xmlns:db="http://moyaproject.com/db"
    xmlns:forms="http://moyaproject.com/forms"
    xmlns:w="http://moyaproject.com/widgets"
    xmlns:html="http://moyaproject.com/html">

    <!-- your content here -->

</moya>
"""


class New(SubCommand):
    """Create a boilerplate moya file"""
    help = "create a new boilerplate moya file"

    def add_arguments(self, parser):
        parser.add_argument(dest='filename', metavar="PATH",
                            help="path / filename for new file")
        parser.add_argument('-f', '-force', dest="force", action="store_true",
                            help="fore overwriting")

    def run(self):
        args = self.args

        if not args.force and os.path.exists(args.filename):
            self.console.error('destination exists, use --force to overwrite')
            return -1

        td = {}
        file_data = MOYA_TEMPLATE_XML.format(td)

        try:
            with open(args.filename, 'wt') as f:
                f.write(file_data)
        except Exception as e:
            self.console.error('unable to write file ({})'.format(e))
            return -1
