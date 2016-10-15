"""

Package tools

"""

from __future__ import print_function
from __future__ import unicode_literals

import fnmatch
import hashlib
import csv
from itertools import chain

import fs.copy
from fs.zipfs import ZipFS
from fs.tempfs import TempFS
from fs import walk

from .compat import implements_bool
from .console import Console


def _make_package_fs(package_fs, output_fs, exclude_wildcards, auth_token=None):
    """Builds a package zip."""
    assert isinstance(exclude_wildcards, list), "wildcards must be a list"

    def match_wildcards(path):
        split_path = path.lstrip('/').split('/')
        for i in range(len(split_path)):
            p = '/'.join(split_path[i:])
            if any(fnmatch.fnmatchcase(p, w) for w in exclude_wildcards):
                return False
        return True

    manifest = []

    console = Console()

    paths = []
    for dir_path, _, files in walk.walk(package_fs):
        output_fs.makedir(dir_path, recreate=True)
        for info in files:
            path = info.make_path(dir_path)
            if not match_wildcards(path):
                continue
            paths.append(path)

    with console.progress("building package...", len(paths)) as progress:
        for path in sorted(paths):
            progress.step()
            data = package_fs.getbytes(path)
            m = hashlib.md5()
            m.update(data)
            file_hash = m.hexdigest()
            if auth_token is None:
                auth_hash = ""
            else:
                m.update(auth_token.encode('utf-8'))
                auth_hash = m.hexdigest()

            output_fs.setbytes(path, data)
            manifest.append((path, file_hash, auth_hash))

    return manifest


def export_manifest(manifest, output_fs, filename="manifest.csv"):
    """Write a manifest file."""
    lines = ['"path","md5","auth md5"']
    for path, file_hash, auth_hash in manifest:
        lines.append('"{}",{},{}'.format(path.replace('"', '\\"'), file_hash, auth_hash))
    manifest_data = "\n".join(lines)
    output_fs.settext(filename, manifest_data, encoding="utf-8")


def read_manifest(manifest_fs, manifest_filename):
    """Read a manifest file."""
    with manifest_fs.open(manifest_filename, 'rb') as manifest_file:
        csv_reader = csv.reader(manifest_file, delimiter=b",", quotechar=b'"')
        manifest = list(csv_reader)[1:]
    return manifest


@implements_bool
class ManifestComparision(object):
    """Stores the result of comparison with a directory and a manifest."""

    def __init__(self, new_files, changed_files, deleted_files):
        self.new_files = new_files
        self.changed_files = changed_files
        self.deleted_files = deleted_files

    def __bool__(self):
        return bool(self.new_files or self.changed_files or self.deleted_files)


def get_md5(input_file, chunk_size=1024 * 16):
    """Get the md5 of a file without reading entire file in to memory."""
    m = hashlib.md5()
    while 1:
        chunk = input_file.read(chunk_size)
        if not chunk:
            break
        m.update(chunk)
    return m.hexdigest()


def make_package(package_fs, output_fs, output_path, exclude_wildcards, auth_token):
    """Make a Moya package."""
    manifest_filename = "manifest.csv"
    with TempFS() as temp_fs:
        manifest = _make_package_fs(package_fs,
                                    temp_fs,
                                    exclude_wildcards,
                                    auth_token=auth_token)

        with output_fs.open(output_path, 'wb') as dest_file:
            with ZipFS(dest_file, 'w') as zip_fs:
                fs.copy.copy_dir(temp_fs, '/', zip_fs, '/')
                export_manifest(manifest, zip_fs, filename=manifest_filename)

        # with output_fs.open(output_path, 'rb') as zip_file:
        #     with ZipFS(zip_file, 'r') as zip_fs:
        #         check_manifest = read_manifest(zip_fs, manifest_filename)
