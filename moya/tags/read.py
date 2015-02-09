from __future__ import unicode_literals

from ..elements.elementbase import Attribute
from ..tags.context import DataSetter
from ..reader import ReaderError
from ..compat import text_type


class ReadData(DataSetter):
    """
    Read and process a data file. The [c]path[/c] parameter may be absolute, or relative from the current application.

    let's say we have a file, crew.txt in our [link library#data-section]data directory[/link], which is a text file with a list of names, one per line. For example:

    [code]
    Rygel
    John
    Scorpies
    Ka D'Argo
    [/code]

    We can read the above file and process each line with the following:

    [code xml]
    <read-data format="text/plain" path="crew.txt" dst="crew" />
    <for src="splitlines:crew" dst="characters">
        <echo>${character} is on board</echo>
    </for>
    [/code]

    """

    class Help:
        synopsis = "read and process data"

    fs = Attribute("FS name", required=False, default="data")
    path = Attribute("Path to data file in data filesystem", required=False)
    _from = Attribute("Application", type="application", required=False, default=None)

    mimetype = Attribute("Mime Type of file (omit to guess based on extension)", required=False, default=None)
    dst = Attribute("Destination", type="reference", default=None)

    def logic(self, context):
        app = self.get_app(context)
        fs_name, path, mimetype, dst = self.get_parameters(context,
                                                           'fs',
                                                           'path',
                                                           'mimetype',
                                                           'dst')
        reader = self.archive.get_reader(fs_name)

        try:
            data = reader.read(path, app=app, mime_type=mimetype)
        except ReaderError as e:
            self.throw("read-data.fail", text_type(e))
        else:
            self.set_context(context, dst, data)
