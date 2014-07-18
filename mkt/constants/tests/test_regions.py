from contextlib import contextmanager
from django.utils import translation
from nose.tools import eq_, ok_
from tower import activate

import amo.tests
import mkt.constants.regions as regions


class TestRegionContentRatings(amo.tests.TestCase):

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
            ok_(region_names_pl.index(regions.SPAIN.name) <
                region_names_pl.index(regions.UK.name))
            ok_(region_names_pl.index(regions.UK.name) >
                region_names_pl.index(regions.US.name))

    def test_localized_sorting_of_region_choices_fr(self):
        with self.tower_activate('fr'):
            region_names_fr = [unicode(r[1]) for r in
                               regions.REGIONS_CHOICES_SORTED_BY_NAME()]
            ok_(region_names_fr.index(regions.SPAIN.name) <
                region_names_fr.index(regions.US.name))
            ok_(region_names_fr.index(regions.US.name) <
                region_names_fr.index(regions.UK.name))
