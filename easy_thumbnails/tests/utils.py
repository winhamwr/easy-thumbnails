from __future__ import with_statement

import shutil
import tempfile
import os
from StringIO import StringIO

from django.conf import settings
from django.core.files import locks
from django.core.files.base import File
from django.core.files.move import file_move_safe
from django.core.files.storage import FileSystemStorage
from django.utils._os import safe_join
from django.test import TestCase

from easy_thumbnails import defaults

class TemporaryStorage(FileSystemStorage):
    """
    A storage class useful for tests that uses a temporary location to store
    all files and provides a method to remove this location when it is finished
    with.

    """

    def __init__(self, location=None, *args, **kwargs):
        """
        Create the temporary location.

        """
        if location is None:
            location = tempfile.mkdtemp()
            self.temporary_location = location
        super(TemporaryStorage, self).__init__(location=location, *args,
                                               **kwargs)

    def delete_temporary_storage(self):
        """
        Delete the temporary directory created during initialisation.
        This storage class should not be used again after this method is
        called.

        """
        temporary_location = getattr(self, 'temporary_location', None)
        if temporary_location:
            shutil.rmtree(temporary_location)


class FakeRemoteStorage(TemporaryStorage):
    """
    A storage class that acts similar to remote storage backend like s3boto.

    """

    def path(self, *args, **kwargs):
        """
        Raise ``NotImplementedError``, since this is the way that
        easy-thumbnails determines if a storage is remote.

        """
        raise NotImplementedError

    def _open(self, name, mode='rb'):
        """
        Uses an underlying file object that doesn't implement all the methods
        of local file access
        """
        return FakeRemoteFile(name, mode, self)

    def exists(self, name):
        """
        Fakes an exists function for testing.
        """
        return os.path.exists(self._fake_path(name))

    def _fake_path(self, name):
        """
        Faking doing something like a key lookup for S3.
        """
        return safe_join(self.location, name)

    def _save(self, name, content):
        full_path = self._fake_path(name)

        directory = os.path.dirname(full_path)
        if not os.path.exists(directory):
            os.makedirs(directory)
        elif not os.path.isdir(directory):
            raise IOError("%s exists and is not a directory." % directory)

        # There's a potential race condition between get_available_name and
        # saving the file; it's possible that two threads might return the
        # same name, at which point all sorts of fun happens. So we need to
        # try to create the file, but if it already exists we have to go back
        # to get_available_name() and try again.

        while True:
            try:
                # This file has a file path that we can move.
                if hasattr(content, 'temporary_file_path'):
                    file_move_safe(content.temporary_file_path(), full_path)
                    content.close()

                # This is a normal uploadedfile that we can stream.
                else:
                    # This fun binary flag incantation makes os.open throw an
                    # OSError if the file already exists before we open it.
                    fd = os.open(full_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_BINARY', 0))
                    try:
                        locks.lock(fd, locks.LOCK_EX)
                        for chunk in content.chunks():
                            os.write(fd, chunk)
                    finally:
                        locks.unlock(fd)
                        os.close(fd)
            except OSError, e:
                if e.errno == errno.EEXIST:
                    # Ooops, the file exists. We need a new file name.
                    name = self.get_available_name(name)
                    full_path = self._fake_path(name)
                else:
                    raise
            else:
                # OK, the file save worked. Break out of the loop.
                break

        if settings.FILE_UPLOAD_PERMISSIONS is not None:
            os.chmod(full_path, settings.FILE_UPLOAD_PERMISSIONS)

        return name

    def url(self, name):
        """
        Url function that add some querystring stuff to the URL. Simulates S3
        querystring auth.
        """
        url = super(TemporaryStorage, self).url(name)
        return '%s?foo=bar' % url

    def get_available_name(self, name):
        return name

class FakeRemoteFile(File):
    """
    Fake file that doesn't implement _open() similar to an s3boto storage file.
    """
    def __init__(self, name, mode, storage):
        self._storage = storage
        self.name = name.lstrip('/')
        self._mode = mode
        self._file = None

    @property
    def file(self):
        if self._file is None:
            self._file = StringIO()
            if 'r' in self._mode:
                with open(self._storage._fake_path(self.name), 'r') as local_f:
                    self._file.write(local_f.read())
                self._file.seek(0)
        return self._file

    def read(self, *args, **kwargs):
        if 'r' not in self._mode:
            raise AttributeError("File was not opened in read mode.")
        return super(FakeRemoteFile, self).read(*args, **kwargs)

    def write(self, *args, **kwargs):
        if 'w' not in self._mode:
            raise AttributeError("File was opened for read-only access.")
        return super(S3BotoStorageFile, self).write(*args, **kwargs)

    def close(self):
        with open(self._storage._fake_path(self.name), 'w') as local_f:
            self.file.seek(0)
            local_f.write(self.file.read())
        self._file = None


class BaseTest(TestCase):
    """
    Remove any customised THUMBNAIL_* settings in a project's ``settings``
    configuration module before running the tests to ensure there is a
    consistent test environment.

    """
    restore_settings = ['THUMBNAIL_%s' % key for key in dir(defaults)
                        if key.isupper()]

    def setUp(self):
        """
        Remember THUMBNAIL_* settings for later and then remove them.

        """
        self._remembered_settings = {}
        for setting in self.restore_settings:
            if hasattr(settings, setting):
                self._remembered_settings[setting] = getattr(settings, setting)
                delattr(settings._wrapped, setting)

    def tearDown(self):
        """
        Restore all THUMBNAIL_* settings to their original state.

        """
        for setting in self.restore_settings:
            self.restore_setting(setting)

    def restore_setting(self, setting):
        """
        Restore an individual setting to it's original value (or remove it if
        it didn't originally exist).

        """
        if setting in self._remembered_settings:
            value = self._remembered_settings.pop(setting)
            setattr(settings, setting, value)
        elif hasattr(settings, setting):
            delattr(settings._wrapped, setting)
