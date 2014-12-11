from os import path

from django.conf import settings

import amo.tests
from amo.utils import ImageCheck


def get_image_path(name):
    return path.join(settings.ROOT, 'apps', 'amo', 'tests', 'images', name)


class TestAnimatedImages(amo.tests.TestCase):

    def test_animated_images(self):
        img = ImageCheck(open(get_image_path('animated.png')))
        assert img.is_animated()
        img = ImageCheck(open(get_image_path('non-animated.png')))
        assert not img.is_animated()

        img = ImageCheck(open(get_image_path('animated.gif')))
        assert img.is_animated()
        img = ImageCheck(open(get_image_path('non-animated.gif')))
        assert not img.is_animated()

    def test_junk(self):
        img = ImageCheck(open(__file__, 'rb'))
        assert not img.is_image()
        img = ImageCheck(open(get_image_path('non-animated.gif')))
        assert img.is_image()
