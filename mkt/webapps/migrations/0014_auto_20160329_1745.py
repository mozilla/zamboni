# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('webapps', '0013_disable_unsupported_apps'),
    ]

    operations = [
        migrations.AlterField(
            model_name='ratingdescriptors',
            name='has_classind_criminal_acts',
            field=models.BooleanField(default=False, help_text='Atos criminosos'),
        ),
        migrations.AlterField(
            model_name='ratingdescriptors',
            name='has_classind_drugs_illegal',
            field=models.BooleanField(default=False, help_text='Drogas il\xedcitas'),
        ),
        migrations.AlterField(
            model_name='ratingdescriptors',
            name='has_classind_drugs_legal',
            field=models.BooleanField(default=False, help_text='Drogas l\xedcitas'),
        ),
        migrations.AlterField(
            model_name='ratingdescriptors',
            name='has_classind_lang',
            field=models.BooleanField(default=False, help_text='Linguagem impr\xf3pria'),
        ),
        migrations.AlterField(
            model_name='ratingdescriptors',
            name='has_classind_sex_content',
            field=models.BooleanField(default=False, help_text='Conte\xfado sexual'),
        ),
        migrations.AlterField(
            model_name='ratingdescriptors',
            name='has_classind_sex_explicit',
            field=models.BooleanField(default=False, help_text='Sexo expl\xedcito'),
        ),
        migrations.AlterField(
            model_name='ratingdescriptors',
            name='has_classind_violence_extreme',
            field=models.BooleanField(default=False, help_text='Viol\xeancia extrema'),
        ),
        migrations.AlterField(
            model_name='ratingdescriptors',
            name='has_usk_horror',
            field=models.BooleanField(default=False, help_text='Schock- und/oder Horrorelemente'),
        ),
        migrations.AlterField(
            model_name='ratingdescriptors',
            name='has_usk_lang',
            field=models.BooleanField(default=False, help_text='Derbe Sprache'),
        ),
        migrations.AlterField(
            model_name='ratingdescriptors',
            name='has_usk_sex_content',
            field=models.BooleanField(default=False, help_text='Sex/Erotik'),
        ),
        migrations.AlterField(
            model_name='ratingdescriptors',
            name='has_usk_sex_violence_ref',
            field=models.BooleanField(default=False, help_text='Verweise auf sexuelle Gewalt'),
        ),
        migrations.AlterField(
            model_name='ratingdescriptors',
            name='has_usk_some_swearing',
            field=models.BooleanField(default=False, help_text='Gelegentliche Verwendung von Kraftausdr\xfccken'),
        ),
    ]
