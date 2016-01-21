from contextlib import contextmanager
from mpconstants.countries import COUNTRY_DETAILS
from nose.tools import eq_, ok_
from tower import activate

import mkt.constants.regions as regions
from mkt.site.tests import TestCase


class TestRegions(TestCase):
    def test_no_missing_region(self):
        """Test that we haven't forgotten to add some regions to the lookup
        dictionary."""
        defined_regions = regions.REGION_LOOKUP.keys()
        available_regions = {c['slug'] for c in COUNTRY_DETAILS.values()}
        eq_(list(available_regions.difference(defined_regions)), [])

    def test_regions_dict(self):
        eq_(regions.REGIONS_DICT['restofworld'], regions.RESTOFWORLD)
        eq_(regions.REGIONS_DICT['us'], regions.USA)
        for region in regions.REGIONS_DICT.values():
            # Make sure the regions dict contains region objects.
            ok_(issubclass(region, regions.REGION))

            # Make sure we can find each region in the regions module locals.
            eq_(getattr(regions, region.__name__), region)

            # Make sure the name is a lazy unicode object - encoding it to
            # utf-8 it should work.
            ok_(region.name.encode('utf-8'))


class TestRegionContentRatings(TestCase):

    @contextmanager
    def tower_activate(self, region):
        try:
            activate(region)
            yield
        finally:
            activate('en-US')

    def test_region_to_ratings_body(self):
        region_to_body = regions.REGION_TO_RATINGS_BODY()
        eq_(region_to_body['br'], 'classind')
        eq_(region_to_body['es'], 'pegi')
        eq_(region_to_body['de'], 'usk')
        eq_(region_to_body['us'], 'esrb')

    def test_name_sorted_regions_eq_slug_sorted_regions(self):
        """Check data is the same, irrespective of ordering."""
        self.assertEqual(len(regions.REGIONS_CHOICES_NAME),
                         len(regions.REGIONS_CHOICES_SORTED_BY_NAME()))
        self.assertSetEqual(regions.REGIONS_CHOICES_NAME,
                            regions.REGIONS_CHOICES_SORTED_BY_NAME())

    def test_rest_of_world_last_regions_by_slug(self):
        eq_(regions.REGIONS_CHOICES_NAME[-1][1], regions.RESTOFWORLD.name)

    def test_rest_of_world_last_regions_by_name(self):
        eq_(regions.REGIONS_CHOICES_SORTED_BY_NAME()[-1][1],
            regions.RESTOFWORLD.name)

    def test_localized_sorting_of_region_choices_pl(self):
        with self.tower_activate('pl'):
            region_names_pl = [r[1] for r in
                               regions.REGIONS_CHOICES_SORTED_BY_NAME()]
            ok_(region_names_pl.index(regions.ESP.name) <
                region_names_pl.index(regions.GBR.name))
            ok_(region_names_pl.index(regions.GBR.name) >
                region_names_pl.index(regions.USA.name))

    def test_localized_sorting_of_region_choices_fr(self):
        with self.tower_activate('fr'):
            region_names_fr = [unicode(r[1]) for r in
                               regions.REGIONS_CHOICES_SORTED_BY_NAME()]
            ok_(region_names_fr.index(regions.ESP.name) <
                region_names_fr.index(regions.USA.name))
            ok_(region_names_fr.index(regions.USA.name) <
                region_names_fr.index(regions.GBR.name))
