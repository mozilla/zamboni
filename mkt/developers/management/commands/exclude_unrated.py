import logging

from django.core.management.base import BaseCommand

import mkt
from mkt.webapps.models import Geodata, Webapp
from mkt.webapps.tasks import index_webapps


log = logging.getLogger('z.task')


class Command(BaseCommand):
    help = ('Exclude pre-IARC unrated public apps in Brazil/Germany.')

    def handle(self, *args, **options):

        ids_to_reindex = []
        apps = Webapp.objects.filter(
            status__in=(mkt.STATUS_PUBLIC, mkt.STATUS_APPROVED))

        for app in apps:
            save = False
            geodata, c = Geodata.objects.safer_get_or_create(webapp=app)

            # Germany.
            if (not app.content_ratings.filter(
                    ratings_body=mkt.ratingsbodies.USK.id).exists()):
                save = True
                geodata.region_de_iarc_exclude = True
                log.info('[App %s - %s] Excluded in region de'
                         % (app.pk, app.app_slug))

            # Brazil.
            if (not app.content_ratings.filter(
                    ratings_body=mkt.ratingsbodies.CLASSIND.id).exists()):
                save = True
                geodata.region_br_iarc_exclude = True
                log.info('[App %s - %s] Excluded in region br'
                         % (app.pk, app.app_slug))

            if save:
                ids_to_reindex.append(app.id)
                geodata.save()

        if ids_to_reindex:
            index_webapps(ids_to_reindex)
