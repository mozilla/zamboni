from django.db.models import Q
from django.http import Http404

import commonware.log
from rest_framework.decorators import action
from rest_framework.exceptions import (MethodNotAllowed, NotAuthenticated,
                                       PermissionDenied)
from rest_framework.mixins import CreateModelMixin
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.viewsets import GenericViewSet, ModelViewSet

import mkt
from lib.metrics import record_action
from mkt.access.acl import check_webapp_ownership
from mkt.api.authentication import (RestAnonymousAuthentication,
                                    RestOAuthAuthentication,
                                    RestSharedSecretAuthentication)
from mkt.api.base import CORSMixin, MarketplaceView
from mkt.api.permissions import (AllowOwner, AllowRelatedAppOwner, AnyOf,
                                 ByHttpMethod, GroupPermission)
from mkt.ratings.serializers import RatingFlagSerializer, RatingSerializer
from mkt.webapps.models import Webapp
from mkt.ratings.models import Review, ReviewFlag


log = commonware.log.getLogger('z.api')


class RatingViewSet(CORSMixin, MarketplaceView, ModelViewSet):
    # Unfortunately, the model class name for ratings is "Review".
    # We prefetch 'version' because it's often going to be similar, and select
    # related 'user' to avoid extra queries.
    queryset = (Review.objects.valid()
                .prefetch_related('version')
                .select_related('user'))
    cors_allowed_methods = ('get', 'post', 'put', 'delete')
    permission_classes = [ByHttpMethod({
        'options': AllowAny,  # Needed for CORS.
        'get': AllowAny,
        'head': AllowAny,
        'post': IsAuthenticated,
        'put': AnyOf(AllowOwner,
                     GroupPermission('Apps', 'Edit')),
        'delete': AnyOf(AllowOwner,
                        AllowRelatedAppOwner,
                        GroupPermission('Users', 'Edit'),
                        GroupPermission('Apps', 'Edit')),
    })]
    authentication_classes = [RestOAuthAuthentication,
                              RestSharedSecretAuthentication,
                              RestAnonymousAuthentication]
    serializer_class = RatingSerializer

    def paginator_class(self, *args, **kwargs):
        paginator = super(RatingViewSet, self).paginator_class(*args, **kwargs)
        if hasattr(self, 'app'):
            # If an app is passed, we want the paginator count to match the
            # number of reviews on the app, without doing an extra query.
            paginator._count = self.app.total_reviews
        return paginator

    # FIXME: Add throttling ? Original tastypie version didn't have it...

    def filter_queryset(self, queryset):
        """
        Custom filter method allowing us to filter on app slug/pk and user pk
        (or the special user value "mine"). A full FilterSet is overkill here.
        """
        filters = Q()
        app = self.request.GET.get('app')
        user = self.request.GET.get('user')
        lang = self.request.GET.get('lang')
        match_lang = self.request.GET.get('match_lang')
        if app:
            self.app = self.get_app(app)
            filters &= Q(webapp=self.app)
        if user:
            filters &= Q(user=self.get_user(user))
        elif lang and match_lang == '1':
            filters &= Q(lang=lang)

        if filters:
            queryset = queryset.filter(filters)
        return queryset

    def get_user(self, ident):
        pk = ident
        if pk == 'mine':
            user = mkt.get_user()
            if not user or not user.is_authenticated():
                # You must be logged in to use "mine".
                raise NotAuthenticated()
            pk = user.pk
        return pk

    def get_app(self, ident):
        try:
            app = Webapp.objects.by_identifier(ident)
        except Webapp.DoesNotExist:
            raise Http404

        if not app.is_public() and not check_webapp_ownership(
                self.request, app):
            # App owners and admin can see the app even if it's not public.
            # Regular users or anonymous users can't.
            raise PermissionDenied('The app requested is not public')
        return app

    def list(self, request, *args, **kwargs):
        response = super(RatingViewSet, self).list(request, *args, **kwargs)
        app = getattr(self, 'app', None)
        if app:
            user, info = self.get_extra_data(app, request.user)
            response.data['user'] = user
            response.data['info'] = info
        return response

    def destroy(self, request, *args, **kwargs):
        obj = self.get_object()
        mkt.log(mkt.LOG.DELETE_REVIEW, obj.webapp, obj,
                details=dict(title=unicode(obj.title),
                             body=unicode(obj.body),
                             webapp_id=obj.webapp.id,
                             webapp_title=unicode(obj.webapp.name)))
        log.debug('[Review:%s] Deleted by %s' %
                  (obj.pk, self.request.user.id))
        return super(RatingViewSet, self).destroy(request, *args, **kwargs)

    def post_save(self, obj, created=False):
        app = obj.webapp
        if created:
            mkt.log(mkt.LOG.ADD_REVIEW, app, obj)
            log.debug('[Review:%s] Created by user %s ' %
                      (obj.pk, self.request.user.id))
            record_action('new-review', self.request, {'app-id': app.id})
        else:
            mkt.log(mkt.LOG.EDIT_REVIEW, app, obj)
            log.debug('[Review:%s] Edited by %s' %
                      (obj.pk, self.request.user.id))

    def partial_update(self, *args, **kwargs):
        # We don't need/want PATCH for now.
        raise MethodNotAllowed('PATCH is not supported for this endpoint.')

    def get_extra_data(self, app, user):
        extra_user = None

        if user.is_authenticated():
            if app.is_premium():
                # If the app is premium, you need to purchase it to rate it.
                can_rate = app.has_purchased(user)
            else:
                # If the app is free, you can not be one of the authors.
                can_rate = not app.has_author(user)

            filters = {
                'webapp': app,
                'user': user
            }
            if app.is_packaged:
                filters['version'] = app.current_version

            extra_user = {
                'can_rate': can_rate,
                'has_rated': Review.objects.valid().filter(**filters).exists()
            }

        extra_info = {
            'average': app.average_rating,
            'slug': app.app_slug,
            'total_reviews': app.total_reviews,
            'current_version': getattr(app.current_version, 'version', None)
        }

        return extra_user, extra_info

    @action(methods=['POST'], permission_classes=[AllowAny])
    def flag(self, request, pk=None):
        self.kwargs[self.lookup_field] = pk
        self.get_object()  # Will check that the Review instance is valid.
        request._request.CORS = RatingFlagViewSet.cors_allowed_methods
        view = RatingFlagViewSet.as_view({'post': 'create'})
        return view(request, *self.args, **{'review': pk})


class RatingFlagViewSet(CORSMixin, CreateModelMixin, GenericViewSet):
    queryset = ReviewFlag.objects.all()
    cors_allowed_methods = ('post',)
    permission_classes = [AllowAny]
    authentication_classes = [RestAnonymousAuthentication]
    serializer_class = RatingFlagSerializer

    def post_save(self, obj, created=False):
        review = self.kwargs['review']
        Review.objects.filter(id=review).update(editorreview=True)
