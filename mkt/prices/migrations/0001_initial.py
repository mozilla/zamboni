# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='AddonPaymentData',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('modified', models.DateTimeField(auto_now=True)),
                ('first_name', models.CharField(max_length=255, blank=True)),
                ('last_name', models.CharField(max_length=255, blank=True)),
                ('email', models.EmailField(max_length=75, blank=True)),
                ('full_name', models.CharField(max_length=255, blank=True)),
                ('business_name', models.CharField(max_length=255, blank=True)),
                ('country', models.CharField(max_length=64)),
                ('payerID', models.CharField(max_length=255, blank=True)),
                ('address_one', models.CharField(max_length=255)),
                ('address_two', models.CharField(max_length=255, blank=True)),
                ('post_code', models.CharField(max_length=128, blank=True)),
                ('city', models.CharField(max_length=128, blank=True)),
                ('state', models.CharField(max_length=64, blank=True)),
                ('phone', models.CharField(max_length=32, blank=True)),
            ],
            options={
                'db_table': 'addon_payment_data',
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='AddonPremium',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('modified', models.DateTimeField(auto_now=True)),
            ],
            options={
                'db_table': 'addons_premium',
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='AddonPurchase',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('modified', models.DateTimeField(auto_now=True)),
                ('type', models.PositiveIntegerField(default=1, db_index=True, choices=[(0, 'Voluntary'), (1, 'Purchase'), (2, 'Refund'), (3, 'Chargeback'), (99, 'Other')])),
                ('uuid', models.CharField(unique=True, max_length=255, db_index=True)),
            ],
            options={
                'db_table': 'addon_purchase',
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='Price',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('modified', models.DateTimeField(auto_now=True)),
                ('active', models.BooleanField(default=True, db_index=True)),
                ('name', models.CharField(max_length=4)),
                ('price', models.DecimalField(max_digits=10, decimal_places=2)),
                ('method', models.IntegerField(default=2, choices=[(0, b'operator'), (1, b'card'), (2, b'operator+card')])),
            ],
            options={
                'db_table': 'prices',
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='PriceCurrency',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('modified', models.DateTimeField(auto_now=True)),
                ('carrier', models.IntegerField(null=True, blank=True)),
                ('currency', models.CharField(max_length=10, choices=[(b'AED', 'United Arab Emirates Dirham'), (b'AFN', 'Afghanistan Afghani'), (b'ALL', 'Albania Lek'), (b'AMD', 'Armenia Dram'), (b'ANG', 'Netherlands Antilles Guilder'), (b'AOA', 'Angola Kwanza'), (b'ARS', 'Argentina Peso'), (b'AUD', 'Australia Dollar'), (b'AWG', 'Aruba Guilder'), (b'AZN', 'Azerbaijan New Manat'), (b'BAM', 'Bosnia and Herzegovina Convertible Marka'), (b'BBD', 'Barbados Dollar'), (b'BDT', 'Bangladesh Taka'), (b'BGN', 'Bulgaria Lev'), (b'BHD', 'Bahrain Dinar'), (b'BIF', 'Burundi Franc'), (b'BMD', 'Bermuda Dollar'), (b'BND', 'Brunei Darussalam Dollar'), (b'BOB', 'Bolivia Boliviano'), (b'BRL', 'Brazil Real'), (b'BSD', 'Bahamas Dollar'), (b'BTN', 'Bhutan Ngultrum'), (b'BWP', 'Botswana Pula'), (b'BYR', 'Belarus Ruble'), (b'BZD', 'Belize Dollar'), (b'CAD', 'Canada Dollar'), (b'CDF', 'Congo/Kinshasa Franc'), (b'CHF', 'Switzerland Franc'), (b'CLP', 'Chile Peso'), (b'CNY', 'China Yuan Renminbi'), (b'COP', 'Colombia Peso'), (b'CRC', 'Costa Rica Colon'), (b'CUC', 'Cuba Convertible Peso'), (b'CUP', 'Cuba Peso'), (b'CVE', 'Cape Verde Escudo'), (b'CZK', 'Czech Republic Koruna'), (b'DJF', 'Djibouti Franc'), (b'DKK', 'Denmark Krone'), (b'DOP', 'Dominican Republic Peso'), (b'DZD', 'Algeria Dinar'), (b'EGP', 'Egypt Pound'), (b'ERN', 'Eritrea Nakfa'), (b'ETB', 'Ethiopia Birr'), (b'EUR', 'Euro Member Countries'), (b'FJD', 'Fiji Dollar'), (b'FKP', 'Falkland Islands (Malvinas) Pound'), (b'GBP', 'United Kingdom Pound'), (b'GEL', 'Georgia Lari'), (b'GGP', 'Guernsey Pound'), (b'GHS', 'Ghana Cedi'), (b'GIP', 'Gibraltar Pound'), (b'GMD', 'Gambia Dalasi'), (b'GNF', 'Guinea Franc'), (b'GTQ', 'Guatemala Quetzal'), (b'GYD', 'Guyana Dollar'), (b'HKD', 'Hong Kong Dollar'), (b'HNL', 'Honduras Lempira'), (b'HRK', 'Croatia Kuna'), (b'HTG', 'Haiti Gourde'), (b'HUF', 'Hungary Forint'), (b'IDR', 'Indonesia Rupiah'), (b'ILS', 'Israel Shekel'), (b'IMP', 'Isle of Man Pound'), (b'INR', 'India Rupee'), (b'IQD', 'Iraq Dinar'), (b'IRR', 'Iran Rial'), (b'ISK', 'Iceland Krona'), (b'JEP', 'Jersey Pound'), (b'JMD', 'Jamaica Dollar'), (b'JOD', 'Jordan Dinar'), (b'JPY', 'Japan Yen'), (b'KES', 'Kenya Shilling'), (b'KGS', 'Kyrgyzstan Som'), (b'KHR', 'Cambodia Riel'), (b'KMF', 'Comoros Franc'), (b'KPW', 'Korea (North) Won'), (b'KRW', 'Korea (South) Won'), (b'KWD', 'Kuwait Dinar'), (b'KYD', 'Cayman Islands Dollar'), (b'KZT', 'Kazakhstan Tenge'), (b'LAK', 'Laos Kip'), (b'LBP', 'Lebanon Pound'), (b'LKR', 'Sri Lanka Rupee'), (b'LRD', 'Liberia Dollar'), (b'LSL', 'Lesotho Loti'), (b'LTL', 'Lithuania Litas'), (b'LVL', 'Latvia Lat'), (b'LYD', 'Libya Dinar'), (b'MAD', 'Morocco Dirham'), (b'MDL', 'Moldova Leu'), (b'MGA', 'Madagascar Ariary'), (b'MKD', 'Macedonia Denar'), (b'MMK', 'Myanmar (Burma) Kyat'), (b'MNT', 'Mongolia Tughrik'), (b'MOP', 'Macau Pataca'), (b'MRO', 'Mauritania Ouguiya'), (b'MUR', 'Mauritius Rupee'), (b'MVR', 'Maldives (Maldive Islands) Rufiyaa'), (b'MWK', 'Malawi Kwacha'), (b'MXN', 'Mexico Peso'), (b'MYR', 'Malaysia Ringgit'), (b'MZN', 'Mozambique Metical'), (b'NAD', 'Namibia Dollar'), (b'NGN', 'Nigeria Naira'), (b'NIO', 'Nicaragua Cordoba'), (b'NOK', 'Norway Krone'), (b'NPR', 'Nepal Rupee'), (b'NZD', 'New Zealand Dollar'), (b'OMR', 'Oman Rial'), (b'PAB', 'Panama Balboa'), (b'PEN', 'Peru Nuevo Sol'), (b'PGK', 'Papua New Guinea Kina'), (b'PHP', 'Philippines Peso'), (b'PKR', 'Pakistan Rupee'), (b'PLN', 'Poland Zloty'), (b'PYG', 'Paraguay Guarani'), (b'QAR', 'Qatar Riyal'), (b'RON', 'Romania New Leu'), (b'RSD', 'Serbia Dinar'), (b'RUB', 'Russia Ruble'), (b'RWF', 'Rwanda Franc'), (b'SAR', 'Saudi Arabia Riyal'), (b'SBD', 'Solomon Islands Dollar'), (b'SCR', 'Seychelles Rupee'), (b'SDG', 'Sudan Pound'), (b'SEK', 'Sweden Krona'), (b'SGD', 'Singapore Dollar'), (b'SHP', 'Saint Helena Pound'), (b'SLL', 'Sierra Leone Leone'), (b'SOS', 'Somalia Shilling'), (b'SPL', 'Seborga Luigino'), (b'SRD', 'Suriname Dollar'), (b'STD', 'S\xe3o Tom\xe9 and Pr\xedncipe Dobra'), (b'SVC', 'El Salvador Colon'), (b'SYP', 'Syria Pound'), (b'SZL', 'Swaziland Lilangeni'), (b'THB', 'Thailand Baht'), (b'TJS', 'Tajikistan Somoni'), (b'TMT', 'Turkmenistan Manat'), (b'TND', 'Tunisia Dinar'), (b'TOP', "Tonga Pa'anga"), (b'TRY', 'Turkey Lira'), (b'TTD', 'Trinidad and Tobago Dollar'), (b'TVD', 'Tuvalu Dollar'), (b'TWD', 'Taiwan New Dollar'), (b'TZS', 'Tanzania Shilling'), (b'UAH', 'Ukraine Hryvna'), (b'UGX', 'Uganda Shilling'), (b'USD', 'United States Dollar'), (b'UYU', 'Uruguay Peso'), (b'UZS', 'Uzbekistan Som'), (b'VEF', 'Venezuela Bolivar'), (b'VND', 'Viet Nam Dong'), (b'VUV', 'Vanuatu Vatu'), (b'WST', 'Samoa Tala'), (b'XAF', 'Communaut\xe9 Financi\xe8re Africaine (BEAC) CFA Franc BEAC'), (b'XCD', 'East Caribbean Dollar'), (b'XDR', 'International Monetary Fund (IMF) Special Drawing Rights'), (b'XOF', 'Communaut\xe9 Financi\xe8re Africaine (BCEAO) Franc'), (b'XPF', 'Comptoirs Fran\xe7ais du Pacifique (CFP) Franc'), (b'YER', 'Yemen Rial'), (b'ZAR', 'South Africa Rand'), (b'ZMW', 'Zambia Kwacha'), (b'ZWD', 'Zimbabwe Dollar')])),
                ('price', models.DecimalField(max_digits=10, decimal_places=2)),
                ('provider', models.IntegerField(blank=True, null=True, choices=[(0, b'paypal'), (1, b'bango'), (2, b'reference')])),
                ('method', models.IntegerField(default=2, choices=[(0, b'operator'), (1, b'card'), (2, b'operator+card')])),
                ('region', models.IntegerField(default=1)),
                ('dev', models.BooleanField(default=True)),
                ('paid', models.BooleanField(default=True)),
            ],
            options={
                'db_table': 'price_currency',
                'verbose_name': 'Price currencies',
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='Refund',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('modified', models.DateTimeField(auto_now=True)),
                ('status', models.PositiveIntegerField(default=0, db_index=True, choices=[(0, 'Pending'), (1, 'Approved'), (2, 'Approved Instantly'), (3, 'Declined'), (4, 'Failed')])),
                ('refund_reason', models.TextField(default=b'', blank=True)),
                ('rejection_reason', models.TextField(default=b'', blank=True)),
                ('requested', models.DateTimeField(null=True, db_index=True)),
                ('approved', models.DateTimeField(null=True, db_index=True)),
                ('declined', models.DateTimeField(null=True, db_index=True)),
            ],
            options={
                'db_table': 'refunds',
            },
            bases=(models.Model,),
        ),
    ]
