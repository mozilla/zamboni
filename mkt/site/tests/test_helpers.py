# -*- coding: utf-8 -*-
from django.conf import settings

import fudge
import mock
from nose.tools import eq_

import amo
import amo.tests
from mkt.site.helpers import css, js, product_as_dict
from mkt.site.fixtures import fixture
from mkt.webapps.models import Webapp


class TestCSS(amo.tests.TestCase):

    @mock.patch.object(settings, 'TEMPLATE_DEBUG', True)
    @fudge.patch('mkt.site.helpers.jingo_minify_helpers')
    def test_dev_unminified(self, fake_css):
        request = mock.Mock()
        request.GET = {}
        context = {'request': request}

        # Should be called with `debug=True`.
        fake_css.expects('css').with_args('mkt/devreg', False, True)
        css(context, 'mkt/devreg')

    @mock.patch.object(settings, 'TEMPLATE_DEBUG', False)
    @fudge.patch('mkt.site.helpers.jingo_minify_helpers')
    def test_prod_minified(self, fake_css):
        request = mock.Mock()
        request.GET = {}
        context = {'request': request}

        # Should be called with `debug=False`.
        fake_css.expects('css').with_args('mkt/devreg', False, False)
        css(context, 'mkt/devreg')

    @mock.patch.object(settings, 'TEMPLATE_DEBUG', True)
    @fudge.patch('mkt.site.helpers.jingo_minify_helpers')
    def test_dev_unminified_overridden(self, fake_css):
        request = mock.Mock()
        request.GET = {'debug': 'true'}
        context = {'request': request}

        # Should be called with `debug=True`.
        fake_css.expects('css').with_args('mkt/devreg', False, True)
        css(context, 'mkt/devreg')

    @mock.patch.object(settings, 'TEMPLATE_DEBUG', False)
    @fudge.patch('mkt.site.helpers.jingo_minify_helpers')
    def test_prod_unminified_overridden(self, fake_css):
        request = mock.Mock()
        request.GET = {'debug': 'true'}
        context = {'request': request}

        # Should be called with `debug=True`.
        fake_css.expects('css').with_args('mkt/devreg', False, True)
        css(context, 'mkt/devreg')


class TestJS(amo.tests.TestCase):

    @mock.patch.object(settings, 'TEMPLATE_DEBUG', True)
    @fudge.patch('mkt.site.helpers.jingo_minify_helpers')
    def test_dev_unminified(self, fake_js):
        request = mock.Mock()
        request.GET = {}
        context = {'request': request}

        # Should be called with `debug=True`.
        fake_js.expects('js').with_args('mkt/devreg', True, False, False)
        js(context, 'mkt/devreg')

    @mock.patch.object(settings, 'TEMPLATE_DEBUG', False)
    @fudge.patch('mkt.site.helpers.jingo_minify_helpers')
    def test_prod_minified(self, fake_js):
        request = mock.Mock()
        request.GET = {}
        context = {'request': request}

        # Should be called with `debug=False`.
        fake_js.expects('js').with_args('mkt/devreg', False, False, False)
        js(context, 'mkt/devreg')

    @mock.patch.object(settings, 'TEMPLATE_DEBUG', True)
    @fudge.patch('mkt.site.helpers.jingo_minify_helpers')
    def test_dev_unminified_overridden(self, fake_js):
        request = mock.Mock()
        request.GET = {'debug': 'true'}
        context = {'request': request}

        # Should be called with `debug=True`.
        fake_js.expects('js').with_args('mkt/devreg', True, False, False)
        js(context, 'mkt/devreg')

    @mock.patch.object(settings, 'TEMPLATE_DEBUG', False)
    @fudge.patch('mkt.site.helpers.jingo_minify_helpers')
    def test_prod_unminified_overridden(self, fake_js):
        request = mock.Mock()
        request.GET = {'debug': 'true'}
        context = {'request': request}

        # Should be called with `debug=True`.
        fake_js.expects('js').with_args('mkt/devreg', True, False, False)
        js(context, 'mkt/devreg')


class TestProductAsDict(amo.tests.TestCase):
    fixtures = fixture('webapp_337141')

    def test_correct(self):
        request = mock.Mock(GET={'src': 'poop'})
        app = Webapp.objects.get(id=337141)

        data = product_as_dict(request, app)
        eq_(data['src'], 'poop')
        eq_(data['is_packaged'], False)
        eq_(data['categories'], [])
        eq_(data['name'], 'Something Something Steamcube!')
        eq_(data['id'], '337141')
        eq_(data['manifest_url'], 'http://micropipes.com/temp/steamcube.webapp')

        tokenUrl = '/reviewers/app/something-something/token'
        recordUrl = '/app/something-something/purchase/record?src=poop'
        assert tokenUrl in data['tokenUrl'], (
            'Invalid Token URL. Expected %s; Got %s'
            % (tokenUrl, data['tokenUrl']))
        assert recordUrl in data['recordUrl'], (
            'Invalid Record URL. Expected %s; Got %s'
            % (recordUrl, data['recordUrl']))
