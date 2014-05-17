# -*- coding: utf-8 -*-
from django.conf import settings

import fudge
import mock

import amo
import amo.tests
from mkt.site.helpers import css, js


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
