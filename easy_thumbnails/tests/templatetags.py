from __future__ import with_statement

import os.path, urllib2, shutil
try:
    from PIL import Image
except ImportError:
    import Image
from StringIO import StringIO

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import get_storage_class
from django.template import Template, Context, TemplateSyntaxError

from easy_thumbnails.tests.utils import (
    BaseTest,
    TemporaryStorage,
    FakeRemoteStorage,
)
from easy_thumbnails.files import get_thumbnailer
from easy_thumbnails.models import Thumbnail
from easy_thumbnails import utils

ET_FIXTURES_DIR = os.path.join(
    os.path.abspath(
        os.path.dirname(__file__)),
    '..',
    'fixtures')
TRANS_PNG = 'gmail_trans.png'
OPAQUE_PNG = 'gmail.png'
default_storage_cls = get_storage_class()

class BlankThumbnailTest(BaseTest):
    RELATIVE_PIC_NAME = 'test.jpg'
    STORAGE_BACKEND = TemporaryStorage
    THUMBNAIL_EXT = 'jpg'
    restore_settings = ['THUMBNAIL_DEBUG']

    def _create_test_image(self):
        # Save a test image.
        data = StringIO()
        Image.new('RGB', (800, 600)).save(data, 'JPEG')
        data.seek(0)
        image_file = ContentFile(data.read())

        return image_file

    def _cleanup_storage(self):
        self.storage.delete_temporary_storage()

    def _get_expected(self, opts_str):
        context = (self.RELATIVE_PIC_NAME, opts_str, self.THUMBNAIL_EXT)
        return '%s.%s.%s' % context

    def setUp(self):
        BaseTest.setUp(self)
        self.storage = self.STORAGE_BACKEND()

        image_file = self._create_test_image()
        self.storage.save(self.RELATIVE_PIC_NAME, image_file)

    def tearDown(self):
        self._cleanup_storage()
        BaseTest.tearDown(self)

    def render_template(self, source):
        source_image = get_thumbnailer(self.storage, self.RELATIVE_PIC_NAME)
        source_image.thumbnail_storage = self.storage
        context = Context({
            'source': source_image,
            'invalid_source': 'not%s' % self.RELATIVE_PIC_NAME,
            'size': (90, 100),
            'invalid_size': (90, 'fish'),
            'strsize': '80x90',
            'invalid_strsize': ('1notasize2'),
            'invalid_q': 'notanumber'})
        source = '{% load thumbnail %}' + source
        return Template(source).render(context)

    def verify_thumbnail(self, expected_size, expected_filename):
        # Verify that the thumbnail file exists
        thumbnail_subdir = utils.get_setting('SUBDIR')
        full_name = os.path.join(thumbnail_subdir, expected_filename)
        self.assert_(
            self.storage.exists(full_name),
            'Thumbnail file %r not found' % expected_filename)
        # Verify the thumbnail has the expected dimensions
        image_f = self.storage.open(full_name)
        image = Image.open(image_f)
        self.assertEqual(image.size, expected_size)

    def testWrongArgs(self):
        # No args, or wrong number of args
        src = '{% thumbnail %}'
        self.assertRaises(TemplateSyntaxError, self.render_template, src)
        src = '{% thumbnail source %}'
        self.assertRaises(TemplateSyntaxError, self.render_template, src)
        src = '{% thumbnail source 80x80 as variable crop %}'
        self.assertRaises(TemplateSyntaxError, self.render_template, src)

    def testInvalidOption(self):
        # Invalid option
        src = '{% thumbnail source 240x200 invalid %}'
        self.assertRaises(TemplateSyntaxError, self.render_template, src)

    def testInvalidCsvOption(self):
        # Old comma separated options format can only have an = for quality
        src = '{% thumbnail source 80x80 crop=1,quality=1 %}'
        self.assertRaises(TemplateSyntaxError, self.render_template, src)

    def testInvalidQuality(self):
        # Invalid quality
        src_invalid = '{% thumbnail source 240x200 quality=invalid_q %}'
        src_missing = '{% thumbnail source 240x200 quality=missing_q %}'
        # ...with THUMBNAIL_DEBUG = False
        self.assertEqual(self.render_template(src_invalid), '')
        self.assertEqual(self.render_template(src_missing), '')
        # ...and with THUMBNAIL_DEBUG = True
        settings.THUMBNAIL_DEBUG = True
        self.assertRaises(TemplateSyntaxError, self.render_template,
                          src_invalid)
        self.assertRaises(TemplateSyntaxError, self.render_template,
                          src_missing)

    def testInvalidSource(self):
        # Invalid source
        src = '{% thumbnail invalid_source 80x80 %}'
        src_on_context = '{% thumbnail invalid_source 80x80 as thumb %}'
        # ...with THUMBNAIL_DEBUG = False
        settings.THUMBNAIL_DEBUG = False
        self.assertEqual(self.render_template(src), '')
        # ...and with THUMBNAIL_DEBUG = True
        settings.THUMBNAIL_DEBUG = True
        self.assertRaises(TemplateSyntaxError, self.render_template, src)
        self.assertRaises(TemplateSyntaxError, self.render_template,
                          src_on_context)

    def testNonexistentSource(self):
        # Non-existant source
        src = '{% thumbnail non_existant_source 80x80 %}'
        src_on_context = '{% thumbnail non_existant_source 80x80 as thumb %}'
        # ...with THUMBNAIL_DEBUG = False
        settings.THUMBNAIL_DEBUG = False
        self.assertEqual(self.render_template(src), '')
        # ...and with THUMBNAIL_DEBUG = True
        settings.THUMBNAIL_DEBUG = True
        self.assertRaises(TemplateSyntaxError, self.render_template, src)

    def testInvalidSizes(self):
        # Invalid size as a tuple:
        src = '{% thumbnail source invalid_size %}'
        # ...with THUMBNAIL_DEBUG = False
        settings.THUMBNAIL_DEBUG = False
        self.assertEqual(self.render_template(src), '')
        # ...and THUMBNAIL_DEBUG = True
        settings.THUMBNAIL_DEBUG = True
        self.assertRaises(TemplateSyntaxError, self.render_template, src)
        # Invalid size as a string:
        src = '{% thumbnail source invalid_strsize %}'
        # ...with THUMBNAIL_DEBUG = False
        settings.THUMBNAIL_DEBUG = False
        self.assertEqual(self.render_template(src), '')
        # ...and THUMBNAIL_DEBUG = True
        settings.THUMBNAIL_DEBUG = True
        self.assertRaises(TemplateSyntaxError, self.render_template, src)

    def testNonexistentSize(self):
        # Non-existant size
        src = '{% thumbnail source non_existant_size %}'
        # ...with THUMBNAIL_DEBUG = False
        settings.THUMBNAIL_DEBUG = False
        self.assertEqual(self.render_template(src), '')
        # ...and THUMBNAIL_DEBUG = True
        settings.THUMBNAIL_DEBUG = True
        self.assertRaises(TemplateSyntaxError, self.render_template, src)

    def testBasic(self):
        # Set THUMBNAIL_DEBUG = True to make it easier to trace any failures
        settings.THUMBNAIL_DEBUG = True
        thumbnail_subdir = utils.get_setting('SUBDIR')

        # Basic
        output = self.render_template('src="'
            '{% thumbnail source 240x240 %}"')
        expected = self._get_expected('240x240_q85')
        self.verify_thumbnail((240, 180), expected)
        if utils.is_storage_local(self.storage):
            expected_url = ''.join(
                (settings.MEDIA_URL, thumbnail_subdir, expected))
            self.assertEqual(output, 'src="%s"' % expected_url)
        else:
            self.assertTrue(output.find(expected) != -1)

    def testSizeFromContext(self):
        # Set THUMBNAIL_DEBUG = True to make it easier to trace any failures
        settings.THUMBNAIL_DEBUG = True
        thumbnail_subdir = utils.get_setting('SUBDIR')

        # Size from context variable
        # as a tuple:
        output = self.render_template('src="'
            '{% thumbnail source size %}"')
        expected = self._get_expected('90x100_q85')
        self.verify_thumbnail((90, 67), expected)
        if utils.is_storage_local(self.storage):
            expected_url = ''.join(
                (settings.MEDIA_URL, thumbnail_subdir, expected))
            self.assertEqual(output, 'src="%s"' % expected_url)
        else:
            self.assertTrue(output.find(expected) != -1)

    def testSizeFromContextStr(self):
        # Set THUMBNAIL_DEBUG = True to make it easier to trace any failures
        settings.THUMBNAIL_DEBUG = True
        thumbnail_subdir = utils.get_setting('SUBDIR')

        # as a string:
        output = self.render_template('src="'
            '{% thumbnail source strsize %}"')
        expected = self._get_expected('80x90_q85')
        self.verify_thumbnail((80, 60), expected)
        if utils.is_storage_local(self.storage):
            expected_url = ''.join(
                (settings.MEDIA_URL, thumbnail_subdir, expected))
            self.assertEqual(output, 'src="%s"' % expected_url)
        else:
            self.assertTrue(output.find(expected) != -1)

    def testToContext(self):
        # Set THUMBNAIL_DEBUG = True to make it easier to trace any failures
        settings.THUMBNAIL_DEBUG = True
        thumbnail_subdir = utils.get_setting('SUBDIR')

        # On context
        output = self.render_template('height:'
            '{% thumbnail source 240x240 as thumb %}{{ thumb.height }}')
        self.assertEqual(output, 'height:180')

    def testWithOptAndQual(self):
        # Set THUMBNAIL_DEBUG = True to make it easier to trace any failures
        settings.THUMBNAIL_DEBUG = True
        thumbnail_subdir = utils.get_setting('SUBDIR')

        # With options and quality
        output = self.render_template('src="'
            '{% thumbnail source 240x240 sharpen crop quality=95 %}"')
        # Note that the opts are sorted to ensure a consistent filename.
        expected = self._get_expected('240x240_q95_crop_sharpen')
        self.verify_thumbnail((240, 240), expected)
        if utils.is_storage_local(self.storage):
            expected_url = ''.join(
                (settings.MEDIA_URL, thumbnail_subdir, expected))
            self.assertEqual(output, 'src="%s"' % expected_url)
        else:
            self.assertTrue(output.find(expected) != -1)

    def testWithOptQualToContext(self):
        # Set THUMBNAIL_DEBUG = True to make it easier to trace any failures
        settings.THUMBNAIL_DEBUG = True
        thumbnail_subdir = utils.get_setting('SUBDIR')

        # With option and quality on context (also using its unicode method to
        # display the url)
        output = self.render_template(
            '{% thumbnail source 240x240 sharpen crop quality=95 as thumb %}'
            'width:{{ thumb.width }}, url:{{ thumb.url }}')
        expected = self._get_expected('240x240_q95_crop_sharpen')
        if utils.is_storage_local(self.storage):
            expected_url = ''.join(
                (settings.MEDIA_URL, thumbnail_subdir, expected))
            self.assertEqual(output, 'width:240, url:%s' % expected_url)
        else:
            self.assertTrue(output.find(expected) != -1)
            self.assertTrue(output.find('width:240') != -1)

    def testBasicCached(self):
        # Set THUMBNAIL_DEBUG = True to make it easier to trace any failures
        settings.THUMBNAIL_DEBUG = True
        thumbnail_subdir = utils.get_setting('SUBDIR')

        self.assertEqual(Thumbnail.objects.all().count(), 0)
        # Basic
        output = self.render_template('src="'
            '{% thumbnail source 240x240 %}"')
        expected = self._get_expected('240x240_q85')
        self.verify_thumbnail((240, 180), expected)
        if utils.is_storage_local(self.storage):
            expected_url = ''.join(
                (settings.MEDIA_URL, thumbnail_subdir, expected))
            self.assertEqual(output, 'src="%s"' % expected_url)
        else:
            self.assertTrue(output.find(expected) != -1)

        # Added one thumbnail
        self.assertEqual(Thumbnail.objects.all().count(), 1)

        # Render the same thumbnail
        output = self.render_template('src="'
            '{% thumbnail source 240x240 %}"')
        self.verify_thumbnail((240, 180), expected)
        if utils.is_storage_local(self.storage):
            self.assertEqual(output, 'src="%s"' % expected_url)
        else:
            self.assertTrue(output.find(expected) != -1)

        # Ensure that we didn't add another thumbnail to the cache
        self.assertEqual(Thumbnail.objects.all().count(), 1)

class BlankRemoteThumbnailTest(BlankThumbnailTest):
    RELATIVE_PIC_NAME = 'test.jpg'
    STORAGE_BACKEND = FakeRemoteStorage
    restore_settings = ['THUMBNAIL_DEBUG']


class BlankDefaultfsThumbnailTest(BlankThumbnailTest):
    RELATIVE_PIC_NAME = 'test.jpg'
    STORAGE_BACKEND =default_storage_cls
    restore_settings = ['THUMBNAIL_DEBUG']

    def _cleanup_storage(self):
        pass


class TransparentPngThumbnailTest(BlankThumbnailTest):
    RELATIVE_PIC_NAME = 'test.png'
    STORAGE_BACKEND = TemporaryStorage
    THUMBNAIL_EXT = 'png'
    restore_settings = ['THUMBNAIL_DEBUG']

    def _create_test_image(self):
        # Save a test transparent png
        img_path = os.path.join(ET_FIXTURES_DIR, TRANS_PNG)
        with open(img_path, 'rb') as img_f:
            data = img_f.read()
        image_f = ContentFile(data)

        return image_f


class TransparentPngRemoteThumbnailTest(BlankThumbnailTest):
    RELATIVE_PIC_NAME = 'test.png'
    STORAGE_BACKEND = FakeRemoteStorage
    THUMBNAIL_EXT = 'png'
    restore_settings = ['THUMBNAIL_DEBUG']

    def _create_test_image(self):
        # Save a test transparent png
        img_path = os.path.join(ET_FIXTURES_DIR, TRANS_PNG)
        with open(img_path, 'rb') as img_f:
            data = img_f.read()
        image_f = ContentFile(data)

        return image_f


class TransparentDefaultfsThumbnailTest(BlankThumbnailTest):
    RELATIVE_PIC_NAME = 'test.png'
    STORAGE_BACKEND = default_storage_cls
    THUMBNAIL_EXT = 'png'
    restore_settings = ['THUMBNAIL_DEBUG']

    def _create_test_image(self):
        # Save a test transparent png
        img_path = os.path.join(ET_FIXTURES_DIR, TRANS_PNG)
        with open(img_path, 'rb') as img_f:
            data = img_f.read()
        image_f = ContentFile(data)

        return image_f

    def _cleanup_storage(self):
        pass


class OpaquePngThumbnailTest(BlankThumbnailTest):
    RELATIVE_PIC_NAME = 'test.png'
    STORAGE_BACKEND = TemporaryStorage
    restore_settings = ['THUMBNAIL_DEBUG']

    def _create_test_image(self):
        # Save a test transparent png
        img_path = os.path.join(ET_FIXTURES_DIR, OPAQUE_PNG)
        with open(img_path, 'rb') as img_f:
            data = img_f.read()
        image_f = ContentFile(data)

        return image_f


class OpaquePngRemoteThumbnailTest(BlankThumbnailTest):
    RELATIVE_PIC_NAME = 'test.png'
    STORAGE_BACKEND = FakeRemoteStorage
    restore_settings = ['THUMBNAIL_DEBUG']

    def _create_test_image(self):
        # Save a test transparent png
        img_path = os.path.join(ET_FIXTURES_DIR, OPAQUE_PNG)
        with open(img_path, 'rb') as img_f:
            data = img_f.read()
        image_f = ContentFile(data)

        return image_f


class OpaquePngDefaultfsThumbnailTest(BlankThumbnailTest):
    RELATIVE_PIC_NAME = 'test.png'
    STORAGE_BACKEND = default_storage_cls
    restore_settings = ['THUMBNAIL_DEBUG']

    def _create_test_image(self):
        # Save a test transparent png
        img_path = os.path.join(ET_FIXTURES_DIR, OPAQUE_PNG)
        with open(img_path, 'rb') as img_f:
            data = img_f.read()
        image_f = ContentFile(data)

        return image_f

    def _cleanup_storage(self):
        pass


