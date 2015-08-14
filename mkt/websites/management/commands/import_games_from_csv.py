# docs.google.com/spreadsheets/d/
# 1tShUCIR3tilh2WGeoXQMjy4ExGf94_7MilZqorjPfrM/edit#gid=0
import csv
from os.path import basename, splitext

from django.core.management.base import BaseCommand, CommandError
from django.core.validators import URLValidator, ValidationError
from django.db.transaction import atomic

from mkt.constants.applications import DEVICE_DESKTOP
from mkt.constants.base import STATUS_PUBLIC
from mkt.tags.models import Tag
from mkt.websites.indexers import WebsiteIndexer
from mkt.websites.models import Website
from mkt.websites.tasks import fetch_icon, fetch_promo_imgs


class ParsingError(Exception):
    pass


class Command(BaseCommand):
    """
    Usage:

        python manage.py import_games_from_csv <file>

    Columns are:
        - Name
        - URL
        - Description
        - Icon URL: direct link to image.
        - Promo Image URL: direct link to image, 1050x300px minimum.
    """
    help = u'Import Desktop Games from a CSV file'
    args = u'<file>'
    subcommand = splitext(basename(__file__))[0]

    def clean_string(self, s):
        return s.strip().decode('utf-8')

    def validate_url(self, url):
        if url:
            URLValidator()(url)

    def set_tags(self, instance, row):
        keywords = [
            'featured-game',
            'featured-game-' + self.clean_string(row['Category']).lower()]
        for keyword in keywords:
            tag, _ = Tag.objects.get_or_create(tag_text=keyword)
            instance.keywords.add(tag)

    def set_url(self, instance, row):
        url = self.clean_string(row['URL']).lower()
        try:
            self.validate_url(url)
        except ValidationError:
            raise ParsingError(u'%s has invalid URL %s' % (row['Name'], url))
        instance.url = url

    def set_icon(self, instance, row):
        icon_url = self.clean_string(row['Icon URL'])
        if icon_url:
            self.validate_url(icon_url)
            icon = fetch_icon(instance.pk, icon_url)
            if not icon:
                raise ValidationError('Icon for %s could not be fetched.' %
                                      instance.name)
        else:
            raise ParsingError(u'%s has no icon' % (row['Name'],))

    def set_promo_imgs(self, instance, row):
        promo_img_url = self.clean_string(row['Promo Img URL'])
        if promo_img_url:
            self.validate_url(promo_img_url)
            promo_img = fetch_promo_imgs(instance.pk, promo_img_url)
            if not promo_img:
                raise ValidationError('Promo img for %s failed fetching.' %
                                      instance.name)
        else:
            raise ParsingError(u'%s has no icon' % (row['Name'],))

    def parse(self, filename):
        try:
            return csv.DictReader(open(filename))
        except IOError as err:
            raise CommandError(err)

    def create_instances(self, data):
        created_count = 0
        for i, row in enumerate(data):
            name = self.clean_string(row['Name'])
            if not name:
                continue

            try:
                url = self.clean_string(row['URL'])
                website = Website.objects.get(url=url)
                print 'Game with URL %s already exists. Continuing.' % url
                continue
            except Website.DoesNotExist:
                pass

            with atomic():
                try:
                    website = Website(
                        categories=['games'],
                        devices=[DEVICE_DESKTOP.id],
                        description=self.clean_string(row['Description']),
                        name=name,
                        status=STATUS_PUBLIC,
                    )
                    self.set_url(website, row)
                    website.save()

                    # Keywords use a M2M, so do that once the website is saved.
                    self.set_tags(website, row)

                    # Launch task to fetch imgs once we know everything is OK.
                    try:
                        self.set_icon(website, row)
                        self.set_promo_imgs(website, row)
                        WebsiteIndexer.index_ids([website.id], no_delay=True)
                    except Exception as e:
                        print e
                        WebsiteIndexer.refresh_index()
                        website.delete()
                        raise e

                    created_count += 1
                except ParsingError as e:
                    print e.message
        return created_count

    def handle(self, *args, **kwargs):
        if len(args) != 1:
            self.print_help('manage.py', self.subcommand)
            return
        filename = args[0]
        data = self.parse(filename)
        created_count = self.create_instances(data)
        print '[DONE] Imported %d games' % created_count
