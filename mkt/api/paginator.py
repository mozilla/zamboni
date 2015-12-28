from collections import OrderedDict

from django.core.paginator import (EmptyPage, Page, PageNotAnInteger,
                                   Paginator)

from elasticsearch_dsl.search import Search
from rest_framework import pagination, response


class ESPaginator(Paginator):
    """
    A better paginator for search results, used by Django views.
    The normal Paginator does a .count() query and then a slice. Since ES
    results contain the total number of results, we can take an optimistic
    slice and then adjust the count.

    """
    def validate_number(self, number):
        """
        Validates the given 1-based page number.

        This class overrides the default behavior and ignores the upper bound.
        """
        try:
            number = int(number)
        except (TypeError, ValueError):
            raise PageNotAnInteger('That page number is not an integer')
        if number < 1:
            raise EmptyPage('That page number is less than 1')
        return number

    def page(self, number):
        """
        Returns a page object.

        This class overrides the default behavior and ignores "orphans" and
        assigns the count from the ES result to the Paginator.
        """
        number = self.validate_number(number)
        bottom = (number - 1) * self.per_page
        top = bottom + self.per_page

        # Force the search to evaluate and then attach the count. We want to
        # avoid an extra useless query even if there are no results, so we
        # directly fetch the count from hits.
        # Overwrite `object_list` with the list of ES results.
        result = self.object_list[bottom:top].execute()
        page = Page(result.hits, number, self)
        # Update the `_count`.
        self._count = page.object_list.total

        # Now that we have the count validate that the page number isn't higher
        # than the possible number of pages and adjust accordingly.
        if number > self.num_pages:
            if number == 1 and self.allow_empty_first_page:
                pass
            else:
                raise EmptyPage('That page contains no results')

        return page


class CustomPagination(pagination.LimitOffsetPagination):
    """
    Paginator for DRF API views. Marketplace API was defined using limit/offset
    pagination before DRF was adopted, this class preserves its legacy
    behaviour.
    """
    count_override = 0

    def __init__(self, default_limit=None):
        pagination.LimitOffsetPagination.__init__(self)
        if default_limit is not None:
            self.default_limit = default_limit

    def get_paginated_response(self, data):
        return response.Response(OrderedDict([
            ('meta', OrderedDict([
                ('next', self.get_next_link()),
                ('previous', self.get_previous_link()),
                ('total_count', self.count),
                ('offset', self.get_offset(self.request)),
                ('limit', self.get_limit(self.request))])),
            ('objects', data)]))

    def paginate_queryset(self, queryset, request, view=None):
        # Modified from superclass method to skip an extra count call for ES
        # searches, since it provides .total in the response. (This is similar
        # to ESPaginator's behavior.)
        self.limit = self.get_limit(request)
        if self.limit is None:
            return None

        self.offset = self.get_offset(request)
        page = queryset[self.offset:self.offset + self.limit]
        if isinstance(page, Search):
            page = page.execute()
            self.count = page.hits.total
        else:
            self.count = self.count_override or pagination._get_count(queryset)
        self.request = request
        if self.count > self.limit and self.template is not None:
            self.display_page_controls = True
        return list(page)


class PageNumberPagination(pagination.PageNumberPagination):

    def django_paginator_class(self, queryset, page_size):
        if isinstance(queryset, Search):
            return ESPaginator(queryset, page_size)
        else:
            return Paginator(queryset, page_size)

    def get_paginated_response(self, data):
        return response.Response(OrderedDict([
            ('meta', OrderedDict([
                ('count', self.page.paginator.count),
                ('next', self.get_next_link()),
                ('previous', self.get_previous_link())])),
            ('objects', data)]))
