import os

from django.conf import settings
from django.core.management import call_command

import mock
from nose.tools import eq_, ok_

from mkt.site.tests import TestCase
from mkt.websites.models import Website


class TestImportGamesFromCSV(TestCase):
    def setUp(self):
        path = os.path.dirname(os.path.abspath(__file__))
        self.filename = '%s/files/games.csv' % path

    def _get_requests_mock(self, is_icon=False):
        img_filename = 'mkt_icon_72.png' if is_icon else 'game_1050.jpg'
        img_path = os.path.join(settings.ROOT, 'mkt', 'site', 'tests',
                                'images', img_filename)
        with open(img_path, 'r') as content:
            content = content.read()
            return mock.Mock(
                content=content,
                iter_content=mock.Mock(
                    return_value=mock.Mock(
                        next=mock.Mock(return_value=content))),
                headers={'ok': 'ok'},
                status_code=200)

    def _requests_side_effect(self, url, **kw):
        return self._get_requests_mock(is_icon='icon' in url)

    @mock.patch('mkt.developers.tasks.pngcrush_image')
    @mock.patch('mkt.developers.tasks.requests.get')
    def test_import(self, requests_mock, crush_mock):
        requests_mock.side_effect = self._requests_side_effect

        call_command('import_games_from_csv', self.filename)
        eq_(Website.objects.count(), 2)

        cycleblob = Website.objects.get(name__localized_string='Cycleblob')
        eq_(cycleblob.url, 'http://cycleblob.com/')
        eq_(cycleblob.keywords.count(), 2)
        ok_(cycleblob.keywords.get(tag_text='featured-game'))
        ok_(cycleblob.keywords.get(tag_text='featured-game-strategy'))
        ok_(cycleblob.description)
        ok_(cycleblob.icon_hash)
        ok_(cycleblob.promo_img_hash)

        dt2 = Website.objects.get(name__localized_string='Dead Trigger 2')
        eq_(dt2.keywords.count(), 2)
        ok_(dt2.keywords.get(tag_text='featured-game'))
        ok_(dt2.keywords.get(tag_text='featured-game-action'))
        ok_(dt2.description)
        ok_(dt2.icon_hash)
        ok_(dt2.promo_img_hash)

    @mock.patch('mkt.developers.tasks.pngcrush_image')
    @mock.patch('mkt.developers.tasks.requests.get')
    def test_no_dupes(self, requests_mock, crush_mock):
        requests_mock.side_effect = self._requests_side_effect

        call_command('import_games_from_csv', self.filename)
        call_command('import_games_from_csv', self.filename)
        eq_(Website.objects.count(), 2)
