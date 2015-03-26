import os
import site

wsgidir = os.path.dirname(__file__)
for path in ['../', '../..']:
    site.addsitedir(os.path.abspath(os.path.join(wsgidir, path)))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mkt.settings')
from verify import application  # noqa
