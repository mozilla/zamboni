import jingo
from nose.tools import eq_
from pyquery import PyQuery as pq

import amo.tests


class TestRatingsHelpers(amo.tests.TestCase):
    def render(self, s, context={}):
        t = jingo.env.from_string(s)
        return t.render(context)

    def test_stars(self):
        s = self.render('{{ num|stars }}', {'num': None})
        eq_(s, 'Not yet rated')

        doc = pq(self.render('{{ num|stars }}', {'num': 1}))
        msg = 'Rated 1 out of 5 stars'
        eq_(doc.attr('class'), 'stars stars-1')
        eq_(doc.attr('title'), msg)
        eq_(doc.text(), msg)

    def test_stars_details_page(self):
        doc = pq(self.render('{{ num|stars(large=True) }}', {'num': 2}))
        eq_(doc('.stars').attr('class'), 'stars large stars-2')

    def test_stars_max(self):
        doc = pq(self.render('{{ num|stars }}', {'num': 5.3}))
        eq_(doc.attr('class'), 'stars stars-5')
