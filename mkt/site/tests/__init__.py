import json
import os
import random
import time
from contextlib import contextmanager
from datetime import datetime, timedelta
from decimal import Decimal
from functools import partial
from urlparse import SplitResult, urlsplit, urlunsplit

from django import forms, test
from django.db import connections, transaction, DEFAULT_DB_ALIAS
from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.core.cache import cache
from django.core.management import call_command
from django.core.urlresolvers import reverse
from django.test.client import Client, RequestFactory
from django.utils import translation
from django.utils.translation import trans_real

import elasticsearch
import mock
import tower
from dateutil.parser import parse as dateutil_parser
from django_browserid.tests import mock_browserid
from nose.exc import SkipTest
from nose.tools import eq_
from pyquery import PyQuery as pq
from waffle.models import Flag, Sample, Switch

import mkt
from lib.es.management.commands import reindex
from lib.post_request_task import task as post_request_task
from mkt.access.acl import check_ownership
from mkt.access.models import Group, GroupUser
from mkt.constants import regions
from mkt.constants.payments import PROVIDER_REFERENCE
from mkt.prices.models import AddonPremium, Price, PriceCurrency
from mkt.search.indexers import BaseIndexer
from mkt.site.fixtures import fixture
from mkt.site.storage_utils import (copy_stored_file, local_storage,
                                    private_storage)
from mkt.site.utils import (app_factory, extension_factory,  # NOQA
                            website_factory)  # NOQA
from mkt.translations.hold import clean_translations
from mkt.translations.models import Translation
from mkt.users.models import UserProfile
from mkt.webapps.models import Webapp


# We might now have gettext available in jinja2.env.globals when running tests.
# It's only added to the globals when activating a language with tower (which
# is usually done in the middlewares). During tests, however, we might not be
# running middlewares, and thus not activating a language, and thus not
# installing gettext in the globals, and thus not have it in the context when
# rendering templates.
tower.activate('en-us')


class DynamicBoolFieldsTestMixin():

    def setUp(self):
        """
        Create an instance of the DynamicBoolFields model and call super
        on the inheriting setUp.
        (e.g. RatingDescriptors.objects.create(addon=self.app))
        """
        self.app = app_factory()
        self.model = None
        self.related_name = ''  # Related name of the bool table on the Webapp.

        self.BOOL_DICT = []
        self.flags = []  # Flag names.
        self.expected = []  # Translation names.

    def _get_related_bool_obj(self):
        return getattr(self.app, self.related_name)

    def _flag(self):
        """Flag app with a handful of flags for testing."""
        self._get_related_bool_obj().update(
            **dict(('has_%s' % f.lower(), True) for f in self.flags))

    def _check(self, obj=None):
        if not obj:
            obj = self._get_related_bool_obj()

        for bool_name in self.BOOL_DICT:
            field = 'has_%s' % bool_name.lower()
            value = bool_name in self.flags
            if isinstance(obj, dict):
                eq_(obj[field], value,
                    u'Unexpected value for field: %s' % field)
            else:
                eq_(getattr(obj, field), value,
                    u'Unexpected value for field: %s' % field)

    def to_unicode(self, items):
        """
        Force unicode evaluation of lazy items in the passed list, for set
        comparison to a list of already-evaluated unicode strings.
        """
        return [unicode(i) for i in items]

    def test_bools_set(self):
        self._flag()
        self._check()

    def test_to_dict(self):
        self._flag()
        self._check(self._get_related_bool_obj().to_dict())

    def test_default_false(self):
        obj = self.model(addon=self.app)
        eq_(getattr(obj, 'has_%s' % self.flags[0].lower()), False)


def formset(*args, **kw):
    """
    Build up a formset-happy POST.

    *args is a sequence of forms going into the formset.
    prefix and initial_count can be set in **kw.
    """
    prefix = kw.pop('prefix', 'form')
    total_count = kw.pop('total_count', len(args))
    initial_count = kw.pop('initial_count', len(args))
    data = {prefix + '-TOTAL_FORMS': total_count,
            prefix + '-INITIAL_FORMS': initial_count}
    for idx, d in enumerate(args):
        data.update(('%s-%s-%s' % (prefix, idx, k), v)
                    for k, v in d.items())
    data.update(kw)
    return data


def initial(form):
    """Gather initial data from the form into a dict."""
    data = {}
    for name, field in form.fields.items():
        if form.is_bound:
            data[name] = form[name].data
        else:
            data[name] = form.initial.get(name, field.initial)
        # The browser sends nothing for an unchecked checkbox.
        if isinstance(field, forms.BooleanField):
            val = field.to_python(data[name])
            if not val:
                del data[name]
    return data


def check_links(expected, elements, selected=None, verify=True):
    """Useful for comparing an `expected` list of links against PyQuery
    `elements`. Expected format of links is a list of tuples, like so:

    [
        ('Home', '/'),
        ('Extensions', reverse('browse.extensions')),
        ...
    ]

    If you'd like to check if a particular item in the list is selected,
    pass as `selected` the title of the link.

    Links are verified by default.

    """
    for idx, item in enumerate(expected):
        # List item could be `(text, link)`.
        if isinstance(item, tuple):
            text, link = item
        # Or list item could be `link`.
        elif isinstance(item, basestring):
            text, link = None, item

        e = elements.eq(idx)
        if text is not None:
            eq_(e.text(), text)
        if link is not None:
            # If we passed an <li>, try to find an <a>.
            if not e.filter('a'):
                e = e.find('a')
            eq_(e.attr('href'), link)
            if verify and link != '#':
                eq_(Client().head(link, follow=True).status_code, 200,
                    '%r is dead' % link)
        if text is not None and selected is not None:
            e = e.filter('.selected, .sel') or e.parents('.selected, .sel')
            eq_(bool(e.length), text == selected)


class _JSONifiedResponse(object):

    def __init__(self, response):
        self._orig_response = response

    def __getattr__(self, n):
        return getattr(self._orig_response, n)

    def __getitem__(self, n):
        return self._orig_response[n]

    def __iter__(self):
        return iter(self._orig_response)

    @property
    def json(self):
        """Will return parsed JSON on response if there is any."""
        if self.content and 'application/json' in self['Content-Type']:
            if not hasattr(self, '_content_json'):
                self._content_json = json.loads(self.content)
            return self._content_json


class JSONClient(Client):

    def _with_json(self, response):
        if hasattr(response, 'json'):
            return response
        else:
            return _JSONifiedResponse(response)

    def get(self, *args, **kw):
        return self._with_json(super(JSONClient, self).get(*args, **kw))

    def delete(self, *args, **kw):
        return self._with_json(super(JSONClient, self).delete(*args, **kw))

    def post(self, *args, **kw):
        return self._with_json(super(JSONClient, self).post(*args, **kw))

    def put(self, *args, **kw):
        return self._with_json(super(JSONClient, self).put(*args, **kw))

    def patch(self, *args, **kw):
        return self._with_json(super(JSONClient, self).patch(*args, **kw))

    def options(self, *args, **kw):
        return self._with_json(super(JSONClient, self).options(*args, **kw))


ES_patchers = [mock.patch('elasticsearch.Elasticsearch'),
               mock.patch('mkt.extensions.indexers.ExtensionIndexer',
                          spec=True),
               mock.patch('mkt.websites.indexers.WebsiteIndexer', spec=True),
               mock.patch('mkt.webapps.indexers.HomescreenIndexer', spec=True),
               mock.patch('mkt.webapps.indexers.WebappIndexer', spec=True),
               mock.patch('mkt.search.indexers.index', spec=True),
               mock.patch('mkt.search.indexers.BaseIndexer.unindex'),
               mock.patch('mkt.search.indexers.Reindexing', spec=True,
                          side_effect=lambda i: [i]),
               ]


def start_es_mock():
    for patch in ES_patchers:
        patch.start()


def stop_es_mock():
    for patch in ES_patchers:
        patch.stop()

    # Reset cached Elasticsearch objects.
    BaseIndexer._es = {}


def days_ago(days):
    return datetime.now().replace(microsecond=0) - timedelta(days=days)


class MockEsMixin(object):
    mock_es = True

    @classmethod
    def setUpClass(cls):
        if cls.mock_es:
            start_es_mock()
        try:
            super(MockEsMixin, cls).setUpClass()
        except Exception:
            # We need to unpatch here because tearDownClass will not be
            # called.
            if cls.mock_es:
                stop_es_mock()
            raise

    @classmethod
    def tearDownClass(cls):
        try:
            super(MockEsMixin, cls).tearDownClass()
        finally:
            if cls.mock_es:
                stop_es_mock()


class MockBrowserIdMixin(object):

    def mock_browser_id(self):
        cache.clear()
        real_login = self.client.login

        def fake_login(email, password=None):
            with mock_browserid(email=email):
                return real_login(email=email, assertion='test',
                                  audience='test')

        self.client.login = fake_login

    def login(self, profile):
        email = getattr(profile, 'email', profile)
        if '@' not in email:
            email += '@mozilla.com'
        assert self.client.login(email=email, password='password')


JINJA_INSTRUMENTED = False


class ClassFixtureTestCase(test.TestCase):
    """ Based on the changes to TestCase (& TransactionTestCase) in Django1.8.
    Fixtures are loaded once per class, and a class setUpTestData method is
    added to be overridden by sublasses.  `transaction.atomic()` is used to
    achieve test isolation.
    See orginal code:
    https://github.com/django/django/blob/1.8b2/django/test/testcases.py
    #L747-990.
    A noteable difference is that this class assumes the database supports
    transactions.  This class will be obsolete on upgrade to 1.8.
    """
    fixtures = None

    @classmethod
    def _databases_names(cls, include_mirrors=True):
        # If the test case has a multi_db=True flag, act on all databases,
        # including mirrors or not. Otherwise, just on the default DB.
        if getattr(cls, 'multi_db', False):
            return [alias for alias in connections
                    if (include_mirrors or
                        connections[alias].settings_dict['TEST']['MIRROR'])]
        else:
            return [DEFAULT_DB_ALIAS]

    @classmethod
    def _enter_atomics(cls):
        """Helper method to open atomic blocks for multiple databases"""
        atomics = {}
        for db_name in cls._databases_names():
            atomics[db_name] = transaction.atomic(using=db_name)
            atomics[db_name].__enter__()
        return atomics

    @classmethod
    def _rollback_atomics(cls, atomics):
        """Rollback atomic blocks opened through the previous method"""
        for db_name in reversed(cls._databases_names()):
            transaction.set_rollback(True, using=db_name)
            atomics[db_name].__exit__(None, None, None)

    @classmethod
    def setUpClass(cls):
        super(ClassFixtureTestCase, cls).setUpClass()
        cls.cls_atomics = cls._enter_atomics()

        try:
            if cls.fixtures:
                for db_name in cls._databases_names(include_mirrors=False):
                    call_command('loaddata', *cls.fixtures, **{
                        'verbosity': 0,
                        'commit': False,
                        'database': db_name,
                    })

            cls.setUpTestData()
        except Exception:
            cls._rollback_atomics(cls.cls_atomics)
            raise

    @classmethod
    def tearDownClass(cls):
        cls._rollback_atomics(cls.cls_atomics)
        for conn in connections.all():
            conn.close()
        super(ClassFixtureTestCase, cls).tearDownClass()

    @classmethod
    def setUpTestData(cls):
        """Load initial data for the TestCase"""
        pass

    def _should_reload_connections(self):
        return False

    def _fixture_setup(self):
        assert not self.reset_sequences, (
            'reset_sequences cannot be used on TestCase instances')
        self.atomics = self._enter_atomics()

    def _fixture_teardown(self):
        self._rollback_atomics(self.atomics)

    def _post_teardown(self):
        """Patch _post_teardown so connections don't get closed.
        In django 1.6's _post_teardown connections are closed and we don't want
        that to happen after each test anymore.  This method isn't copied from
        Django 1.8 code.
        https://github.com/django/django/blob/1.6.10/django/test/testcases.py
        #L788
        """
        if not self._should_reload_connections():
            real_connections_all = connections.all
            connections.all = lambda: []
        super(ClassFixtureTestCase, self)._post_teardown()
        if not self._should_reload_connections():
            connections.all = real_connections_all


class TestCase(MockEsMixin, MockBrowserIdMixin, ClassFixtureTestCase):
    """Base class for all mkt tests."""
    client_class = Client

    def shortDescription(self):
        # Stop nose using the test docstring and instead the test method name.
        pass

    def _pre_setup(self):
        super(TestCase, self)._pre_setup()

        # XXX See if we can remove this when we switch to Django 1.8.
        # Some crud from the migration system gets stuck here and we have to
        # kick it loose manually.
        from mkt.webapps.models import AddonUser
        UserProfile.addonuser_set.related.model = AddonUser

        # Clean the slate.
        cache.clear()
        post_request_task._discard_tasks()

        trans_real.deactivate()
        trans_real._translations = {}  # Django fails to clear this cache.
        trans_real.activate(settings.LANGUAGE_CODE)

        self.mock_browser_id()

        global JINJA_INSTRUMENTED
        if not JINJA_INSTRUMENTED:
            import jinja2
            old_render = jinja2.Template.render

            def instrumented_render(self, *args, **kwargs):
                context = dict(*args, **kwargs)
                test.signals.template_rendered.send(sender=self, template=self,
                                                    context=context)
                return old_render(self, *args, **kwargs)

            jinja2.Template.render = instrumented_render
            JINJA_INSTRUMENTED = True

    def _post_teardown(self):
        mkt.set_user(None)
        clean_translations(None)  # Make sure queued translations are removed.
        super(TestCase, self)._post_teardown()

    @contextmanager
    def activate(self, locale=None):
        """Active a locale."""
        old_locale = translation.get_language()
        if locale:
            translation.activate(locale)
        yield
        translation.activate(old_locale)

    def assertNoFormErrors(self, response):
        """Asserts that no form in the context has errors.

        If you add this check before checking the status code of the response
        you'll see a more informative error.
        """
        # TODO(Kumar) liberate upstream to Django?
        if response.context is None:
            # It's probably a redirect.
            return
        if len(response.templates) == 1:
            tpl = [response.context]
        else:
            # There are multiple contexts so iter all of them.
            tpl = response.context
        for ctx in tpl:
            for k, v in ctx.iteritems():
                if isinstance(v, (forms.BaseForm, forms.formsets.BaseFormSet)):
                    if isinstance(v, forms.formsets.BaseFormSet):
                        # Concatenate errors from each form in the formset.
                        msg = '\n'.join(f.errors.as_text() for f in v.forms)
                    else:
                        # Otherwise, just return the errors for this form.
                        msg = v.errors.as_text()
                    msg = msg.strip()
                    if msg != '':
                        self.fail('form %r had the following error(s):\n%s'
                                  % (k, msg))
                    if hasattr(v, 'non_field_errors'):
                        self.assertEquals(v.non_field_errors(), [])
                    if hasattr(v, 'non_form_errors'):
                        self.assertEquals(v.non_form_errors(), [])

    def assertLoginRedirects(self, response, to, status_code=302):
        # Not using urlparams, because that escapes the variables, which
        # is good, but bad for assertRedirects which will fail.
        self.assert3xx(response,
                       '%s?to=%s' % (reverse('users.login'), to), status_code)

    def assert3xx(self, response, expected_url, status_code=302,
                  target_status_code=200):
        """Asserts redirect and final redirect matches expected URL.

        Similar to Django's `assertRedirects` but skips the final GET
        verification for speed.

        """
        if hasattr(response, 'redirect_chain'):
            # The request was a followed redirect
            self.assertTrue(len(response.redirect_chain) > 0,
                            "Response didn't redirect as expected: Response"
                            " code was %d (expected %d)" %
                            (response.status_code, status_code))

            url, status_code = response.redirect_chain[-1]

            self.assertEqual(response.status_code, target_status_code,
                             "Response didn't redirect as expected: Final"
                             " Response code was %d (expected %d)" %
                             (response.status_code, target_status_code))

        else:
            # Not a followed redirect
            self.assertEqual(response.status_code, status_code,
                             "Response didn't redirect as expected: Response"
                             " code was %d (expected %d)" %
                             (response.status_code, status_code))
            url = response['Location']

        scheme, netloc, path, query, fragment = urlsplit(url)
        e_scheme, e_netloc, e_path, e_query, e_fragment = urlsplit(
            expected_url)
        if (scheme and not e_scheme) and (netloc and not e_netloc):
            expected_url = urlunsplit(('http', 'testserver', e_path, e_query,
                                       e_fragment))

        self.assertEqual(
            url, expected_url,
            "Response redirected to '%s', expected '%s'" % (url, expected_url))

    def assertLoginRequired(self, response, status_code=302):
        """
        A simpler version of assertLoginRedirects that just checks that we
        get the matched status code and bounced to the correct login page.
        """
        assert response.status_code == status_code, (
            'Response returned: %s, expected: %s'
            % (response.status_code, status_code))

        path = urlsplit(response['Location'])[2]
        assert path == reverse('users.login'), (
            'Redirected to: %s, expected: %s'
            % (path, reverse('users.login')))

    def assertSetEqual(self, a, b, message=None):
        """
        This is a thing in unittest in 2.7,
        but until then this is the thing.

        Oh, and Django's `assertSetEqual` is lame and requires actual sets:
        http://bit.ly/RO9sTr
        """
        eq_(set(a), set(b), message)
        eq_(len(a), len(b), message)

    def assertCloseToNow(self, dt, now=None):
        """
        Make sure the datetime is within a minute from `now`.
        """

        # Try parsing the string if it's not a datetime.
        if isinstance(dt, basestring):
            try:
                dt = dateutil_parser(dt)
            except ValueError, e:
                raise AssertionError(
                    'Expected valid date; got %s\n%s' % (dt, e))

        if not dt:
            raise AssertionError('Expected datetime; got %s' % dt)

        dt_later_ts = time.mktime((dt + timedelta(minutes=1)).timetuple())
        dt_earlier_ts = time.mktime((dt - timedelta(minutes=1)).timetuple())
        if not now:
            now = datetime.now()
        now_ts = time.mktime(now.timetuple())

        assert dt_earlier_ts < now_ts < dt_later_ts, (
            'Expected datetime to be within a minute of %s. Got %r.' % (now,
                                                                        dt))

    def assertCORS(self, res, *verbs, **kw):
        """
        Determines if a response has suitable CORS headers. Appends 'OPTIONS'
        on to the list of verbs.
        """
        headers = kw.pop('headers', None)
        if not headers:
            headers = ['X-HTTP-Method-Override', 'Content-Type']
        eq_(res['Access-Control-Allow-Origin'], '*')
        assert 'API-Status' in res['Access-Control-Expose-Headers']
        assert 'API-Version' in res['Access-Control-Expose-Headers']

        verbs = map(str.upper, verbs) + ['OPTIONS']
        actual = res['Access-Control-Allow-Methods'].split(', ')
        self.assertSetEqual(verbs, actual)
        eq_(res['Access-Control-Allow-Headers'], ', '.join(headers))

    def assertApiUrlEqual(self, *args, **kwargs):
        """
        Allows equality comparison of two or more URLs agnostic of API version.
        This is done by prepending '/api/vx' (where x is equal to the `version`
        keyword argument or API_CURRENT_VERSION) to each string passed as a
        positional argument if that URL doesn't already start with that string.
        Also accepts 'netloc' and 'scheme' optional keyword arguments to
        compare absolute URLs.

        Example usage:

        url = '/api/v1/apps/app/bastacorp/'
        self.assertApiUrlEqual(url, '/apps/app/bastacorp1/')

        # settings.API_CURRENT_VERSION = 2
        url = '/api/v1/apps/app/bastacorp/'
        self.assertApiUrlEqual(url, '/apps/app/bastacorp/', version=1)
        """
        # Constants for the positions of the URL components in the tuple
        # returned by urlsplit. Only here for readability purposes.
        SCHEME = 0
        NETLOC = 1
        PATH = 2

        version = kwargs.get('version', settings.API_CURRENT_VERSION)
        scheme = kwargs.get('scheme', None)
        netloc = kwargs.get('netloc', None)
        urls = list(args)
        prefix = '/api/v%d' % version
        for idx, url in enumerate(urls):
            urls[idx] = list(urlsplit(url))
            if not urls[idx][PATH].startswith(prefix):
                urls[idx][PATH] = prefix + urls[idx][PATH]
            if scheme and not urls[idx][SCHEME]:
                urls[idx][SCHEME] = scheme
            if netloc and not urls[idx][NETLOC]:
                urls[idx][NETLOC] = netloc
            urls[idx] = SplitResult(*urls[idx])
        eq_(*urls)

    def make_price(self, price='1.00'):
        price_obj, created = Price.objects.get_or_create(price=price,
                                                         name='1')

        for region in [regions.USA.id, regions.RESTOFWORLD.id]:
            PriceCurrency.objects.create(region=region, currency='USD',
                                         price=price, tier=price_obj,
                                         provider=PROVIDER_REFERENCE)
        # Call Price transformer in order to repopulate _currencies cache.
        Price.transformer([])
        return price_obj

    def make_premium(self, addon, price='1.00'):
        price_obj = self.make_price(price=Decimal(price))
        addon.update(premium_type=mkt.ADDON_PREMIUM)
        addon._premium = AddonPremium.objects.create(addon=addon,
                                                     price=price_obj)
        if hasattr(Price, '_currencies'):
            del Price._currencies
        return addon._premium

    def create_sample(self, name=None, **kw):
        if name is not None:
            kw['name'] = name
        kw.setdefault('percent', 100)
        sample, created = Sample.objects.get_or_create(name=name, defaults=kw)
        if not created:
            sample.__dict__.update(kw)
            sample.save()
        return sample

    def create_switch(self, name=None, **kw):
        kw.setdefault('active', True)
        if name is not None:
            kw['name'] = name
        switch, created = Switch.objects.get_or_create(name=name, defaults=kw)
        if not created:
            switch.__dict__.update(kw)
            switch.save()
        return switch

    def create_flag(self, name=None, **kw):
        if name is not None:
            kw['name'] = name
        kw.setdefault('everyone', True)
        flag, created = Flag.objects.get_or_create(name=name, defaults=kw)
        if not created:
            flag.__dict__.update(kw)
            flag.save()
        return flag

    @staticmethod
    def grant_permission(user_obj, rules, name='Test Group'):
        """Creates group with rule, and adds user to group."""
        group = Group.objects.create(name=name, rules=rules)
        GroupUser.objects.create(group=group, user=user_obj)
        return group

    def remove_permission(self, user_obj, rules):
        """Remove a permission from a user."""
        group = Group.objects.get(rules=rules)
        GroupUser.objects.filter(user=user_obj, group=group).delete()

    def days_ago(self, days):
        return days_ago(days)

    def trans_eq(self, trans, locale, localized_string):
        eq_(Translation.objects.get(id=trans.id,
                                    locale=locale).localized_string,
            localized_string)

    def extract_script_template(self, html, template_selector):
        """Extracts the inner JavaScript text/template from a html page.

        Example::

            >>> template = extract_script_template(res.content, '#template-id')
            >>> template('#my-jquery-selector')

        Returns a PyQuery object that you can refine using jQuery selectors.
        """
        return pq(pq(html)(template_selector).html())


class MktPaths(object):
    """Mixin for getting common Marketplace Paths."""

    def manifest_path(self, name):
        return os.path.join(settings.ROOT,
                            'mkt/submit/tests/webapps/%s' % name)

    def manifest_copy_over(self, dest, name):
        copy_stored_file(
            self.manifest_path(name), dest,
            src_storage=local_storage, dst_storage=private_storage)

    @staticmethod
    def sample_key():
        return os.path.join(settings.ROOT,
                            'mkt/webapps/tests/sample.key')

    def sample_packaged_key(self):
        return os.path.join(settings.ROOT,
                            'mkt/webapps/tests/sample.packaged.pem')

    def mozball_image(self):
        return os.path.join(settings.ROOT,
                            'mkt/developers/tests/addons/mozball-128.png')

    def packaged_app_path(self, name):
        return os.path.join(
            settings.ROOT, 'mkt/submit/tests/packaged/%s' % name)

    def packaged_copy_over(self, dest, name):
        copy_stored_file(
            self.packaged_app_path(name), dest,
            src_storage=local_storage, dst_storage=private_storage)


def assert_no_validation_errors(validation):
    """Assert that the validation (JSON) does not contain a traceback.

    Note that this does not test whether the addon passed
    validation or not.
    """
    if hasattr(validation, 'task_error'):
        # FileUpload object:
        error = validation.task_error
    else:
        # Upload detail - JSON output
        error = validation['error']
    if error:
        print '-' * 70
        print error
        print '-' * 70
        raise AssertionError("Unexpected task error: %s" %
                             error.rstrip().split("\n")[-1])


def _get_created(created):
    """
    Returns a datetime.

    If `created` is "now", it returns `datetime.datetime.now()`. If `created`
    is set use that. Otherwise generate a random datetime in the year 2011.
    """
    if created == 'now':
        return datetime.now()
    elif created:
        return created
    else:
        return datetime(2011,
                        random.randint(1, 12),  # Month
                        random.randint(1, 28),  # Day
                        random.randint(0, 23),  # Hour
                        random.randint(0, 59),  # Minute
                        random.randint(0, 59))  # Seconds


def req_factory_factory(url='', user=None, post=False, data=None, **kwargs):
    """Creates a request factory, logged in with the user."""
    req = RequestFactory()
    if post:
        req = req.post(url, data or {})
    else:
        req = req.get(url, data or {})
    if user:
        req.user = UserProfile.objects.get(id=user.id)
        req.groups = user.groups.all()
    else:
        req.user = AnonymousUser()
    req.check_ownership = partial(check_ownership, req)
    req.REGION = kwargs.pop('region', mkt.regions.REGIONS_CHOICES[0][1])
    req.API_VERSION = 2

    for key in kwargs:
        setattr(req, key, kwargs[key])
    return req


user_factory_counter = 0


def user_factory(**kw):
    """
    If not provided, email will be 'factoryuser<number>@mozilla.com'.
    If email has no '@' it will be corrected to 'email@mozilla.com'
    """
    global user_factory_counter
    email = kw.pop('email', 'factoryuser%d' % user_factory_counter)
    if '@' not in email:
        email = '%s@mozilla.com' % email

    user = UserProfile.objects.create(email=email, **kw)

    if 'email' not in kw:
        user_factory_counter = user.id + 1
    return user


class ESTestCase(TestCase):
    """Base class for tests that require elasticsearch."""
    # ES is slow to set up so this uses class setup/teardown. That happens
    # outside Django transactions so be careful to clean up afterwards.
    test_es = True
    mock_es = False
    exempt_from_fixture_bundling = True  # ES doesn't support bundling (yet?)

    @classmethod
    def setUpClass(cls):
        if not settings.RUN_ES_TESTS:
            raise SkipTest('ES disabled')
        cls.es = elasticsearch.Elasticsearch(hosts=settings.ES_HOSTS)

        # The ES setting are set before we call super()
        # because we may have indexation occuring in upper classes.
        for key, index in settings.ES_INDEXES.items():
            if not index.startswith('test_'):
                settings.ES_INDEXES[key] = 'test_%s' % index

        cls._SEARCH_ANALYZER_MAP = mkt.SEARCH_ANALYZER_MAP
        mkt.SEARCH_ANALYZER_MAP = {
            'english': ['en-us'],
            'spanish': ['es'],
        }

        super(ESTestCase, cls).setUpClass()

    @classmethod
    def setUpTestData(cls):
        try:
            cls.es.cluster.health()
        except Exception, e:
            e.args = tuple([u'%s (it looks like ES is not running, '
                            'try starting it or set RUN_ES_TESTS=False)'
                            % e.args[0]] + list(e.args[1:]))
            raise

        for index in set(settings.ES_INDEXES.values()):
            # Get the index that's pointed to by the alias.
            try:
                indices = cls.es.indices.get_aliases(index=index)
                assert indices[index]['aliases']
            except (KeyError, AssertionError):
                # There's no alias, just use the index.
                print 'Found no alias for %s.' % index
            except elasticsearch.NotFoundError:
                pass

            # Remove any alias as well.
            try:
                cls.es.indices.delete(index=index)
            except elasticsearch.NotFoundError as e:
                print 'Could not delete index %r: %s' % (index, e)

        for indexer in reindex.INDEXERS:
            indexer.setup_mapping()

    @classmethod
    def tearDownClass(cls):
        mkt.SEARCH_ANALYZER_MAP = cls._SEARCH_ANALYZER_MAP
        super(ESTestCase, cls).tearDownClass()

    def tearDown(self):
        post_request_task._send_tasks()
        super(ESTestCase, self).tearDown()

    @classmethod
    def refresh(cls, doctypes=None):
        """
        Force an immediate refresh for the index(es) holding the given
        doctype(s) in ES. Both a string corresponding to a single doctypes or a
        list of multiple doctypes are accepted.

        If there are tasks in the post_request_task queue, they are processed
        first.
        """
        post_request_task._send_tasks()

        if doctypes:
            if not isinstance(doctypes, (list, tuple)):
                doctypes = [doctypes]
            indexes = [settings.ES_INDEXES[doctype] for doctype in doctypes]
            try:
                cls.es.indices.refresh(index=indexes)
            except elasticsearch.NotFoundError as e:
                print "Could not refresh indexes '%s': %s" % (indexes, e)

    @classmethod
    def reindex(cls, model):
        """
        Convenience method that re-save all instances of the specified model
        and then refreshes the corresponding ES index.
        """
        # Emit post-save signal so all of the objects get reindexed.
        [o.save() for o in model.objects.all()]
        cls.refresh(doctypes=model.get_indexer().get_mapping_type_name())


class WebappTestCase(TestCase):
    fixtures = fixture('webapp_337141')

    def setUp(self):
        self.app = self.get_app()

    def get_app(self):
        return Webapp.objects.get(id=337141)

    def make_game(self, app=None, rated=False):
        app = make_game(self.app or app, rated)


def make_game(app, rated):
    app.update(categories=['games'])
    if rated:
        make_rated(app)
    app = app.reload()
    return app


def make_rated(app):
    app.set_content_ratings(
        dict((body, body.ratings[0]) for body in
             mkt.ratingsbodies.ALL_RATINGS_BODIES))
    app.set_iarc_info(123, 'abc')
    app.set_descriptors([])
    app.set_interactives([])
