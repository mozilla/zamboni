from django.http import Http404

import commonware
from rest_framework import status
from rest_framework.generics import CreateAPIView, ListAPIView
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.serializers import ModelSerializer, SerializerMethodField

import amo
import lib.iarc
from amo.decorators import skip_cache

from mkt.api.base import CORSMixin, SlugOrIdMixin
from mkt.developers.forms import ContentRatingForm
from mkt.webapps.models import ContentRating, Webapp


log = commonware.log.getLogger('z.devhub')


class ContentRatingSerializer(ModelSerializer):
    body = SerializerMethodField('get_body')
    rating = SerializerMethodField('get_rating')

    def get_body(self, obj):
        return obj.get_body().label

    def get_rating(self, obj):
        return obj.get_rating().label

    class Meta:
        model = ContentRating
        fields = ('created', 'modified', 'body', 'rating')


class ContentRatingList(CORSMixin, SlugOrIdMixin, ListAPIView):
    model = ContentRating
    serializer_class = ContentRatingSerializer
    permission_classes = (AllowAny,)
    cors_allowed_methods = ['get']

    queryset = Webapp.objects.all()
    slug_field = 'app_slug'

    @skip_cache
    def get(self, request, *args, **kwargs):
        app = self.get_object()

        self.queryset = app.content_ratings.all()

        if 'since' in request.GET:
            form = ContentRatingForm(request.GET)
            if form.is_valid():
                self.queryset = self.queryset.filter(
                    modified__gt=form.cleaned_data['since'])

        if not self.queryset.exists():
            raise Http404()

        return super(ContentRatingList, self).get(self, request)


class ContentRatingsPingback(CORSMixin, SlugOrIdMixin, CreateAPIView):
    cors_allowed_methods = ['post']
    parser_classes = (lib.iarc.utils.IARC_JSON_Parser,)
    permission_classes = (AllowAny,)

    queryset = Webapp.objects.all()
    slug_field = 'app_slug'

    def post(self, request, pk, *args, **kwargs):
        log.info(u'Received IARC pingback for app:%s' % pk)

        if request.content_type != 'application/json':
            log.info(u'IARC pingback not of content-type "application/json"')
            return Response({
                'detail': "Endpoint only accepts 'application/json'."
            }, status=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE)

        app = self.get_object()

        # Verify token.
        data = request.DATA[0]
        if app.iarc_token() != data.get('token'):
            log.info(u'Token mismatch in IARC pingback for app:%s' % app.id)
            return Response({'detail': 'Token mismatch'},
                            status=status.HTTP_400_BAD_REQUEST)

        if data.get('ratings'):
            # Double-check with IARC that it's the correct rating.
            if not self.verify_data(data):
                return Response('The ratings do not match the submission ID.',
                                status=status.HTTP_400_BAD_REQUEST)

            log.info(u'Setting content ratings from IARC pingback for app:%s' %
                     app.id)
            # We found a rating, so store the id and code for future use.
            if 'submission_id' in data and 'security_code' in data:
                app.set_iarc_info(data['submission_id'], data['security_code'])

            # Update status if incomplete status.
            # Do this before set_content_ratings to not prematurely trigger
            # a refresh.
            log.info('Checking app:%s completeness after IARC pingback.'
                     % app.id)
            if (app.has_incomplete_status() and
                app.is_fully_complete(ignore_ratings=True)):
                log.info('Updating app status from IARC pingback for app:%s' %
                         app.id)
                # Don't call update to prevent recursion in update_status.
                app.update(status=amo.STATUS_PENDING)
                log.info('Updated app status from IARC pingback for app:%s' %
                         app.id)
            elif app.has_incomplete_status():
                log.info('Reasons for app:%s incompleteness after IARC '
                         'pingback: %s' % (app.id, app.completion_errors()))

            app.set_descriptors(data.get('descriptors', []))
            app.set_interactives(data.get('interactives', []))
            # Set content ratings last since it triggers a refresh on Content
            # Ratings page. We want descriptors and interactives visible by
            # the time it's refreshed.
            app.set_content_ratings(data.get('ratings', {}))

        return Response('ok')

    def verify_data(self, data):
        client = lib.iarc.client.get_iarc_client('services')
        xml = lib.iarc.utils.render_xml('get_app_info.xml', data)
        resp = client.Get_App_Info(XMLString=xml)
        check_data = lib.iarc.utils.IARC_XML_Parser().parse_string(resp)
        try:
            check_data = check_data.get('rows', [])[0]
        except IndexError:
            return False

        rates_bad = data.get('ratings') != check_data.get('ratings')
        inter_bad = (set(data.get('interactives', [])) !=
                     set(check_data.get('interactives', [])))
        descs_bad = (set(data.get('descriptors', [])) !=
                     set(check_data.get('descriptors', [])))
        if rates_bad:
            log.error('IARC pingback did not match rating %s vs %s' %
                      (data.get('ratings'), check_data.get('ratings')))
        if inter_bad:
            log.error('IARC pingback did not match interactives %s vs %s' %
                      (data.get('interactives'),
                       check_data.get('interactives')))
        if descs_bad:
            log.error('IARC pingback did not match descriptors %s vs %s' %
                      (data.get('descriptors'), check_data.get('descriptors')))
        if rates_bad or inter_bad or descs_bad:
            return False

        return True
