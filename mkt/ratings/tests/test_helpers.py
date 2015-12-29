
from nose.tools import eq_
from pyquery import PyQuery as pq

from mkt.site.utils import env
import mkt.site.tests


class TestRatingsHelpers(mkt.site.tests.TestCase):
    def render(self, s, context={}):
        t = env.from_string(s)
        return t.render(context)

    def test_stars(self):
        s = self.render('{{ num|stars }}', {'num': None})
        eq_(s, 'Not yet reviewed')

        doc = pq(self.render('{{ num|stars }}', {'num': 1}))
        msg = 'Reviewed 1 out of 5 stars'
        eq_(doc.text(), msg)

    def test_stars_max(self):
        doc = pq(self.render('{{ num|stars }}', {'num': 5.5}))
        msg = 'Reviewed 5 out of 5 stars'
        eq_(doc.text(), msg)
