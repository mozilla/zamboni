# -*- coding: utf-8 -*-
from urlparse import urlparse

from django.http import QueryDict
from django.test.client import RequestFactory

from nose.tools import eq_
from rest_framework.request import Request

from mkt.api.paginator import CustomPagination, ESPaginator
from mkt.site.tests import ESTestCase, TestCase
from mkt.webapps.indexers import WebappIndexer


class TestSearchPaginator(ESTestCase):

    def test_single_hit(self):
        """Test the ESPaginator only queries ES one time."""
        es = WebappIndexer.get_es()
        orig_search = es.search
        es.counter = 0

        def monkey_search(*args, **kwargs):
            es.counter += 1
            return orig_search(*args, **kwargs)

        es.search = monkey_search

        ESPaginator(WebappIndexer.search(), 5).object_list.execute()
        eq_(es.counter, 1)

        es.search = orig_search


class TestMetaSerializer(TestCase):
    def setUp(self):
        self.url = '/api/whatever'
        self.paginator = CustomPagination()

    def get_serialized_data(self, page):
        return self.paginator.get_paginated_response(page).data['meta']

    def req(self, **kwargs):
        self.request = Request(RequestFactory().get(self.url, kwargs))

    def test_simple(self):
        data = ['a', 'b', 'c']
        per_page = 3
        self.req(limit=per_page)
        page = self.paginator.paginate_queryset(data, self.request)
        serialized = self.get_serialized_data(page)
        eq_(serialized['offset'], 0)
        eq_(serialized['next'], None)
        eq_(serialized['previous'], None)
        eq_(serialized['total_count'], len(data))
        eq_(serialized['limit'], per_page)

    def test_first_page_of_two(self):
        data = ['a', 'b', 'c', 'd', 'e']
        per_page = 3
        self.req(limit=per_page)
        page = self.paginator.paginate_queryset(data, self.request)
        serialized = self.get_serialized_data(page)
        eq_(serialized['offset'], 0)
        eq_(serialized['total_count'], len(data))
        eq_(serialized['limit'], per_page)

        eq_(serialized['previous'], None)

        next = urlparse(serialized['next'])
        eq_(next.path, self.url)
        eq_(QueryDict(next.query), QueryDict('limit=3&offset=3'))

    def test_third_page_of_four(self):
        data = ['a', 'b', 'c', 'd', 'e', 'f', 'g']
        per_page = 2
        self.req(limit=per_page, offset=4)
        page = self.paginator.paginate_queryset(data, self.request)
        serialized = self.get_serialized_data(page)
        # Third page will begin after fourth item
        # (per_page * number of pages before) item.
        eq_(serialized['offset'], 4)
        eq_(serialized['total_count'], len(data))
        eq_(serialized['limit'], per_page)

        prev = urlparse(serialized['previous'])
        eq_(prev.path, self.url)
        eq_(QueryDict(prev.query), QueryDict('limit=2&offset=2'))

        next = urlparse(serialized['next'])
        eq_(next.path, self.url)
        eq_(QueryDict(next.query), QueryDict('limit=2&offset=6'))

    def test_fourth_page_of_four(self):
        data = ['a', 'b', 'c', 'd', 'e', 'f', 'g']
        per_page = 2
        self.req(limit=per_page, offset=6)
        page = self.paginator.paginate_queryset(data, self.request)
        serialized = self.get_serialized_data(page)
        # Third page will begin after fourth item
        # (per_page * number of pages before) item.
        eq_(serialized['offset'], 6)
        eq_(serialized['total_count'], len(data))
        eq_(serialized['limit'], per_page)

        prev = urlparse(serialized['previous'])
        eq_(prev.path, self.url)
        eq_(QueryDict(prev.query), QueryDict('limit=2&offset=4'))

        eq_(serialized['next'], None)

    def test_with_request_path_override_existing_params(self):
        self.url = '/api/whatever/?limit=2&offset=2&extra=n&superfluous=yes'
        self.request = Request(RequestFactory().get(self.url))
        data = ['a', 'b', 'c', 'd', 'e', 'f']
        page = self.paginator.paginate_queryset(data, self.request)
        serialized = self.get_serialized_data(page)
        eq_(serialized['offset'], 2)
        eq_(serialized['total_count'], len(data))
        eq_(serialized['limit'], 2)

        prev = urlparse(serialized['previous'])
        eq_(prev.path, '/api/whatever/')
        eq_(QueryDict(prev.query),
            QueryDict('limit=2&extra=n&superfluous=yes'))

        next = urlparse(serialized['next'])
        eq_(next.path, '/api/whatever/')
        eq_(QueryDict(next.query),
            QueryDict('limit=2&offset=4&extra=n&superfluous=yes'))

    def test_urlencoded_query_string(self):
        self.url = '/api/whatever/yó'
        data = ['a', 'b', 'c', 'd', 'e', 'f']
        self.req(limit=1)
        page = self.paginator.paginate_queryset(data, self.request)
        serialized = self.get_serialized_data(page)
        assert '/y%C3%B3?' in serialized['next']
