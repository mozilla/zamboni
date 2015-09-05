from django import forms
from django.forms.models import modelformset_factory

import happyforms
from quieter_formset.formset import BaseModelFormSet
from tower import ugettext as _, ugettext_lazy as _lazy

import mkt
from mkt.reviewers.models import ReviewerScore, RereviewQueue
from mkt.webapps.models import Webapp
from mkt.websites.models import Website


ABUSE_REPORT_SKIP = 0
ABUSE_REPORT_READ = 1
ABUSE_REPORT_FLAG = 2


class BaseAbuseViewFormSet(BaseModelFormSet):

    def __init__(self, *args, **kwargs):
        self.form = AbuseViewForm
        self.request = kwargs.pop('request', None)
        super(BaseAbuseViewFormSet, self).__init__(*args, **kwargs)

    def save(self):
        for form in self.forms:
            if form.cleaned_data:
                action = int(form.cleaned_data['action'])
                if action == ABUSE_REPORT_SKIP:
                    continue

                inst = form.instance

                app = None
                site = None
                user = None
                texts = []
                for report in inst.abuse_reports.all().filter(read=False):
                    report.read = True
                    report.save()
                    app = report.webapp
                    site = report.website
                    user = report.user
                    if report.message:
                        texts.append(report.message)
                    if app:
                        mkt.log(mkt.LOG.APP_ABUSE_MARKREAD, app, report,
                                details=dict(
                                    body=unicode(report.message),
                                    webapp_id=app.id,
                                    webapp_title=unicode(app.name)
                                ))
                    elif user:
                        # Not possible on Marketplace currently.
                        pass
                    elif site:
                        mkt.log(mkt.LOG.WEBSITE_ABUSE_MARKREAD, site,
                                report,
                                details=dict(
                                    body=unicode(report.message),
                                    website_id=site.id,
                                    website_title=unicode(site.name)
                                ))
                if app or site:
                    ReviewerScore.award_mark_abuse_points(
                        self.request.user, webapp=app, website=site)
                if app and action == ABUSE_REPORT_FLAG:
                    message = _('Abuse reports needing investigation: %s' %
                                (', '.join(texts)))
                    RereviewQueue.flag(
                        app, mkt.LOG.REREVIEW_ABUSE_APP, message=message)


class AbuseViewForm(happyforms.ModelForm):

    action_choices = [
        (ABUSE_REPORT_SKIP, _lazy(u'Skip for now')),
        (ABUSE_REPORT_READ, _lazy(u'Mark all reports Read')),
        (ABUSE_REPORT_FLAG, _lazy(u'Flag for re-review'))]
    action = forms.ChoiceField(choices=action_choices, required=False,
                               initial=0, widget=forms.RadioSelect())

    class Meta:
        model = Webapp
        fields = ('action',)


class WebsiteAbuseViewForm(AbuseViewForm):

    action_choices = [
        (ABUSE_REPORT_SKIP, _lazy(u'Skip for now')),
        (ABUSE_REPORT_READ, _lazy(u'Mark all reports Read'))]
    action = forms.ChoiceField(choices=action_choices, required=False,
                               initial=0, widget=forms.RadioSelect())

    class Meta:
        model = Website
        fields = ('action',)


AppAbuseViewFormSet = modelformset_factory(Webapp, extra=0,
                                           form=AbuseViewForm,
                                           formset=BaseAbuseViewFormSet)

WebsiteAbuseViewFormSet = modelformset_factory(Website, extra=0,
                                               form=WebsiteAbuseViewForm,
                                               formset=BaseAbuseViewFormSet)
