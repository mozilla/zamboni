from rest_framework.views import APIView

from django.http import Http404
from django.views.decorators.csrf import csrf_exempt


class EndpointRemoved(APIView):
    """
    View that always returns a 404.

    To be used when API endpoints are removed in newer versions of the API.
    """
    def dispatch(self, request, *args, **kwargs):
        raise Http404


endpoint_removed = csrf_exempt(EndpointRemoved.as_view())
