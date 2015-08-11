# -*- coding: utf-8 -*-
from django.contrib.auth.models import AnonymousUser
from django.test.client import RequestFactory

from nose.tools import eq_

import mkt
import mkt.site.tests
from mkt.fireplace.serializers import FireplaceAppSerializer
from mkt.site.fixtures import fixture
from mkt.users.models import UserProfile


class TestFireplaceAppSerializer(mkt.site.tests.TestCase):
    fixtures = fixture('user_2519')

    def setUp(self):
        self.creation_date = self.days_ago(1)
        self.app = mkt.site.tests.app_factory(
            version_kw={'version': '1.8'}, created=self.creation_date)
        self.profile = UserProfile.objects.get(pk=2519)
        self.request = RequestFactory().get('/')

    def serialize(self, app, profile=None):
        self.request.user = profile if profile else AnonymousUser()
        a = FireplaceAppSerializer(instance=app,
                                   context={'request': self.request})
        return a.data

    def test_promo_imgs(self):
        res = self.serialize(self.app)
        eq_(res['promo_imgs'],
            dict([(promo_img_size, self.app.get_promo_img_url(promo_img_size))
                  for promo_img_size in mkt.PROMO_IMG_SIZES]))
