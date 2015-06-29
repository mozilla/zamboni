import os
import stat
import tempfile

from mock import Mock, patch
from nose import SkipTest
from nose.tools import eq_
import waffle

from django.conf import settings

import mkt
import mkt.site.tests
from lib.video import dummy, ffmpeg, get_library, totem
from lib.video.tasks import resize_video
from mkt.developers.models import UserLog
from mkt.site.fixtures import fixture
from mkt.site.tests.test_utils_ import get_image_path
from mkt.users.models import UserProfile
from mkt.webapps.models import Preview, Webapp


files = {
    'good': os.path.join(os.path.dirname(__file__),
                         'fixtures/disco-truncated.webm'),
    'bad': get_image_path('mozilla.png'),
}

older_output = """
Input #0, matroska,webm, from 'lib/video/fixtures/disco-truncated.webm':
  Duration: 00:00:10.00, start: 0.000000, bitrate: 298 kb/s
    Stream #0:0(eng): Video: vp8, yuv420p, 640x360, SAR 1:1 DAR 16:9,
    Stream #0:1(eng): Audio: vorbis, 44100 Hz, stereo, s16 (default)
"""

other_output = """
Input #0, matroska, from 'disco-truncated.webm':
  Metadata:
    doctype         : webm
"""

totem_indexer_good = """
TOTEM_INFO_DURATION=10
TOTEM_INFO_HAS_VIDEO=True
TOTEM_INFO_VIDEO_WIDTH=640
TOTEM_INFO_VIDEO_HEIGHT=360
TOTEM_INFO_VIDEO_CODEC=VP8 video
TOTEM_INFO_FPS=25
TOTEM_INFO_HAS_AUDIO=True
TOTEM_INFO_AUDIO_BITRATE=128
TOTEM_INFO_AUDIO_CODEC=Vorbis
TOTEM_INFO_AUDIO_SAMPLE_RATE=44100
TOTEM_INFO_AUDIO_CHANNELS=Stereo
"""

totem_indexer_bad = """
TOTEM_INFO_HAS_VIDEO=False
TOTEM_INFO_HAS_AUDIO=False
"""


class TestFFmpegVideo(mkt.site.tests.TestCase):

    def setUp(self):
        self.video = ffmpeg.Video(files['good'])
        if not ffmpeg.Video.library_available():
            raise SkipTest
        self.video._call = Mock()
        self.video._call.return_value = older_output

    def test_meta(self):
        self.video.get_meta()
        eq_(self.video.meta['formats'], ['matroska', 'webm'])
        eq_(self.video.meta['duration'], 10.0)
        eq_(self.video.meta['dimensions'], (640, 360))

    def test_valid(self):
        self.video.get_meta()
        assert self.video.is_valid()

    def test_dev_valid(self):
        self.video._call.return_value = other_output
        self.video.get_meta()
        eq_(self.video.meta['formats'], ['webm'])

    # These tests can be a little bit slow, to say the least so they are
    # skipped. Un-skip them if you want.
    def test_screenshot(self):
        raise SkipTest
        self.video.get_meta()
        try:
            screenshot = self.video.get_screenshot(mkt.ADDON_PREVIEW_SIZES[0])
            assert os.stat(screenshot)[stat.ST_SIZE]
        finally:
            os.remove(screenshot)

    def test_encoded(self):
        raise SkipTest
        self.video.get_meta()
        try:
            video = self.video.get_encoded(mkt.ADDON_PREVIEW_SIZES[0])
            assert os.stat(video)[stat.ST_SIZE]
        finally:
            os.remove(video)


class TestBadFFmpegVideo(mkt.site.tests.TestCase):

    def setUp(self):
        self.video = ffmpeg.Video(files['bad'])
        if not self.video.library_available():
            raise SkipTest
        self.video.get_meta()

    def test_meta(self):
        eq_(self.video.meta['formats'], ['image2'])
        assert not self.video.is_valid()

    def test_valid(self):
        assert not self.video.is_valid()

    def test_screenshot(self):
        self.assertRaises(AssertionError, self.video.get_screenshot,
                          mkt.ADDON_PREVIEW_SIZES[0])

    def test_encoded(self):
        self.assertRaises(AssertionError, self.video.get_encoded,
                          mkt.ADDON_PREVIEW_SIZES[0])


class TestTotemVideo(mkt.site.tests.TestCase):

    def setUp(self):
        self.video = totem.Video(files['good'])
        self.video._call_indexer = Mock()

    def test_meta(self):
        self.video._call_indexer.return_value = totem_indexer_good
        self.video.get_meta()
        eq_(self.video.meta['formats'], 'VP8')
        eq_(self.video.meta['duration'], '10')

    def test_valid(self):
        self.video._call_indexer = Mock()
        self.video._call_indexer.return_value = totem_indexer_good
        self.video.get_meta()
        assert self.video.is_valid()

    def test_not_valid(self):
        self.video._call_indexer.return_value = totem_indexer_bad
        self.video.get_meta()
        assert not self.video.is_valid()


@patch('lib.video.totem.Video.library_available')
@patch('lib.video.ffmpeg.Video.library_available')
@patch.object(settings, 'VIDEO_LIBRARIES',
              ['lib.video.totem', 'lib.video.ffmpeg'])
def test_choose(ffmpeg_, totem_):
    ffmpeg_.return_value = True
    totem_.return_value = True
    eq_(get_library(), totem.Video)
    totem_.return_value = False
    eq_(get_library(), ffmpeg.Video)
    ffmpeg_.return_value = False
    eq_(get_library(), None)


class TestTask(mkt.site.tests.TestCase):
    fixtures = fixture('webapp_337141')

    def setUp(self):
        waffle.models.Switch.objects.create(name='video-encode', active=True)
        self.app = Webapp.objects.get(pk=337141)
        self.preview = Preview.objects.create(
            addon=self.app, thumbnail_path=tempfile.mkstemp()[1],
            image_path=tempfile.mkstemp()[1])

    @patch('lib.video.tasks.Preview.delete')
    @patch('lib.video.tasks._resize_video')
    def test_resize_error(self, _resize_video, _preview_delete):
        user = UserProfile.objects.create(email='a@a.com')
        _resize_video.side_effect = ValueError
        with self.assertRaises(ValueError):
            resize_video(files['good'], self.preview.pk, user_pk=user.pk,
                         lib=dummy.Video)
        assert _preview_delete.called
        assert UserLog.objects.filter(
            user=user, activity_log__action=mkt.LOG.VIDEO_ERROR.id).exists()

    @patch('lib.video.tasks.Preview.delete')
    @patch('lib.video.tasks._resize_video')
    def test_resize_failed(self, _resize_video, _preview_delete):
        user = UserProfile.objects.create(email='a@a.com')
        _resize_video.return_value = None
        resize_video(files['good'], self.preview.pk, user_pk=user.pk,
                     lib=dummy.Video)
        assert _preview_delete.called

    @patch('lib.video.tasks.Preview.save')
    @patch('lib.video.ffmpeg.Video.get_encoded')
    def test_resize_video_no_encode(self, get_encoded, _preview_save):
        waffle.models.Switch.objects.update(name='video-encode', active=False)
        resize_video(files['good'], self.preview.pk, lib=dummy.Video)
        assert not get_encoded.called
        assert _preview_save.called

    @patch('lib.video.tasks.Preview.save')
    @patch('lib.video.totem.Video.get_encoded')
    def test_resize_video(self, get_encoded, _preview_save):
        name = tempfile.mkstemp()[1]
        get_encoded.return_value = name
        resize_video(files['good'], self.preview.pk, lib=dummy.Video)
        mode = oct(os.stat(self.preview.image_path)[stat.ST_MODE])
        assert mode.endswith('644'), mode
        assert _preview_save.called

    @patch('lib.video.tasks.Preview.save')
    def test_resize_image(self, _preview_save):
        resize_video(files['bad'], self.preview.pk, lib=dummy.Video)
        eq_(self.preview.sizes, {})
        assert not _preview_save.called
