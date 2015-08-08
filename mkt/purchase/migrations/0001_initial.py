# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Contribution',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('modified', models.DateTimeField(auto_now=True)),
                ('amount', models.DecimalField(null=True, max_digits=9, decimal_places=2, blank=True)),
                ('currency', models.CharField(default=b'USD', max_length=3, choices=[(b'AUD', 'Australia Dollar'), (b'BRL', 'Brazil Real'), (b'CAD', 'Canada Dollar'), (b'CHF', 'Switzerland Franc'), (b'CZK', 'Czech Republic Koruna'), (b'DKK', 'Denmark Krone'), (b'EUR', 'Euro Member Countries'), (b'GBP', 'United Kingdom Pound'), (b'HKD', 'Hong Kong Dollar'), (b'HUF', 'Hungary Forint'), (b'ILS', 'Israel Shekel'), (b'JPY', 'Japan Yen'), (b'MXN', 'Mexico Peso'), (b'MYR', 'Malaysia Ringgit'), (b'NOK', 'Norway Krone'), (b'NZD', 'New Zealand Dollar'), (b'PHP', 'Philippines Peso'), (b'PLN', 'Poland Zloty'), (b'SEK', 'Sweden Krona'), (b'SGD', 'Singapore Dollar'), (b'THB', 'Thailand Baht'), (b'TWD', 'Taiwan New Dollar'), (b'USD', 'United States Dollar')])),
                ('source', models.CharField(max_length=255, null=True)),
                ('source_locale', models.CharField(max_length=10, null=True)),
                ('uuid', models.CharField(max_length=255, null=True, db_index=True)),
                ('comment', models.CharField(max_length=255)),
                ('transaction_id', models.CharField(max_length=255, null=True, db_index=True)),
                ('paykey', models.CharField(max_length=255, null=True)),
                ('type', models.PositiveIntegerField(default=0, db_index=True, choices=[(0, 'Voluntary'), (1, 'Purchase'), (2, 'Refund'), (3, 'Chargeback'), (99, 'Other')])),
            ],
            options={
                'db_table': 'stats_contributions',
            },
            bases=(models.Model,),
        ),
    ]
