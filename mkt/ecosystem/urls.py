from django.conf.urls import patterns, url
from django.views.generic import RedirectView

from . import views


APP_SLUGS = {
    'chrono': 'Chrono',
    'face_value': 'Face_Value',
    'podcasts': 'Podcasts',
    'roller': 'Roller',
    'webfighter': 'Webfighter',
    'generalnotes': 'General_Notes',
    'rtcamera': 'rtcamera'
}


def redirect_doc(uri, request=None):
    view = RedirectView.as_view(
        url='https://developer.mozilla.org/docs%s' % uri)
    return view(request) if request else view


redirect_patterns = patterns(
    '',
    url('^docs/firefox_os_guideline$',
        redirect_doc('/Web/Apps/Design'),
        name='ecosystem.ffos_guideline'),
    url('^docs/responsive_design$',
        redirect_doc('/Web_Development/Mobile/Responsive_design'),
        name='ecosystem.responsive_design'),
    url('^docs/patterns$',
        redirect_doc('/Web/Apps/Design/Responsive_Navigation_Patterns'),
        name='ecosystem.design_patterns'),
    url('^docs/review$',
        redirect_doc('/Web/Apps/Publishing/Marketplace_review_criteria'),
        name='ecosystem.publish_review'),
    url('^docs/deploy$',
        redirect_doc('/Mozilla/Marketplace/Options/Introduction'),
        name='ecosystem.publish_deploy'),
    url('^docs/hosted$',
        redirect_doc('/Mozilla/Marketplace/Options/Self_publishing'
                     '#Self-publishing_Hosted_Apps'),
        name='ecosystem.publish_hosted'),
    url('^docs/submission$',
        redirect_doc('/Mozilla/Marketplace/Publishing/Submit/Overview'),
        name='ecosystem.publish_submit'),
    url('^docs/packaged$',
        redirect_doc('/Mozilla/Marketplace/Options/Packaged_apps'),
        name='ecosystem.publish_packaged'),
    url('^docs/intro_apps$',
        redirect_doc('/Web/Apps/Quickstart/Build/Intro_to_open_web_apps'),
        name='ecosystem.build_intro'),
    url('^docs/firefox_os$',
        redirect_doc('/Mozilla/Firefox_OS'),
        name='ecosystem.build_ffos'),
    url('^docs/manifests$',
        redirect_doc('/Web/Apps/FAQs/About_app_manifests'),
        name='ecosystem.build_manifests'),
    url('^docs/apps_offline$',
        redirect_doc('/Web/Apps/Offline_apps'),
        name='ecosystem.build_apps_offline'),
    url('^docs/game_apps$',
        redirect_doc('/Web/Apps/Developing/Games'),
        name='ecosystem.build_game_apps'),
    url('^docs/mobile_developers$',
        redirect_doc('/Web/Apps/Quickstart/Build/For_mobile_developers'),
        name='ecosystem.build_mobile_developers'),
    url('^docs/web_developers$',
        redirect_doc('/Web/Apps/Quickstart/Build/For_Web_developers'),
        name='ecosystem.build_web_developers'),
    url('^docs/firefox_os_simulator$',
        redirect_doc('/Tools/Firefox_OS_Simulator'),
        name='ecosystem.firefox_os_simulator'),
    url('^docs/payments$',
        redirect_doc('/Mozilla/Marketplace/Monetization'
                     '/Introduction_Monetization'),
        name='ecosystem.build_payments'),
    url('^docs/concept$',
        redirect_doc('/Web/Apps/Quickstart/Design/Concept_A_great_app'),
        name='ecosystem.design_concept'),
    url('^docs/fundamentals$',
        redirect_doc('/Web/Apps/Design/Design_Principles'),
        name='ecosystem.design_fundamentals'),
    url('^docs/ui_guidelines$',
        redirect_doc('/Web/Apps/Design'),
        name='ecosystem.design_ui'),
    url('^docs/quick_start$',
        redirect_doc('/Web/Apps/Quickstart'),
        name='ecosystem.build_quick'),
    url('^docs/reference_apps$',
        redirect_doc('/Web/Apps/Reference_apps'),
        name='ecosystem.build_reference'),
    url('^docs/apps/(?P<page>\w+)?$',
        lambda req, page:
            redirect_doc('/Web/Apps/Reference_apps/' + APP_SLUGS.get(page, ''),
                         req),
        name='ecosystem.apps_documentation'),
    url('^docs/payments/status$',
        redirect_doc('/Mozilla/Marketplace/Payments_Status'),
        name='ecosystem.publish_payments'),
    url('^docs/tools$',
        redirect_doc('/Web/Apps/Quickstart/Build/App_tools'),
        name='ecosystem.build_tools'),
    url('^docs/app_generator$',
        redirect_doc('/Web/Apps/Developing/App_templates'),
        name='ecosystem.build_app_generator'),
    url('^docs/app_manager$',
        redirect_doc('/Mozilla/Firefox_OS/Using_the_App_Manager'),
        name='ecosystem.app_manager'),
    url('^docs/dev_tools$',
        redirect_doc('/Tools'),
        name='ecosystem.build_dev_tools'),

    # Doesn't start with docs/, but still redirects to MDN.
    url('^dev_phone$',
        redirect_doc('/Mozilla/Firefox_OS/Developer_phone_guide/Flame'),
        name='ecosystem.dev_phone'),
)


urlpatterns = redirect_patterns + patterns(
    '',
    url('^$', views.landing, name='ecosystem.landing'),
    url('^partners$', views.partners, name='ecosystem.partners'),
    url('^support$', views.support, name='ecosystem.support'),
    url('^docs/badges$', views.publish_badges, name='ecosystem.publish_badges')
)
