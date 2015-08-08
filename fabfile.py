import os
import fabdeploytools.envs
import deploysettings as settings
from os.path import join as pjoin
from fabric.api import (env, execute, lcd, local, parallel,
                        run, roles, task)
from fabdeploytools import helpers

os.environ['DJANGO_SETTINGS_MODULE'] = 'settings_local_mkt'

env.key_filename = settings.SSH_KEY
fabdeploytools.envs.loadenv(settings.CLUSTER)

SCL_NAME = getattr(settings, 'SCL_NAME', False)
if SCL_NAME:
    helpers.scl_enable(SCL_NAME)

ROOT, ZAMBONI = helpers.get_app_dirs(__file__)

VIRTUALENV = pjoin(ROOT, 'venv')
PYTHON = pjoin(VIRTUALENV, 'bin', 'python')


def managecmd(cmd):
    with lcd(ZAMBONI):
        local('%s manage.py %s' % (PYTHON, cmd))


@task
def create_virtualenv(update_on_change=False):
    helpers.create_venv(VIRTUALENV, settings.PYREPO,
                        pjoin(ZAMBONI, 'requirements/prod.txt'),
                        update_on_change=update_on_change)

    if settings.LOAD_TESTING:
        helpers.pip_install_reqs(pjoin(ZAMBONI, 'requirements/load.txt'))


@task
def update_locales():
    with lcd(pjoin(ZAMBONI, 'locale')):
        local("VENV=%s ./compile-mo.sh ." % VIRTUALENV)


@task
def loadtest(repo=''):
    if hasattr(settings, 'MARTEAU'):
        os.environ['MACAUTH_USER'] = settings.MARTEAU_USER
        os.environ['MACAUTH_SECRET'] = settings.MARTEAU_SECRET
        local('%s %s --server %s' % (settings.MARTEAU, repo,
                                     settings.MARTEAU_SERVER))


@task
def compress_assets(arg=''):
    managecmd('compress_assets -t %s' % arg)


@task
def update_info(ref='origin/master'):
    helpers.git_info(ZAMBONI)
    with lcd(ZAMBONI):
        local("/bin/bash -c "
              "'source /etc/bash_completion.d/git && __git_ps1'")
        local('git show -s {0} --pretty="format:%h" '
              '> media/git-rev.txt'.format(ref))


@task
def disable_cron():
    local("rm -f /etc/cron.d/%s" % settings.CRON_NAME)


@task
def install_cron(installed_dir):
    installed_zamboni_dir = os.path.join(installed_dir, 'zamboni')
    installed_python = os.path.join(installed_dir, 'venv', 'bin', 'python')
    with lcd(ZAMBONI):
        local('%s ./scripts/crontab/gen-cron.py '
              '-z %s -u %s -p %s > /etc/cron.d/.%s' %
              (PYTHON, installed_zamboni_dir,
               getattr(settings, 'CRON_USER', 'apache'),
               installed_python, settings.CRON_NAME))

        local('mv /etc/cron.d/.%s /etc/cron.d/%s' % (settings.CRON_NAME,
                                                     settings.CRON_NAME))


@task
@roles('celery')
@parallel
def update_celery():
    restarts = []
    if getattr(settings, 'CELERY_SERVICE_PREFIX', False):
        restarts.extend(['supervisorctl restart {0}{1} &'.format(
                         settings.CELERY_SERVICE_PREFIX, x)
                         for x in ('', '-devhub', '-priority', '-limited')])
    if getattr(settings, 'CELERY_SERVICE_MKT_PREFIX', False):
        restarts.extend(['supervisorctl restart {0}{1} &'.format(
                         settings.CELERY_SERVICE_MKT_PREFIX, x)
                         for x in ('', '-devhub', '-priority', '-limited')])

    if restarts:
        run('%s wait' % ' '.join(restarts))


@task
def deploy():
    package_dirs = ['zamboni', 'venv']
    if os.path.isdir(os.path.join(ROOT, 'aeskeys')):
        package_dirs.append('aeskeys')

    rpmbuild = helpers.deploy(name='zamboni',
                              env=settings.ENV,
                              cluster=settings.CLUSTER,
                              domain=settings.DOMAIN,
                              root=ROOT,
                              deploy_roles=['web', 'celery'],
                              package_dirs=package_dirs)

    helpers.restart_uwsgi(getattr(settings, 'UWSGI', []))
    execute(update_celery)
    execute(install_cron, rpmbuild.install_to)
    managecmd('cron cleanup_validation_results')


@task
def pre_update(ref=settings.UPDATE_REF):
    local('date')
    execute(disable_cron)
    execute(helpers.git_update, ZAMBONI, ref)
    execute(update_info, ref)


@task
def build():
    execute(create_virtualenv, getattr(settings, 'DEV', False))
    execute(update_locales)
    execute(compress_assets, arg='--settings=settings_local_mkt')
    managecmd('statsd_ping --key=build')


@task
def deploy_jenkins():
    package_dirs = ['zamboni', 'venv']
    if os.path.isdir(os.path.join(ROOT, 'aeskeys')):
        package_dirs.append('aeskeys')

    rpm = helpers.build_rpm(name='zamboni',
                            env=settings.ENV,
                            cluster=settings.CLUSTER,
                            domain=settings.DOMAIN,
                            root=ROOT,
                            package_dirs=package_dirs)

    execute(disable_cron)

    rpm.local_install()

    install_path = os.path.join(rpm.install_to, 'zamboni')
    managecmd('migrate')

    rpm.remote_install(['web', 'celery'])

    helpers.restart_uwsgi(getattr(settings, 'UWSGI', []))
    execute(update_celery)
    execute(install_cron, rpm.install_to)

    managecmd('cron cleanup_validation_results')

    rpm.clean()


@task
def update():
    execute(create_virtualenv, getattr(settings, 'DEV', False))
    execute(update_locales)
    execute(compress_assets, arg='--settings=settings_local_mkt')
    managecmd('migrate')
    managecmd('statsd_ping --key=update')


@task
def pre_update_latest_tag():
    current_tag_file = os.path.join(ZAMBONI, '.tag')
    latest_tag = helpers.git_latest_tag(ZAMBONI)
    with open(current_tag_file, 'r+') as f:
        if f.read() == latest_tag:
            print 'Environemnt is at %s' % latest_tag
        else:
            pre_update(latest_tag)
            f.seek(0)
            f.write(latest_tag)
            f.truncate()
