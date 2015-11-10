from django.db.models import Q
from rest_framework.filters import BaseFilterBackend

from mkt.users.models import UserProfile


class NoteContentFilter(BaseFilterBackend):
    """
    Filter that searches note content based on `q`.
    Query must be at least two characters.
    """
    def filter_queryset(self, request, queryset, view):
        q = request.GET.get('q', '').lower()
        if not q or len(q) < 3:
            return queryset

        # Get notes where body matches search query.
        note_ids = list((queryset.filter(body__icontains=q)
                                 .values_list('id', flat=True)))
        # Combine w/ notes where search query matches author user profile.
        note_ids += filter(None, UserProfile.objects.filter(
            Q(email__icontains=q) | Q(display_name__icontains=q)
        ).values_list('comm_notes', flat=True))
        return queryset.filter(id__in=note_ids)


class NoteContentTypeFilter(BaseFilterBackend):
    """
    Filters apps vs. add-ons based on `doc_type`.
    """
    def filter_queryset(self, request, queryset, view):
        doc_type = request.GET.get('doc_type', '').lower()
        if not doc_type:
            return queryset

        if doc_type == 'extension':
            queryset = queryset.filter(thread___extension__isnull=False)
        if doc_type == 'webapp':
            queryset = queryset.filter(thread___addon__isnull=False)
        return queryset
