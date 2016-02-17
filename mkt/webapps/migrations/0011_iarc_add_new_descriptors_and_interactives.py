# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('webapps', '0010_auto_20160216_1705'),
    ]

    operations = [
        migrations.AddField(
            model_name='ratingdescriptors',
            name='has_esrb_diverse_content_discretion_advised',
            field=models.BooleanField(default=False, help_text='Diverse Content: Discretion Advised'),
        ),
        migrations.AddField(
            model_name='ratingdescriptors',
            name='has_pegi_criminal_technique_instructions',
            field=models.BooleanField(default=False, help_text='Criminal Technique Instructions'),
        ),
        migrations.AddField(
            model_name='ratingdescriptors',
            name='has_pegi_extreme_violence',
            field=models.BooleanField(default=False, help_text='Extreme Violence'),
        ),
        migrations.AddField(
            model_name='ratingdescriptors',
            name='has_pegi_implied_violence',
            field=models.BooleanField(default=False, help_text='Implied Violence'),
        ),
        migrations.AddField(
            model_name='ratingdescriptors',
            name='has_pegi_mild_swearing',
            field=models.BooleanField(default=False, help_text='Mild Swearing'),
        ),
        migrations.AddField(
            model_name='ratingdescriptors',
            name='has_pegi_mild_violence',
            field=models.BooleanField(default=False, help_text='Mild Violence'),
        ),
        migrations.AddField(
            model_name='ratingdescriptors',
            name='has_pegi_moderate_violence',
            field=models.BooleanField(default=False, help_text='Moderate Violence'),
        ),
        migrations.AddField(
            model_name='ratingdescriptors',
            name='has_pegi_parental_guidance_recommended',
            field=models.BooleanField(default=False, help_text='Parental Guidance Recommended'),
        ),
        migrations.AddField(
            model_name='ratingdescriptors',
            name='has_pegi_sexual_innuendo',
            field=models.BooleanField(default=False, help_text='Sexual Innuendo'),
        ),
        migrations.AddField(
            model_name='ratingdescriptors',
            name='has_pegi_sexual_violence',
            field=models.BooleanField(default=False, help_text='Sexual Violence'),
        ),
        migrations.AddField(
            model_name='ratingdescriptors',
            name='has_pegi_strong_language',
            field=models.BooleanField(default=False, help_text='Strong Language'),
        ),
        migrations.AddField(
            model_name='ratingdescriptors',
            name='has_pegi_strong_violence',
            field=models.BooleanField(default=False, help_text='Strong Violence'),
        ),
        migrations.AddField(
            model_name='ratingdescriptors',
            name='has_pegi_use_of_alcohol_and_tobacco',
            field=models.BooleanField(default=False, help_text='Use of Alcohol/Tobacco'),
        ),
        migrations.AddField(
            model_name='ratingdescriptors',
            name='has_usk_shop_streaming_service',
            field=models.BooleanField(default=False, help_text='Shop/ Streamingdienst \u2013 dynamische  Inhalte'),
        ),
        migrations.AddField(
            model_name='ratinginteractives',
            name='has_unrestricted_internet',
            field=models.BooleanField(default=False, help_text=b'Unrestricted Internet'),
        ),
    ]
