# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import uuidfield.fields


class Migration(migrations.Migration):

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='LangPack',
            fields=[
                ('created', models.DateTimeField(auto_now_add=True)),
                ('modified', models.DateTimeField(auto_now=True)),
                ('uuid', uuidfield.fields.UUIDField(primary_key=True, serialize=False, editable=False, max_length=32, blank=True, unique=True)),
                ('language', models.CharField(default=b'en-US', max_length=10, choices=[(b'el', '\u0395\u03bb\u03bb\u03b7\u03bd\u03b9\u03ba\u03ac'), (b'xh', 'isiXhosa'), (b'bn-BD', '\u09ac\u09be\u0982\u09b2\u09be (\u09ac\u09be\u0982\u09b2\u09be\u09a6\u09c7\u09b6)'), (b'af', 'Afrikaans'), (b'ee', 'E\u028be'), (b'bn-IN', '\u09ac\u09be\u0982\u09b2\u09be (\u09ad\u09be\u09b0\u09a4)'), (b'ca', 'Catal\xe0'), (b'en-US', 'English (US)'), (b'it', 'Italiano'), (b'cs', '\u010ce\u0161tina'), (b'cy', 'Cymraeg'), (b'ar', '\u0639\u0631\u0628\u064a'), (b'pt-BR', 'Portugu\xeas (do\xa0Brasil)'), (b'zu', 'isiZulu'), (b'eu', 'Euskara'), (b'sv-SE', 'Svenska'), (b'id', 'Bahasa Indonesia'), (b'es', 'Espa\xf1ol'), (b'ru', '\u0420\u0443\u0441\u0441\u043a\u0438\u0439'), (b'ha', 'Hausa'), (b'nl', 'Nederlands'), (b'zh-TW', '\u6b63\u9ad4\u4e2d\u6587 (\u7e41\u9ad4)'), (b'tr', 'T\xfcrk\xe7e'), (b'ga-IE', 'Gaeilge'), (b'zh-CN', '\u4e2d\u6587 (\u7b80\u4f53)'), (b'ig', 'Igbo'), (b'dsb', 'Dolnoserb\u0161\u0107ina'), (b'pl', 'Polski'), (b'hsb', 'Hornjoserbsce'), (b'fr', 'Fran\xe7ais'), (b'bg', '\u0411\u044a\u043b\u0433\u0430\u0440\u0441\u043a\u0438'), (b'yo', 'Yor\xf9b\xe1'), (b'wo', 'Wolof'), (b'de', 'Deutsch'), (b'hu', 'magyar'), (b'ff', 'Pulaar-Fulfulde'), (b'nb-NO', 'Norsk bokm\xe5l'), (b'da', 'Dansk'), (b'ja', '\u65e5\u672c\u8a9e'), (b'sr', '\u0421\u0440\u043f\u0441\u043a\u0438'), (b'sq', 'Shqip'), (b'ko', '\ud55c\uad6d\uc5b4'), (b'sk', 'sloven\u010dina'), (b'uk', '\u0423\u043a\u0440\u0430\u0457\u043d\u0441\u044c\u043a\u0430'), (b'sr-Latn', 'Srpski'), (b'sw', 'Kiswahili')])),
                ('fxos_version', models.CharField(default=b'', max_length=255)),
                ('version', models.CharField(default=b'', max_length=255)),
                ('manifest', models.TextField()),
                ('file_version', models.PositiveIntegerField(default=0)),
                ('active', models.BooleanField(default=False)),
            ],
            options={
                'ordering': ('language',),
            },
            bases=(models.Model,),
        ),
        migrations.AlterIndexTogether(
            name='langpack',
            index_together=set([('fxos_version', 'active', 'language')]),
        ),
    ]
