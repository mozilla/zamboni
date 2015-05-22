from django.conf.urls import include, patterns, url

from rest_framework.routers import SimpleRouter

import mkt
from mkt.receipts.urls import receipt_patterns
from mkt.reviewers import views
from mkt.websites.views import ReviewersWebsiteSearchView


# All URLs under /reviewers/.
url_patterns = patterns(
    '',
    url(r'^apps/$', views.home, name='reviewers.home'),
    url(r'^$', views.route_reviewer, name='reviewers'),
    url(r'^apps/queue/$', views.queue_apps,
        name='reviewers.apps.queue_pending'),
    url(r'^apps/queue/region/(?P<region>[^ /]+)?$', views.queue_region,
        name='reviewers.apps.queue_region'),
    url(r'^apps/queue/additional/(?P<queue>[^ /]+)$', views.additional_review,
        name='reviewers.apps.additional_review'),
    url(r'^apps/queue/rereview/$', views.queue_rereview,
        name='reviewers.apps.queue_rereview'),
    url(r'^apps/queue/updates/$', views.queue_updates,
        name='reviewers.apps.queue_updates'),
    url(r'^apps/queue/escalated/$', views.queue_escalated,
        name='reviewers.apps.queue_escalated'),
    url(r'^apps/queue/moderated/$', views.queue_moderated,
        name='reviewers.apps.queue_moderated'),
    url(r'^apps/queue/abuse/$', views.queue_abuse,
        name='reviewers.apps.queue_abuse'),
    url(r'^apps/review/%s$' % mkt.APP_SLUG, views.app_review,
        name='reviewers.apps.review'),
    url(r'^app/%s/$' % mkt.APP_SLUG, views.app_review),
    url(r'^apps/review/%s/manifest$' % mkt.APP_SLUG, views.app_view_manifest,
        name='reviewers.apps.review.manifest'),
    url(r'^apps/review/attachment/(\d+)$', views.attachment,
        name='reviewers.apps.review.attachment'),
    url(r'^apps/review/%s/abuse$' % mkt.APP_SLUG, views.app_abuse,
        name='reviewers.apps.review.abuse'),

    url(r'^apps/reviewlogs$', views.logs, name='reviewers.apps.logs'),
    url(r'^apps/moderatelogs$', views.moderatelog,
        name='reviewers.apps.moderatelog'),
    url(r'^apps/moderatelog/(\d+)$', views.moderatelog_detail,
        name='reviewers.apps.moderatelog.detail'),

    url(r'^apps/motd$', views.motd, name='reviewers.apps.motd'),
    url(r'^queue_viewing$', views.queue_viewing,
        name='reviewers.queue_viewing'),
    url(r'^review_viewing$', views.review_viewing,
        name='reviewers.review_viewing'),
    url(r'^apps/reviewing$', views.apps_reviewing,
        name='reviewers.apps.apps_reviewing'),

    url(r'^receipt/', include(receipt_patterns)),
    url(r'^%s/(?P<version_id>\d+)/mini-manifest$' % mkt.APP_SLUG,
        views.mini_manifest, name='reviewers.mini_manifest'),
    url(r'^signed/%s/(?P<version_id>\d+)$' % mkt.APP_SLUG,
        views.get_signed_packaged, name='reviewers.signed'),

    url(r'''^performance/(?P<email>[^/<>"']+)?$''', views.performance,
        name='reviewers.performance'),
    url(r'^leaderboard/$', views.leaderboard, name='reviewers.leaderboard'),
)

reviewers_router = SimpleRouter()
reviewers_router.register(r'canned-responses', views.CannedResponseViewSet)
reviewers_router.register(r'scores', views.ReviewerScoreViewSet)


api_patterns = patterns(
    '',
    url(r'reviewers/', include(reviewers_router.urls)),
    url('^reviewers/search', views.ReviewersSearchView.as_view(),
        name='reviewers-search-api'),
    url('^reviewers/sites/search', ReviewersWebsiteSearchView.as_view(),
        name='reviewers-website-search-api'),
    url(r'^reviewers/app/(?P<pk>[^/<>"\']+)/approve/(?P<region>[^ /]+)$',
        views.ApproveRegion.as_view(), name='approve-region'),
    url(r'^reviewers/app/(?P<pk>[^/<>"\']+)/approve/$',
        views.AppApprove.as_view(), name='app-approve'),
    url(r'^reviewers/app/(?P<pk>[^/<>"\']+)/reject/',
        views.AppReject.as_view(), name='app-reject'),
    url(r'^reviewers/app/(?P<pk>[^/<>"\']+)/info/',
        views.AppInfo.as_view(), name='app-info'),
    url(r'^reviewers/app/(?P<pk>[^/<>"\']+)/escalate/',
        views.AppEscalate.as_view(), name='app-escalate'),
    url(r'^reviewers/app/(?P<pk>[^/<>"\']+)/disable/',
        views.AppDisable.as_view(), name='app-disable'),
    url(r'^reviewers/app/(?P<pk>[^/<>"\']+)/rereview/',
        views.AppRereview.as_view(), name='app-rereview'),
    url(r'^reviewers/app/(?P<pk>[^/<>"\']+)/comment/',
        views.AppReviewerComment.as_view(), name='app-comment'),
    url(r'^reviewers/queue/additional$',
        views.CreateAdditionalReviewViewSet.as_view(),
        name='additionalreviews'),
    url(r'^reviewers/queue/additional/(?P<pk>\d+)$',
        views.UpdateAdditionalReviewViewSet.as_view(),
        name='additionalreview-detail'),
    url(r'^reviewers/reviewing', views.ReviewingView.as_view(),
        name='reviewing-list'),
    url('^reviewers/%s/review/(?P<review_pk>\d+)/translate/'
        '(?P<language>[a-z]{2}(-[A-Z]{2})?)$' % mkt.APP_SLUG,
        views.review_translate,
        name='reviewers.review_translate'),
    url('^reviewers/%s/abuse/(?P<report_pk>\d+)/translate/'
        '(?P<language>[a-z]{2}(-[A-Z]{2})?)$' % mkt.APP_SLUG,
        views.abuse_report_translate,
        name='reviewers.abuse_report_translate'),
    url(r'^reviewers/app/(?P<pk>[^/<>"\']+)/token$',
        views.GenerateToken.as_view(), name='generate-reviewer-token')
)
