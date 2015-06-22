import random

import mock
import requests
import responses
from nose.tools import eq_, ok_

from mkt.site.tests import TestCase
from mkt.websites.helpers import WebsiteMetadata


class TestWebsiteMetadataMixin(object):
    url = 'https://mobile.piedpiper.com'

    @responses.activate
    def get_obj(self, response_body):
        responses.add(responses.GET, self.url, body=response_body, status=200)
        return WebsiteMetadata(self.url)

    def get_obj_with(self, response_body):
        return self.get_obj('<html>%s</html>' % response_body)

    def get_empty_obj(self):
        return self.get_obj_with('')


class TestWebsiteMetadata(TestWebsiteMetadataMixin, TestCase):
    def test_check_ms_icon_size_nomatch(self):
        eq_(self.get_empty_obj()._check_ms_icon_size(310), None)

    def test_check_ms_icon_size_match(self):
        VALUE = 'http://i.imgur.com/Ng0I5UA.gif'
        test = ('<meta name="msapplication-square310x310logo" '
                'content="%s">') % VALUE
        eq_(self.get_obj_with(test)._check_ms_icon_size(310), VALUE)

    def test_check_apple_icon_size_nomatch(self):
        eq_(self.get_empty_obj()._check_apple_icon_size(152), None)

    def test_check_apple_icon_size_match(self):
        VALUE = 'http://i.imgur.com/Ng0I5UA.gif'
        test = '<link rel="apple-touch-icon-precomposed" href="%s">' % VALUE
        eq_(self.get_obj_with(test)._check_apple_icon_size(None), VALUE)

    def test_check_apple_icon_size_with_sizes_match(self):
        VALUE = 'http://i.imgur.com/Ng0I5UA.gif'
        test = ('<link rel="apple-touch-icon-precomposed" sizes="152x152" '
                'href="%s">') % VALUE
        eq_(self.get_obj_with(test)._check_apple_icon_size(152), VALUE)

    def test_check_opengraph_nomatch(self):
        eq_(self.get_empty_obj()._check_opengraph('url'), None)

    def test_check_opengraph_match(self):
        VALUE = 'http://www.piedpiper.com'
        test = '<meta property="og:url" content="%s">' % VALUE
        eq_(self.get_obj_with(test)._check_opengraph('url'), VALUE)

    def test_check_link_nomatch(self):
        eq_(self.get_empty_obj()._check_link('canonical'), None)

    def test_check_link_match(self):
        VALUE = 'http://www.piedpiper.com'
        test = '<link rel="canonical" href="%s">' % VALUE
        eq_(self.get_obj_with(test)._check_link('canonical'), VALUE)

    def test_check_meta_nomatch(self):
        eq_(self.get_empty_obj()._check_meta('keywords'), None)

    def test_check_meta_match(self):
        VALUE = 'Compression,Middle Out,Startup,Gilfoyle'
        test = '<meta name="keywords" content="%s">' % VALUE
        eq_(self.get_obj_with(test)._check_meta('keywords'), VALUE)

    def test_check_text_nomatch(self):
        eq_(self.get_empty_obj()._check_text('title'), None)

    def test_check_text_match(self):
        VALUE = 'Pied Piper'
        test = '<title>%s</title>' % VALUE
        eq_(self.get_obj_with(test)._check_text('title'), VALUE)

    @mock.patch('mkt.websites.helpers.WebsiteMetadata._get_metadata')
    def test_init_gets_metadata(self, mock_get_metadata):
        self.get_empty_obj()
        eq_(mock_get_metadata.call_count, 1)

    @mock.patch('mkt.websites.helpers.WebsiteMetadata._get_metadata')
    def test_update(self, mock_get_metadata):
        obj = self.get_empty_obj()
        eq_(mock_get_metadata.call_count, 1)
        obj.update()
        eq_(mock_get_metadata.call_count, 2)

    @responses.activate
    def test_get_document_400(self):
        STATUS = 400
        responses.add(responses.GET, self.url, body='', status=STATUS)
        with self.assertRaises(requests.exceptions.HTTPError) as e:
            WebsiteMetadata(self.url)
        eq_(e.exception.response.status_code, STATUS)

    def test_get_document_markup(self):
        CONTENT = '<p>Hi!</p>'
        obj = self.get_obj(CONTENT)
        eq_(obj._markup, CONTENT)

    def test_get_document_document(self):
        CONTENT = 'Middle-Out Compression Algorithm'
        obj = self.get_obj_with(CONTENT)
        eq_(CONTENT, obj._document.text())

    def test_set_valid_key(self):
        KEY = 'Gilfoyle'
        ok_(KEY not in WebsiteMetadata._valid_keys)
        obj = self.get_empty_obj()
        with self.assertRaises(KeyError):
            obj[KEY] = 'First name, or last name?'

    def test_get_valid_key(self):
        KEY = 'Dinesh'
        ok_(KEY not in WebsiteMetadata._valid_keys)
        obj = self.get_empty_obj()
        with self.assertRaises(KeyError):
            obj[KEY]


class FragmentTestingMixin(TestWebsiteMetadataMixin):
    """
    A number of methods on the WebsiteMetadata class search for a metadata
    value by querying an HTML document for one of a series of CSS selectors,
    returning a value from first query that returns a match.

    For example, if we are attempting to determine the name of a website, it
    will query the document like this:

    1) The innerText of the `<title>` element.
    2) If #1 cannot be found, look for the `content` attribute of a
       <meta property="og:title"> tag.
    3) If #2 cannot be found, look for the `content` attribute of a
       <meta property="apple-mobile-web-app-title" /> tag.
    4) If #3 cannot be found, return None.

    This mixin allows us to declaratively unit test that logic.

    Each subclass will test one value on the WebsiteMetadata dict. It should
    define three properties:

    - `prop`, the name of the key being tested.
    - `fragments`, an array of strings representing possible matches, in the
      reverse order they are looked for. Each string should contain a string
      interpolation token, `%s`, which will be substituted with a unique value.
    - `value`, a string containing a string interpolation token (`%s`), from
      which a unique value is generated for each fragment.

    Two tests are performed: `test_no_values`, which constructs an empty HTML
    document and ensures that the value of `WebsiteMetadata().prop` is
    `None`, and`test_values`, which tests the preference order by:

    1) Constructing an HTML document with one child, the first item in the
       `fragments` array, populated with a unique value generated by the
       `value` string.
    2) Creates a WebsiteMetadata object from that string.
    3) Tests that the value of the `prop` key in the resulting dict matches
       the unique value set in step 1.

    This test is then repeated, instead creating a document with two elements,
    the first two items in `fragments`, testing that `prop` is set to the
    unique value of the second item. This is repeated by adding an additional
    item from `fragments` until the list is exhausted.
    """
    fragments = []
    prop = None
    value = '%s'

    def get_value(self, iteration):
        value = "%s_%s" % (self.prop, str(iteration))
        return self.value % value

    def get_fragment(self, iteration):
        return self.fragments[iteration] % self.get_value(iteration)

    def make_obj(self, iteration):
        doc = '<html>%s</html>'
        inner = [self.get_fragment(i) for i in xrange(0, iteration + 1)]
        random.shuffle(inner)
        markup = doc % ''.join(inner)
        return self.get_obj(markup)

    def test_no_values(self):
        eq_(None, self.get_empty_obj()[self.prop])

    def test_values(self):
        for n in xrange(0, len(self.fragments)):
            eq_(self.get_value(n), self.make_obj(n)[self.prop])


class TestWebsiteScrapeName(FragmentTestingMixin, TestCase):
    fragments = [
        '<meta name="application-name" content="%s">',
        '<meta name="apple-mobile-web-app-title" content="%s">',
        '<meta property="og:title" content="%s">',
        '<title>%s</title>'
    ]
    prop = 'name'
    value = 'Pied Piper %s'


class TestWebsiteScrapeDescription(FragmentTestingMixin, TestCase):
    fragments = [
        '<meta name="msapplication-tooltip" content="%s">',
        '<meta property="og:description" content="%s">',
        '<meta name="description" content="%s">',
    ]
    prop = 'description'
    value = ('Using our revolutionary middle-out algorithm, Pied Piper takes'
             ' all your files and makes them smaller %s.')


class TestWebsiteScrapeIcon(FragmentTestingMixin, TestCase):
    fragments = [
        '<link rel="fluid-icon" href="%s">',
        '<meta name="msapplication-square70x70logo" content="%s">',
        '<meta name="msapplication-square150x150logo" content="%s">',
        '<meta name="msapplication-square310x310logo" content="%s">',
        '<meta property="og:image" content="%s">',
        '<link rel="apple-touch-icon-precomposed" href="%s">',
        '<link rel="apple-touch-icon-precomposed" sizes="72x72" href="%s">',
        '<link rel="apple-touch-icon-precomposed" sizes="76x76" href="%s">',
        '<link rel="apple-touch-icon-precomposed" sizes="114x114" href="%s">',
        '<link rel="apple-touch-icon-precomposed" sizes="120x120" href="%s">',
        '<link rel="apple-touch-icon-precomposed" sizes="144x144" href="%s">',
        '<link rel="apple-touch-icon-precomposed" sizes="152x152" href="%s">',
    ]
    prop = 'icon'
    value = 'http://www.piedpiper.com/icons/icon_%s.png'


class TestWebsiteScrapeCanonicalUrl(FragmentTestingMixin, TestCase):
    fragments = [
        '<meta property="og:url" content="%s">',
        '<link rel="canonical" href="%s">',
    ]
    prop = 'canonical_url'
    value = 'http://www.piedpiper.com/?%s'


class TestWebsiteScrapeKeywords(FragmentTestingMixin, TestCase):
    fragments = [
        '<meta name="keywords" content="%s">',
    ]
    prop = 'keywords'
    value = 'Compression,Middle Out,Startup,Gilfoyle,%s'
