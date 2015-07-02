import happyforms
from tower import ugettext as _
from tower import ugettext_lazy as _lazy
from tower import ungettext as ngettext

from django import forms

import mkt
from mkt.constants.applications import DEVICE_CHOICES
from mkt.constants.categories import CATEGORY_CHOICES
from mkt.constants.regions import REGIONS_CHOICES_NAME
from mkt.tags.utils import clean_tags
from mkt.translations.fields import TransField
from mkt.translations.widgets import TransInput, TransTextarea
from mkt.websites.models import Website
from mkt.tags.models import Tag
from mkt.site.utils import slugify


class WebsiteForm(happyforms.ModelForm):
    categories = forms.MultipleChoiceField(
        label=_lazy(u'Categories'), choices=CATEGORY_CHOICES,
        widget=forms.CheckboxSelectMultiple)
    description = TransField(label=_lazy(u'Description'),
                             widget=TransTextarea(attrs={'rows': 4}))
    devices = forms.MultipleChoiceField(
        label=_lazy(u'Compatible Devices'), choices=DEVICE_CHOICES,
        widget=forms.SelectMultiple)
    keywords = forms.CharField(label=_lazy(u'Keywords'), required=False,
                               widget=forms.Textarea(attrs={'rows': 2}))
    name = TransField(label=_lazy(u'Name'), widget=TransInput())
    preferred_regions = forms.MultipleChoiceField(
        label=_lazy(u'Preferred Regions'), choices=REGIONS_CHOICES_NAME,
        required=False, widget=forms.SelectMultiple(attrs={'size': 10}))
    short_name = TransField(label=_lazy(u'Short Name'), widget=TransInput(),
                            required=False)
    title = TransField(label=_lazy(u'Title'), widget=TransInput(),
                       required=False)
    url = forms.URLField(label=_lazy(u'URL'))

    class Meta(object):
        model = Website
        fields = ('categories', 'description', 'devices', 'is_disabled',
                  'keywords', 'mobile_url', 'name', 'preferred_regions',
                  'short_name', 'status', 'title', 'url')

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request')
        super(WebsiteForm, self).__init__(*args, **kwargs)

        keywords = self.instance.keywords.values_list('tag_text', flat=True)
        self.initial['keywords'] = ', '.join(keywords)

    def clean_categories(self):
        categories = self.cleaned_data['categories']
        max_cat = mkt.MAX_CATEGORIES

        if len(set(categories)) > max_cat:
            # L10n: {0} is the number of categories.
            raise forms.ValidationError(ngettext(
                'You can have only {0} category.',
                'You can have only {0} categories.',
                max_cat).format(max_cat))

        return categories

    def clean_keywords(self):
        return clean_tags(self.request, self.cleaned_data['keywords'])

    def clean_preferred_regions(self):
        try:
            regions = map(int, self.cleaned_data.get('preferred_regions'))
        except (TypeError, ValueError):
            # Data is not a list or data contains non-integers.
            raise forms.ValidationError(_('Invalid region(s) selected.'))

        return list(regions)

    def clean_devices(self):
        try:
            devices = map(int, self.cleaned_data.get('devices'))
        except (TypeError, ValueError):
            # Data is not a list or data contains non-integers.
            raise forms.ValidationError(_('Invalid device(s) selected.'))

        return list(devices)

    def save(self, commit=False):
        form = super(WebsiteForm, self).save(commit=False)

        keywords_new = self.cleaned_data['keywords']
        keywords_old = [slugify(keyword, spaces=True)
                        for keyword in self.instance.keywords.values_list(
                            'tag_text', flat=True)]
        for k in set(keywords_new) - set(keywords_old):
            Tag(tag_text=k).save_tag(self.instance)
        for k in set(keywords_old) - set(keywords_new):
            Tag(tag_text=k).remove_tag(self.instance)

        form.save()
        return form
