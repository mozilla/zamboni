from django import http
from django.core.exceptions import PermissionDenied

import mock
from nose.tools import eq_
from test_utils import RequestFactory

import amo.tests
from mkt.webapps import decorators as dec
from mkt.webapps.models import Webapp


class TestWebappDecorators(amo.tests.TestCase):

    def setUp(self):
        self.app = Webapp.objects.create(slug='x')
        self.func = mock.Mock()
        self.func.return_value = mock.sentinel.OK
        self.func.__name__ = 'mock_function'
        self.view = dec.app_view(self.func)
        self.request = mock.Mock()
        self.slug_path = '/app/%s/reviews' % self.app.app_slug
        self.request.path = self.id_path = '/app/%s/reviews' % self.app.id
        self.request.GET = {}

    def test_301_by_id(self):
        res = self.view(self.request, str(self.app.id))
        self.assert3xx(res, self.slug_path, 301)

    def test_slug_replace_no_conflict(self):
        self.request.path = '/app/{id}/reviews/{id}345/path'.format(
            id=self.app.id)
        res = self.view(self.request, str(self.app.id))
        self.assert3xx(res, '/app/{slug}/reviews/{id}345/path'.format(
            id=self.app.id, slug=self.app.app_slug), 301)

    def test_301_with_querystring(self):
        self.request.GET = mock.Mock()
        self.request.GET.urlencode.return_value = 'q=1'
        res = self.view(self.request, str(self.app.id))
        self.assert3xx(res, self.slug_path + '?q=1', 301)

    def test_200_by_slug(self):
        res = self.view(self.request, self.app.app_slug)
        eq_(res, mock.sentinel.OK)

    def test_404_by_id(self):
        with self.assertRaises(http.Http404):
            self.view(self.request, str(self.app.id * 2))

    def test_404_by_slug(self):
        with self.assertRaises(http.Http404):
            self.view(self.request, self.app.slug + 'xx')

    def test_alternate_qs_301_by_id(self):
        qs = lambda: Webapp.objects.all()
        view = dec.app_view_factory(qs=qs)(self.func)
        res = view(self.request, str(self.app.id))
        self.assert3xx(res, self.slug_path, 301)

    def test_alternate_qs_200_by_slug(self):
        qs = lambda: Webapp.objects.all()
        view = dec.app_view_factory(qs=qs)(self.func)
        res = view(self.request, self.app.app_slug)
        eq_(res, mock.sentinel.OK)

    def test_alternate_qs_404_by_id(self):
        qs = lambda: Webapp.objects.filter(status=amo.STATUS_DELETED)
        view = dec.app_view_factory(qs=qs)(self.func)
        with self.assertRaises(http.Http404):
            view(self.request, str(self.app.id))

    def test_alternate_qs_404_by_slug(self):
        qs = lambda: Webapp.objects.filter(status=amo.STATUS_DELETED)
        view = dec.app_view_factory(qs=qs)(self.func)
        with self.assertRaises(http.Http404):
            view(self.request, self.app.slug)

    def test_app_no_slug(self):
        app = Webapp.objects.create(name='xxxx')
        res = self.view(self.request, app.app_slug)
        eq_(res, mock.sentinel.OK)

    def test_slug_isdigit(self):
        app = Webapp.objects.create(name='xxxx')
        app.update(app_slug=str(app.id))
        r = self.view(self.request, app.app_slug)
        eq_(r, mock.sentinel.OK)
        request, addon = self.func.call_args[0]
        eq_(addon, app)

    def test_app(self):
        app = amo.tests.app_factory(name='xxxx')
        app.update(slug=str(app.id) + 'foo', app_slug=str(app.id))
        res = self.view(self.request, app_slug=str(app.id))
        eq_(res, mock.sentinel.OK)
        eq_(self.func.call_args[0][1].type, amo.ADDON_WEBAPP)


class TestPremiumDecorators(amo.tests.TestCase):

    def setUp(self):
        self.addon = mock.Mock(pk=1)
        self.func = mock.Mock()
        self.func.return_value = True
        self.func.__name__ = 'mock_function'
        self.request = RequestFactory().get('/')
        self.request.user = mock.Mock()

    def test_cant_become_premium(self):
        self.addon.can_become_premium.return_value = False
        view = dec.can_become_premium(self.func)
        with self.assertRaises(PermissionDenied):
            view(self.request, self.addon.pk, self.addon)

    def test_can_become_premium(self):
        self.addon.can_become_premium.return_value = True
        view = dec.can_become_premium(self.func)
        eq_(view(self.request, self.addon.pk, self.addon), True)

    def test_has_purchased(self):
        view = dec.has_purchased(self.func)
        self.addon.is_premium.return_value = True
        self.addon.has_purchased.return_value = True
        eq_(view(self.request, self.addon), True)

    def test_has_purchased_failure(self):
        view = dec.has_purchased(self.func)
        self.addon.is_premium.return_value = True
        self.addon.has_purchased.return_value = False
        with self.assertRaises(PermissionDenied):
            view(self.request, self.addon)
