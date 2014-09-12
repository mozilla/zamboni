import tempfile

from .utils import VideoBase


class Video(VideoBase):
    """Used for testing."""

    @classmethod
    def library_available(cls):
        return True

    def is_valid(self):
        return self.filename.endswith('.webm')

    def get_encoded(self, size):
        return tempfile.mkstemp()[1]

    def get_screenshot(self, size):
        return tempfile.mkstemp()[1]
