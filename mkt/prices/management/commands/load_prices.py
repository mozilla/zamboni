from optparse import make_option

import requests

from django.core.management.base import BaseCommand

from mkt.prices.models import Price, PriceCurrency


domains = {
    'prod': 'https://marketplace.firefox.com',
    'stage': 'https://marketplace.allizom.org',
    'dev': 'https://marketplace-dev.allizom.org',
    'altpay': 'https://payments-alt.allizom.org'
}

endpoint = '/api/v1/webpay/prices/'


class Command(BaseCommand):
    help = """
    Load prices and pricecurrencies from the specified marketplace.
    Defaults to prod.
    """
    option_list = BaseCommand.option_list + (
        make_option('--prod',
                    action='store_const',
                    const=domains['prod'],
                    dest='domain',
                    help='Use prod as source of data.'),
        make_option('--stage',
                    action='store_const',
                    const=domains['stage'],
                    dest='domain',
                    help='Use stage as source of data.'),
        make_option('--dev',
                    action='store_const',
                    const=domains['dev'],
                    dest='domain',
                    default=domains['dev'],
                    help='Use use dev as source of data.'),
        make_option('--altpay',
                    action='store_const',
                    const=domains['altpay'],
                    dest='domain',
                    help='Use use payments-alt as source of data.'),
        make_option('--delete',
                    action='store_true',
                    dest='delete',
                    default=False,
                    help='Start by deleting all prices.'),
        make_option('--noop',
                    action='store_true',
                    dest='noop',
                    default=False,
                    help=('Show data that would be added, '
                          'but do not create objects.')),
    )

    def handle(self, *args, **kw):
        print 'Loading prices from: {0}'.format(kw['domain'])
        data = requests.get(kw['domain'] + endpoint).json()

        if kw['delete']:
            if kw['noop']:
                print 'Not actually deleting everything :)'
            else:
                Price.objects.all().delete()
                PriceCurrency.objects.all().delete()

        for p in data['objects']:
            params = dict(name=p['name'].split(' ')[-1],
                          active=p['active'],
                          method=p['method'],
                          price=p['price'])
            print p['price']
            pr = None
            if Price.objects.filter(**params).count():
                pr = Price.objects.filter(**params).get()
                print '---- Skipping existing price:', pr
            else:
                print '**** This price needs to be added'
                if not kw['noop']:
                    pr = Price.objects.create(**params)
            if pr:
                for pc in p['prices']:
                    cur_params = dict(currency=pc['currency'],
                                      carrier=pc['carrier'],
                                      price=pc['price'],
                                      paid=pc['paid'],
                                      tier=pc['tier'],
                                      dev=pc['dev'],
                                      provider=pc['provider'],
                                      method=pc['method'],
                                      region=pc['region'])
                    if pr.pricecurrency_set.filter(**cur_params).count():
                        print '---- Skipping currency', pc['currency']
                    else:
                        print '**** Currency needs adding', pc['currency']
                        if not kw['noop']:
                            pr.pricecurrency_set.create(**cur_params)
