import commonware.log

from translations.query import order_by_translation

from .models import Addon


log = commonware.log.getLogger('z.addons')


class BaseFilter(object):
    """
    Filters help generate querysets for add-on listings.

    You have to define ``opts`` on the subclass as a sequence of (key, title)
    pairs.  The key is used in GET parameters and the title can be used in the
    view.

    The chosen filter field is combined with the ``base`` queryset using
    the ``key`` found in request.GET.  ``default`` should be a key in ``opts``
    that's used if nothing good is found in request.GET.
    """

    def __init__(self, request, base, key, default, model=Addon):
        self.opts_dict = dict(self.opts)
        self.extras_dict = dict(self.extras) if hasattr(self, 'extras') else {}
        self.request = request
        self.base_queryset = base
        self.key = key
        self.model = model
        self.field, self.title = self.options(self.request, key, default)
        self.qs = self.filter(self.field)

    def options(self, request, key, default):
        """Get the (option, title) pair we want according to the request."""
        if key in request.GET and (request.GET[key] in self.opts_dict or
                                   request.GET[key] in self.extras_dict):
            opt = request.GET[key]
        else:
            opt = default
        if opt in self.opts_dict:
            title = self.opts_dict[opt]
        else:
            title = self.extras_dict[opt]
        return opt, title

    def all(self):
        """Get a full mapping of {option: queryset}."""
        return dict((field, self.filter(field)) for field in dict(self.opts))

    def filter(self, field):
        """Get the queryset for the given field."""
        filter = self._filter(field) & self.base_queryset
        order = getattr(self, 'order_%s' % field, None)
        if order:
            return order(filter)
        return filter

    def _filter(self, field):
        return getattr(self, 'filter_%s' % field)()

    def filter_price(self):
        return self.model.objects.order_by('addonpremium__price__price', 'id')

    def filter_free(self):
        if self.model == Addon:
            return self.model.objects.top_free(self.request.APP, listed=False)
        else:
            return self.model.objects.top_free(listed=False)

    def filter_paid(self):
        if self.model == Addon:
            return self.model.objects.top_paid(self.request.APP, listed=False)
        else:
            return self.model.objects.top_paid(listed=False)

    def filter_created(self):
        return (self.model.objects.order_by('-created')
                .with_index(addons='created_type_idx'))

    def filter_name(self):
        return order_by_translation(self.model.objects.all(), 'name')
