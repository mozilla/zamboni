import csv
from optparse import make_option
from os.path import basename, splitext

from django.core.management.base import BaseCommand, CommandError
from django.core.validators import URLValidator, ValidationError
from django.db.transaction import atomic
from django.utils import translation

from mpconstants.mozilla_languages import LANGUAGES

from mkt.constants.base import STATUS_PUBLIC
from mkt.constants.categories import CATEGORY_CHOICES_DICT
from mkt.constants.regions import REGIONS_DICT
from mkt.tags.models import Tag
from mkt.translations.utils import to_language
from mkt.websites.models import Website
from mkt.websites.tasks import fetch_icon


class ParsingError(Exception):
    pass


class Command(BaseCommand):
    """
    Usage:

        python manage.py import_websites_from_csv <file>

    """
    help = u'Import Websites from a CSV file'
    args = u'<file> [--overwrite]'
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
        for keyword in set(keywords.split(',')):
            keyword = keyword.strip()
            if len(keyword) > max_len:
                raise ParsingError(
                    u'Website %s has a keyword which is too long: %s'
                    % (row['Unique Moz ID'], keyword))
            tag, _ = Tag.objects.get_or_create(tag_text=keyword)
            instance.keywords.add(tag)

    def set_url(self, instance, row):
        # Ultimately, we don't care whether the website has a mobile specific
        # URL, is responsive, etc: If it has a desktop-specific URL and a
        # mobile URL set, then set both accordingly, otherwise just set
        # url.
        desktop_url = self.clean_string(row['Desktop URL']).lower()
        mobile_url = self.clean_string(row['Mobile URL']).lower()
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
        if desktop_url and mobile_url:
            instance.url = desktop_url
            instance.mobile_url = mobile_url
        elif mobile_url:
            instance.url = mobile_url
        else:
            raise ParsingError(
                u'Website %s has no URL ?!' % row['Unique Moz ID'])

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

    def create_instances(self, data):
        created_instances = []
        created_count = 0
        for i, row in enumerate(data):
            if (i + 1) % 100 == 0:
                print 'Processing row %d... (%d websites created)' % (
                    i + 1, created_count)
            if self.limit and created_count >= self.limit:
                print 'Limit (%d) was hit, stopping the import' % self.limit
                break

            id_ = int(self.clean_string(row['Unique Moz ID']))
            try:
                website = Website.objects.get(moz_id=id_)
                if self.overwrite:
                    # Existing website and we were asked to overwrite: delete
                    # it!
                    website.delete()
                else:
                    # Existing website and we were not asked to overwrite: skip
                    # it!
                    continue

            except Website.DoesNotExist:
                pass

            with atomic():
                try:
                    website = Website(moz_id=id_, status=STATUS_PUBLIC)
                    self.set_default_locale(website, row)
                    self.set_automatic_properties(website, row)
                    self.set_categories(website, row)
                    self.set_preferred_regions(website, row)
                    self.set_url(website, row)
                    website.save()

                    # Keywords use a M2M, so do that once the website is saved.
                    self.set_tags(website, row)

                    # Launch task to fetch icon once we know everything is OK.
                    self.set_icon(website, row)

                    created_instances.append(website)
                    created_count += 1
                except ParsingError as e:
                    print e.message
        return created_count, created_instances

    def handle(self, *args, **kwargs):
        if len(args) != 1:
            self.print_help('manage.py', self.subcommand)
            return
        filename = args[0]
        self.overwrite = kwargs.get('overwrite', False)
        self.limit = kwargs.get('limit', None)

        with translation.override('en-US'):
            self.languages = dict(LANGUAGES).keys()
            self.reversed_languages = {v['English'].lower(): k for k, v
                                       in LANGUAGES.items()}
            self.categories = CATEGORY_CHOICES_DICT.keys()
            self.reversed_categories = {unicode(v).lower(): k for k, v
                                        in CATEGORY_CHOICES_DICT.items()}
        data = self.parse(filename)
        created_count, created_instances = self.create_instances(data)
        print 'Done, created %d websites.' % created_count

        # No need to manually call _send_tasks() even though we are in a
        # management command. The only tasks we are using are fetch_icon(),
        # for which we use original_apply_async() directly, and the indexation
        # task, which would be useless to fire since the fetch icon task will
        # trigger a save and a re-index anyway.
