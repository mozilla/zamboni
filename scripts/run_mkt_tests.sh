# This script should be called from within Jenkins

if [ -z SET_PY_27 ]; then
    source /opt/rh/python27/enable
fi

cd $WORKSPACE
VENV=$WORKSPACE/venv
VENDOR=$WORKSPACE/vendor
LOCALE=$WORKSPACE/locale
ES_HOST='jenkins-es20'
SETTINGS=mkt

echo "Starting build on executor $EXECUTOR_NUMBER..." `date`

if [ -z $1 ]; then
    echo "Warning: You should provide a unique name for this job to prevent database collisions."
    echo "Usage: ./run_mkt_tests.sh <name> <settings> --with-coverage"
    echo "Continuing, but don't say you weren't warned."
fi

if [ -z $2 ]; then
    echo "Warning: no settings directory specified, using: ${SETTINGS}"
    echo "Usage: ./run_mkt_tests.sh <name> <settings> --with-coverage"
else
    SETTINGS=$2
fi

echo "Setup..." `date`

# Make sure there's no old pyc files around.
find . -name '*.pyc' | xargs rm

if [ ! -d "$VENV/bin" ]; then
  echo "No virtualenv found.  Making one..."
  virtualenv $VENV --system-site-packages --python=python
fi

source $VENV/bin/activate

pip install -U --exists-action=w --no-deps -q \
	--download-cache=$WORKSPACE/.pip-cache \
	-r requirements/compiled.txt -r requirements/test.txt \
	-f https://pyrepo.addons.mozilla.org/

if [ ! -d "$LOCALE" ]; then
    echo "No locale dir?  Cloning..."
    svn co http://svn.mozilla.org/addons/trunk/site/app/locale/ $LOCALE
fi

if [ ! -d "$VENDOR" ]; then
    echo "No vendor lib?  Cloning..."
    git clone --recursive git://github.com/mozilla/zamboni-lib.git $VENDOR
fi

# Update the vendor lib.
echo "Updating vendor..."
git submodule --quiet foreach 'git submodule --quiet sync'
git submodule --quiet sync && git submodule update --init --recursive

cat > settings_local.py <<SETTINGS
from ${SETTINGS}.settings import *

DATABASES['default']['TEST_NAME'] = 'test_zamboni_$1'
ES_HOSTS = ['${ES_HOST}:9200']
ES_URLS = ['http://%s' % h for h in ES_HOSTS]

SETTINGS

export DJANGO_SETTINGS_MODULE=settings_local

# Update product details to pull in any changes (namely, 'dbg' locale)
echo "Updating product details..."
python manage.py update_product_details

echo "Starting tests..." `date`
export FORCE_DB='yes sir'

run_tests="python manage.py test -v 2 --noinput --logging-clear-handlers --with-blockage --http-whitelist=127.0.0.1,localhost,${ES_HOST} --with-xunit"
if [[ $3 = '--with-coverage' ]]; then
    run_tests+=" --with-coverage --cover-package=mkt --cover-erase --cover-html --cover-xml --cover-xml-file=coverage.xml"
else
   if [[ $3 ]]; then
    run_tests+=" $3"
   fi
fi
exec $run_tests

rv=$?

echo 'shazam!'
exit $rv
