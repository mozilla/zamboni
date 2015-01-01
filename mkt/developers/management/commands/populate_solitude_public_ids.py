from optparse import make_option

from django.core.exceptions import ObjectDoesNotExist, MultipleObjectsReturned
from django.core.management.base import BaseCommand

from mkt.developers.providers import Provider
from mkt.developers.utils import uri_to_pk
from mkt.site.utils import chunked
from mkt.webapps.models import Webapp
from mkt.webpay.utils import make_external_id


def get_generic_product(app):
    if app.app_payment_accounts.exists():
        for account in app.app_payment_accounts.all():
            print (
                'Looking up public_id for app '
                '{app} using account {account}'
            ).format(
                app=app,
                account=account.payment_account.seller_uri)
            try:
                generic_product = Provider.generic.product.get_object(
                    seller=uri_to_pk(account.payment_account.seller_uri),
                    external_id=make_external_id(app))
                print (
                    'Found generic product {product} for '
                    'app {app} using account {account}'
                ).format(
                    product=generic_product['public_id'],
                    app=app,
                    account=account)
                return generic_product
            except ObjectDoesNotExist:
                pass
            except MultipleObjectsReturned:
                print 'Found multiple generic products for app {app}'.format(
                    app=app)
        print 'Unable to find a generic product for app {app}'.format(app=app)


class Command(BaseCommand):
    help = ('Look up and store the Generic Product public_ids'
            ' for existing webapps with configured payment accounts.')
    option_list = BaseCommand.option_list + (
        make_option(
            '--dry-run',
            default=False,
            action='store_true',
            dest='dry_run',
            help='Look up the public_ids in Solitude without saving'),)

    def handle(self, *args, **options):
        webapps = (Webapp.objects.filter(app_payment_accounts__isnull=False)
                                 .no_transforms()
                                 .select_related('app_payment_accounts'))
        for chunk in chunked(webapps, 50):
            for app in chunk:
                generic_product = get_generic_product(app)
                if not generic_product:
                    continue
                print 'Found public_id', generic_product['public_id']

                if not options['dry_run']:
                    print 'Saving app', app
                    app.solitude_public_id = generic_product['public_id']
                    app.save()
