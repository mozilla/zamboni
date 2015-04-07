from tower import ugettext_lazy as _


APP_STEPS = [
    ('terms', _('Agreement')),
    ('manifest', _('Submit')),
    ('details', _('Details')),
    ('next_steps', _('Next Steps')),
]
APP_STEPS_TITLE = dict(APP_STEPS)

# Preview sizes in the format (width, height, type)
APP_PREVIEW_MINIMUMS = (320, 480)
APP_PREVIEW_SIZES = [
    (100, 150, 'mobile'),  # Thumbnail size.
    (700, 1050, 'full'),  # Because it's proportional, that's why.
]

MAX_PACKAGED_APP_SIZE = 250 * 1024 * 1024  # 250MB
