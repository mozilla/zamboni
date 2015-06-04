from django import forms
from django.forms.models import modelformset_factory

import happyforms
from quieter_formset.formset import BaseModelFormSet

import mkt
from mkt.webapps.models import Webapp
from mkt.websites.models import Website


class BaseAbuseViewFormSet(BaseModelFormSet):

    def __init__(self, *args, **kwargs):
        self.form = AbuseViewForm
        self.request = kwargs.pop('request', None)
        super(BaseAbuseViewFormSet, self).__init__(*args, **kwargs)

    def save(self):
        for form in self.forms:
            if form.cleaned_data:
                mark_read = form.cleaned_data.get('action', False)
                inst = form.instance
                if mark_read:
                    for report in inst.abuse_reports.all().filter(read=False):
                        report.read = True
                        report.save()
                        if report.addon:
                            mkt.log(mkt.LOG.APP_ABUSE_MARKREAD, report.addon,
                                    report,
                                    details=dict(
                                        body=unicode(report.message),
                                        addon_id=report.addon.id,
                                        addon_title=unicode(
                                            report.addon.name)))
                        elif report.user:
                            # Not possible on Marketplace currently.
                            pass
                        elif report.website:
                            mkt.log(mkt.LOG.WEBSITE_ABUSE_MARKREAD,
                                    report.website, report,
                                    details=dict(
                                        body=unicode(report.message),
                                        website_id=report.website.id,
                                        website_title=unicode(
                                            report.website.name)))


class AbuseViewForm(happyforms.ModelForm):

    action = forms.BooleanField(required=False, initial=False,
                                widget=forms.CheckboxInput(
                                    attrs={'hidden': 'true'}))

    class Meta:
        model = Webapp
        fields = ('action',)


AppAbuseViewFormSet = modelformset_factory(Webapp, extra=0,
                                           form=AbuseViewForm,
                                           formset=BaseAbuseViewFormSet)

WebsiteAbuseViewFormSet = modelformset_factory(Website, extra=0,
                                               form=AbuseViewForm,
                                               formset=BaseAbuseViewFormSet)
