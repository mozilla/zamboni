# -*- coding: utf-8 -*-
import functools
import hashlib
import json
import os
import shutil
import tempfile
import unittest
import uuid
import zipfile
from contextlib import nested
from datetime import datetime, timedelta

from django import forms
from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.core import mail
from django.core.files.storage import default_storage as storage
from django.core.urlresolvers import reverse
from django.db.models.signals import post_delete, post_save
from django.test.utils import override_settings
from django.utils import translation
from django.utils.translation import ugettext_lazy as _

import mock
import pyelasticsearch
from elasticutils.contrib.django import S
from mock import Mock, patch
from nose.tools import eq_, ok_, raises

import amo
import amo.tests
import mkt
from amo.helpers import absolutify
from amo.tests import app_factory, version_factory
from constants.applications import DEVICE_TYPES
from constants.payments import PROVIDER_BANGO, PROVIDER_BOKU
from lib.crypto import packaged
from lib.crypto.tests import mock_sign
from lib.iarc.utils import (DESC_MAPPING, INTERACTIVES_MAPPING,
                            REVERSE_DESC_MAPPING, REVERSE_INTERACTIVES_MAPPING)
from lib.utils import static_url
from mkt.constants import apps
from mkt.developers.models import (AddonPaymentAccount, PaymentAccount,
                                   SolitudeSeller)
from mkt.files.models import File, Platform
from mkt.files.tests.test_models import UploadTest as BaseUploadTest
from mkt.files.utils import WebAppParser
from mkt.prices.models import AddonPremium, Price
from mkt.reviewers.models import EscalationQueue, RereviewQueue
from mkt.site.fixtures import fixture
from mkt.site.tests import DynamicBoolFieldsTestMixin
from mkt.submit.tests.test_views import BasePackagedAppTest, BaseWebAppTest
from mkt.translations.models import Translation
from mkt.users.models import UserProfile
from mkt.versions.models import update_status, Version
from mkt.webapps.indexers import WebappIndexer
from mkt.webapps.models import (Addon, AddonCategory, AddonDeviceType,
                                AddonExcludedRegion, AddonUpsell, AppFeatures,
                                AppManifest, BlacklistedSlug, Category,
                                ContentRating, Geodata, get_excluded_in,
                                IARCInfo, Installed, Preview, RatingDescriptors,
                                RatingInteractives, version_changed, Webapp)
from mkt.webapps.signals import version_changed as version_changed_signal


class TestCleanSlug(amo.tests.TestCase):

    def test_clean_slug_new_object(self):
        # Make sure there's at least an addon with the "addon" slug, subsequent
        # ones should be "addon-1", "addon-2" ...
        a = Addon.objects.create()
        eq_(a.slug, "addon")

        # Start with a first clash. This should give us "addon-1".
        # We're not saving yet, we're testing the slug creation without an id.
        b = Addon()
        b.clean_slug()
        eq_(b.slug, 'addon-1')
        # Now save the instance to the database for future clashes.
        b.save()

        # Test on another object without an id.
        c = Addon()
        c.clean_slug()
        eq_(c.slug, 'addon-2')

        # Even if an addon is deleted, don't clash with its slug.
        c.status = amo.STATUS_DELETED
        # Now save the instance to the database for future clashes.
        c.save()

        # And yet another object without an id. Make sure we're not trying to
        # assign the 'addon-2' slug from the deleted addon.
        d = Addon()
        d.clean_slug()
        eq_(d.slug, 'addon-3')

    def test_clean_slug_with_id(self):
        # Create an addon and save it to have an id.
        a = Addon.objects.create()
        # Start over: don't use the name nor the id to generate the slug.
        a.slug = a.name = ""
        a.clean_slug()
        # Slugs created from an id are of the form "id~", eg "123~" to avoid
        # clashing with URLs.
        eq_(a.slug, "%s~" % a.id)

        # And again, this time make it clash.
        b = Addon.objects.create()
        # Set a's slug to be what should be created for b from its id.
        a.slug = "%s~" % b.id
        a.save()

        # Now start over for b.
        b.slug = b.name = ""
        b.clean_slug()
        eq_(b.slug, "%s~-1" % b.id)

    def test_clean_slug_with_name(self):
        # Make sure there's at least an addon with the "fooname" slug,
        # subsequent ones should be "fooname-1", "fooname-2" ...
        a = Addon.objects.create(name="fooname")
        eq_(a.slug, "fooname")

        b = Addon(name="fooname")
        b.clean_slug()
        eq_(b.slug, "fooname-1")

    def test_clean_slug_with_slug(self):
        # Make sure there's at least an addon with the "fooslug" slug,
        # subsequent ones should be "fooslug-1", "fooslug-2" ...
        a = Addon.objects.create(name="fooslug")
        eq_(a.slug, "fooslug")

        b = Addon(name="fooslug")
        b.clean_slug()
        eq_(b.slug, "fooslug-1")

    def test_clean_slug_blacklisted_slug(self):
        blacklisted_slug = 'fooblacklisted'
        BlacklistedSlug.objects.create(name=blacklisted_slug)

        a = Addon(slug=blacklisted_slug)
        a.clean_slug()
        # Blacklisted slugs (like "activate" or IDs) have a "~" appended to
        # avoid clashing with URLs.
        eq_(a.slug, "%s~" % blacklisted_slug)
        # Now save the instance to the database for future clashes.
        a.save()

        b = Addon(slug=blacklisted_slug)
        b.clean_slug()
        eq_(b.slug, "%s~-1" % blacklisted_slug)

    def test_clean_slug_blacklisted_slug_long_slug(self):
        long_slug = "this_is_a_very_long_slug_that_is_longer_than_thirty_chars"
        BlacklistedSlug.objects.create(name=long_slug[:30])

        # If there's no clashing slug, just append a "~".
        a = Addon.objects.create(slug=long_slug[:30])
        eq_(a.slug, "%s~" % long_slug[:29])

        # If there's a clash, use the standard clash resolution.
        a = Addon.objects.create(slug=long_slug[:30])
        eq_(a.slug, "%s-1" % long_slug[:27])

    def test_clean_slug_long_slug(self):
        long_slug = "this_is_a_very_long_slug_that_is_longer_than_thirty_chars"

        # If there's no clashing slug, don't over-shorten it.
        a = Addon.objects.create(slug=long_slug)
        eq_(a.slug, long_slug[:30])

        # Now that there is a clash, test the clash resolution.
        b = Addon(slug=long_slug)
        b.clean_slug()
        eq_(b.slug, "%s-1" % long_slug[:27])

    def test_clean_slug_always_slugify(self):
        illegal_chars = "some spaces and !?@"

        # Slugify if there's a slug provided.
        a = Addon(slug=illegal_chars)
        a.clean_slug()
        assert a.slug.startswith("some-spaces-and"), a.slug

        # Also slugify if there's no slug provided.
        b = Addon(name=illegal_chars)
        b.clean_slug()
        assert b.slug.startswith("some-spaces-and"), b.slug

    def test_clean_slug_worst_case_scenario(self):
        long_slug = "this_is_a_very_long_slug_that_is_longer_than_thirty_chars"

        # Generate 100 addons with this very long slug. We should encounter the
        # worst case scenario where all the available clashes have been
        # avoided. Check the comment in addons.models.clean_slug, in the "else"
        # part of the "for" loop checking for available slugs not yet assigned.
        for i in range(100):
            Addon.objects.create(slug=long_slug)
        with self.assertRaises(RuntimeError):  # Fail on the 100th clash.
            Addon.objects.create(slug=long_slug)


class TestCategoryModel(amo.tests.TestCase):

    def test_category_url(self):
        cat = Category(slug='omg')
        assert cat.get_url_path()

    @patch('mkt.webapps.tasks.index_webapps')
    def test_reindex_on_change(self, index_mock):
        c = Category.objects.create(type=amo.ADDON_WEBAPP, slug='keyboardcat')
        app = amo.tests.app_factory()
        AddonCategory.objects.create(addon=app, category=c)
        c.update(slug='nyancat')
        assert index_mock.called
        eq_(index_mock.call_args[0][0], [app.id])


class TestPreviewModel(amo.tests.TestCase):

    def setUp(self):
        app = Webapp.objects.create()
        self.preview = Preview.objects.create(addon=app, filetype='image/png',
                                              thumbtype='image/png',
                                              caption='my preview')

    def test_as_dict(self):
        expect = ['caption', 'full', 'thumbnail']
        reality = sorted(Preview.objects.all()[0].as_dict().keys())
        eq_(expect, reality)

    def test_filename(self):
        eq_(self.preview.file_extension, 'png')
        self.preview.update(filetype='')
        eq_(self.preview.file_extension, 'png')
        self.preview.update(filetype='video/webm')
        eq_(self.preview.file_extension, 'webm')

    def test_filename_in_url(self):
        self.preview.update(filetype='video/webm')
        assert 'png' in self.preview.thumbnail_path
        assert 'webm' in self.preview.image_path


class TestRemoveLocale(amo.tests.TestCase):

    def test_remove(self):
        app = Webapp.objects.create()
        app.name = {'en-US': 'woo', 'el': 'yeah'}
        app.description = {'en-US': 'woo', 'el': 'yeah', 'he': 'ola'}
        app.save()
        app.remove_locale('el')
        qs = (Translation.objects.filter(localized_string__isnull=False)
              .values_list('locale', flat=True))
        eq_(sorted(qs.filter(id=app.name_id)), ['en-US'])
        eq_(sorted(qs.filter(id=app.description_id)), ['en-US', 'he'])

    def test_remove_version_locale(self):
        app = app_factory()
        version = app.latest_version
        version.releasenotes = {'fr': 'oui'}
        version.save()
        app.remove_locale('fr')
        qs = (Translation.objects.filter(localized_string__isnull=False)
              .values_list('locale', flat=True))
        eq_(sorted(qs), [u'en-us'])


class TestUpdateNames(amo.tests.TestCase):

    def setUp(self):
        self.addon = Webapp.objects.create()
        self.addon.name = self.names = {'en-US': 'woo'}
        self.addon.save()

    def get_name(self, app, locale='en-US'):
        return Translation.objects.no_cache().get(id=app.name_id,
                                                  locale=locale)

    def check_names(self, names):
        """`names` in {locale: name} format."""
        for locale, localized_string in names.iteritems():
            eq_(self.get_name(self.addon, locale).localized_string,
                localized_string)

    def test_new_name(self):
        names = dict(self.names, **{'de': u'frü'})
        self.addon.update_names(names)
        self.addon.save()
        self.check_names(names)

    def test_new_names(self):
        names = dict(self.names, **{'de': u'frü', 'es': u'eso'})
        self.addon.update_names(names)
        self.addon.save()
        self.check_names(names)

    def test_remove_name_missing(self):
        names = dict(self.names, **{'de': u'frü', 'es': u'eso'})
        self.addon.update_names(names)
        self.addon.save()
        self.check_names(names)
        # Now update without de to remove it.
        del names['de']
        self.addon.update_names(names)
        self.addon.save()
        names['de'] = None
        self.check_names(names)

    def test_remove_name_with_none(self):
        names = dict(self.names, **{'de': u'frü', 'es': u'eso'})
        self.addon.update_names(names)
        self.addon.save()
        self.check_names(names)
        # Now update without de to remove it.
        names['de'] = None
        self.addon.update_names(names)
        self.addon.save()
        self.check_names(names)

    def test_add_and_remove(self):
        names = dict(self.names, **{'de': u'frü', 'es': u'eso'})
        self.addon.update_names(names)
        self.addon.save()
        self.check_names(names)
        # Now add a new locale and remove an existing one.
        names['de'] = None
        names['fr'] = u'oui'
        self.addon.update_names(names)
        self.addon.save()
        self.check_names(names)

    def test_default_locale_change(self):
        names = dict(self.names, **{'de': u'frü', 'es': u'eso'})
        self.addon.default_locale = 'de'
        self.addon.update_names(names)
        self.addon.save()
        self.check_names(names)
        addon = self.addon.reload()
        eq_(addon.default_locale, 'de')

    def test_default_locale_change_remove_old(self):
        names = dict(self.names, **{'de': u'frü', 'es': u'eso', 'en-US': None})
        self.addon.default_locale = 'de'
        self.addon.update_names(names)
        self.addon.save()
        self.check_names(names)
        eq_(self.addon.reload().default_locale, 'de')

    def test_default_locale_removal_not_deleted(self):
        names = {'en-US': None}
        self.addon.update_names(names)
        self.addon.save()
        self.check_names(self.names)


class TestAddonWatchDisabled(amo.tests.TestCase):

    def setUp(self):
        self.addon = Webapp.objects.create(disabled_by_user=False,
                                           status=amo.STATUS_PUBLIC)

    @patch('mkt.webapps.models.File.objects.filter')
    def test_no_disabled_change(self, file_mock):
        mock = Mock()
        file_mock.return_value = [mock]
        self.addon.save()
        assert not mock.unhide_disabled_file.called
        assert not mock.hide_disabled_file.called

    @patch('mkt.webapps.models.File.objects.filter')
    def test_disable_addon(self, file_mock):
        mock = Mock()
        file_mock.return_value = [mock]
        self.addon.update(disabled_by_user=True)
        assert not mock.unhide_disabled_file.called
        assert mock.hide_disabled_file.called

    @patch('mkt.webapps.models.File.objects.filter')
    def test_admin_disable_addon(self, file_mock):
        mock = Mock()
        file_mock.return_value = [mock]
        self.addon.update(status=amo.STATUS_DISABLED)
        assert not mock.unhide_disabled_file.called
        assert mock.hide_disabled_file.called

    @patch('mkt.webapps.models.File.objects.filter')
    def test_enable_addon(self, file_mock):
        mock = Mock()
        file_mock.return_value = [mock]
        self.addon.update(status=amo.STATUS_DISABLED)
        mock.reset_mock()
        self.addon.update(status=amo.STATUS_PUBLIC)
        assert mock.unhide_disabled_file.called
        assert not mock.hide_disabled_file.called


class TestAddonUpsell(amo.tests.TestCase):

    def setUp(self):
        self.one = Webapp.objects.create(name='free')
        self.two = Webapp.objects.create(name='premium')
        self.upsell = AddonUpsell.objects.create(free=self.one,
                                                 premium=self.two)

    def test_create_upsell(self):
        eq_(self.one.upsell.free, self.one)
        eq_(self.one.upsell.premium, self.two)
        eq_(self.two.upsell, None)

    def test_delete(self):
        self.upsell = AddonUpsell.objects.create(free=self.two,
                                                 premium=self.one)
        # Note: delete ignores if status 0.
        self.one.update(status=amo.STATUS_PUBLIC)
        self.one.delete()
        eq_(AddonUpsell.objects.count(), 0)


class TestAddonPurchase(amo.tests.TestCase):
    fixtures = fixture('user_999')

    def setUp(self):
        self.user = UserProfile.objects.get(pk=999)
        self.addon = Addon.objects.create(type=amo.ADDON_EXTENSION,
                                          premium_type=amo.ADDON_PREMIUM,
                                          name='premium')

    def test_no_premium(self):
        # If you've purchased something, the fact that its now free
        # doesn't change the fact that you purchased it.
        self.addon.addonpurchase_set.create(user=self.user)
        self.addon.update(premium_type=amo.ADDON_FREE)
        assert self.addon.has_purchased(self.user)

    def test_has_purchased(self):
        self.addon.addonpurchase_set.create(user=self.user)
        assert self.addon.has_purchased(self.user)

    def test_not_purchased(self):
        assert not self.addon.has_purchased(self.user)

    def test_anonymous(self):
        assert not self.addon.has_purchased(None)
        assert not self.addon.has_purchased(AnonymousUser)

    def test_is_refunded(self):
        self.addon.addonpurchase_set.create(user=self.user,
                                            type=amo.CONTRIB_REFUND)
        assert self.addon.is_refunded(self.user)

    def test_is_chargeback(self):
        self.addon.addonpurchase_set.create(user=self.user,
                                            type=amo.CONTRIB_CHARGEBACK)
        assert self.addon.is_chargeback(self.user)

    def test_purchase_state(self):
        purchase = self.addon.addonpurchase_set.create(user=self.user)
        for state in [amo.CONTRIB_PURCHASE, amo.CONTRIB_REFUND,
                      amo.CONTRIB_CHARGEBACK]:
            purchase.update(type=state)
            eq_(state, self.addon.get_purchase_type(self.user))


class TestNewAddonVsWebapp(amo.tests.TestCase):

    def test_addon_from_kwargs(self):
        a = Addon(type=amo.ADDON_EXTENSION)
        assert isinstance(a, Addon)

    def test_webapp_from_kwargs(self):
        w = Addon(type=amo.ADDON_WEBAPP)
        assert isinstance(w, Webapp)

    def test_addon_from_db(self):
        a = Addon.objects.create(type=amo.ADDON_EXTENSION)
        assert isinstance(a, Addon)
        assert isinstance(Addon.objects.get(id=a.id), Addon)

    def test_webapp_from_db(self):
        a = Addon.objects.create(type=amo.ADDON_WEBAPP)
        assert isinstance(a, Webapp)
        assert isinstance(Addon.objects.get(id=a.id), Webapp)


class TestWebapp(amo.tests.TestCase):
    fixtures = fixture('prices')

    def test_icon_url(self):
        app = Webapp.objects.create(id=337141, status=amo.STATUS_PUBLIC,
                                    icon_type='image/png')
        expected = (static_url('ADDON_ICON_URL')
                    % (str(app.id)[0:3], app.id, 32, 'never'))
        assert app.icon_url.endswith(expected), (
            'Expected %s, got %s' % (expected, app.icon_url))

        app.icon_hash = 'abcdef'
        assert app.icon_url.endswith('?modified=abcdef')

        app.icon_type = None
        assert app.icon_url.endswith('hub/default-32.png')

    def test_thumbnail_url_no_preview(self):
        app = Webapp.objects.create()
        assert app.thumbnail_url.endswith('/icons/no-preview.png'), (
            'No match for %s' % app.thumbnail_url)

    def test_thumbnail_url(self):
        app = Webapp.objects.create()
        preview = Preview.objects.create(addon=app, filetype='image/png',
                                         position=0)
        assert app.thumbnail_url.index('/previews/thumbs/%s/%s.png?modified='
                                       % (preview.id / 1000, preview.id))

    def test_is_public(self):
        app = Webapp(status=amo.STATUS_PUBLIC)
        assert app.is_public(), 'public app should be is_pulic()'

        # Public, disabled.
        app.disabled_by_user = True
        assert not app.is_public(), (
            'public, disabled app should not be is_public()')

        # Any non-public status
        app.status = amo.STATUS_PENDING
        app.disabled_by_user = False
        assert not app.is_public(), 'pending, app should not be is_public()'

    def _newlines_helper(self, app, string_before):
        app.privacy_policy = string_before
        app.save()
        return app.privacy_policy.localized_string_clean

    def add_payment_account(self, app, provider_id, user=None):
        if not user:
            user = UserProfile.objects.create(email='a', username='b')
        payment = PaymentAccount.objects.create(
            solitude_seller=SolitudeSeller.objects.create(user=user,
                                                          uuid=uuid.uuid4()),
            provider=provider_id,
            user=user,
            seller_uri=uuid.uuid4(),
            uri=uuid.uuid4())
        return AddonPaymentAccount.objects.create(
            addon=app, payment_account=payment, product_uri=uuid.uuid4())

    def test_delete_reason(self):
        """Test deleting with a reason gives the reason in the mail."""
        reason = u'trêason'
        w = Webapp.objects.create(status=amo.STATUS_PUBLIC)
        w.name = u'é'
        eq_(len(mail.outbox), 0)
        w.delete(msg='bye', reason=reason)
        eq_(len(mail.outbox), 1)
        assert reason in mail.outbox[0].body

    def test_soft_deleted(self):
        w = Webapp.objects.create(slug='ballin', app_slug='app-ballin',
                                  app_domain='http://omg.org/yes',
                                  status=amo.STATUS_PENDING)
        eq_(len(Webapp.objects.all()), 1)
        eq_(len(Webapp.with_deleted.all()), 1)

        w.delete('boom shakalakalaka')
        eq_(len(Webapp.objects.all()), 0)
        eq_(len(Webapp.with_deleted.all()), 1)

        # When an app is deleted its slugs and domain should get relinquished.
        post_mortem = Webapp.with_deleted.filter(id=w.id)
        eq_(post_mortem.count(), 1)
        for attr in ('slug', 'app_slug', 'app_domain'):
            eq_(getattr(post_mortem[0], attr), None)

    def test_with_deleted_count(self):
        w = Webapp.objects.create(slug='ballin', app_slug='app-ballin',
                                  app_domain='http://omg.org/yes',
                                  status=amo.STATUS_PENDING)
        w.delete()
        eq_(Webapp.with_deleted.count(), 1)

    def test_soft_deleted_valid(self):
        w = Webapp.objects.create(status=amo.STATUS_PUBLIC)
        Webapp.objects.create(status=amo.STATUS_DELETED)
        eq_(list(Webapp.objects.valid()), [w])
        eq_(sorted(Webapp.with_deleted.valid()), [w])

    def test_delete_incomplete_with_deleted_version(self):
        """Test deleting incomplete add-ons with no public version attached."""
        app = app_factory()
        app.current_version.delete()
        eq_(Version.objects.count(), 0)
        eq_(Version.with_deleted.count(), 1)
        app.update(status=0, highest_status=0)

        # We want to be in the worst possible situation, no direct foreign key
        # to the deleted versions, do we call update_version() now that we have
        # an incomplete app.
        app.update_version()
        eq_(app.latest_version, None)
        eq_(app.current_version, None)

        app.delete()

        # The app should have been soft-deleted.
        eq_(len(mail.outbox), 1)
        eq_(Webapp.objects.count(), 0)
        eq_(Webapp.with_deleted.count(), 1)

    def test_webapp_type(self):
        webapp = Webapp()
        webapp.save()
        eq_(webapp.type, amo.ADDON_WEBAPP)

    def test_app_slugs_separate_from_addon_slugs(self):
        Addon.objects.create(type=1, slug='slug')
        webapp = Webapp(app_slug='slug')
        webapp.save()
        eq_(webapp.slug, 'app-%s' % webapp.id)
        eq_(webapp.app_slug, 'slug')

    def test_app_slug_collision(self):
        Webapp(app_slug='slug').save()
        w2 = Webapp(app_slug='slug')
        w2.save()
        eq_(w2.app_slug, 'slug-1')

        w3 = Webapp(app_slug='slug')
        w3.save()
        eq_(w3.app_slug, 'slug-2')

    def test_app_slug_blocklist(self):
        BlacklistedSlug.objects.create(name='slug')
        w = Webapp(app_slug='slug')
        w.save()
        eq_(w.app_slug, 'slug~')

    def test_geodata_upon_app_creation(self):
        app = Webapp.objects.create(type=amo.ADDON_WEBAPP)
        assert app.geodata, (
            'Geodata was not created with Webapp.')

    def test_get_url_path(self):
        webapp = Webapp(app_slug='woo')
        eq_(webapp.get_url_path(), '/app/woo/')

    def test_get_api_url(self):
        webapp = Webapp(app_slug='woo', pk=1)
        self.assertApiUrlEqual(webapp.get_api_url(), '/apps/app/woo/')

    def test_get_api_url_pk(self):
        webapp = Webapp(pk=1)
        self.assertApiUrlEqual(webapp.get_api_url(pk=True), '/apps/app/1/')

    def test_get_stats_url(self):
        webapp = Webapp(app_slug='woo')
        eq_(webapp.get_stats_url(), '/statistics/app/woo')

    def test_get_comm_thread_url(self):
        self.create_switch('comm-dashboard')
        app = app_factory(app_slug='putain')
        eq_(app.get_comm_thread_url(), '/comm/app/putain')

    def test_get_origin(self):
        url = 'http://www.xx.com:4000/randompath/manifest.webapp'
        webapp = Webapp(manifest_url=url)
        eq_(webapp.origin, 'http://www.xx.com:4000')

    def test_get_packaged_origin(self):
        webapp = Webapp(app_domain='app://foo.com', is_packaged=True,
                        manifest_url='')
        eq_(webapp.origin, 'app://foo.com')

    def test_punicode_domain(self):
        webapp = Webapp(app_domain=u'http://www.allizôm.org')
        eq_(webapp.punycode_app_domain, 'http://www.xn--allizm-mxa.org')

    def test_cannot_be_purchased(self):
        eq_(Webapp(premium_type=True).can_be_purchased(), False)
        eq_(Webapp(premium_type=False).can_be_purchased(), False)

    def test_can_be_purchased(self):
        w = Webapp(status=amo.STATUS_PUBLIC, premium_type=True)
        eq_(w.can_be_purchased(), True)

        w = Webapp(status=amo.STATUS_PUBLIC, premium_type=False)
        eq_(w.can_be_purchased(), False)

    def test_get_previews(self):
        w = Webapp.objects.create()
        eq_(w.get_promo(), None)

        p = Preview.objects.create(addon=w, position=0)
        eq_(list(w.get_previews()), [p])

        p.update(position=-1)
        eq_(list(w.get_previews()), [])

    def test_get_promo(self):
        w = Webapp.objects.create()
        eq_(w.get_promo(), None)

        p = Preview.objects.create(addon=w, position=0)
        eq_(w.get_promo(), None)

        p.update(position=-1)
        eq_(w.get_promo(), p)

    def test_mark_done_pending(self):
        w = Webapp()
        eq_(w.status, amo.STATUS_NULL)
        w.mark_done()
        eq_(w.status, amo.WEBAPPS_UNREVIEWED_STATUS)

    @mock.patch('mkt.webapps.models.Webapp.get_manifest_json')
    def test_no_icon_in_manifest(self, get_manifest_json):
        webapp = Webapp()
        get_manifest_json.return_value = {}
        eq_(webapp.has_icon_in_manifest(), False)

    @mock.patch('mkt.webapps.models.Webapp.get_manifest_json')
    def test_has_icon_in_manifest(self, get_manifest_json):
        webapp = Webapp()
        get_manifest_json.return_value = {'icons': {}}
        eq_(webapp.has_icon_in_manifest(), True)

    def test_no_version(self):
        webapp = Webapp()
        eq_(webapp.get_manifest_json(), None)
        eq_(webapp.current_version, None)

    def test_has_premium(self):
        webapp = Webapp(premium_type=amo.ADDON_PREMIUM)
        webapp._premium = mock.Mock()
        webapp._premium.price = 1
        eq_(webapp.has_premium(), True)

        webapp._premium.price = 0
        eq_(webapp.has_premium(), True)

    def test_get_price_no_premium(self):
        webapp = Webapp(premium_type=amo.ADDON_PREMIUM)
        eq_(webapp.get_price(), None)
        eq_(webapp.get_price_locale(), None)

    def test_get_price(self):
        webapp = amo.tests.app_factory()
        self.make_premium(webapp)
        eq_(webapp.get_price(region=mkt.regions.US.id), 1)

    def test_get_price_tier(self):
        webapp = amo.tests.app_factory()
        self.make_premium(webapp)
        eq_(str(webapp.get_tier().price), '1.00')
        ok_(webapp.get_tier_name())

    def test_get_price_tier_no_charge(self):
        webapp = amo.tests.app_factory()
        self.make_premium(webapp, 0)
        eq_(str(webapp.get_tier().price), '0')
        ok_(webapp.get_tier_name())

    def test_has_no_premium(self):
        webapp = Webapp(premium_type=amo.ADDON_PREMIUM)
        webapp._premium = None
        eq_(webapp.has_premium(), False)

    def test_not_premium(self):
        eq_(Webapp().has_premium(), False)

    def test_get_region_ids_no_exclusions(self):
        # This returns IDs for the *included* regions.
        eq_(Webapp().get_region_ids(), mkt.regions.REGION_IDS)

    def test_get_region_ids_with_exclusions(self):
        w1 = Webapp.objects.create()
        w2 = Webapp.objects.create()

        AddonExcludedRegion.objects.create(addon=w1, region=mkt.regions.BR.id)
        AddonExcludedRegion.objects.create(addon=w1, region=mkt.regions.US.id)
        AddonExcludedRegion.objects.create(addon=w2, region=mkt.regions.UK.id)

        w1_regions = list(mkt.regions.REGION_IDS)
        w1_regions.remove(mkt.regions.BR.id)
        w1_regions.remove(mkt.regions.US.id)

        w2_regions = list(mkt.regions.REGION_IDS)
        w2_regions.remove(mkt.regions.UK.id)

        eq_(sorted(Webapp.objects.get(id=w1.id).get_region_ids()),
            sorted(w1_regions))
        eq_(sorted(Webapp.objects.get(id=w2.id).get_region_ids()),
            sorted(w2_regions))

    def test_get_regions_no_exclusions(self):
        # This returns the class definitions for the *included* regions.
        eq_(sorted(Webapp().get_regions()),
            sorted(mkt.regions.REGIONS_CHOICES_ID_DICT.values()))

    def test_get_regions_with_exclusions(self):
        w1 = Webapp.objects.create()
        w2 = Webapp.objects.create()

        AddonExcludedRegion.objects.create(addon=w1, region=mkt.regions.BR.id)
        AddonExcludedRegion.objects.create(addon=w1, region=mkt.regions.US.id)
        AddonExcludedRegion.objects.create(addon=w2, region=mkt.regions.UK.id)

        all_regions = mkt.regions.REGIONS_CHOICES_ID_DICT.values()

        w1_regions = list(all_regions)
        w1_regions.remove(mkt.regions.BR)
        w1_regions.remove(mkt.regions.US)

        w2_regions = list(all_regions)
        w2_regions.remove(mkt.regions.UK)

        eq_(sorted(Webapp.objects.get(id=w1.id).get_regions()),
            sorted(w1_regions))
        eq_(sorted(Webapp.objects.get(id=w2.id).get_regions()),
            sorted(w2_regions))

    def test_package_helpers(self):
        app1 = app_factory()
        eq_(app1.is_packaged, False)
        app2 = app_factory(is_packaged=True)
        eq_(app2.is_packaged, True)

    def test_package_no_version(self):
        webapp = Webapp.objects.create(manifest_url='http://foo.com')
        eq_(webapp.is_packaged, False)

    def test_assign_uuid(self):
        app = Webapp()
        eq_(app.guid, None)
        app.save()
        assert app.guid is not None, (
            'Expected app to have a UUID assigned to guid')

    @mock.patch.object(uuid, 'uuid4')
    def test_assign_uuid_max_tries(self, mock_uuid4):
        guid = 'abcdef12-abcd-abcd-abcd-abcdef123456'
        mock_uuid4.return_value = uuid.UUID(guid)
        # Create another webapp with and set the guid.
        Webapp.objects.create(guid=guid)
        # Now `assign_uuid()` should fail.
        app = Webapp()
        with self.assertRaises(ValueError):
            app.save()

    def test_is_premium_type_upgrade_check(self):
        app = Webapp()
        ALL = set(amo.ADDON_FREES + amo.ADDON_PREMIUMS)
        free_upgrade = ALL - set([amo.ADDON_FREE])
        free_inapp_upgrade = ALL - set([amo.ADDON_FREE, amo.ADDON_FREE_INAPP])

        # Checking ADDON_FREE changes.
        app.premium_type = amo.ADDON_FREE
        for pt in ALL:
            eq_(app.is_premium_type_upgrade(pt), pt in free_upgrade)

        # Checking ADDON_FREE_INAPP changes.
        app.premium_type = amo.ADDON_FREE_INAPP
        for pt in ALL:
            eq_(app.is_premium_type_upgrade(pt), pt in free_inapp_upgrade)

        # All else is false.
        for pt_old in ALL - set([amo.ADDON_FREE, amo.ADDON_FREE_INAPP]):
            app.premium_type = pt_old
            for pt_new in ALL:
                eq_(app.is_premium_type_upgrade(pt_new), False)

    @raises(ValueError)
    def test_parse_domain(self):
        Webapp(is_packaged=True).parsed_app_domain

    def test_app_type_hosted(self):
        eq_(Webapp().app_type, 'hosted')

    def test_app_type_packaged(self):
        eq_(Webapp(is_packaged=True).app_type, 'packaged')

    @mock.patch('mkt.versions.models.Version.is_privileged', True)
    def test_app_type_privileged(self):
        # Have to use `app_factory` because we need a `latest_version`
        # to make it a privileged version.
        eq_(app_factory(is_packaged=True).app_type, 'privileged')

    def test_nomination_new(self):
        app = app_factory()
        app.update(status=amo.STATUS_NULL)
        app.versions.latest().update(nomination=None)
        app.update(status=amo.STATUS_PENDING)
        assert app.versions.latest().nomination

    def test_nomination_rejected(self):
        app = app_factory()
        app.update(status=amo.STATUS_REJECTED)
        app.versions.latest().update(nomination=self.days_ago(1))
        app.update(status=amo.STATUS_PENDING)
        self.assertCloseToNow(app.versions.latest().nomination)

    def test_nomination_pkg_pending_new_version(self):
        # New versions while pending inherit version nomination.
        app = app_factory()
        app.update(status=amo.STATUS_PENDING, is_packaged=True)
        old_ver = app.versions.latest()
        old_ver.update(nomination=self.days_ago(1))
        old_ver.all_files[0].update(status=amo.STATUS_PENDING)
        v = Version.objects.create(addon=app, version='1.9')
        eq_(v.nomination, old_ver.nomination)

    def test_nomination_pkg_public_new_version(self):
        # New versions while public get a new version nomination.
        app = app_factory()
        app.update(is_packaged=True)
        old_ver = app.versions.latest()
        old_ver.update(nomination=self.days_ago(1))
        v = Version.objects.create(addon=app, version='1.9')
        self.assertCloseToNow(v.nomination)

    def test_nomination_public_waiting(self):
        # New versions while public waiting get a new version nomination.
        app = app_factory()
        app.update(is_packaged=True, status=amo.STATUS_PUBLIC_WAITING)
        old_ver = app.versions.latest()
        old_ver.update(nomination=self.days_ago(1))
        old_ver.all_files[0].update(status=amo.STATUS_PUBLIC_WAITING)
        v = Version.objects.create(addon=app, version='1.9')
        self.assertCloseToNow(v.nomination)

    def test_excluded_in(self):
        app1 = app_factory()
        region = mkt.regions.BR
        AddonExcludedRegion.objects.create(addon=app1, region=region.id)
        self.assertSetEqual(get_excluded_in(region.id), [app1.id])

    def test_excluded_in_iarc(self):
        app = app_factory()
        geodata = app._geodata
        geodata.update(region_br_iarc_exclude=True,
                       region_de_iarc_exclude=True)
        self.assertSetEqual(get_excluded_in(mkt.regions.BR.id), [app.id])
        self.assertSetEqual(get_excluded_in(mkt.regions.DE.id), [app.id])

    def test_excluded_in_iarc_de(self):
        app = app_factory()
        geodata = app._geodata
        geodata.update(region_br_iarc_exclude=False,
                       region_de_iarc_exclude=True)
        self.assertSetEqual(get_excluded_in(mkt.regions.BR.id), [])
        self.assertSetEqual(get_excluded_in(mkt.regions.DE.id), [app.id])

    def test_excluded_in_usk_exclude(self):
        app = app_factory()
        geodata = app._geodata
        geodata.update(region_de_usk_exclude=True)
        self.assertSetEqual(get_excluded_in(mkt.regions.BR.id), [])
        self.assertSetEqual(get_excluded_in(mkt.regions.DE.id), [app.id])

    def test_supported_locale_property(self):
        app = app_factory()
        app.versions.latest().update(supported_locales='de,fr', _signal=False)
        app.reload()
        eq_(app.supported_locales,
            (u'English (US)', [u'Deutsch', u'Fran\xe7ais']))

    def test_supported_locale_property_empty(self):
        app = app_factory()
        eq_(app.supported_locales, (u'English (US)', []))

    def test_supported_locale_property_bad(self):
        app = app_factory()
        app.versions.latest().update(supported_locales='de,xx', _signal=False)
        app.reload()
        eq_(app.supported_locales, (u'English (US)', [u'Deutsch']))

    def test_supported_locale_app_rejected(self):
        """
        Simulate an app being rejected, which sets the
        app.current_version to None, and verify supported_locales works
        as expected -- which is that if there is no current version we
        can't report supported_locales for it, so we return an empty
        list.
        """
        app = app_factory()
        app.versions.latest().update(supported_locales='de', _signal=False)
        app.update(status=amo.STATUS_REJECTED)
        app.versions.latest().all_files[0].update(status=amo.STATUS_REJECTED)
        app.update_version()
        app.reload()
        eq_(app.supported_locales, (u'English (US)', []))

    def test_get_trending(self):
        # Test no trending record returns zero.
        app = app_factory()
        eq_(app.get_trending(), 0)

        # Add a region specific trending and test the global one is returned
        # because the region is not mature.
        region = mkt.regions.REGIONS_DICT['me']
        app.trending.create(value=20.0, region=0)
        app.trending.create(value=10.0, region=region.id)
        eq_(app.get_trending(region=region), 20.0)

        # Now test the regional trending is returned when adolescent=False.
        region.adolescent = False
        eq_(app.get_trending(region=region), 10.0)

    @mock.patch('mkt.webapps.models.cache.get')
    def test_is_offline_when_packaged(self, mock_get):
        mock_get.return_value = ''
        eq_(Webapp(is_packaged=True).is_offline, True)
        eq_(Webapp(is_packaged=False).is_offline, False)

    def test_is_offline_when_appcache_path(self):
        app = app_factory()
        manifest = {'name': 'Swag'}

        # If there's no appcache_path defined, ain't an offline-capable app.
        am = AppManifest.objects.create(version=app.current_version,
                                        manifest=json.dumps(manifest))
        eq_(app.is_offline, False)

        # If there's an appcache_path defined, this is an offline-capable app.
        manifest['appcache_path'] = '/manifest.appcache'
        am.update(manifest=json.dumps(manifest))
        # reload isn't enough, it doesn't clear cached_property.
        app = Webapp.objects.get(pk=app.pk)
        eq_(app.is_offline, True)

    @mock.patch('mkt.webapps.models.Webapp.completion_errors')
    def test_completion_errors(self, complete_mock):
        app = app_factory()
        complete_mock.return_value = {
            'details': ['1', '2'],
            'payments': 'pc load letter'
        }
        eq_(app.completion_error_msgs(), ['1', '2', 'pc load letter'])
        assert not app.is_fully_complete()

        complete_mock.return_value = {}
        eq_(app.completion_error_msgs(), [])
        assert app.is_fully_complete()

    @mock.patch('mkt.webapps.models.Webapp.payments_complete')
    @mock.patch('mkt.webapps.models.Webapp.content_ratings_complete')
    @mock.patch('mkt.webapps.models.Webapp.details_complete')
    def test_next_step(self, detail_step, rating_step, pay_step):
        self.create_switch('iarc')
        for step in (detail_step, rating_step, pay_step):
            step.return_value = False
        app = app_factory(status=amo.STATUS_NULL)
        self.make_premium(app)
        eq_(app.next_step()['url'], app.get_dev_url())

        detail_step.return_value = True
        eq_(app.next_step()['url'], app.get_dev_url('ratings'))

        rating_step.return_value = True
        eq_(app.next_step()['url'], app.get_dev_url('payments'))

        pay_step.return_value = True
        assert not app.next_step()

    def test_meta_translated_fields(self):
        """Test that we don't load translations for all the translated fields
        that live on Addon but we don't need in Webapp."""
        useless_fields = ()
        useful_fields = ('homepage', 'privacy_policy', 'name', 'description',
                         'support_email', 'support_url')

        self.assertSetEqual(Addon._meta.translated_fields,
            [Addon._meta.get_field(f) for f in useless_fields + useful_fields])
        self.assertSetEqual(Webapp._meta.translated_fields,
            [Webapp._meta.get_field(f) for f in useful_fields])

        # Build fake data with all fields, and use it to create an app.
        data = dict(zip(useless_fields + useful_fields,
                        useless_fields + useful_fields))
        app = app_factory(**data)
        for field_name in useless_fields + useful_fields:
            field_id_name = app._meta.get_field(field_name).attname
            ok_(getattr(app, field_name, None))
            ok_(getattr(app, field_id_name, None))

        # Reload the app, the useless fields should all have ids but the value
        # shouldn't have been loaded.
        app = Webapp.objects.get(pk=app.pk)
        for field_name in useless_fields:
            field_id_name = app._meta.get_field(field_name).attname
            ok_(getattr(app, field_name, None) is None)
            ok_(getattr(app, field_id_name, None))

        # The useful fields should all be ok.
        for field_name in useful_fields:
            field_id_name = app._meta.get_field(field_name).attname
            ok_(getattr(app, field_name, None))
            ok_(getattr(app, field_id_name, None))

    def test_has_payment_account(self):
        app = app_factory()
        assert not app.has_payment_account()

        self.add_payment_account(app, PROVIDER_BANGO)
        assert app.has_payment_account()

    def test_has_multiple_payment_accounts(self):
        app = app_factory()
        assert not app.has_multiple_payment_accounts(), 'no accounts'

        account = self.add_payment_account(app, PROVIDER_BANGO)
        assert not app.has_multiple_payment_accounts(), 'one account'

        self.add_payment_account(app, PROVIDER_BOKU, user=account.user)
        ok_(app.has_multiple_payment_accounts(), 'two accounts')

    def test_no_payment_account(self):
        app = app_factory()
        assert not app.has_payment_account()
        with self.assertRaises(app.PayAccountDoesNotExist):
            app.payment_account(PROVIDER_BANGO)

    def test_get_payment_account(self):
        app = app_factory()
        acct = self.add_payment_account(app, PROVIDER_BANGO)
        fetched_acct = app.payment_account(PROVIDER_BANGO)
        eq_(acct, fetched_acct)

    @mock.patch('mkt.webapps.models.Webapp.has_payment_account')
    def test_payments_complete(self, pay_mock):
        # Default to complete if it's not needed.
        pay_mock.return_value = False
        app = app_factory()
        assert app.payments_complete()

        self.make_premium(app)
        assert not app.payments_complete()

        pay_mock.return_value = True
        assert app.payments_complete()

    def test_version_and_file_transformer_with_empty_query(self):
        # When we process a query, don't return a list just because
        # the query is empty
        empty_query = Webapp.objects.filter(app_slug='mahna__mahna')
        empty_result = Webapp.version_and_file_transformer(empty_query)
        self.assertEqual(empty_result.count(), 0)


class TestWebappContentRatings(amo.tests.TestCase):

    def test_rated(self):
        self.create_switch('iarc')
        assert app_factory(rated=True).is_rated()
        assert not app_factory().is_rated()

    @mock.patch('mkt.webapps.models.Webapp.details_complete')
    @mock.patch('mkt.webapps.models.Webapp.payments_complete')
    def test_set_content_ratings(self, pay_mock, detail_mock):
        self.create_switch('iarc')
        detail_mock.return_value = True
        pay_mock.return_value = True

        rb = mkt.ratingsbodies

        app = app_factory(status=amo.STATUS_NULL)
        app.set_content_ratings({})
        assert not app.is_rated()
        eq_(app.status, amo.STATUS_NULL)

        # Create.
        app.set_content_ratings({
            rb.CLASSIND: rb.CLASSIND_L,
            rb.PEGI: rb.PEGI_3,
        })
        eq_(ContentRating.objects.count(), 2)
        for expected in [(rb.CLASSIND.id, rb.CLASSIND_L.id),
                         (rb.PEGI.id, rb.PEGI_3.id)]:
            assert ContentRating.objects.filter(
                addon=app, ratings_body=expected[0],
                rating=expected[1]).exists()
        eq_(app.reload().status, amo.STATUS_PENDING)

        # Update.
        app.set_content_ratings({
            rb.CLASSIND: rb.CLASSIND_10,
            rb.PEGI: rb.PEGI_3,
            rb.GENERIC: rb.GENERIC_18,
        })
        for expected in [(rb.CLASSIND.id, rb.CLASSIND_10.id),
                         (rb.PEGI.id, rb.PEGI_3.id),
                         (rb.GENERIC.id, rb.GENERIC_18.id)]:
            assert ContentRating.objects.filter(
                addon=app, ratings_body=expected[0],
                rating=expected[1]).exists()
        eq_(app.reload().status, amo.STATUS_PENDING)

    def test_app_delete_clears_iarc_data(self):
        self.create_switch('iarc')
        app = app_factory(rated=True)

        # Ensure we have some data to start with.
        ok_(IARCInfo.objects.filter(addon=app).exists())
        ok_(ContentRating.objects.filter(addon=app).exists())
        ok_(RatingDescriptors.objects.filter(addon=app).exists())
        ok_(RatingInteractives.objects.filter(addon=app).exists())

        # Delete.
        app.delete()
        msg = 'Related IARC data should be deleted.'
        ok_(not IARCInfo.objects.filter(addon=app).exists(), msg)
        ok_(not ContentRating.objects.filter(addon=app).exists(), msg)
        ok_(not RatingDescriptors.objects.filter(addon=app).exists(), msg)
        ok_(not RatingInteractives.objects.filter(addon=app).exists(), msg)

    def test_set_content_ratings_usk_refused(self):
        app = app_factory()
        app.set_content_ratings({
            mkt.ratingsbodies.USK: mkt.ratingsbodies.USK_REJECTED
        })
        ok_(Geodata.objects.get(addon=app).region_de_usk_exclude)

        app.set_content_ratings({
            mkt.ratingsbodies.USK: mkt.ratingsbodies.USK_12
        })
        ok_(not Geodata.objects.get(addon=app).region_de_usk_exclude)

    def test_set_content_ratings_iarc_games_unexclude(self):
        app = app_factory()
        app._geodata.update(region_br_iarc_exclude=True,
                            region_de_iarc_exclude=True)

        app.set_content_ratings({
            mkt.ratingsbodies.USK: mkt.ratingsbodies.USK_12
        })

        geodata = Geodata.objects.get(addon=app)
        ok_(not geodata.region_br_iarc_exclude)
        ok_(not geodata.region_de_iarc_exclude)

    def test_set_content_ratings_purge_unexclude(self):
        app = app_factory()
        app.update(status=amo.STATUS_DISABLED, iarc_purged=True)

        app.set_content_ratings({
            mkt.ratingsbodies.USK: mkt.ratingsbodies.USK_12
        })

        ok_(not app.reload().iarc_purged)
        eq_(app.status, amo.STATUS_PUBLIC)

    def test_set_descriptors(self):
        app = app_factory()
        eq_(RatingDescriptors.objects.count(), 0)
        app.set_descriptors([])

        descriptors = RatingDescriptors.objects.get(addon=app)
        assert not descriptors.has_classind_drugs
        assert not descriptors.has_esrb_blood  # Blood-deuh!

        # Create.
        app.set_descriptors([
            'has_classind_drugs', 'has_pegi_scary', 'has_generic_drugs'
        ])
        descriptors = RatingDescriptors.objects.get(addon=app)
        assert descriptors.has_classind_drugs
        assert descriptors.has_pegi_scary
        assert descriptors.has_generic_drugs
        assert not descriptors.has_esrb_blood

        # Update.
        app.set_descriptors([
            'has_esrb_blood', 'has_classind_drugs'
        ])
        descriptors = RatingDescriptors.objects.get(addon=app)
        assert descriptors.has_esrb_blood
        assert descriptors.has_classind_drugs
        assert not descriptors.has_pegi_scary
        assert not descriptors.has_generic_drugs

    def test_set_interactives(self):
        app = app_factory()
        app.set_interactives([])
        eq_(RatingInteractives.objects.count(), 1)
        app_interactives = RatingInteractives.objects.get(addon=app)
        assert not app_interactives.has_shares_info
        assert not app_interactives.has_digital_purchases

        # Create.
        app.set_interactives([
            'has_shares_info', 'has_digital_PurChaSes', 'has_UWOTM8'
        ])
        eq_(RatingInteractives.objects.count(), 1)
        app_interactives = RatingInteractives.objects.get(addon=app)
        assert app_interactives.has_shares_info
        assert app_interactives.has_digital_purchases
        assert not app_interactives.has_users_interact

        # Update.
        app.set_interactives([
            'has_digital_purchases', 'has_shares_ur_mum'
        ])
        eq_(RatingInteractives.objects.count(), 1)
        app_interactives = RatingInteractives.objects.get(addon=app)
        assert not app_interactives.has_shares_info
        assert app_interactives.has_digital_purchases

    @mock.patch('lib.iarc.client.MockClient.call')
    @mock.patch('mkt.webapps.models.render_xml')
    def test_set_iarc_storefront_data(self, render_mock, storefront_mock):
        # Set up ratings/descriptors/interactives.
        self.create_switch('iarc')
        app = app_factory(name='LOL', app_slug='ha')
        app.current_version.reviewed = datetime(2013, 1, 1, 12, 34, 56)
        app.current_version._developer_name = 'Lex Luthor'

        app.set_iarc_info(submission_id=1234, security_code='sektor')
        app.set_descriptors(['has_esrb_blood', 'has_pegi_scary'])
        app.set_interactives(['has_users_interact', 'has_shares_info'])
        app.content_ratings.create(
            ratings_body=mkt.ratingsbodies.ESRB.id,
            rating=mkt.ratingsbodies.ESRB_A.id)
        app.content_ratings.create(
            ratings_body=mkt.ratingsbodies.PEGI.id,
            rating=mkt.ratingsbodies.PEGI_3.id)

        # Check the client was called.
        app.set_iarc_storefront_data()
        assert storefront_mock.called

        eq_(render_mock.call_count, 2)
        eq_(render_mock.call_args_list[0][0][0], 'set_storefront_data.xml')

        # Check arguments to the XML template are all correct.
        data = render_mock.call_args_list[0][0][1]
        eq_(type(data['title']), unicode)
        eq_(data['app_url'], app.get_url_path())
        eq_(data['submission_id'], 1234)
        eq_(data['security_code'], 'sektor')
        eq_(data['rating_system'], 'ESRB')
        eq_(data['release_date'], app.current_version.reviewed)
        eq_(data['title'], 'LOL')
        eq_(data['company'], 'Lex Luthor')
        eq_(data['rating'], 'Adults Only')
        eq_(data['descriptors'], 'Blood')
        self.assertSetEqual(data['interactive_elements'].split(', '),
                            ['Shares Info', 'Users Interact'])

        data = render_mock.call_args_list[1][0][1]
        eq_(type(data['title']), unicode)
        eq_(data['submission_id'], 1234)
        eq_(data['security_code'], 'sektor')
        eq_(data['rating_system'], 'PEGI')
        eq_(data['release_date'], app.current_version.reviewed)
        eq_(data['title'], 'LOL')
        eq_(data['company'], 'Lex Luthor')
        eq_(data['rating'], '3+')
        eq_(data['descriptors'], 'Fear')
        self.assertSetEqual(data['interactive_elements'].split(', '),
                            ['Shares Info', 'Users Interact'])

    @mock.patch('lib.iarc.client.MockClient.call')
    def test_set_iarc_storefront_data_not_rated_by_iarc(self, storefront_mock):
        self.create_switch('iarc')
        app_factory().set_iarc_storefront_data()
        assert not storefront_mock.called

    @mock.patch('mkt.webapps.models.Webapp.current_version', new=None)
    @mock.patch('lib.iarc.client.MockClient.call')
    def test_set_iarc_storefront_data_no_version(self, storefront_mock):
        self.create_switch('iarc')
        app = app_factory(rated=True, status=amo.STATUS_PUBLIC)
        ok_(not app.current_version)
        app.set_iarc_storefront_data()
        assert storefront_mock.called

    @mock.patch('lib.iarc.client.MockClient.call')
    def test_set_iarc_storefront_data_invalid_status(self, storefront_mock):
        self.create_switch('iarc')
        app = app_factory()
        for status in (amo.STATUS_NULL, amo.STATUS_PENDING):
            app.update(status=status)
            app.set_iarc_storefront_data()
            assert not storefront_mock.called

    @mock.patch('mkt.webapps.models.render_xml')
    @mock.patch('lib.iarc.client.MockClient.call')
    def test_set_iarc_storefront_data_disable(self, storefront_mock,
                                              render_mock):
        self.create_switch('iarc')
        app = app_factory(name='LOL', rated=True)
        app.current_version.update(_developer_name='Lex Luthor')
        app.set_iarc_info(123, 'abc')
        app.set_iarc_storefront_data(disable=True)
        data = render_mock.call_args_list[0][0][1]
        eq_(data['submission_id'], 123)
        eq_(data['security_code'], 'abc')
        eq_(data['title'], 'LOL')
        eq_(data['release_date'], '')

        # Also test that a deleted app has the correct release_date.
        app.delete()
        app.set_iarc_storefront_data()
        data = render_mock.call_args_list[0][0][1]
        eq_(data['submission_id'], 123)
        eq_(data['security_code'], 'abc')
        eq_(data['title'], 'LOL')
        eq_(data['release_date'], '')

    def test_get_descriptors_slugs(self):
        app = app_factory()
        eq_(app.get_descriptors_slugs(), [])

        app.set_descriptors(['has_esrb_blood', 'has_pegi_scary'])
        self.assertSetEqual(
            app.get_descriptors_slugs(), ['ESRB_BLOOD', 'PEGI_SCARY'])

    def test_get_descriptors_dehydrated(self):
        app = app_factory()
        eq_(app.get_descriptors_dehydrated(), {})

        app.set_descriptors(['has_esrb_blood', 'has_pegi_scary'])
        eq_(dict(app.get_descriptors_dehydrated()),
            {'esrb': ['blood'], 'pegi': ['scary']})

    def test_get_interactives_slugs(self):
        app = app_factory()
        eq_(app.get_interactives_slugs(), [])

        app.set_interactives(['has_digital_purchases', 'has_shares_info'])
        self.assertSetEqual(app.get_interactives_slugs(),
                            ['DIGITAL_PURCHASES', 'SHARES_INFO'])

    def test_get_interactives_dehydrated(self):
        app = app_factory()
        eq_(app.get_interactives_dehydrated(), [])

        app.set_interactives(['has_digital_purchases', 'has_shares_info'])
        eq_(app.get_interactives_dehydrated(), ['shares-info',
                                                'digital-purchases'])

    @override_settings(SECRET_KEY='test')
    def test_iarc_token(self):
        app = Webapp()
        app.id = 1
        eq_(app.iarc_token(),
            hashlib.sha512(settings.SECRET_KEY + str(app.id)).hexdigest())

    @mock.patch('mkt.webapps.models.Webapp.set_iarc_storefront_data')
    def test_delete_with_iarc(self, storefront_mock):
        self.create_switch('iarc')
        app = app_factory(rated=True)
        app.delete()
        eq_(app.status, amo.STATUS_DELETED)
        assert storefront_mock.called

    @mock.patch('mkt.webapps.models.Webapp.is_rated')
    def test_content_ratings_complete(self, is_rated_mock):
        # Default to complete if it's not needed.
        is_rated_mock.return_value = False
        app = app_factory()
        assert app.content_ratings_complete()

        self.create_switch('iarc', db=True)
        assert not app.content_ratings_complete()

        is_rated_mock.return_value = True
        assert app.content_ratings_complete()

    @mock.patch('mkt.webapps.models.Webapp.details_complete')
    @mock.patch('mkt.webapps.models.Webapp.payments_complete')
    def test_completion_errors_ignore_ratings(self, mock1, mock2):
        self.create_switch('iarc')
        app = app_factory()
        for mock in (mock1, mock2):
            mock.return_value = True

        assert app.completion_errors()
        assert not app.is_fully_complete()

        assert 'content_ratings' not in (
            app.completion_errors(ignore_ratings=True))
        assert app.is_fully_complete(ignore_ratings=True)


class DeletedAppTests(amo.tests.TestCase):

    def test_soft_deleted_no_current_version(self):
        webapp = amo.tests.app_factory()
        webapp._current_version = None
        webapp.save()
        webapp.delete()
        eq_(webapp.current_version, None)

    def test_soft_deleted_no_latest_version(self):
        webapp = amo.tests.app_factory()
        webapp._latest_version = None
        webapp.save()
        webapp.delete()
        eq_(webapp.latest_version, None)


class TestExclusions(amo.tests.TestCase):
    fixtures = fixture('prices')

    def setUp(self):
        self.app = Webapp.objects.create(premium_type=amo.ADDON_PREMIUM)
        self.app.addonexcludedregion.create(region=mkt.regions.US.id)
        self.geodata = self.app._geodata

    def make_tier(self):
        self.price = Price.objects.get(pk=1)
        AddonPremium.objects.create(addon=self.app, price=self.price)

    def test_not_premium(self):
        ok_(mkt.regions.US.id in self.app.get_excluded_region_ids())

    def test_premium(self):
        self.make_tier()
        ok_(mkt.regions.US.id in self.app.get_excluded_region_ids())

    def test_premium_remove_tier(self):
        self.make_tier()
        (self.price.pricecurrency_set
             .filter(region=mkt.regions.PL.id).update(paid=False))
        ok_(mkt.regions.PL.id in self.app.get_excluded_region_ids())

    def test_usk_rating_refused(self):
        self.geodata.update(region_de_usk_exclude=True)
        ok_(mkt.regions.DE.id in self.app.get_excluded_region_ids())

    def test_game_iarc(self):
        self.geodata.update(region_de_iarc_exclude=True,
                            region_br_iarc_exclude=True)
        excluded = self.app.get_excluded_region_ids()
        ok_(mkt.regions.BR.id in excluded)
        ok_(mkt.regions.DE.id in excluded)


class TestPackagedAppManifestUpdates(amo.tests.TestCase):
    # Note: More extensive tests for `.update_names` are above.

    def setUp(self):
        self.webapp = amo.tests.app_factory(is_packaged=True,
                                            default_locale='en-US')
        self.webapp.name = {'en-US': 'Packaged App'}
        self.webapp.save()

    @mock.patch('mkt.webapps.models.Webapp.get_manifest_json')
    def test_package_manifest_default_name_change(self, get_manifest_json):
        get_manifest_json.return_value = {'name': 'Yo'}
        self.trans_eq(self.webapp.name, 'en-US', 'Packaged App')
        self.webapp.update_name_from_package_manifest()
        self.webapp = Webapp.objects.get(pk=self.webapp.pk)
        self.trans_eq(self.webapp.name, 'en-US', 'Yo')

    @mock.patch('mkt.webapps.models.Webapp.get_manifest_json')
    def test_package_manifest_default_locale_change(self, get_manifest_json):
        get_manifest_json.return_value = {'name': 'Yo', 'default_locale': 'fr'}
        eq_(self.webapp.default_locale, 'en-US')
        self.webapp.update_name_from_package_manifest()
        eq_(self.webapp.default_locale, 'fr')
        self.trans_eq(self.webapp.name, 'en-US', None)
        self.trans_eq(self.webapp.name, 'fr', 'Yo')

    @mock.patch('mkt.webapps.models.Webapp.get_manifest_json')
    def test_package_manifest_locales_change(self, get_manifest_json):
        get_manifest_json.return_value = {'name': 'Yo',
                                          'locales': {'es': {'name': 'es'},
                                                      'de': {'name': 'de'}}}
        self.webapp.update_supported_locales()
        eq_(self.webapp.current_version.supported_locales, 'de,es')

    def test_update_name_from_package_manifest_version(self):
        evil_manifest = {
            'name': u'Evil App Name'
        }
        good_manifest = {
            'name': u'Good App Name',
        }
        latest_version = version_factory(addon=self.webapp, version='2.3',
            file_kw=dict(status=amo.STATUS_DISABLED))
        current_version = self.webapp.current_version
        AppManifest.objects.create(version=current_version,
                                   manifest=json.dumps(good_manifest))
        AppManifest.objects.create(version=latest_version,
                                   manifest=json.dumps(evil_manifest))

        self.webapp.update_name_from_package_manifest()
        eq_(self.webapp.name, u'Good App Name')


class TestWebappVersion(amo.tests.TestCase):
    fixtures = fixture('platform_all')

    def test_no_version(self):
        eq_(Webapp().get_latest_file(), None)

    def test_no_file(self):
        webapp = Webapp.objects.create(manifest_url='http://foo.com')
        webapp._current_version = Version.objects.create(addon=webapp)
        eq_(webapp.get_latest_file(), None)

    def test_right_file(self):
        webapp = Webapp.objects.create(manifest_url='http://foo.com')
        version = Version.objects.create(addon=webapp)
        old_file = File.objects.create(version=version, platform_id=1)
        old_file.update(created=datetime.now() - timedelta(days=1))
        new_file = File.objects.create(version=version, platform_id=1)
        webapp._current_version = version
        eq_(webapp.get_latest_file().pk, new_file.pk)


class TestWebappManager(amo.tests.TestCase):

    def test_by_identifier(self):
        w = Webapp.objects.create(app_slug='foo')
        eq_(Webapp.objects.by_identifier(w.id), w)
        eq_(Webapp.objects.by_identifier(str(w.id)), w)
        eq_(Webapp.objects.by_identifier(w.app_slug), w)
        with self.assertRaises(Webapp.DoesNotExist):
            Webapp.objects.by_identifier('fake')

    def test_rated(self):
        self.create_switch('iarc')
        rated = app_factory(rated=True)
        app_factory()
        eq_(Webapp.objects.count(), 2)
        eq_(list(Webapp.objects.rated()), [rated])


class TestManifest(BaseWebAppTest):

    def test_get_manifest_json(self):
        webapp = self.post_addon()
        assert webapp.current_version
        assert webapp.current_version.has_files
        with open(self.manifest, 'r') as mf:
            manifest_json = json.load(mf)
            eq_(webapp.get_manifest_json(), manifest_json)


class PackagedFilesMixin(amo.tests.AMOPaths):

    def setUp(self):
        self.package = self.packaged_app_path('mozball.zip')

    def setup_files(self, filename='mozball.zip'):
        # This assumes self.file exists.
        if not storage.exists(self.file.file_path):
            try:
                # We don't care if these dirs exist.
                os.makedirs(os.path.dirname(self.file.file_path))
            except OSError:
                pass
            shutil.copyfile(self.packaged_app_path(filename),
                            self.file.file_path)


class TestPackagedModel(amo.tests.TestCase):

    @mock.patch.object(settings, 'SITE_URL', 'http://hy.fr')
    @mock.patch('lib.crypto.packaged.os.unlink', new=mock.Mock)
    def test_create_blocklisted_version(self):
        app = app_factory(name=u'Mozillaball ょ', app_slug='test',
                          is_packaged=True, version_kw={'version': '1.0',
                                                        'created': None})
        app.create_blocklisted_version()
        app = app.reload()
        v = app.versions.latest()
        f = v.files.latest()

        eq_(app.status, amo.STATUS_BLOCKED)
        eq_(app.versions.count(), 2)
        eq_(v.version, 'blocklisted')

        eq_(app._current_version, v)
        assert 'blocklisted' in f.filename
        eq_(f.status, amo.STATUS_BLOCKED)

        # Check manifest.
        url = app.get_manifest_url()
        res = self.client.get(url)
        eq_(res['Content-type'],
            'application/x-web-app-manifest+json; charset=utf-8')
        assert 'etag' in res._headers
        data = json.loads(res.content)
        eq_(data['name'], 'Blocked by Mozilla')
        eq_(data['version'], 'blocklisted')
        eq_(data['package_path'], 'http://hy.fr/downloads/file/%s/%s' % (
            f.id, f.filename))


class TestPackagedManifest(BasePackagedAppTest):

    def _get_manifest_json(self):
        zf = zipfile.ZipFile(self.package)
        data = zf.open('manifest.webapp').read()
        zf.close()
        return json.loads(data)

    def test_get_manifest_json(self):
        webapp = self.post_addon()
        eq_(webapp.status, amo.STATUS_NULL)
        assert webapp.current_version
        assert webapp.current_version.has_files
        mf = self._get_manifest_json()
        eq_(webapp.get_manifest_json(), mf)

    def test_get_manifest_json_w_file(self):
        webapp = self.post_addon()
        eq_(webapp.status, amo.STATUS_NULL)
        assert webapp.current_version
        assert webapp.current_version.has_files
        file_ = webapp.current_version.all_files[0]
        mf = self._get_manifest_json()
        eq_(webapp.get_manifest_json(file_), mf)

    def test_get_manifest_json_multiple_versions(self):
        # Post the real app/version, but backfill an older version.
        webapp = self.post_addon()
        latest_version = webapp.latest_version
        webapp.current_version.files.update(status=amo.STATUS_PUBLIC)
        version = version_factory(addon=webapp, version='0.5',
                                  created=self.days_ago(1))
        version.files.update(created=self.days_ago(1))
        webapp = Webapp.objects.get(pk=webapp.pk)
        webapp._current_version = None  # update_version() should find the 1.0.
        webapp.update_version()
        eq_(webapp.current_version, latest_version)
        assert webapp.current_version.has_files
        mf = self._get_manifest_json()
        eq_(webapp.get_manifest_json(), mf)

    def test_get_manifest_json_multiple_version_disabled(self):
        # Post an app, then emulate a reviewer reject and add a new, pending
        # version.
        webapp = self.post_addon()
        webapp.latest_version.files.update(status=amo.STATUS_DISABLED)
        webapp.latest_version.update(created=self.days_ago(1))
        webapp.update(status=amo.STATUS_REJECTED, _current_version=None)
        version = version_factory(addon=webapp, version='2.0',
                                  file_kw=dict(status=amo.STATUS_PENDING))
        mf = self._get_manifest_json()
        AppManifest.objects.create(version=version,
                                   manifest=json.dumps(mf))
        webapp.update_version()
        webapp = webapp.reload()
        eq_(webapp.latest_version, version)
        self.file = version.all_files[0]
        self.setup_files()
        eq_(webapp.get_manifest_json(), mf)

    def test_cached_manifest_is_cached(self):
        webapp = self.post_addon()
        # First call does queries and caches results.
        webapp.get_cached_manifest()
        # Subsequent calls are cached.
        with self.assertNumQueries(0):
            webapp.get_cached_manifest()

    @mock.patch('mkt.webapps.models.cache')
    def test_cached_manifest_no_version_not_cached(self, cache_mock):
        webapp = self.post_addon(
            data={'packaged': True, 'free_platforms': 'free-firefoxos'})
        webapp._current_version = None
        eq_(webapp.get_cached_manifest(force=True), '{}')
        assert not cache_mock.called

    def test_cached_manifest_contents(self):
        webapp = self.post_addon(
            data={'packaged': True, 'free_platforms': 'free-firefoxos'})
        version = webapp.current_version
        self.file = version.all_files[0]
        self.setup_files()
        manifest = self._get_manifest_json()

        data = json.loads(webapp.get_cached_manifest())
        eq_(data['name'], webapp.name)
        eq_(data['version'], webapp.current_version.version)
        eq_(data['size'], self.file.size)
        eq_(data['release_notes'], version.releasenotes)
        eq_(data['package_path'], absolutify(
            os.path.join(reverse('downloads.file', args=[self.file.id]),
                         self.file.filename)))
        eq_(data['developer'], manifest['developer'])
        eq_(data['icons'], manifest['icons'])
        eq_(data['locales'], manifest['locales'])

    @mock.patch.object(packaged, 'sign', mock_sign)
    def test_package_path(self):
        webapp = self.post_addon(
            data={'packaged': True, 'free_platforms': 'free-firefoxos'})
        version = webapp.current_version
        file = version.all_files[0]
        res = self.client.get(file.get_url_path('manifest'))
        eq_(res.status_code, 200)
        eq_(res['content-type'], 'application/zip')

    def test_packaged_with_BOM(self):
        # Exercise separate code paths to loading the packaged app manifest.
        self.setup_files('mozBOM.zip')
        assert WebAppParser().parse(self.file.file_path)
        self.assertTrue(self.app.has_icon_in_manifest())


class TestDomainFromURL(unittest.TestCase):

    def test_simple(self):
        eq_(Webapp.domain_from_url('http://mozilla.com/'),
            'http://mozilla.com')

    def test_long_path(self):
        eq_(Webapp.domain_from_url('http://mozilla.com/super/rad.webapp'),
            'http://mozilla.com')

    def test_no_normalize_www(self):
        eq_(Webapp.domain_from_url('http://www.mozilla.com/super/rad.webapp'),
            'http://www.mozilla.com')

    def test_with_port(self):
        eq_(Webapp.domain_from_url('http://mozilla.com:9000/'),
            'http://mozilla.com:9000')

    def test_subdomains(self):
        eq_(Webapp.domain_from_url('http://apps.mozilla.com/'),
            'http://apps.mozilla.com')

    def test_https(self):
        eq_(Webapp.domain_from_url('https://mozilla.com/'),
            'https://mozilla.com')

    def test_normalize_case(self):
        eq_(Webapp.domain_from_url('httP://mOzIllA.com/'),
            'http://mozilla.com')

    @raises(ValueError)
    def test_none(self):
        Webapp.domain_from_url(None)

    @raises(ValueError)
    def test_empty(self):
        Webapp.domain_from_url('')

    def test_empty_or_none(self):
        eq_(Webapp.domain_from_url(None, allow_none=True), None)


class TestTransformer(amo.tests.TestCase):
    fixtures = fixture('webapp_337141')

    def setUp(self):
        self.device = DEVICE_TYPES.keys()[0]

    @mock.patch('mkt.webapps.models.Addon.transformer')
    def test_addon_transformer_not_called(self, transformer):
        transformer.return_value = {}
        list(Webapp.objects.all())
        assert not transformer.called

    def test_versions(self):
        webapps = list(Webapp.objects.all())
        with self.assertNumQueries(0):
            for webapp in webapps:
                ok_(isinstance(webapp.latest_version, Version))
                ok_(isinstance(webapp.current_version, Version))

    def test_previews(self):
        p1 = Preview.objects.create(filetype='image/png', addon_id=337141,
                                    position=0)
        p2 = Preview.objects.create(filetype='image/png', addon_id=337141,
                                    position=1)

        webapps = list(Webapp.objects.all())
        with self.assertNumQueries(0):
            for webapp in webapps:
                eq_(webapp.all_previews, [p1, p2])

    def test_prices(self):
        self.make_premium(Webapp.objects.get(pk=337141))
        webapps = list(Webapp.objects.all())
        with self.assertNumQueries(0):
            for webapp in webapps:
                ok_(unicode(webapp.premium))
                eq_(str(webapp.get_tier().price), '1.00')
                ok_(webapp.get_tier_name())

    def test_prices_free(self):
        webapps = list(Webapp.objects.all())
        with self.assertNumQueries(0):
            for webapp in webapps:
                eq_(webapp.premium, None)
                eq_(webapp.get_tier(), None)

    def test_device_types(self):
        AddonDeviceType.objects.create(addon_id=337141,
                                       device_type=self.device)
        webapps = list(Webapp.objects.filter(id=337141))

        with self.assertNumQueries(0):
            for webapp in webapps:
                assert webapp._device_types
                eq_(webapp.device_types, [DEVICE_TYPES[self.device]])

    def test_device_type_cache(self):
        webapp = Webapp.objects.get(id=337141)
        webapp._device_types = []
        with self.assertNumQueries(0):
            eq_(webapp.device_types, [])


class TestDetailsComplete(amo.tests.TestCase):

    def setUp(self):
        self.device = DEVICE_TYPES.keys()[0]
        self.cat = Category.objects.create(name='c', type=amo.ADDON_WEBAPP)
        self.webapp = Webapp.objects.create(type=amo.ADDON_WEBAPP,
                                            status=amo.STATUS_NULL)

    def fail(self, value):
        assert not self.webapp.details_complete(), value
        reasons = self.webapp.details_errors()
        assert value in reasons[0], reasons

    def test_fail(self):
        self.fail('email')

        self.webapp.support_email = 'a@a.com'
        self.webapp.save()
        self.fail('name')

        self.webapp.name = 'name'
        self.webapp.save()
        self.fail('device')

        self.webapp.addondevicetype_set.create(device_type=self.device)
        self.webapp.save()
        self.fail('category')

        AddonCategory.objects.create(addon=self.webapp, category=self.cat)
        self.fail('screenshot')

        self.webapp.previews.create()
        eq_(self.webapp.details_complete(), True)


class TestAddonExcludedRegion(amo.tests.WebappTestCase):

    def setUp(self):
        super(TestAddonExcludedRegion, self).setUp()
        self.excluded = self.app.addonexcludedregion

        eq_(list(self.excluded.values_list('id', flat=True)), [])
        self.er = self.app.addonexcludedregion.create(region=mkt.regions.UK.id)
        eq_(list(self.excluded.values_list('id', flat=True)), [self.er.id])

    def test_exclude_multiple(self):
        other = AddonExcludedRegion.objects.create(addon=self.app,
                                                   region=mkt.regions.BR.id)
        self.assertSetEqual(self.excluded.values_list('id', flat=True),
                            [self.er.id, other.id])

    def test_remove_excluded(self):
        self.er.delete()
        eq_(list(self.excluded.values_list('id', flat=True)), [])

    def test_get_region(self):
        eq_(self.er.get_region(), mkt.regions.UK)

    def test_unicode(self):
        eq_(unicode(self.er), '%s: %s' % (self.app, mkt.regions.UK.slug))


class TestContentRating(amo.tests.WebappTestCase):

    def setUp(self):
        self.app = self.get_app()
        self.create_switch('iarc')

    @mock.patch.object(mkt.regions.BR, 'ratingsbody',
                       mkt.ratingsbodies.CLASSIND)
    @mock.patch.object(mkt.regions.US, 'ratingsbody', mkt.ratingsbodies.ESRB)
    @mock.patch.object(mkt.regions.VE, 'ratingsbody',
                       mkt.ratingsbodies.GENERIC)
    def test_get_regions_and_slugs(self):
        classind_rating = ContentRating.objects.create(
            addon=self.app, ratings_body=mkt.ratingsbodies.CLASSIND.id,
            rating=0)
        regions = classind_rating.get_regions()
        assert mkt.regions.BR in regions
        assert mkt.regions.US not in regions
        assert mkt.regions.VE not in regions

        slugs = classind_rating.get_region_slugs()
        assert mkt.regions.BR.slug in slugs
        assert mkt.regions.US.slug not in slugs
        assert mkt.regions.VE.slug not in slugs

    @mock.patch.object(mkt.regions.BR, 'ratingsbody',
                       mkt.ratingsbodies.CLASSIND)
    @mock.patch.object(mkt.regions.DE, 'ratingsbody', mkt.ratingsbodies.ESRB)
    @mock.patch.object(mkt.regions.VE, 'ratingsbody',
                       mkt.ratingsbodies.GENERIC)
    def test_get_regions_and_slugs_generic_fallback(self):
        gen_rating = ContentRating.objects.create(
            addon=self.app, ratings_body=mkt.ratingsbodies.GENERIC.id,
            rating=0)
        regions = gen_rating.get_regions()
        assert mkt.regions.BR not in regions
        assert mkt.regions.DE not in regions
        assert mkt.regions.VE in regions

        slugs = gen_rating.get_region_slugs()
        assert mkt.regions.BR.slug not in slugs
        assert mkt.regions.DE.slug not in slugs
        assert mkt.regions.VE.slug not in slugs

        # We have a catch-all 'generic' region for all regions wo/ r.body.
        assert mkt.regions.GENERIC_RATING_REGION_SLUG in slugs

    @mock.patch.object(mkt.ratingsbodies.CLASSIND, 'name', 'CLASSIND')
    @mock.patch.object(mkt.ratingsbodies.CLASSIND_10, 'name', '10+')
    @mock.patch.object(mkt.ratingsbodies.ESRB_E, 'name', 'Everybody 10+')
    @mock.patch.object(mkt.ratingsbodies.ESRB_E, 'label', '10')
    def test_get_ratings(self):
        # Infer the label from the name.
        cr = ContentRating.objects.create(
            addon=self.app, ratings_body=mkt.ratingsbodies.CLASSIND.id,
            rating=mkt.ratingsbodies.CLASSIND_10.id)
        eq_(cr.get_rating().label, '10')
        eq_(cr.get_body().label, 'classind')

        # When already has label set.
        eq_(ContentRating.objects.create(
                addon=self.app, ratings_body=mkt.ratingsbodies.ESRB.id,
                rating=mkt.ratingsbodies.ESRB_E.id).get_rating().label,
            '10')


class TestContentRatingsIn(amo.tests.WebappTestCase):

    def test_not_in_region(self):
        for region in mkt.regions.ALL_REGIONS:
            eq_(self.app.content_ratings_in(region=region), [])

        for region in mkt.regions.ALL_REGIONS:
            AddonExcludedRegion.objects.create(addon=self.app,
                                               region=region.id)
            eq_(self.get_app().content_ratings_in(region=region), [])

    def test_in_for_region_and_category(self):
        cat = Category.objects.create(slug='games', type=amo.ADDON_WEBAPP)
        for region in mkt.regions.ALL_REGIONS:
            eq_(self.app.content_ratings_in(region=region, category='games'),
                [])
            eq_(self.app.content_ratings_in(region=region, category=cat), [])

    def test_in_region_and_category(self):
        self.make_game()
        cat = Category.objects.get(slug='games')
        for region in mkt.regions.ALL_REGIONS:
            eq_(self.app.listed_in(region=region, category='games'), True)
            eq_(self.app.listed_in(region=region, category=cat),
                True)

    def test_in_region_and_not_in_category(self):
        cat = Category.objects.create(slug='games', type=amo.ADDON_WEBAPP)
        for region in mkt.regions.ALL_REGIONS:
            eq_(self.app.content_ratings_in(region=region, category='games'),
                [])
            eq_(self.app.content_ratings_in(region=region, category=cat), [])

    @mock.patch.object(mkt.regions.CO, 'ratingsbody', None)
    @mock.patch.object(mkt.regions.BR, 'ratingsbody',
                       mkt.ratingsbodies.CLASSIND)
    def test_generic_fallback(self):
        # Test region with no rating body returns generic content rating.
        crs = ContentRating.objects.create(
            addon=self.app, ratings_body=mkt.ratingsbodies.GENERIC.id,
            rating=mkt.ratingsbodies.GENERIC_3.id)
        eq_(self.app.content_ratings_in(region=mkt.regions.CO), [crs])

        # Test region with rating body does not include generic content rating.
        assert crs not in self.app.content_ratings_in(region=mkt.regions.BR)


class TestIARCInfo(amo.tests.WebappTestCase):

    def test_no_info(self):
        with self.assertRaises(IARCInfo.DoesNotExist):
            self.app.iarc_info

    def test_info(self):
        IARCInfo.objects.create(addon=self.app, submission_id=1,
                                security_code='s3kr3t')
        eq_(self.app.iarc_info.submission_id, 1)
        eq_(self.app.iarc_info.security_code, 's3kr3t')


class TestQueue(amo.tests.WebappTestCase):

    def test_in_rereview_queue(self):
        assert not self.app.in_rereview_queue()
        RereviewQueue.objects.create(addon=self.app)
        assert self.app.in_rereview_queue()

    def test_in_escalation_queue(self):
        assert not self.app.in_escalation_queue()
        EscalationQueue.objects.create(addon=self.app)
        assert self.app.in_escalation_queue()


class TestPackagedSigning(amo.tests.WebappTestCase):

    @mock.patch('lib.crypto.packaged.sign')
    def test_not_packaged(self, sign):
        self.app.update(is_packaged=False)
        assert not self.app.sign_if_packaged(self.app.current_version.pk)
        assert not sign.called

    @mock.patch('lib.crypto.packaged.sign')
    def test_packaged(self, sign):
        self.app.update(is_packaged=True)
        assert self.app.sign_if_packaged(self.app.current_version.pk)
        eq_(sign.call_args[0][0], self.app.current_version.pk)

    @mock.patch('lib.crypto.packaged.sign')
    def test_packaged_reviewer(self, sign):
        self.app.update(is_packaged=True)
        assert self.app.sign_if_packaged(self.app.current_version.pk,
                                         reviewer=True)
        eq_(sign.call_args[0][0], self.app.current_version.pk)
        eq_(sign.call_args[1]['reviewer'], True)


class TestUpdateStatus(amo.tests.TestCase):

    def setUp(self):
        # Disabling signals to simplify these tests. We call update_status()
        # manually in them.
        version_changed_signal.disconnect(version_changed,
                                          dispatch_uid='version_changed')
        post_save.disconnect(update_status, sender=Version,
                             dispatch_uid='version_update_status')
        post_delete.disconnect(update_status, sender=Version,
                               dispatch_uid='version_update_status')

    def tearDown(self):
        version_changed_signal.connect(version_changed,
                                       dispatch_uid='version_changed')
        post_save.connect(update_status, sender=Version,
                          dispatch_uid='version_update_status')
        post_delete.connect(update_status, sender=Version,
                            dispatch_uid='version_update_status')

    def test_no_versions(self):
        app = Webapp.objects.create(status=amo.STATUS_PUBLIC)
        app.update_status()
        eq_(app.status, amo.STATUS_NULL)

    def test_version_no_files(self):
        app = Webapp.objects.create(status=amo.STATUS_PUBLIC)
        Version(addon=app).save()
        app.update_status()
        eq_(app.status, amo.STATUS_NULL)

    def test_only_version_deleted(self):
        app = amo.tests.app_factory(status=amo.STATUS_REJECTED)
        app.current_version.delete()
        app.update_status()
        eq_(app.status, amo.STATUS_NULL)

    def test_other_version_deleted(self):
        app = amo.tests.app_factory(status=amo.STATUS_REJECTED)
        amo.tests.version_factory(addon=app)
        app.current_version.delete()
        app.update_status()
        eq_(app.status, amo.STATUS_REJECTED)

    def test_one_version_pending(self):
        app = amo.tests.app_factory(status=amo.STATUS_REJECTED,
                                    file_kw=dict(status=amo.STATUS_DISABLED))
        amo.tests.version_factory(addon=app,
                                  file_kw=dict(status=amo.STATUS_PENDING))
        with mock.patch('mkt.webapps.models.Webapp.is_fully_complete') as comp:
            comp.return_value = True
            app.update_status()
        eq_(app.status, amo.STATUS_PENDING)

    def test_one_version_pending_not_fully_complete(self):
        app = amo.tests.app_factory(status=amo.STATUS_REJECTED,
                                    file_kw=dict(status=amo.STATUS_DISABLED))
        amo.tests.version_factory(addon=app,
                                  file_kw=dict(status=amo.STATUS_PENDING))
        with mock.patch('mkt.webapps.models.Webapp.is_fully_complete') as comp:
            comp.return_value = False
            app.update_status()
        eq_(app.status, amo.STATUS_REJECTED)  # Didn't change.

    def test_one_version_public(self):
        app = amo.tests.app_factory(status=amo.STATUS_PUBLIC)
        amo.tests.version_factory(addon=app,
                                  file_kw=dict(status=amo.STATUS_DISABLED))
        app.update_status()
        eq_(app.status, amo.STATUS_PUBLIC)

    def test_was_public_waiting_then_new_version(self):
        app = amo.tests.app_factory(status=amo.STATUS_PUBLIC_WAITING)
        File.objects.filter(version__addon=app).update(status=app.status)
        amo.tests.version_factory(addon=app,
                                  file_kw=dict(status=amo.STATUS_PENDING))
        app.update_status()
        eq_(app.status, amo.STATUS_PUBLIC_WAITING)

    def test_blocklisted(self):
        app = amo.tests.app_factory(status=amo.STATUS_BLOCKED)
        app.current_version.delete()
        app.update_status()
        eq_(app.status, amo.STATUS_BLOCKED)


class TestInstalled(amo.tests.TestCase):

    def setUp(self):
        user = UserProfile.objects.create(email='f@f.com')
        app = Addon.objects.create(type=amo.ADDON_WEBAPP)
        self.m = functools.partial(Installed.objects.safer_get_or_create,
                                   user=user, addon=app)

    def test_install_type(self):
        assert self.m(install_type=apps.INSTALL_TYPE_USER)[1]
        assert not self.m(install_type=apps.INSTALL_TYPE_USER)[1]
        assert self.m(install_type=apps.INSTALL_TYPE_REVIEWER)[1]


class TestAppFeatures(DynamicBoolFieldsTestMixin, amo.tests.TestCase):

    def setUp(self):
        super(TestAppFeatures, self).setUp()

        self.model = AppFeatures
        self.related_name = 'features'

        self.BOOL_DICT = mkt.constants.features.APP_FEATURES
        self.flags = ('APPS', 'GEOLOCATION', 'PAY', 'SMS')
        self.expected = [u'App Management API', u'Geolocation', u'Web Payment',
                         u'WebSMS']

        self.af = AppFeatures.objects.get()

    def _get_related_bool_obj(self):
        return getattr(self.app.current_version, self.related_name)

    def test_signature_parity(self):
        # Test flags -> signature -> flags works as expected.
        self._flag()
        signature = self.app.current_version.features.to_signature()
        eq_(signature.count('.'), 2, 'Unexpected signature format')

        self.af.set_flags(signature)
        self._check(self.af)

    def test_bad_data(self):
        self.af.set_flags('foo')
        self.af.set_flags('<script>')

    def test_default_false(self):
        obj = self.model(version=self.app.current_version)
        eq_(getattr(obj, 'has_%s' % self.flags[0].lower()), False)


class TestRatingDescriptors(DynamicBoolFieldsTestMixin, amo.tests.TestCase):

    def setUp(self):
        super(TestRatingDescriptors, self).setUp()
        self.model = RatingDescriptors
        self.related_name = 'rating_descriptors'

        self.BOOL_DICT = mkt.ratingdescriptors.RATING_DESCS
        self.flags = ('ESRB_VIOLENCE', 'PEGI_LANG', 'CLASSIND_DRUGS')
        self.expected = [u'Violence', u'Language', u'Drugs']

        RatingDescriptors.objects.create(addon=self.app)

    @mock.patch.dict('mkt.ratingdescriptors.RATING_DESCS',
                     PEGI_LANG={'name': _(u'H\xe9llo')})
    def test_to_list_nonascii(self):
        self.expected[1] = u'H\xe9llo'
        self._flag()
        to_list = self.app.rating_descriptors.to_list()
        self.assertSetEqual(self.to_unicode(to_list), self.expected)

    def test_desc_mapping(self):
        descs = RatingDescriptors.objects.create(addon=app_factory())
        for body, mapping in DESC_MAPPING.items():
            for native, rating_desc_field in mapping.items():
                assert hasattr(descs, rating_desc_field), rating_desc_field

    def test_reverse_desc_mapping(self):
        descs = RatingDescriptors.objects.create(addon=app_factory())
        for desc in descs._fields():
            eq_(type(REVERSE_DESC_MAPPING.get(desc)), unicode, desc)

    def test_iarc_deserialize(self):
        descs = RatingDescriptors.objects.create(
            addon=app_factory(), has_esrb_blood=True, has_pegi_scary=True)
        self.assertSetEqual(descs.iarc_deserialize().split(', '),
                            ['Blood', 'Fear'])
        eq_(descs.iarc_deserialize(body=mkt.ratingsbodies.ESRB), 'Blood')


class TestRatingInteractives(DynamicBoolFieldsTestMixin, amo.tests.TestCase):

    def setUp(self):
        super(TestRatingInteractives, self).setUp()
        self.model = RatingInteractives
        self.related_name = 'rating_interactives'

        self.BOOL_DICT = mkt.ratinginteractives.RATING_INTERACTIVES
        self.flags = ('SHARES_INFO', 'DIGITAL_PURCHASES', 'USERS_INTERACT')
        self.expected = [u'Shares Info', u'Digital Purchases',
                         u'Users Interact']

        RatingInteractives.objects.create(addon=self.app)

    def test_interactives_mapping(self):
        interactives = RatingInteractives.objects.create(addon=app_factory())
        for native, field in INTERACTIVES_MAPPING.items():
            assert hasattr(interactives, field)

    def test_reverse_interactives_mapping(self):
        interactives = RatingInteractives.objects.create(addon=app_factory())
        for interactive_field in interactives._fields():
            assert REVERSE_INTERACTIVES_MAPPING.get(interactive_field)

    def test_iarc_deserialize(self):
        interactives = RatingInteractives.objects.create(
            addon=app_factory(), has_users_interact=True, has_shares_info=True)
        self.assertSetEqual(
            interactives.iarc_deserialize().split(', '),
            ['Shares Info', 'Users Interact'])


class TestManifestUpload(BaseUploadTest, amo.tests.TestCase):
    fixtures = fixture('webapp_337141')

    def setUp(self):
        super(TestManifestUpload, self).setUp()
        self.platform = Platform.objects.get(id=amo.PLATFORM_ALL.id)
        self.addCleanup(translation.deactivate)

    def manifest(self, name):
        return os.path.join(settings.ROOT, 'mkt', 'developers', 'tests',
                            'addons', name)

    @mock.patch('mkt.webapps.models.parse_addon')
    def test_manifest_updated_developer_name(self, parse_addon):
        parse_addon.return_value = {
            'version': '4.0',
            'developer_name': u'Méâ'
        }
        # Note: we need a valid FileUpload instance, but in the end we are not
        # using its contents since we are mocking parse_addon().
        upload = self.get_upload(abspath=self.manifest('mozball.webapp'),
                                 is_webapp=True)
        app = Addon.objects.get(pk=337141)
        app.manifest_updated('', upload)
        version = app.current_version.reload()
        eq_(version.version, '4.0')
        eq_(version.developer_name, u'Méâ')

    @mock.patch('mkt.webapps.models.parse_addon')
    def test_manifest_updated_long_developer_name(self, parse_addon):
        truncated_developer_name = u'é' * 255
        long_developer_name = truncated_developer_name + u'ßßßß'
        parse_addon.return_value = {
            'version': '4.1',
            'developer_name': long_developer_name,
        }
        # Note: we need a valid FileUpload instance, but in the end we are not
        # using its contents since we are mocking parse_addon().
        upload = self.get_upload(abspath=self.manifest('mozball.webapp'),
                                 is_webapp=True)
        app = Addon.objects.get(pk=337141)
        app.manifest_updated('', upload)
        version = app.current_version.reload()
        eq_(version.version, '4.1')
        eq_(version.developer_name, truncated_developer_name)

    def test_manifest_url(self):
        upload = self.get_upload(abspath=self.manifest('mozball.webapp'))
        addon = Addon.from_upload(upload, [self.platform])
        assert addon.is_webapp()
        eq_(addon.manifest_url, upload.name)

    def test_app_domain(self):
        upload = self.get_upload(abspath=self.manifest('mozball.webapp'))
        upload.name = 'http://mozilla.com/my/rad/app.webapp'  # manifest URL
        addon = Addon.from_upload(upload, [self.platform])
        eq_(addon.app_domain, 'http://mozilla.com')

    def test_non_english_app(self):
        upload = self.get_upload(abspath=self.manifest('non-english.webapp'))
        upload.name = 'http://mozilla.com/my/rad/app.webapp'  # manifest URL
        addon = Addon.from_upload(upload, [self.platform])
        eq_(addon.default_locale, 'it')
        eq_(unicode(addon.name), 'ItalianMozBall')
        eq_(addon.name.locale, 'it')

    def test_webapp_default_locale_override(self):
        with nested(tempfile.NamedTemporaryFile('w', suffix='.webapp'),
                    open(self.manifest('mozball.webapp'))) as (tmp, mf):
            mf = json.load(mf)
            mf['default_locale'] = 'es'
            tmp.write(json.dumps(mf))
            tmp.flush()
            upload = self.get_upload(abspath=tmp.name)
        addon = Addon.from_upload(upload, [self.platform])
        eq_(addon.default_locale, 'es')

    def test_webapp_default_locale_unsupported(self):
        with nested(tempfile.NamedTemporaryFile('w', suffix='.webapp'),
                    open(self.manifest('mozball.webapp'))) as (tmp, mf):
            mf = json.load(mf)
            mf['default_locale'] = 'gb'
            tmp.write(json.dumps(mf))
            tmp.flush()
            upload = self.get_upload(abspath=tmp.name)
        addon = Addon.from_upload(upload, [self.platform])
        eq_(addon.default_locale, 'en-US')

    def test_browsing_locale_does_not_override(self):
        with translation.override('fr'):
            # Upload app with en-US as default.
            upload = self.get_upload(abspath=self.manifest('mozball.webapp'))
            addon = Addon.from_upload(upload, [self.platform])
            eq_(addon.default_locale, 'en-US')  # not fr

    @raises(forms.ValidationError)
    def test_malformed_locales(self):
        manifest = self.manifest('malformed-locales.webapp')
        upload = self.get_upload(abspath=manifest)
        Addon.from_upload(upload, [self.platform])


class TestGeodata(amo.tests.WebappTestCase):

    def setUp(self):
        super(TestGeodata, self).setUp()
        self.geo = self.app.geodata

    def test_app_geodata(self):
        assert isinstance(Webapp(id=337141).geodata, Geodata)

    def test_unicode(self):
        eq_(unicode(self.geo),
            u'%s (unrestricted): <Webapp 337141>' % self.geo.id)
        self.geo.update(restricted=True)
        eq_(unicode(self.geo),
            u'%s (restricted): <Webapp 337141>' % self.geo.id)

    def test_get_status(self):
        status = amo.STATUS_PENDING
        eq_(self.geo.get_status(mkt.regions.CN), status)
        eq_(self.geo.region_cn_status, status)

        status = amo.STATUS_PUBLIC
        self.geo.update(region_cn_status=status)
        eq_(self.geo.get_status(mkt.regions.CN), status)
        eq_(self.geo.region_cn_status, status)

    def test_set_status(self):
        status = amo.STATUS_PUBLIC

        # Called with `save=False`.
        self.geo.set_status(mkt.regions.CN, status)
        eq_(self.geo.region_cn_status, status)
        eq_(self.geo.reload().region_cn_status, amo.STATUS_PENDING,
            '`set_status(..., save=False)` should not save the value')

        # Called with `save=True`.
        self.geo.set_status(mkt.regions.CN, status, save=True)
        eq_(self.geo.region_cn_status, status)
        eq_(self.geo.reload().region_cn_status, status)

    def test_banner_regions_names(self):
        eq_(self.geo.banner_regions, None)
        eq_(self.geo.banner_regions_names(), [])

        self.geo.update(banner_regions=[mkt.regions.UK.id, mkt.regions.CN.id])
        eq_(self.geo.banner_regions_names(), [u'China', u'United Kingdom'])


@mock.patch.object(settings, 'PRE_GENERATE_APKS', True)
@mock.patch('mkt.webapps.tasks.pre_generate_apk')
class TestPreGenAPKs(amo.tests.WebappTestCase):

    def setUp(self):
        super(TestPreGenAPKs, self).setUp()
        self.manifest_url = 'http://some-app.com/manifest.webapp'
        self.app.update(status=amo.STATUS_PUBLIC,
                        manifest_url=self.manifest_url)
        # Set up the app to support Android.
        self.app.addondevicetype_set.create(device_type=amo.DEVICE_MOBILE.id)

    def switch_device(self, device_id):
        self.app.addondevicetype_set.all().delete()
        self.app.addondevicetype_set.create(device_type=device_id)

    def test_approved_apps(self, pre_gen_task):
        assert not pre_gen_task.delay.called
        self.app.save()
        pre_gen_task.delay.assert_called_with(self.app.id)

    def test_unapproved_apps(self, pre_gen_task):
        self.app.update(status=amo.STATUS_REJECTED)
        assert not pre_gen_task.delay.called, (
            'APKs for unapproved apps should not be pre-generated')

    def test_disabled(self, pre_gen_task):
        with self.settings(PRE_GENERATE_APKS=False):
            self.app.save()
        assert not pre_gen_task.delay.called, (
            'task should not be called if PRE_GENERATE_APKS is False')

    def test_ignore_firefox_os_apps(self, pre_gen_task):
        self.switch_device(amo.DEVICE_GAIA.id)
        self.app.save()
        assert not pre_gen_task.delay.called, (
            'task should not be called for Firefox OS apps')

    def test_treat_tablet_as_android(self, pre_gen_task):
        self.switch_device(amo.DEVICE_TABLET.id)
        self.app.save()
        assert pre_gen_task.delay.called, (
            'task should be called for tablet apps')


class TestSearchSignals(amo.tests.ESTestCase):

    def setUp(self):
        super(TestSearchSignals, self).setUp()
        self.addCleanup(self.cleanup)

    def cleanup(self):
        for index in settings.ES_INDEXES.values():
            try:
                self.es.delete_index(index)
            except pyelasticsearch.ElasticHttpNotFoundError:
                pass

    def test_create(self):
        eq_(S(WebappIndexer).count(), 0)
        amo.tests.app_factory()
        self.refresh()
        eq_(S(WebappIndexer).count(), 1)

    def test_update(self):
        app = amo.tests.app_factory()
        self.refresh()
        eq_(S(WebappIndexer).count(), 1)

        prev_name = unicode(app.name)
        app.name = 'yolo'
        app.save()
        self.refresh()

        eq_(S(WebappIndexer).count(), 1)
        eq_(S(WebappIndexer).query(name=prev_name).count(), 0)
        eq_(S(WebappIndexer).query(name='yolo').count(), 1)
