from django import forms
from django.forms.models import modelformset_factory

import happyforms
from quieter_formset.formset import BaseModelFormSet
from tower import ugettext_lazy as _lazy

import mkt
from mkt.ratings import (REVIEW_MODERATE_DELETE, REVIEW_MODERATE_KEEP,
                         REVIEW_MODERATE_SKIP)
from mkt.ratings.helpers import user_can_delete_review
from mkt.ratings.models import Review
from mkt.reviewers.models import ReviewerScore


class BaseReviewFlagFormSet(BaseModelFormSet):

    def __init__(self, *args, **kwargs):
        self.form = ModerateReviewFlagForm
        self.request = kwargs.pop('request', None)
        super(BaseReviewFlagFormSet, self).__init__(*args, **kwargs)

    def save(self):

        for form in self.forms:
            if form.cleaned_data and user_can_delete_review(self.request,
                                                            form.instance):
                action = int(form.cleaned_data['action'])

                is_flagged = (form.instance.reviewflag_set.count() > 0)

                if action != REVIEW_MODERATE_SKIP:  # Delete flags.
                    for flag in form.instance.reviewflag_set.all():
                        flag.delete()

                review = form.instance
                webapp = review.webapp
                if action == REVIEW_MODERATE_DELETE:
                    review.delete()
                    mkt.log(mkt.LOG.DELETE_REVIEW, webapp, review,
                            details=dict(title=unicode(review.title),
                                         body=unicode(review.body),
                                         webapp_id=webapp.id,
                                         webapp_title=unicode(webapp.name),
                                         is_flagged=is_flagged))
                    if self.request:
                        ReviewerScore.award_moderation_points(
                            self.request.user, webapp, review.id)
                elif action == REVIEW_MODERATE_KEEP:
                    review.editorreview = False
                    review.save()
                    mkt.log(mkt.LOG.APPROVE_REVIEW, webapp, review,
                            details=dict(title=unicode(review.title),
                                         body=unicode(review.body),
                                         webapp_id=webapp.id,
                                         webapp_title=unicode(webapp.name),
                                         is_flagged=is_flagged))
                    if self.request:
                        ReviewerScore.award_moderation_points(
                            self.request.user, webapp, review.id)


class ModerateReviewFlagForm(happyforms.ModelForm):

    action_choices = [
        (REVIEW_MODERATE_KEEP, _lazy(u'Keep review; remove flags')),
        (REVIEW_MODERATE_SKIP, _lazy(u'Skip for now')),
        (REVIEW_MODERATE_DELETE, _lazy(u'Delete review'))]
    action = forms.ChoiceField(choices=action_choices, required=False,
                               initial=0, widget=forms.RadioSelect())

    class Meta:
        model = Review
        fields = ('action',)


ReviewFlagFormSet = modelformset_factory(Review, extra=0,
                                         form=ModerateReviewFlagForm,
                                         formset=BaseReviewFlagFormSet)
