# -*- coding: utf-8 -*-
from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect

import basket
import commonware.log
from session_csrf import anonymous_csrf
from django.utils.translation import ugettext as _

from mkt.developers.forms import DevNewsletterForm
from mkt.site.utils import render


log = commonware.log.getLogger('z.ecosystem')


@anonymous_csrf
def landing(request):
    """Developer Hub landing page."""
    videos = [
        {
            'name': 'airbnb',
            'path': 'FirefoxMarketplace-airbnb-BR-RC-SD1%20640'
        },
        {
            'name': 'evernote',
            'path': 'FirefoxMarketplace-Evernote_BR-RC-SD1%20640'
        },
        {
            'name': 'uken',
            'path': 'FirefoxMarketplace-uken-BR-RC-SD1%20640'
        },
        {
            'name': 'soundcloud',
            'path': 'FirefoxMarketplace-Soundcloud-BR-RC-SD1%20640'
        },
        {
            'name': 'box',
            'path': 'FirefoxMarketplace_box-BR-RC-SD1%20640'
        }
    ]

    form = DevNewsletterForm(request.LANG, request.POST or None)

    if request.method == 'POST' and form.is_valid():
        data = form.cleaned_data

        try:
            basket.subscribe(data['email'],
                             'app-dev',
                             format=data['email_format'],
                             source_url=settings.SITE_URL)
            messages.success(request, _('Thank you for subscribing!'))
            return redirect('ecosystem.landing')
        except basket.BasketException as e:
            log.error(
                'Basket exception in ecosystem newsletter: %s' % e)
            messages.error(
                request, _('We apologize, but an error occurred in our '
                           'system. Please try again later.'))

    return render(request, 'ecosystem/landing.html',
                  {'videos': videos, 'newsletter_form': form})


def support(request):
    """Landing page for support."""
    return render(request, 'ecosystem/support.html',
                  {'page': 'support', 'category': 'build'})


def partners(request):
    """Landing page for partners."""
    return render(request, 'ecosystem/partners.html', {'page': 'partners'})


def installation(request):
    """Landing page for installation."""
    return render(request, 'ecosystem/installation.html',
                  {'page': 'installation', 'category': 'publish'})


def publish_badges(request):
    """Publish - Marketplace badges."""
    return render(request, 'ecosystem/publish_badges.html',
                  {'page': 'badges', 'category': 'publish'})
