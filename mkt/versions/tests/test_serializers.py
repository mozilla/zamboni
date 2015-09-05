from django.core.urlresolvers import reverse
from django.test.client import RequestFactory

from nose.tools import eq_, ok_

from mkt.site.tests import app_factory, TestCase
from mkt.versions.models import Version
from mkt.versions.serializers import VersionSerializer


class TestVersionSerializer(TestCase):
    def setUp(self):
        self.app = app_factory()
        self.features = self.app.current_version.features
        self.request = RequestFactory().get('/')
        self.serializer = VersionSerializer(context={'request': self.request})

    def native(self, obj=None, **kwargs):
        if not obj:
            obj = self.app.current_version
        obj.update(**kwargs)
        return self.serializer.to_native(obj)

    def test_renamed_fields(self):
        native = self.native()
        removed_keys = self.serializer.Meta.field_rename.keys()
        added_keys = self.serializer.Meta.field_rename.values()
        ok_(all(k not in native for k in removed_keys))
        ok_(all(k in native for k in added_keys))

    def test_webapp(self):
        eq_(self.native()['app'], reverse('app-detail',
                                          kwargs={'pk': self.app.pk}))

    def test_is_current_version(self):
        old_version = Version.objects.create(webapp=self.app, version='0.1')
        ok_(self.native()['is_current_version'])
        ok_(not self.native(obj=old_version)['is_current_version'])

    def test_features(self, **kwargs):
        if kwargs:
            self.features.update(**kwargs)
        native = self.native()
        for key in dir(self.features):
            if key.startswith('has_') and getattr(self.features, key):
                ok_(key.replace('has_', '') in native['features'])

    def test_features_updated(self):
        self.test_features(has_fm=True)
