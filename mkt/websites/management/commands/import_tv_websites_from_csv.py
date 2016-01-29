import csv
from os.path import basename, splitext

from django.core.management.base import BaseCommand, CommandError
from django.core.validators import URLValidator, ValidationError
from django.db.transaction import atomic
from django.utils import translation

from mpconstants.mozilla_languages import LANGUAGES

from mkt.constants.applications import DEVICE_TV
from mkt.constants.base import STATUS_PUBLIC
from mkt.constants.categories import CATEGORY_CHOICES_DICT
from mkt.tags.models import Tag
from mkt.websites.models import Website
from mkt.websites.tasks import fetch_icon, fetch_promo_imgs


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
            'name': 'App/Service name',
            'description': 'A short description of the app, 430 char max.',
        }

        with translation.override(instance.default_locale):
            for prop, column in mapping.items():
                setattr(instance, prop, self.clean_string(row[column]))

            if not instance.name:
                raise ParsingError(
                    u'Website name is empty ! ' + str(row))

    def set_default_locale(self, instance, row):
        instance.default_locale = 'en-US'

    def set_categories(self, instance, row):
        cat = self.clean_string(row['Category ']).lower()
        if cat == 'science & tech':
            cat = 'science-tech'
        elif cat == 'comics':
            cat = 'books-comics'
        elif cat == 'health & fitness':
            cat = 'health-fitness'
        elif cat == 'navigation':
            cat = 'maps-navigation'
        if cat not in self.categories:
            cat = self.reversed_categories.get(cat)
            if cat is None:
                raise ParsingError(
                    u'Website %s has unknown category set: %s'
                    % (row['App/Service name'], row['Category ']))
        instance.categories = [cat]

    def set_tags(self, instance, row):
        keywords = self.clean_string(row['Keywords'].lower())
        max_len = Tag._meta.get_field('tag_text').max_length
        row_keywords = set(keywords.split(','))
        for keyword in row_keywords:
            keyword = keyword.strip()
            if len(keyword) > max_len:
                raise ParsingError(
                    u'Website %s has a keyword which is too long: %s'
                    % (row['App/Service name'], keyword))
            tag, _ = Tag.objects.get_or_create(tag_text=keyword)
            instance.keywords.add(tag)

    def clean_url(self, row):
        tv_url = self.clean_string(row['URL/Link']).lower()
        try:
            self.validate_url(tv_url)
        except ValidationError:
            raise ParsingError(
                u'Website %s has invalid TV URL %s'
                % (row['App/Service name'], tv_url))
        return tv_url

    def set_icon(self, instance, row):
        icon_url = self.clean_string(
            row['An icon, 336x336px image in 24-bit PNG'])
        try:
            # Lots of rows with no icons or just 'Default' in the data, so
            # ignore the issue and don't report it.
            if icon_url:
                self.validate_url(icon_url)
                # Use original_apply_async instead of using the
                # post_request_task mechanism. See comment below at the end of
                # the file for an explanation.
                fetch_icon.original_apply_async(args=(instance.pk, icon_url),
                                                kwargs={'sizes': (336, 128)})
            else:
                raise ValidationError('Empty Icon URL')
        except ValidationError:
            instance.icon_type = ''

    def set_promo_img(self, instance, row):
        img_url = self.clean_string(row['A screenshot, 575 x 325 .pngREM'])
        try:
            if img_url:
                self.validate_url(img_url)
                fetch_promo_imgs.original_apply_async(args=(instance.pk,
                                                            img_url))
            else:
                raise ValidationError('Empty Screenshot URL')
        except ValidationError:
            instance.icon_type = ''

    def parse(self, filename):
        try:
            return csv.DictReader(open(filename))
        except IOError as err:
            raise CommandError(err)

    def create_instances(self, data):
        created_count = 0
        for i, row in enumerate(data):
            if (i + 1) % 100 == 0:
                print 'Processing row %d... (%d websites created)' % (
                    i + 1, created_count)

            with atomic():
                try:
                    url = self.clean_url(row)
                    website, created = Website.objects.get_or_create(
                        status=STATUS_PUBLIC,
                        devices=[DEVICE_TV.id],
                        url=url,
                        tv_url=url)
                    self.set_default_locale(website, row)
                    self.set_automatic_properties(website, row)
                    self.set_categories(website, row)
                    website.save()

                    # Keywords use a M2M, so do that once the website is saved.
                    self.set_tags(website, row)

                    # Launch task to fetch icon/screenshot once we know
                    # everything is OK.
                    self.set_icon(website, row)
                    self.set_promo_img(website, row)

                    created_count += created
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

        with translation.override('en-US'):
            self.languages = dict(LANGUAGES).keys()
            self.reversed_languages = {v['English'].lower(): k for k, v
                                       in LANGUAGES.items()}
            self.categories = CATEGORY_CHOICES_DICT.keys()
            self.reversed_categories = {unicode(v).lower(): k for k, v
                                        in CATEGORY_CHOICES_DICT.items()}
        data = list(self.parse(filename))
        # Skip first line, since it's explanatory, not a site.
        created_count = self.create_instances(data[1:])
        print 'Import phase done, created %d websites.' % created_count

        # No need to manually call _send_tasks() even though we are in a
        # management command. The only tasks we are using are fetch_icon() and
        # fetch_promo_imgs(), for which we use original_apply_async() directly,
        # and the indexation task, which would be useless to fire since the
        # fetch icon task will trigger a save and a re-index anyway. Plus, we
        # won't have many sites so it's probably simpler to trigger a full
        # reindex.
