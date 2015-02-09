from __future__ import unicode_literals
from __future__ import division

from ..elements.elementbase import LogicElement, Attribute
from ..tags.context import DataSetterBase
from .. import namespaces
from ..compat import implements_to_string

from fs.path import basename, pathjoin

from PIL import Image

import logging
log = logging.getLogger('moya.image')


@implements_to_string
class MoyaImage(object):
    """Proxy interface for a PIL image"""

    def __init__(self, img, filename):
        self._img = img
        self.filename = filename

    def __str__(self):
        w, h = self.size
        return "<image '{}' {}x{} {}>".format(self.filename, w, h, self.mode)

    def __repr__(self):
        w, h = self.size
        return "<image '{}' {}x{} {}>".format(self.filename, w, h, self.mode)

    def replace(self, img):
        self._img = img

    @property
    def format(self):
        return self._img.format

    @property
    def size(self):
        return self._img.size

    @property
    def mode(self):
        return self._img.mode

    @property
    def info(self):
        return self._img.info


class Read(DataSetterBase):
    """Read an image"""
    xmlns = namespaces.image

    class Help:
        synopsis = """read an image from disk"""

    path = Attribute("Path", required=True)
    fsobj = Attribute("FS", type="Index")
    fs = Attribute("FS name")
    dst = Attribute('Destination', type="reference", default="image")

    def logic(self, context):
        params = self.get_parameters(context)

        if params.fsobj is not None:
            fs = params.fsobj
        else:
            try:
                fs = self.archive.filesystems[params.fs]
            except KeyError:
                self.throw("moya.image.no-fs", "No filesystem called '{}'".format(params.fs))
                return

        try:
            with fs.open(params.path, 'rb') as fp:
                img = Image.open(fp)
                img.load()
        except Exception as e:
            self.throw("moya.image.read-fail", "Failed to read '{}' from {} ({})".format(params.path, fs, e))

        moya_image = MoyaImage(img, filename=basename(params.path))
        self.set_context(context, params.dst, moya_image)


class Write(LogicElement):
    """Write an image"""
    xmlns = namespaces.image

    class Help:
        synopsis = """write an image to disk"""

    image = Attribute("Image to write", type="expression", default="image", evaldefault=True)
    dirpath = Attribute("Directory to write image", required=False, default="/")
    filename = Attribute("Image filename", required=True)
    fsobj = Attribute("FS", type="Index")
    fs = Attribute("FS name")
    format = Attribute("Image format", default=None, choices=['jpeg', 'png', 'gif'])

    def logic(self, context):

        params = self.get_parameters(context)

        if params.fsobj is not None:
            fs = params.fsobj
        else:
            try:
                fs = self.archive.filesystems[params.fs]
            except KeyError:
                self.throw("moya.image.no-fs", "No filesystem called '{}'".format(params.fs))
                return
        path = pathjoin(params.dirpath, params.filename)

        img = params.image._img

        save_params = self.get_let_map(context)
        try:
            with fs.makeopendir(params.dirpath, recursive=True) as dir_fs:
                with dir_fs.open(params.filename, 'wb') as f:
                    img.save(f, params.format, **save_params)
        except Exception as e:
            self.throw('moya.image.write-fail', "Failed to write {} to '{}' in {} ({})".format(params.image, path, fs, e))


class New(DataSetterBase):
    """Create a blank image."""
    xmlns = namespaces.image

    class Help:
        synopsis = "create a blank image"

    size = Attribute("Size of new image", type="expression", required=True)
    mode = Attribute("Mode", default="RGB")
    color = Attribute("Color", default="#000000")
    dst = Attribute('Destination', type="index", default="image")

    def logic(self, context):
        params = self.get_parameters(context)
        image = Image.new(params.mode, params.size, params.color)
        moya_image = MoyaImage(image, filename="new.jpg")
        self.set_context(context, params.dst, moya_image)


class Copy(DataSetterBase):
    """Create an copy of [c]image[/c] in [c]dst[/c]."""
    xmlns = namespaces.image

    class Help:
        synopsis = "create a copy of an image"

    image = Attribute("Image to copy", type="expression", default="image", evaldefault=True)
    dst = Attribute('Destination', type="reference", default="image")

    def logic(self, context):
        params = self.get_parameters(context)
        img = params.image._img
        moya_image = MoyaImage(img.copy(), params.image.filename)
        self.set_context(context, params.dst, moya_image)


class Show(LogicElement):
    """Show an image (for debugging purposes). Imagemagick is required for this operation."""
    xmlns = namespaces.image

    class Help:
        synopsis = "show an image"

    image = Attribute("Image to show", type="expression", default="image", evaldefault=True)

    def logic(self, context):
        if context['.debug']:
            self.image(context)._img.show()
        else:
            log.warn('<show> can be used in debug mode only')


_resample_methods = {
    "nearest": Image.NEAREST,
    "bilinear": Image.BILINEAR,
    "bicubic": Image.BICUBIC,
    "antialias": Image.ANTIALIAS
}


def _fit_dimensions(image, width, height):
    w, h = image.size
    if width is None:
        width = w * (height / h)
    if height is None:
        height = h * (width / w)

    ratio = min(width / w, height / h)
    width = w * ratio
    height = h * ratio

    return int(round(width)), int(round(height))


class ResizeToFit(LogicElement):
    """Resize image to fit within the given dimensions (maintains aspect ratio)."""

    xmlns = namespaces.image

    class Help:
        synopsis = "resize an image to fit within new dimensions"

    image = Attribute("Image to show", type="expression", default="image", evaldefault=True)
    width = Attribute("New width", type="integer", required=False, default=None,)
    height = Attribute("New height", type="integer", required=False, default=None)
    resample = Attribute("Method for resampling", default="antialias", choices=_resample_methods.keys())

    def logic(self, context):
        params = self.get_parameters(context)
        image = params.image._img
        new_size = _fit_dimensions(image, params.width, params.height)
        w, h = new_size
        if not w or not h:
            self.throw('moya.image.bad-dimensions',
                       'Invalid image dimensions ({} x {})'.format(params.width, params.height),
                       diagnosis="Width and / or height should be supplied, and should be non-zero")
        params.image.replace(image.resize(new_size, _resample_methods[params.resample]))


class Resize(LogicElement):
    """Resize an image to new dimensions."""
    xmlns = namespaces.image

    class Help:
        synopsis = "resize an image"

    image = Attribute("Image to show", type="expression", default="image", evaldefault=True)
    width = Attribute("New width", type="integer", required=False, default=None,)
    height = Attribute("New height", type="integer", required=False, default=None)
    resample = Attribute("Method for resampling", default="antialias", choices=["nearest", "bilinear", "bicubic", "antialias"])

    def logic(self, context):
        params = self.get_parameters(context)
        image = params.image._img
        new_size = (params.width, params.height)
        w, h = new_size
        if not w or not h:
            self.throw('moya.image.bad-dimensions',
                       'Invalid image dimensions ({} x {})'.format(params.width, params.height),
                       diagnosis="Width and / or height should be supplied, and should be non-zero")
        params.image.replace(image.resize(new_size, _resample_methods[params.resample]))


class ResizeCanvas(LogicElement):
    """Resize the image canvas."""

    xmlns = namespaces.image

    class Help:
        synopsis = "resize the image canvas"

    image = Attribute("Image to show", type="expression", default="image", evaldefault=True)
    width = Attribute("New width", type="integer", required=True, default=None,)
    height = Attribute("New height", type="integer", required=True, default=None)
    color = Attribute("Background color", default="#000000")

    def logic(self, context):
        params = self.get_parameters(context)
        img = params.image._img
        w = params.width
        h = params.height
        new_img = Image.new(img.mode, (int(w), int(h)), params.color)

        iw, ih = img.size

        x = (w - iw) // 2
        y = (h - ih) // 2

        new_img.paste(img, (x, y))
        params.image.replace(new_img)


class Square(LogicElement):
    """Square crop an image."""

    xmlns = namespaces.image

    class Help:
        synopsis = "square crop an image"

    image = Attribute("Image to crop", type="expression", default="image", evaldefault=True)

    def logic(self, context):
        params = self.get_parameters(context)
        img = params.image._img

        w, h = img.size
        size = min(img.size)
        x = (w - size) // 2
        y = (h - size) // 2

        new_img = Image.new(img.mode, (size, size))
        new_img.paste(img, (-x, -y))

        params.image.replace(new_img)


class Crop(LogicElement):
    """Crop an image to a given area."""
    xmlns = namespaces.image

    class Help:
        synopsis = "crop an image"

    image = Attribute("Image to show", type="expression", default="image", evaldefault=True)
    box = Attribute("Crop size (either [width, height] or [x, y, width, height])", type="expression")

    def logic(self, context):
        params = self.get_parameters(context)
        size = params.box

        img = params.image._img
        if len(size) == 2:
            w, h = size
            x = (img.size[0] - w) // 2
            y = (img.size[1] - h) // 2
        elif len(size) == 4:
            x, y, w, h = size

        box = x, y, w, h
        params.image.replace(img.crop(box))
