from __future__ import unicode_literals
from __future__ import division

import logging
import threading

from ..elements.elementbase import LogicElement, Attribute
from ..tags.context import DataSetterBase
from .. import namespaces
from ..compat import implements_to_string

from fs.path import basename, join, splitext

from PIL import Image, ImageFilter
try:
    from PIL import ExifTags
except ImportError:
    ExifTags = None


log = logging.getLogger('moya.image')


@implements_to_string
class MoyaImage(object):
    """Proxy interface for a PIL image"""

    def __init__(self, img, filename):
        self._img = img
        self.filename = filename
        self._lock = threading.RLock()

    def __str__(self):
        w, h = self._img.size
        return "<image '{}' {}x{} {}>".format(self.filename, w, h, self.mode)

    def __repr__(self):
        w, h = self._img.size
        return "<image '{}' {}x{} {}>".format(self.filename, w, h, self.mode)

    def replace(self, img):
        self._img = img

    @property
    def format(self):
        return self._img.format

    @property
    def size(self):
        w, h = self._img.size
        return {'width': w, 'height': h}

    @property
    def mode(self):
        return self._img.mode

    @property
    def info(self):
        return self._img.info

    @property
    def exif(self):
        with self._lock:
            self._img.load()
            _exif = self._img._getexif()
            if _exif is None:
                return {}

            exif = {}
            if ExifTags:
                for k, v in _exif.items():
                    try:
                        key = ExifTags.TAGS.get(k, None)
                        if key is not None:
                            value = v.decode('utf-8', 'replace') if isinstance(v, bytes) else v
                            exif[key] = value
                    except Exception as e:
                        # EXIF can be full of arbitrary data
                        log.debug('exif extract error: %s', e)

            return exif


class Read(DataSetterBase):
    """Read an image"""
    xmlns = namespaces.image

    class Help:
        synopsis = """read an image from disk"""

    class Meta:
        one_of = [('fsobj', 'fs', 'file')]

    path = Attribute("Path", required=False, default=None)
    fsobj = Attribute("FS", type="Index")
    fs = Attribute("FS name")
    dst = Attribute('Destination', type="reference", default="image")
    _file = Attribute('File object with image data', type="expression")
    filename = Attribute("Filename to associate with the image if the filename can't be detected", default='', type="expression")

    def get_image(self, context, params):
        if self.has_parameter('file'):
            fp = getattr(params.file, '__moyafile__', lambda: params.file)()
            try:
                fp.seek(0)
                img = Image.open(fp)
                img.load()
                fp.seek(0)
            except Exception as e:
                self.throw("image.read-fail", "Failed to read image from file ({})".format(e))
        else:
            if params.fsobj is not None:
                fs = params.fsobj
            else:
                try:
                    fs = self.archive.filesystems[params.fs]
                except KeyError:
                    self.throw("image.no-fs", "No filesystem called '{}'".format(params.fs))
            if params.path is None:
                self.throw("image.path-required", "a path is required when reading from a filesystem")
            try:
                fp = fs.open(params.path, 'rb')
                img = Image.open(fp)
            except Exception as e:
                self.throw("image.read-fail", "failed to read '{}' from {!r} ({})".format(params.path, fs, e))
        return img

    def logic(self, context):
        params = self.get_parameters(context)
        img = self.get_image(context, params)
        try:
            img.load()
        except Exception as e:
            self.throw("image.read-fail", "Failed to read image ({})".format(e))

        moya_image = MoyaImage(img, filename=basename(params.path or params.filename or ''))
        self.set_context(context, params.dst, moya_image)
        log.debug("%r read", moya_image)


class GetSize(Read):
    """Get the dimensions of an image without loading image data, returns a dictionary with keys 'width' and 'height'."""
    xmlns = namespaces.image

    class Help:
        synopsis = """get the dimensions of an image"""

    class Meta:
        one_of = [('fsobj', 'fs', 'file')]

    path = Attribute("Path")
    fsobj = Attribute("FS", type="Index")
    fs = Attribute("FS name")
    dst = Attribute('Destination', type="reference", default="image")
    _file = Attribute('File object with image data', type="expression")

    def logic(self, context):
        params = self.get_parameters(context)
        img = self.get_image(context, params)
        with img._lock:
            w, h = img.size
            result = {'width': w, 'height': h}
            self.set_context(context, params.dst, result)


class CheckImageMixin(object):
    """Mixin for checking images."""

    def check_image(self, context, image):
        if not isinstance(image, MoyaImage):
            _msg = "attribute 'image' should reference an image object, not {}"
            self.throw(
                'bad-value.image',
                _msg.format(context.to_expr(image))
            )


class ImageElement(LogicElement, CheckImageMixin):
    pass


class Write(ImageElement):
    """Write an image"""
    xmlns = namespaces.image

    class Help:
        synopsis = """write an image to disk"""

    class Meta:
        one_of = [('fs', 'fsobj')]

    image = Attribute("Image to write", type="expression", default="image", evaldefault=True, missing=False)
    dirpath = Attribute("Directory to write image", required=False, default="/")
    filename = Attribute("Image filename", required=True)
    fsobj = Attribute("FS", type="expression")
    fs = Attribute("FS name")
    format = Attribute("Image format", default=None, choices=['jpeg', 'png', 'gif'])

    def logic(self, context):

        params = self.get_parameters(context)
        self.check_image(context, params.image)

        if params.fsobj is not None:
            fs = params.fsobj
        else:
            try:
                fs = self.archive.filesystems[params.fs]
            except KeyError:
                self.throw("image.no-fs", "No filesystem called '{}'".format(params.fs))
                return
        path = join(params.dirpath, params.filename)

        with params.image._lock:
            img = params.image._img
            img_format = params.format or splitext(params.filename or '')[-1].lstrip('.') or 'jpeg'

            if img_format == 'jpeg':
                if img.mode != 'RGB':
                    img = img.convert('RGB')

            save_params = self.get_let_map(context)
            try:
                with fs.makedirs(params.dirpath, recreate=True) as dir_fs:
                    with dir_fs.open(params.filename, 'wb') as f:
                        img.save(f, img_format, **save_params)
                log.debug("wrote '%s'", params.filename)
            except Exception as e:
                raise
                self.throw('image.write-fail', "Failed to write {} to '{}' in {!r} ({})".format(params.image, path, fs, e))


class New(DataSetterBase, CheckImageMixin):
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


class Copy(DataSetterBase, CheckImageMixin):
    """Create an copy of [c]image[/c] in [c]dst[/c]."""
    xmlns = namespaces.image

    class Help:
        synopsis = "create a copy of an image"

    image = Attribute("Image to copy", type="expression", default="image", evaldefault=True)
    dst = Attribute('Destination', type="reference", default="image")

    def logic(self, context):
        params = self.get_parameters(context)
        self.check_image(context, params.image)
        with params.image._lock:
            img = params.image._img
            moya_image = MoyaImage(img.copy(), params.image.filename)
            self.set_context(context, params.dst, moya_image)


class Show(ImageElement):
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


class ResizeToFit(ImageElement):
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
        self.check_image(context, params.image)
        with params.image._lock:
            image = params.image._img
            new_size = _fit_dimensions(image, params.width, params.height)
            w, h = new_size
            if not w or not h:
                self.throw('image.bad-dimensions',
                           'Invalid image dimensions ({} x {})'.format(params.width, params.height),
                           diagnosis="Width and / or height should be supplied, and should be non-zero")
            params.image.replace(image.resize(new_size, _resample_methods[params.resample]))


class ZoomToFit(ImageElement):
    """Resize image to given dimensions, cropping if necessary."""

    xmlns = namespaces.image

    class Help:
        synopsis = "resize an image to fit in new dimensions, with cropping"

    image = Attribute("Image to show", type="expression", default="image", evaldefault=True)
    width = Attribute("New width", type="integer", required=True)
    height = Attribute("New height", type="integer", required=True)
    resample = Attribute("Method for resampling", default="antialias", choices=_resample_methods.keys())

    def logic(self, context):
        params = self.get_parameters(context)
        self.check_image(context, params.image)
        with params.image._lock:
            image = params.image._img

            aspect = image.size[0] / image.size[1]
            if image.size[0] > image.size[1]:
                new_size = int(params.height * aspect), params.height
            else:
                new_size = params.width, int(params.width / aspect)

            img = image.resize(new_size, _resample_methods[params.resample])

            w = params.width
            h = params.height
            x = (img.size[0] - w) // 2
            y = (img.size[1] - h) // 2

            box = x, y, x + w, y + h
            params.image.replace(img.crop(box))


class Resize(ImageElement):
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
        self.check_image(context, params.image)
        with params.image._lock:
            image = params.image._img
            new_size = (params.width, params.height)
            w, h = new_size
            if not w or not h:
                self.throw('image.bad-dimensions',
                           'Invalid image dimensions ({} x {})'.format(params.width, params.height),
                           diagnosis="Width and / or height should be supplied, and should be non-zero")
            params.image.replace(image.resize(new_size, _resample_methods[params.resample]))


class ResizeCanvas(ImageElement):
    """Resize the image canvas."""

    xmlns = namespaces.image

    class Help:
        synopsis = "resize the image canvas"

    image = Attribute("Image to show", type="expression", default="image", evaldefault=True)
    width = Attribute("New width", type="integer", required=True)
    height = Attribute("New height", type="integer", required=True)
    color = Attribute("Background color", type="color", default="#000000")

    def logic(self, context):
        image, w, h, color = self.get_parameters(context, 'image', 'width', 'height', 'color')
        self.check_image(context, image)
        with image._lock:
            img = image._img
            mode = img.mode
            if color.a != 1:
                mode = 'RGBA'
            new_img = Image.new(mode, (w, h), color.as_pillow_tuple())

            iw, ih = img.size

            x = (w - iw) // 2
            y = (h - ih) // 2

            new_img.paste(img, (x, y))
            image.replace(new_img)


class Square(ImageElement):
    """Square crop an image."""

    xmlns = namespaces.image

    class Help:
        synopsis = "square crop an image"

    image = Attribute("Image to crop", type="expression", default="image", evaldefault=True)

    def logic(self, context):
        params = self.get_parameters(context)
        self.check_image(context, params.image)
        with params.image._lock:
            img = params.image._img

            w, h = img.size
            size = min(img.size)
            x = (w - size) // 2
            y = (h - size) // 2

            new_img = Image.new(img.mode, (size, size))
            new_img.paste(img, (-x, -y))

            params.image.replace(new_img)


class Crop(ImageElement):
    """Crop an image to a given area."""
    xmlns = namespaces.image

    class Help:
        synopsis = "crop an image"

    image = Attribute("Image to show", type="expression", default="image", evaldefault=True)
    box = Attribute("Crop size (either [width, height] or [x, y, width, height])", type="expression")

    def logic(self, context):
        params = self.get_parameters(context)
        size = params.box
        self.check_image(context, params.image)
        with params.image._lock:
            img = params.image._img
            if len(size) == 2:
                w, h = size
                x = (img.size[0] - w) // 2
                y = (img.size[1] - h) // 2
            elif len(size) == 4:
                x, y, w, h = size
            else:
                self.throw('bad-value.box-invalid',
                           "parameter 'box' should be  sequence of 2 or 4 parameters (not {})".format(context.to_expr(size)))

            box = x, y, x + w, y + h
            params.image.replace(img.crop(box))


class GaussianBlur(ImageElement):
    """Guassian blur an image."""
    xmlns = namespaces.image

    image = Attribute("Image to show", type="expression", default="image", evaldefault=True)
    radius = Attribute("Radius of blur", type="integer", default=2)

    def logic(self, context):
        params = self.get_parameters(context)
        self.check_image(context, params.image)
        with params.image._lock:
            img = params.image._img
            if img.mode == 'P':
                img = img.convert('RGB')
            new_image = img.filter(ImageFilter.GaussianBlur(radius=params.radius))
            params.image.replace(new_image)
