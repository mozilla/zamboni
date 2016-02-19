import collections
import csv
import random
from operator import itemgetter
from optparse import make_option
from os.path import basename, splitext

from django.core.management.base import BaseCommand, CommandError
from django.core.validators import URLValidator, ValidationError
from django.db.transaction import atomic
from django.utils import translation

from mpconstants.mozilla_languages import LANGUAGES

from mkt.constants.applications import (DEVICE_GAIA, DEVICE_MOBILE,
                                        DEVICE_TABLET, DEVICE_TV)
from mkt.constants.base import STATUS_PUBLIC
from mkt.constants.categories import CATEGORY_CHOICES_DICT
from mkt.constants.regions import REGIONS_CHOICES_ID_DICT, REGIONS_DICT
from mkt.tags.models import Tag
from mkt.translations.utils import to_language
from mkt.webapps.models import Installs, Webapp
from mkt.websites.models import Website, WebsitePopularity
from mkt.websites.tasks import fetch_icon


class ParsingError(Exception):
    pass


class Command(BaseCommand):
    """
    Usage:

        python manage.py import_websites_from_csv <file>

    """
    help = u'Import Websites from a CSV file'
    args = u'<file> [--overwrite] [--limit] [--set-popularity]'
    subcommand = splitext(basename(__file__))[0]

    option_list = BaseCommand.option_list + (
        make_option(
            '--overwrite',
            action='store_true',
            dest='overwrite',
            default=False,
            help='Overwrite existing Website with the same Unique Moz ID. '
                 'Otherwise, any row with an existing Unique Moz ID in the '
                 'database will be skipped.',
        ),
        make_option(
            '--limit',
            action='store',
            type=int,
            dest='limit',
            default=None,
            help='Maximum number of sites to import. Skipped websites do not '
                 'count towards the limit',
        ),
        make_option(
            '--set-popularity',
            action='store_true',
            dest='set_popularity',
            default=False,
            help='Set a (fake) initial popularity and last updated date '
                 'using the Rank and Unique Moz ID columns in the CSV.',
        ),
    )

    def clean_string(self, s):
        return s.strip().decode('utf-8')

    def validate_url(self, url):
        if url:
            URLValidator()(url)

    def set_automatic_properties(self, instance, row):
        """
        Set properties automatically from the included mapping. Since it sets
        translated fields, it's important to set default_locale on the instance
        first, it's then used by this method to set the correct locale for the
        fields.
        """
        mapping = {
            # property on Website : field name in csv.
            'short_name': 'Short Name (enter text up to 12 characters)',
            'name': 'Display Title',
            'title': 'Long Name to Use (type in if no)',
            'description': 'Description from site',
        }

        with translation.override(instance.default_locale):
            for prop, column in mapping.items():
                setattr(instance, prop, self.clean_string(row[column]))

            if not instance.name:
                raise ParsingError(
                    u'Website %s name is empty !' % (row['Unique Moz ID']))

    def set_default_locale(self, instance, row):
        lang = to_language(self.clean_string(row['Language of Meta Data']))
        if not lang or lang == 'english':
            # Exception because 'en-US' is set as 'English (US)'.
            lang = 'en-US'
        elif lang == 'chinese':
            # Consider 'chinese' without more information as simplified
            # chinese, zh-CN.
            lang = 'zh-CN'
        elif lang == 'portuguese':
            # We don't support pt-PT in Marketplace, use pt-BR.
            lang = 'pt-BR'
        if lang not in self.languages:
            lang = self.reversed_languages.get(lang)
            if lang is None:
                raise ParsingError(
                    u'Website %s has unknown language set for its metadata: %s'
                    % (row['Unique Moz ID'], row['Language of Meta Data']))
        instance.default_locale = lang

    def set_categories(self, instance, row):
        cat = self.clean_string(row['Marketplace Category']).lower()
        if cat == 'science & tech':
            cat = 'science-tech'
        elif cat == 'comics':
            cat = 'books-comics'
        elif cat == 'fitness':
            cat = 'health-fitness'
        elif cat == 'navigation':
            cat = 'maps-navigation'
        if cat not in self.categories:
            cat = self.reversed_categories.get(cat)
            if cat is None:
                raise ParsingError(
                    u'Website %s has unknown category set: %s'
                    % (row['Unique Moz ID'], row['Marketplace Category']))
        instance.categories = [cat]

    def set_preferred_regions(self, instance, row):
        # For each region, find the region object, add the id to the list,
        # store it. Warn about unknown regions.
        regions_slugs = self.clean_string(row['List of Countries']).split(',')
        preferred_regions = []
        for region in regions_slugs:
            if region == 'gb':
                region = 'uk'
            elif region == 'wo':
                region = 'restofworld'
            try:
                preferred_regions.append(REGIONS_DICT[region].id)
            except KeyError:
                raise ParsingError(
                    u'Website %s has unknown country: %s'
                    % (row['Unique Moz ID'], region))
        instance.preferred_regions = preferred_regions

    def set_tags(self, instance, row):
        keywords = self.clean_string(row['Keywords to use'].lower())
        if keywords.startswith('http'):
            raise ParsingError(
                u'Website %s has invalid keywords: %s'
                % (row['Unique Moz ID'], keywords))
        max_len = Tag._meta.get_field('tag_text').max_length
        row_keywords = set(keywords.split(','))
        if row['TV Featured']:
            row_keywords.add('featured-tv')
        for keyword in row_keywords:
            keyword = keyword.strip()
            if len(keyword) > max_len:
                raise ParsingError(
                    u'Website %s has a keyword which is too long: %s'
                    % (row['Unique Moz ID'], keyword))
            tag, _ = Tag.objects.get_or_create(tag_text=keyword)
            instance.keywords.add(tag)

    def set_url(self, instance, row):
        # 'url' field will be set to a device-specific url in priority order
        # 'desktop', 'mobile', 'tv'.
        desktop_url = self.clean_string(row['Desktop URL']).lower()
        mobile_url = self.clean_string(row['Mobile URL']).lower()
        tv_url = self.clean_string(row['TV URL']).lower()
        try:
            self.validate_url(desktop_url)
        except ValidationError:
            raise ParsingError(
                u'Website %s has invalid Desktop URL %s'
                % (row['Unique Moz ID'], desktop_url))
        try:
            self.validate_url(mobile_url)
        except ValidationError:
            raise ParsingError(
                u'Website %s has invalid Mobile URL %s'
                % (row['Unique Moz ID'], mobile_url))
        try:
            self.validate_url(tv_url)
        except ValidationError:
            raise ParsingError(
                u'Website %s has invalid TV URL %s'
                % (row['Unique Moz ID'], tv_url))

        if not any([desktop_url, mobile_url, tv_url]):
            raise ParsingError(
                u'Website %s has no URL ?!' % row['Unique Moz ID'])

        instance.mobile_url = mobile_url
        instance.tv_url = tv_url

        if desktop_url:
            instance.url = desktop_url
        elif mobile_url:
            instance.url = mobile_url
        elif tv_url:
            instance.url = tv_url

    def set_icon(self, instance, row):
        icon_url = self.clean_string(row['Icon url'])
        try:
            # Lots of rows with no icons or just 'Default' in the data, so
            # ignore the issue and don't report it.
            if icon_url:
                self.validate_url(icon_url)
                # Use original_apply_async instead of using the
                # post_request_task mechanism. See comment below at the end of
                # the file for an explanation.
                fetch_icon.original_apply_async(args=(instance.pk, icon_url))
            else:
                raise ValidationError('Empty Icon URL')
        except ValidationError:
            instance.icon_type = ''

    def parse(self, filename):
        try:
            return csv.DictReader(open(filename))
        except IOError as err:
            raise CommandError(err)

    def assign_popularity(self):
        print 'Setting regional popularity values...'
        for region in self.ranking_per_region.keys():
            websites_len = len(self.ranking_per_region[region])
            print u'Setting regional popularity for %d site(s) in %s' % (
                websites_len, unicode(REGIONS_CHOICES_ID_DICT[region].name))
            # Sort sites by rank in that region.
            websites = sorted(self.ranking_per_region[region],
                              key=itemgetter(1), reverse=True)
            # Take the same number of popularity values for apps in that
            # region.
            apps_popularity = (Installs.objects.filter(region=region)
                                       .values_list('value', flat=True)
                                       .order_by('-value')[:websites_len])

            for i, app_popularity_value in enumerate(apps_popularity):
                # Steal popularity value, minus one just to get a chance to end
                # up with a more stable ordering (no equal values).
                pk = websites[i][0]
                popularity, created = WebsitePopularity.objects.get_or_create(
                    website_id=pk, region=region)
                popularity.update(value=app_popularity_value - 1)
        print 'Setting global popularity values...'
        GLOBAL_REGION = 0
        for pk in self.websites:
            values = list(WebsitePopularity.objects
                                           .filter(website=pk)
                                           .exclude(region=GLOBAL_REGION)
                                           .values_list('value', flat=True))
            popularity, created = WebsitePopularity.objects.get_or_create(
                website_id=pk, region=GLOBAL_REGION)
            popularity.update(value=sum(values))

    def assign_last_updated(self):
        print 'Setting last updated dates...'
        # To make new and popular different, assign a random value for
        # last_updated stolen from the last x apps, where x is twice the number
        # of websites.
        desired_len = len(self.websites) * 2
        last_updated_dates = list(
            Webapp.objects
                  .exclude(last_updated=None)
                  .values_list('last_updated', flat=True)
                  .order_by('-last_updated')[:desired_len])
        if len(last_updated_dates) < desired_len:
            raise CommandError('Not enough apps with a last_updated set in the'
                               ' database to continue!')
            return
        random.shuffle(last_updated_dates)
        for pk in self.websites:
            (Website.objects.filter(pk=pk)
                            .update(last_updated=last_updated_dates.pop()))

    def remember_website_ranking(self, instance, rank):
        for region in instance.preferred_regions:
            self.ranking_per_region[region].append((instance.pk, rank))
        self.websites.append(instance.pk)

    def create_instances(self, data):
        created_count = 0
        for i, row in enumerate(data):
            if (i + 1) % 100 == 0:
                print 'Processing row %d... (%d websites created)' % (
                    i + 1, created_count)
            if self.limit and created_count >= self.limit:
                print 'Limit (%d) was hit, stopping the import' % self.limit
                break

            id_ = int(self.clean_string(row['Unique Moz ID']))
            rank = int(self.clean_string(row['Rank']))
            try:
                website = Website.objects.get(moz_id=id_)
                if self.overwrite:
                    # Existing website and we were asked to overwrite: delete
                    # it!
                    website.delete()
                else:
                    # Existing website and we were not asked to overwrite: skip
                    # it, storing its ranking first to set popularity later.
                    if self.set_popularity:
                        self.remember_website_ranking(website, rank)
                    continue

            except Website.DoesNotExist:
                pass

            with atomic():
                try:
                    devices = []
                    if row['Mobile URL']:
                        devices += [DEVICE_GAIA.id, DEVICE_MOBILE.id,
                                    DEVICE_TABLET.id]
                    if row['TV URL']:
                        devices.append(DEVICE_TV.id)
                    website = Website(moz_id=id_, status=STATUS_PUBLIC,
                                      devices=devices)
                    self.set_default_locale(website, row)
                    self.set_automatic_properties(website, row)
                    self.set_categories(website, row)
                    self.set_preferred_regions(website, row)
                    self.set_url(website, row)
                    website.save()

                    if self.set_popularity:
                        # Remember ranking to set popularity later.
                        self.remember_website_ranking(website, rank)

                    # Keywords use a M2M, so do that once the website is saved.
                    self.set_tags(website, row)

                    # Launch task to fetch icon once we know everything is OK.
                    self.set_icon(website, row)

                    created_count += 1
                except ParsingError as e:
                    print e.message
        return created_count

    def handle(self, *args, **kwargs):
        if len(args) != 1:
            self.print_help('manage.py', self.subcommand)
            return
        filename = args[0]
        self.overwrite = kwargs.get('overwrite', False)
        self.limit = kwargs.get('limit', None)
        self.set_popularity = kwargs.get('set_popularity', False)

        if self.set_popularity:
            if self.limit:
                raise CommandError(
                    'Can not use --set_popularity with --limit, the full data '
                    'set is needed to set popularity, aborting.')
            self.websites = []
            self.ranking_per_region = collections.defaultdict(list)

        with translation.override('en-US'):
            self.languages = dict(LANGUAGES).keys()
            self.reversed_languages = {v['English'].lower(): k for k, v
                                       in LANGUAGES.items()}
            self.categories = CATEGORY_CHOICES_DICT.keys()
            self.reversed_categories = {unicode(v).lower(): k for k, v
                                        in CATEGORY_CHOICES_DICT.items()}
        data = self.parse(filename)
        created_count = self.create_instances(data)
        print 'Import phase done, created %d websites.' % created_count

        if self.set_popularity:
            self.assign_popularity()
            self.assign_last_updated()
