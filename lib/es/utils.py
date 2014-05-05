from .models import Reindexing


# Shortcut functions.
is_reindexing_mkt = Reindexing.objects.is_reindexing_mkt
flag_reindexing_mkt = Reindexing.objects.flag_reindexing_mkt
unflag_reindexing_mkt = Reindexing.objects.unflag_reindexing_mkt
get_indices = Reindexing.objects.get_indices
