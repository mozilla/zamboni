import os
import json

from django.core.urlresolvers import reverse

import mock
from nose.tools import eq_, ok_

import mkt.regions
import mkt.carriers
from lib.crypto import packaged
from lib.crypto.tests import mock_sign
from mkt.api.tests.test_oauth import RestOAuth
from mkt.extensions.models import Extension
from mkt.operators.models import OperatorPermission
from mkt.site.fixtures import fixture
from mkt.site.tests import app_factory
from mkt.site.storage_utils import private_storage
from mkt.latecustomization.models import LateCustomizationItem


def make_packaged_app():
    ap = app_factory()
    ap.update(is_packaged=True)
    f = ap.latest_version.all_files[0]
    fp = os.path.join(ap.latest_version.path_prefix, f.filename)
    with private_storage.open(fp, 'w') as out:
        out.write('.')
    return ap


class TestLateCustomization(RestOAuth):
    fixtures = fixture('user_2519')

    @mock.patch.object(packaged, 'sign', mock_sign)
    def create_apps_extensions(self):
        apps = []
        extensions = []
        for r, c in (('de', 'deutsche_telekom'), ('jp', 'kddi')):
            for _ in range(3):
                ap = make_packaged_app()
                apps.append(ap)
                LateCustomizationItem.objects.create(
                    app=ap, region=mkt.regions.REGIONS_DICT[r].id,
                    carrier=mkt.carriers.CARRIER_MAP[c].id)

        for r, c in (('de', 'deutsche_telekom'), ('jp', 'kddi')):
            for i in range(3):
                e = Extension.objects.create(name="Ext %s" % i)
                extensions.append(e)
                LateCustomizationItem.objects.create(
                    extension=e, region=mkt.regions.REGIONS_DICT[r].id,
                    carrier=mkt.carriers.CARRIER_MAP[c].id)

        return apps, extensions

    def check_list_data(self, data, apps, extensions):
        for result, a in zip(data['objects'][:3], apps[:3]):
            eq_(result['slug'], a.app_slug)
            eq_(result['id'], a.pk)
            eq_(result['latecustomization_type'], 'webapp')
            eq_(result['latecustomization_id'],
                LateCustomizationItem.objects.get(app=a).pk)
            eq_(result['manifest_url'],
                'http://testserver/app/%s/manifest.webapp' % (a.guid,))

        for result, e in zip(data['objects'][3:], extensions[:3]):
            eq_(result['slug'], e.slug)
            eq_(result['id'], e.pk)
            eq_(result['latecustomization_type'], 'extension')
            eq_(result['latecustomization_id'],
                LateCustomizationItem.objects.get(extension=e).pk)
            eq_(result['mini_manifest_url'], e.mini_manifest_url)

    def test_list(self):
        apps, extensions = self.create_apps_extensions()
        res = self.anon.get(reverse('api-v2:late-customization-list'),
                            {'region': 'de',
                             'carrier': 'deutsche_telekom'})
        eq_(res.status_code, 200)
        data = json.loads(res.content)
        eq_(len(data['objects']), 6)
        self.check_list_data(data, apps, extensions)

    def test_list_mcc(self):
        apps, extensions = self.create_apps_extensions()
        res = self.anon.get(reverse('api-v2:late-customization-list'),
                            {'mcc': 262,
                             'mnc': 2})
        eq_(res.status_code, 200)
        data = json.loads(res.content)
        eq_(len(data['objects']), 6)
        self.check_list_data(data, apps, extensions)

    def test_create(self):
        OperatorPermission.objects.create(user=self.user, region=14, carrier=4)
        ap = make_packaged_app()
        res = self.client.post(reverse('api-v2:late-customization-list'),
                               data=json.dumps(
                                   {'type': 'webapp', 'app': ap.pk,
                                    'region': 'de',
                                    'carrier': 'deutsche_telekom'}))
        eq_(res.status_code, 201)
        ok_(LateCustomizationItem.objects.filter(
            app_id=ap.pk, region=14, carrier=4).exists())

    def test_create_forbidden(self):
        res = self.client.post(reverse('api-v2:late-customization-list'),
                               data=json.dumps(
                                   {'app': 337141, 'region': 'de',
                                    'carrier': 'deutsche_telekom'}))
        eq_(res.status_code, 403)

    def test_delete(self):
        ap = make_packaged_app()
        OperatorPermission.objects.create(user=self.user, region=14, carrier=4)
        lci = LateCustomizationItem.objects.create(app_id=ap.pk, region=14,
                                                   carrier=4)
        res = self.client.delete(
            reverse('api-v2:late-customization-detail', kwargs={'pk': lci.pk}))
        eq_(res.status_code, 204)

    def test_delete_forbidden(self):
        ap = make_packaged_app()
        lci = LateCustomizationItem.objects.create(app_id=ap.pk, region=14,
                                                   carrier=4)
        res = self.client.delete(
            reverse('api-v2:late-customization-detail', kwargs={'pk': lci.pk}))
        eq_(res.status_code, 403)
        ok_(LateCustomizationItem.objects.filter(app_id=ap.pk, region=14,
                                                 carrier=4).exists())

    def test_delete_wrong_operator_forbidden(self):
        ap = make_packaged_app()
        OperatorPermission.objects.create(user=self.user, region=14,
                                          carrier=20)
        lci = LateCustomizationItem.objects.create(app_id=ap.pk, region=14,
                                                   carrier=4)
        res = self.client.delete(
            reverse('api-v2:late-customization-detail', kwargs={'pk': lci.pk}))
        eq_(res.status_code, 403)
        ok_(LateCustomizationItem.objects.filter(app_id=ap.pk, region=14,
                                                 carrier=4).exists())
