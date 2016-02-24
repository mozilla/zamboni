# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('webapps', '0011_iarc_add_new_descriptors_and_interactives'),
    ]

    operations = [
        migrations.AddField(
            model_name='ratingdescriptors',
            name='has_generic_criminal_technique_instructions',
            field=models.BooleanField(default=False, help_text='Criminal Technique Instructions'),
        ),
        migrations.AddField(
            model_name='ratingdescriptors',
            name='has_generic_extreme_violence',
            field=models.BooleanField(default=False, help_text='Extreme Violence'),
        ),
        migrations.AddField(
            model_name='ratingdescriptors',
            name='has_generic_horror',
            field=models.BooleanField(default=False, help_text='Horror'),
        ),
        migrations.AddField(
            model_name='ratingdescriptors',
            name='has_generic_implied_violence',
            field=models.BooleanField(default=False, help_text='Implied Violence'),
        ),
        migrations.AddField(
            model_name='ratingdescriptors',
            name='has_generic_mild_swearing',
            field=models.BooleanField(default=False, help_text='Mild Swearing'),
        ),
        migrations.AddField(
            model_name='ratingdescriptors',
            name='has_generic_mild_violence',
            field=models.BooleanField(default=False, help_text='Mild Violence'),
        ),
        migrations.AddField(
            model_name='ratingdescriptors',
            name='has_generic_moderate_violence',
            field=models.BooleanField(default=False, help_text='Moderate Violence'),
        ),
        migrations.AddField(
            model_name='ratingdescriptors',
            name='has_generic_parental_guidance_recommended',
            field=models.BooleanField(default=False, help_text='Parental Guidance Recommended'),
        ),
        migrations.AddField(
            model_name='ratingdescriptors',
            name='has_generic_sexual_innuendo',
            field=models.BooleanField(default=False, help_text='Sexual Innuendo'),
        ),
        migrations.AddField(
            model_name='ratingdescriptors',
            name='has_generic_sexual_violence',
            field=models.BooleanField(default=False, help_text='Sexual Violence'),
        ),
        migrations.AddField(
            model_name='ratingdescriptors',
            name='has_generic_strong_language',
            field=models.BooleanField(default=False, help_text='Strong Language'),
        ),
        migrations.AddField(
            model_name='ratingdescriptors',
            name='has_generic_strong_violence',
            field=models.BooleanField(default=False, help_text='Strong Violence'),
        ),
        migrations.AddField(
            model_name='ratingdescriptors',
            name='has_generic_use_of_alcohol_and_tobacco',
            field=models.BooleanField(default=False, help_text='Use of Alcohol/Tobacco'),
        ),
    ]
