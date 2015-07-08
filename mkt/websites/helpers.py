import urlparse
from contextlib import closing

import requests
from pyquery import PyQuery as pq


class WebsiteMetadata(dict):
    """
    A subclass of dict representing inferred metadata of a URL passed in
    construction. Currently includes:

    - Canonical URL
    - Description
    - Icon
    - Keywords
    - Name

    Usage:
    >>> WebsiteMetadata('http://mobile.nytimes.com')
    {
      'keywords': None,
      'icon': 'http://mobile.nytimes.com/.../touch-icon-ipad-144.498cc670.png',
      'canonical_url': 'http://www.nytimes.com/?nytmobile=0',
      'name': 'The New York Times',
      'description': None
    }
    """
    _valid_keys = ['canonical_url', 'description', 'icon', 'keywords', 'name']
    _appletouchicon_sizes = [152, 144, 120, 114, 76, 72, None]
    _msapplication_sizes = [310, 150, 70]

    def __init__(self, url):
        self.url = url
        self._document = None
        self._markup = None
        self._get_metadata()

    def __getitem__(self, key):
        """
        Prevents invalid keys from being retrieved.
        """
        if key in self._valid_keys:
            return dict.__getitem__(self, key)
        else:
            raise KeyError(self._invalid_key % key)

    def __setitem__(self, key, val):
        """
        Prevents invalid keys from being set.
        """
        if key in self._valid_keys:
            return dict.__setitem__(self, key, val)
        else:
            raise KeyError(self._invalid_key % key)

    def update(self):
        """
        Retries the request to fetch the URL

        and updates any discoverable metadata.
        """
        self._get_metadata()

    @property
    def _invalid_key(self):
        """
        Returns a comma-separated list of valid keys, useful for exception
        messages.
        """
        return 'Invalid key "%%s". Valid: %s' % ', '.join(self._valid_keys)

    def _get_document(self):
        """
        Makes a request to the passed URL, returns and stores a PyQuery
        document for the response body.

        If the document errors (HTTP codes 400 or higher), an instance of
        requests.exceptions.HTTPError is raised, with an additional property
        `response` containing the response object.
        """
        with closing(requests.get(self.url, stream=True)) as response:
            if response.status_code >= 400:
                exception = requests.exceptions.HTTPError()
                exception.response = response
                raise exception
            self._markup = response.content
            self._document = pq(self._markup)
        return self._document

    def _get_metadata(self):
        """
        Determines and sets the document's metadata on self.
        """
        if not self._document:
            self._get_document()
        self['canonical_url'] = self._get_canonical_url()
        self['description'] = self._get_description()
        self['icon'] = self._get_icon()
        self['keywords'] = self._get_keywords()
        self['name'] = self._get_name()

    def _get_name(self):
        """
        Attempts to return a name for the object's document. If one cannot be
        found, returns None.
        """
        return (self._check_text('title') or
                self._check_opengraph('title') or
                self._check_meta('apple-mobile-web-app-title') or
                self._check_meta('application-name'))

    def _get_description(self):
        """
        Attempts to return a description for the object's document. If one
        cannot be found, returns None.
        """
        return (self._check_meta('description') or
                self._check_opengraph('description') or
                self._check_meta('msapplication-tooltip'))

    def _get_icon(self):
        """
        Attempts to join the reported path to an icon for the object's
        document with the URL itself. If one cannot be found, returns None.
        """
        path = self._get_icon_path()
        if path and not path.startswith('http'):
            return urlparse.urljoin(self.url, path)
        elif path and path.startswith('http'):
            return path
        return None

    def _get_icon_path(self):
        """
        Attempts to return the reported path to an icon for the object's
        document. If one cannot be found, returns None.
        """
        return (self._check_apple_icon() or
                self._check_opengraph('image') or
                self._check_ms_icon() or
                self._check_link('fluid-icon'))

    def _get_canonical_url(self):
        """
        Attempts to return the canonical URL for the object's document. If one
        cannot be found, returns None.
        """
        return (self._check_link('canonical') or
                self._check_opengraph('url'))

    def _get_keywords(self):
        """
        Attempts to return the appropriate keywords for the object's document.
        If they cannot be found, returns None.
        """
        return self._check_meta('keywords')

    def _check_text(self, selector):
        """
        Passed a CSS selector, attempts to return the DOM innerText of the
        first element matching that selector. If there are no matches, returns
        None.
        """
        try:
            return self._document(selector)[0].text
        except:
            return None

    def _check_meta(self, name):
        """
        Attempts to return the `content` attribute of the `<meta />` element
        with the `name` attribute of the passed name. If one cannot be found,
        returns None.
        """
        """
        Attempts to return the `content` attribute of a `<meta />` tag with
        the passed name. If one cannot be found, returns None.
        """
        selector = 'meta[name="%s"]' % name
        try:
            return self._document(selector)[0].attrib['content']
        except:
            return None

    def _check_link(self, rel):
        """
        Attempts to return the `href` attribute of a `<link />` tag with `rel`
        set to the passed name. If one cannot be found, returns None.
        """
        selector = 'link[rel="%s"]' % rel
        try:
            return self._document(selector)[0].attrib['href']
        except:
            return None

    def _check_opengraph(self, name):
        """
        Attempts to return the value of an OpenGraph `<meta />` tag of the
        property with the passed name. If one cannot be found, returns None.
        """
        selector = 'meta[property="og:%s"]' % name
        try:
            return self._document(selector)[0].attrib['content']
        except:
            return None

    def _check_apple_icon(self):
        """
        Attempts to return the URL of the apple-touch-icon of the most
        preferred size (based on the order in cls._appletouchicon_sizes). If
        one is not defined, returns None.
        """
        for size in self._appletouchicon_sizes:
            icon = self._check_apple_icon_size(size)
            if icon:
                return icon
        return None

    def _check_apple_icon_size(self, dimension):
        """
        Attempts to return the URL to an apple-touch-icon icon with the
        passed dimension. If a dimension is not defined, checks for one with an
        undefined size. If no icon matching the criteria can be found, returns
        None.
        """
        selector = 'link[rel="apple-touch-icon-precomposed"]'
        if dimension:
            selector = '%s[sizes="%sx%s"]' % (selector, dimension, dimension)
        try:
            return self._document(selector)[0].attrib['href']
        except:
            return None

    def _check_ms_icon(self):
        """
        Attempts to return the URL of the msapplication icon of the most
        preferred size (based on the order in cls._msapplication_sizes). If one
        is not defined, returns None.
        """
        for size in self._msapplication_sizes:
            icon = self._check_ms_icon_size(size)
            if icon:
                return icon
        return None

    def _check_ms_icon_size(self, dimension):
        """
        Attempts to return the URL to an msapplication square icon with the
        passed dimension. If one is not defined, returns None.
        """
        selector = 'meta[name="msapplication-square%sx%slogo"]' % (dimension,
                                                                   dimension)
        try:
            return self._document(selector)[0].attrib['content']
        except:
            return None
