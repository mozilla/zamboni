import urllib
import urlparse
from datetime import datetime
from functools import partial

from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.core.urlresolvers import reverse
from django.test.client import RequestFactory
from django.utils.encoding import iri_to_uri, smart_str

from django_browserid.tests import mock_browserid
from jingo.helpers import urlparams
from nose.tools import eq_, ok_
from oauthlib import oauth1
from pyquery import PyQuery as pq
from rest_framework.request import Request

from mkt.api import authentication
from mkt.api.middleware import RestOAuthMiddleware
from mkt.api.models import Access, ACCESS_TOKEN, REQUEST_TOKEN, Token
from mkt.api.tests import BaseAPI
from mkt.site.fixtures import fixture
from mkt.site.helpers import absolutify
from mkt.site.tests import JSONClient, TestCase
from mkt.users.models import UserProfile


def get_absolute_url(url, api_name='apps', absolute=True):
    # Gets an absolute url, except where you don't want that.
    url[1]['api_name'] = api_name
    res = reverse(url[0], kwargs=url[1])
    if absolute:
        res = urlparse.urljoin(settings.SITE_URL, res)
    if len(url) > 2:
        res = urlparams(res, **url[2])
    return res


class OAuthClient(JSONClient):
    """
    OAuthClient can do all the requests the Django test client,
    but even more. And it can magically sign requests.
    TODO (andym): this could be cleaned up and split out, it's useful.
    """
    signature_method = oauth1.SIGNATURE_HMAC

    def __init__(self, access, api_name='apps'):
        super(OAuthClient, self).__init__(self)
        self.access = access
        self.get_absolute_url = partial(get_absolute_url,
                                        api_name=api_name)

    def login(self, email, password):
        with mock_browserid(email=email):
            return super(OAuthClient, self).login(email=email,
                                                  password=password)

    def sign(self, method, url):
        if not self.access:
            return url, {}, ''
        cl = oauth1.Client(self.access.key,
                           client_secret=self.access.secret,
                           signature_method=self.signature_method)
        url, headers, body = cl.sign(url, http_method=method)
        # We give cl.sign a str, but it gives us back a unicode, which cause
        # double-encoding problems later down the road with the django test
        # client. To fix that, ensure it's still an str after signing.
        return smart_str(url), headers, body

    def kw(self, headers, **kw):
        kw.setdefault('HTTP_HOST', 'testserver')
        kw.setdefault('HTTP_AUTHORIZATION', headers.get('Authorization', ''))
        return kw

    def get(self, url, data={}, **kw):
        if isinstance(url, tuple) and len(url) > 2 and data:
            raise RuntimeError('Query string specified both in urlspec and as '
                               'data arg. Pick one or the other.')

        urlstring = self.get_absolute_url(url)
        if data:
            urlstring = '?'.join([urlstring,
                                  urllib.urlencode(data, doseq=True)])
        url, headers, _ = self.sign('GET', urlstring)
        return super(OAuthClient, self).get(url, **self.kw(headers, **kw))

    def delete(self, url, data={}, **kw):
        if isinstance(url, tuple) and len(url) > 2 and data:
            raise RuntimeError('Query string specified both in urlspec and as '
                               'data arg. Pick one or the other.')
        urlstring = self.get_absolute_url(url)
        if data:
            urlstring = '?'.join([urlstring,
                                  urllib.urlencode(data, doseq=True)])
        url, headers, _ = self.sign('DELETE', urlstring)
        return super(OAuthClient, self).delete(url, **self.kw(headers, **kw))

    def post(self, url, data='', content_type='application/json', **kw):
        url, headers, _ = self.sign('POST', self.get_absolute_url(url))
        return super(OAuthClient, self).post(
            url, data=data, content_type=content_type,
            **self.kw(headers, **kw))

    def put(self, url, data='', content_type='application/json', **kw):
        url, headers, body = self.sign('PUT', self.get_absolute_url(url))
        return super(OAuthClient, self).put(
            url, data=data, content_type=content_type,
            **self.kw(headers, **kw))

    def patch(self, url, data='', content_type='application/json', **kw):
        url, headers, body = self.sign('PATCH', self.get_absolute_url(url))
        return super(OAuthClient, self).patch(
            url, data=data, content_type=content_type,
            **self.kw(headers, **kw))

    def options(self, url):
        url, headers, body = self.sign('OPTIONS', self.get_absolute_url(url))
        return super(OAuthClient, self).options(url, **self.kw(headers))


class BaseOAuth(BaseAPI):
    fixtures = fixture('user_2519', 'group_admin', 'group_editor',
                       'group_support')

    def setUp(self, api_name='apps'):
        self.profile = self.user = UserProfile.objects.get(pk=2519)
        self.profile.update(read_dev_agreement=datetime.now())
        self.access = Access.objects.create(key='oauthClientKeyForTests',
                                            secret='super secret',
                                            user=self.user)
        self.client = OAuthClient(self.access, api_name=api_name)
        self.anon = OAuthClient(None, api_name=api_name)


class RestOAuthClient(OAuthClient):

    def __init__(self, access):
        super(OAuthClient, self).__init__(self)
        self.access = access

    def get_absolute_url(self, url):
        unquoted_url = urlparse.unquote(url)
        return absolutify(iri_to_uri(unquoted_url))


class RestOAuth(BaseOAuth):
    fixtures = fixture('user_2519')

    def setUp(self):
        self.profile = self.user = UserProfile.objects.get(pk=2519)
        self.login_user()

    def login_user(self):
        self.profile.update(read_dev_agreement=datetime.now())
        self.access = Access.objects.create(key='oauthClientKeyForTests',
                                            secret='super secret',
                                            user=self.user)
        self.client = RestOAuthClient(self.access)
        self.anon = RestOAuthClient(None)


class Test3LeggedOAuthFlow(TestCase):
    fixtures = fixture('user_2519', 'user_999')

    def setUp(self, api_name='apps'):
        self.profile = self.user = UserProfile.objects.get(pk=2519)
        self.user2 = UserProfile.objects.get(pk=999)
        self.profile.update(read_dev_agreement=datetime.now())
        self.app_name = 'Mkt Test App'
        self.redirect_uri = 'https://example.com/redirect_target'
        self.access = Access.objects.create(key='oauthClientKeyForTests',
                                            secret='super secret',
                                            user=self.user,
                                            redirect_uri=self.redirect_uri,
                                            app_name=self.app_name)

    def _oauth_request_info(self, url, **kw):
        oa = oauth1.Client(signature_method=oauth1.SIGNATURE_HMAC, **kw)
        url, headers, _ = oa.sign(url, http_method='GET')
        return url, headers['Authorization']

    def test_use_access_token(self):
        url = absolutify(reverse('app-list'))
        t = Token.generate_new(ACCESS_TOKEN, creds=self.access,
                               user=self.user2)
        url, auth_header = self._oauth_request_info(
            url, client_key=self.access.key, client_secret=self.access.secret,
            resource_owner_key=t.key, resource_owner_secret=t.secret)
        auth = authentication.RestOAuthAuthentication()
        req = RequestFactory().get(
            url, HTTP_HOST='testserver',
            HTTP_AUTHORIZATION=auth_header)
        req.API = True
        req.user = AnonymousUser()
        RestOAuthMiddleware().process_request(req)
        ok_(auth.authenticate(Request(req)))
        ok_(req.user.is_authenticated())
        eq_(req.user, self.user2)

    def test_bad_access_token(self):
        url = absolutify(reverse('app-list'))
        Token.generate_new(ACCESS_TOKEN, creds=self.access, user=self.user2)
        url, auth_header = self._oauth_request_info(
            url, client_key=self.access.key,
            client_secret=self.access.secret, resource_owner_key='test_ro_key',
            resource_owner_secret='test_ro_secret')
        auth = authentication.RestOAuthAuthentication()
        req = RequestFactory().get(
            url, HTTP_HOST='testserver',
            HTTP_AUTHORIZATION=auth_header)
        req.API = True
        req.user = AnonymousUser()
        RestOAuthMiddleware().process_request(req)
        ok_(not auth.authenticate(Request(req)))
        ok_(not req.user.is_authenticated())

    def test_get_authorize_page(self):
        t = Token.generate_new(REQUEST_TOKEN, self.access)
        self.login('regular@mozilla.com')
        res = self.client.get('/oauth/authorize/', data={'oauth_token': t.key})
        eq_(res.status_code, 200)
        page = pq(res.content)
        eq_(page('input[name=oauth_token]').attr('value'), t.key)

    def test_get_authorize_page_bad_token(self):
        self.login('regular@mozilla.com')
        res = self.client.get('/oauth/authorize/',
                              data={'oauth_token': 'bad_token_value'})
        eq_(res.status_code, 401)

    def test_post_authorize_page(self):
        t = Token.generate_new(REQUEST_TOKEN, self.access)
        full_redirect = (
            self.redirect_uri + '?oauth_token=%s&oauth_verifier=%s'
            % (t.key, t.verifier))
        self.login('regular@mozilla.com')
        url = reverse('mkt.developers.oauth_authorize')
        res = self.client.post(url, data={'oauth_token': t.key, 'grant': ''})
        eq_(res.status_code, 302)
        eq_(res.get('location'), full_redirect)
        eq_(Token.objects.get(pk=t.pk).user.pk, 999)

    def test_deny_authorize_page(self):
        t = Token.generate_new(REQUEST_TOKEN, self.access)
        self.login('regular@mozilla.com')
        url = reverse('mkt.developers.oauth_authorize')
        res = self.client.post(url, data={'oauth_token': t.key, 'deny': ''})
        eq_(res.status_code, 200)
        eq_(Token.objects.filter(pk=t.pk).count(), 0)

    def test_fail_authorize_page(self):
        self.login('regular@mozilla.com')
        url = reverse('mkt.developers.oauth_authorize')
        res = self.client.post(url, data={'oauth_token': "fake", 'grant': ''})
        eq_(res.status_code, 401)

    def test_access_request(self):
        t = Token.generate_new(REQUEST_TOKEN, self.access)
        url = urlparse.urljoin(settings.SITE_URL,
                               reverse('mkt.developers.oauth_access_request'))
        url, auth_header = self._oauth_request_info(
            url, client_key=self.access.key, client_secret=self.access.secret,
            resource_owner_key=t.key, resource_owner_secret=t.secret,
            verifier=t.verifier, callback_uri=self.access.redirect_uri)
        res = self.client.get(url, HTTP_HOST='testserver',
                              HTTP_AUTHORIZATION=auth_header)
        eq_(res.status_code, 200)
        data = dict(urlparse.parse_qsl(res.content))
        assert Token.objects.filter(
            token_type=ACCESS_TOKEN,
            key=data['oauth_token'],
            secret=data['oauth_token_secret'],
            user=t.user,
            creds=self.access).exists()
        assert not Token.objects.filter(
            token_type=REQUEST_TOKEN,
            key=t.key).exists()

    def test_bad_access_request(self):
        t = Token.generate_new(REQUEST_TOKEN, self.access)
        url = urlparse.urljoin(settings.SITE_URL,
                               reverse('mkt.developers.oauth_access_request'))
        url, auth_header = self._oauth_request_info(
            url, client_key=t.key, client_secret=t.secret,
            resource_owner_key='test_ro_key',
            resource_owner_secret='test_ro_secret',
            verifier='test_verifier', callback_uri=self.access.redirect_uri)
        res = self.client.get(url, HTTP_HOST='testserver',
                              HTTP_AUTHORIZATION=auth_header)
        eq_(res.status_code, 401)
        assert not Token.objects.filter(token_type=ACCESS_TOKEN).exists()

    def test_token_request(self):
        url = urlparse.urljoin(settings.SITE_URL,
                               reverse('mkt.developers.oauth_token_request'))
        url, auth_header = self._oauth_request_info(
            url, client_key=self.access.key, client_secret=self.access.secret,
            callback_uri=self.access.redirect_uri)
        res = self.client.get(url, HTTP_HOST='testserver',
                              HTTP_AUTHORIZATION=auth_header)
        eq_(res.status_code, 200)
        data = dict(urlparse.parse_qsl(res.content))
        assert Token.objects.filter(
            token_type=REQUEST_TOKEN,
            key=data['oauth_token'],
            secret=data['oauth_token_secret'],
            creds=self.access).exists()

    def test_bad_token_request(self):
        url = urlparse.urljoin(settings.SITE_URL,
                               reverse('mkt.developers.oauth_token_request'))
        url, auth_header = self._oauth_request_info(
            url, client_key=self.access.key, client_secret='test_cli_secret',
            callback_uri=self.access.redirect_uri)

        res = self.client.get(url, HTTP_HOST='testserver',
                              HTTP_AUTHORIZATION=auth_header)
        eq_(res.status_code, 401)
        assert not Token.objects.filter(token_type=REQUEST_TOKEN).exists()


class Test2LeggedOAuthFlow(TestCase):
    fixtures = fixture('user_2519', 'user_999')

    def setUp(self, api_name='apps'):
        self.profile = self.user = UserProfile.objects.get(pk=2519)
        self.profile.update(read_dev_agreement=datetime.now())
        self.app_name = 'Mkt Test App'
        self.redirect_uri = 'https://example.com/redirect_target'
        self.access = Access.objects.create(key='oauthClientKeyForTests',
                                            secret='test_2leg_secret',
                                            user=self.user,
                                            redirect_uri=self.redirect_uri,
                                            app_name=self.app_name)

    def _oauth_request_info(self, url, **kw):
        oa = oauth1.Client(signature_method=oauth1.SIGNATURE_HMAC, **kw)
        url, headers, _ = oa.sign(url, http_method='GET')
        return url, headers['Authorization']

    def test_success(self):
        url = absolutify(reverse('app-list'))
        url, auth_header = self._oauth_request_info(
            url, client_key=self.access.key,
            client_secret=self.access.secret)
        auth = authentication.RestOAuthAuthentication()
        req = RequestFactory().get(
            url, HTTP_HOST='testserver',
            HTTP_AUTHORIZATION=auth_header)
        req.API = True
        req.user = AnonymousUser()
        RestOAuthMiddleware().process_request(req)
        ok_(auth.authenticate(Request(req)))
        ok_(req.user.is_authenticated())
        eq_(req.user, self.user)

    def test_fail(self):
        url = absolutify(reverse('app-list'))
        url, auth_header = self._oauth_request_info(
            url, client_key=self.access.key,
            client_secret="none")
        auth = authentication.RestOAuthAuthentication()
        req = RequestFactory().get(
            url, HTTP_HOST='testserver',
            HTTP_AUTHORIZATION=auth_header)
        req.API = True
        req.user = AnonymousUser()
        RestOAuthMiddleware().process_request(req)
        ok_(not auth.authenticate(Request(req)))
        ok_(not req.user.is_authenticated())
