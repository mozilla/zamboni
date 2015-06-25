import logging

from django.conf import settings

from lib.post_request_task.task import task as post_request_task
from mkt.developers.tasks import (_fetch_content, get_content_and_check_size,
                                  ResponseTooLargeException, save_icon)
from mkt.site.decorators import write
from mkt.websites.models import Website


log = logging.getLogger('z.mkt.websites.tasks')


@post_request_task
@write
def fetch_icon(pk, icon_url, **kw):
    """
    Downloads a website icon from the location passed to the task.

    Returns False if icon was not able to be retrieved
    """
    website = Website.objects.get(pk=pk)
    log.info(u'[Website:%s] Fetching icon for website', website.name)

    try:
        response = _fetch_content(icon_url)
    except Exception, e:
        log.error(u'[Website:%s] Failed to fetch icon for website: %s'
                  % (website, e))
        # Set the icon type to empty.
        website.update(icon_type='')
        return False

    try:
        content = get_content_and_check_size(
            response, settings.MAX_ICON_UPLOAD_SIZE)
    except ResponseTooLargeException:
        log.warning(u'[Website:%s] Icon exceeds maximum size', website.name)
        return False

    log.info('[Website:%s] Icon fetching completed, saving icon', website.name)
    save_icon(website, content)
