from django.conf import settings
from django.core.files.base import ContentFile
from django.template import Template, Context, TemplateSyntaxError
from easy_thumbnails.tests.utils import BaseTest, TemporaryStorage
import os.path, urllib2, shutil
from tempfile import NamedTemporaryFile
try:
    from PIL import Image
except ImportError:
    import Image
from StringIO import StringIO
from easy_thumbnails.files import get_thumbnailer
from easy_thumbnails import utils


class ThumbnailTagTest(BaseTest):
    RELATIVE_PIC_NAME = 'test.jpg'
    restore_settings = ['THUMBNAIL_DEBUG']

    def setUp(self):
        BaseTest.setUp(self)
        from backends.s3boto import S3BotoStorage
        self.storage = S3BotoStorage()
        # Save a test image.
        data = StringIO()
        Image.new('RGB', (800, 600)).save(data, 'JPEG')
        data.seek(0)
        image_file = ContentFile(data.read())
        self.storage.save(self.RELATIVE_PIC_NAME, image_file)

    def tearDown(self):
        #self.storage.delete_temporary_storage()
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
        if utils.is_storage_local(self.storage):
            image_f = self.storage.open(full_name)
        else:
            image_f = StringIO()
            remote_image_f = urllib2.urlopen(self.storage.url(full_name))
            image_f.write(remote_image_f.read())
            image_f.seek(0)
        image = Image.open(image_f)
        self.assertEqual(image.size, expected_size)

    def testTagInvalid(self):
        # No args, or wrong number of args
        src = '{% thumbnail %}'
        self.assertRaises(TemplateSyntaxError, self.render_template, src)
        src = '{% thumbnail source %}'
        self.assertRaises(TemplateSyntaxError, self.render_template, src)
        src = '{% thumbnail source 80x80 as variable crop %}'
        self.assertRaises(TemplateSyntaxError, self.render_template, src)

        # Invalid option
        src = '{% thumbnail source 240x200 invalid %}'
        self.assertRaises(TemplateSyntaxError, self.render_template, src)

        # Old comma separated options format can only have an = for quality
        src = '{% thumbnail source 80x80 crop=1,quality=1 %}'
        self.assertRaises(TemplateSyntaxError, self.render_template, src)

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

        # Non-existant source
        src = '{% thumbnail non_existant_source 80x80 %}'
        src_on_context = '{% thumbnail non_existant_source 80x80 as thumb %}'
        # ...with THUMBNAIL_DEBUG = False
        settings.THUMBNAIL_DEBUG = False
        self.assertEqual(self.render_template(src), '')
        # ...and with THUMBNAIL_DEBUG = True
        settings.THUMBNAIL_DEBUG = True
        self.assertRaises(TemplateSyntaxError, self.render_template, src)

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

        # Non-existant size
        src = '{% thumbnail source non_existant_size %}'
        # ...with THUMBNAIL_DEBUG = False
        settings.THUMBNAIL_DEBUG = False
        self.assertEqual(self.render_template(src), '')
        # ...and THUMBNAIL_DEBUG = True
        settings.THUMBNAIL_DEBUG = True
        self.assertRaises(TemplateSyntaxError, self.render_template, src)

    def testTag(self):
        # Set THUMBNAIL_DEBUG = True to make it easier to trace any failures
        settings.THUMBNAIL_DEBUG = True

        # Basic
        output = self.render_template('src="'
            '{% thumbnail source 240x240 %}"')
        expected = '%s.240x240_q85.jpg' % self.RELATIVE_PIC_NAME
        self.verify_thumbnail((240, 180), expected)
        if utils.is_storage_local(self.storage):
            expected_url = ''.join((settings.MEDIA_URL, expected))
            self.assertEqual(output, 'src="%s"' % expected_url)
        else:
            self.assertTrue(output.find(expected) != -1)

        # Size from context variable
        # as a tuple:
        output = self.render_template('src="'
            '{% thumbnail source size %}"')
        expected = '%s.90x100_q85.jpg' % self.RELATIVE_PIC_NAME
        self.verify_thumbnail((90, 67), expected)
        if utils.is_storage_local(self.storage):
            expected_url = ''.join((settings.MEDIA_URL, expected))
            self.assertEqual(output, 'src="%s"' % expected_url)
        else:
            self.assertTrue(output.find(expected) != -1)

        # as a string:
        output = self.render_template('src="'
            '{% thumbnail source strsize %}"')
        expected = '%s.80x90_q85.jpg' % self.RELATIVE_PIC_NAME
        self.verify_thumbnail((80, 60), expected)
        if utils.is_storage_local(self.storage):
            expected_url = ''.join((settings.MEDIA_URL, expected))
            self.assertEqual(output, 'src="%s"' % expected_url)
        else:
            self.assertTrue(output.find(expected) != -1)

        # On context
        output = self.render_template('height:'
            '{% thumbnail source 240x240 as thumb %}{{ thumb.height }}')
        self.assertEqual(output, 'height:180')

        # With options and quality
        output = self.render_template('src="'
            '{% thumbnail source 240x240 sharpen crop quality=95 %}"')
        # Note that the opts are sorted to ensure a consistent filename.
        expected = '%s.240x240_q95_crop_sharpen.jpg' % self.RELATIVE_PIC_NAME
        self.verify_thumbnail((240, 240), expected)
        if utils.is_storage_local(self.storage):
            expected_url = ''.join((settings.MEDIA_URL, expected))
            self.assertEqual(output, 'src="%s"' % expected_url)
        else:
            self.assertTrue(output.find(expected) != -1)

        # With option and quality on context (also using its unicode method to
        # display the url)
        output = self.render_template(
            '{% thumbnail source 240x240 sharpen crop quality=95 as thumb %}'
            'width:{{ thumb.width }}, url:{{ thumb.url }}')
        if utils.is_storage_local(self.storage):
            expected_url = ''.join((settings.MEDIA_URL, expected))
            self.assertEqual(output, 'width:240, url:%s' % expected_url)
        else:
            self.assertTrue(output.find(expected) != -1)
            self.assertTrue(output.find('width:240') != -1)