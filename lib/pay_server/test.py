import datetime
import json

from django.conf import settings
from django.test import TestCase

from mock import patch
from nose.tools import eq_

from lib.pay_server import filter_encoder, model_to_uid, ZamboniEncoder
from mkt.webapps.models import Webapp
from mkt.users.models import UserProfile


@patch.object(settings, 'SOLITUDE_HOSTS', ('http://localhost'))
@patch.object(settings, 'DOMAIN', 'testy')
class TestUtils(TestCase):

    def setUp(self):
        self.user = UserProfile.objects.create()
        self.addon = Webapp.objects.create()

    def test_uid(self):
        eq_(model_to_uid(self.user), 'testy:users:%s' % self.user.pk)

    def test_encoder(self):
        today = datetime.date.today()
        res = json.loads(json.dumps({'uuid': self.user, 'date': today},
                                    cls=ZamboniEncoder))
        eq_(res['uuid'], 'testy:users:%s' % self.user.pk)
        eq_(res['date'], today.strftime('%Y-%m-%d'))

    def test_filter_encoder(self):
        eq_(filter_encoder({'uuid': self.user, 'bar': 'bar'}),
            'bar=bar&uuid=testy%%3Ausers%%3A%s' % self.user.pk)
