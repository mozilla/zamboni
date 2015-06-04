import functools

from django.shortcuts import get_object_or_404

from mkt.websites.models import Website


def website_view(f, qs=Website.objects.all):
    @functools.wraps(f)
    def wrapper(request, pk, *args, **kw):
        website = get_object_or_404(qs(), pk=pk)
        return f(request, website, *args, **kw)
    return wrapper
