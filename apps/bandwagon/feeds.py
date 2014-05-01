from django.contrib.syndication.views import Feed

from tower import ugettext as _

from amo.helpers import absolutify, page_name
from amo.urlresolvers import reverse
from . import views


class CollectionFeedMixin(Feed):
    """Common pieces for collections in a feed."""

    def item_link(self, c):
        return absolutify(c.get_url_path())

    def item_title(self, c):
        return unicode(c.name or '')

    def item_description(self, c):
        return unicode(c.description or '')

    def item_author_name(self, c):
        return c.author_username

    def item_pubdate(self, c):
        sort = self.request.GET.get('sort')
        return c.created if sort == 'created' else c.modified


class CollectionFeed(CollectionFeedMixin, Feed):

    request = None

    def get_object(self, request):
        self.request = request

    def title(self, c):
        app = page_name(self.request.APP)
        # L10n: {0} is 'Add-ons for <app>'.
        return _(u'Collections :: %s') % app

    def link(self):
        return absolutify(reverse('collections.list'))

    def description(self):
        return _('Collections are groups of related add-ons that anyone can '
                 'create and share.')

    def items(self):
        return views.get_filter(self.request).qs[:20]
