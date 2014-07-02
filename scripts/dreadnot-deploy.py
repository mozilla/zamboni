# commandline deployer for dreadnot

# Based on the original at
# https://github.com/jasonthomas/random/blob/master/dreadnot.deploy

import getpass
from ConfigParser import SafeConfigParser
from optparse import OptionParser
from urlparse import urljoin

import requests

try:
    import keyring
except ImportError:
    keyring = None
    print ('Keyring module not found, "pip install keyring" if you want your'
           ' password remembered')


# config file should be ini format
def configure(config_file, env):
    config = {}
    conf = SafeConfigParser()
    passwd = None
    if conf.read(config_file):
        config['username'] = conf.get(env, 'username')
        config['dreadnot'] = conf.get(env, 'dreadnot')
        config['region'] = conf.get(env, 'region')
    else:
        config['dreadnot'] = raw_input('Dreadnot URL:')
        config['region'] = raw_input('Deployment region:')
        config['username'] = raw_input('Dreadnot username:')
        conf.add_section(env)
        for name in ('dreadnot', 'region', 'username'):
            conf.set(env, name, config[name])
        with open(config_file, 'w') as f:
            conf.write(f)
    if keyring:
        passwd = keyring.get_password('dreadnot', config['dreadnot'])
    if not passwd:
        passwd = getpass.getpass('Dreadnot password:')
        if keyring:
            keyring.set_password('dreadnot', config['dreadnot'], passwd)
    config['password'] = passwd
    return config


# deploy the goodness
def deploy(dreadnot, username, password, region, app_name, revision,
           ssl_verify=False):
    DREADNOT_DEPLOY = urljoin(
        dreadnot,
        '/api/1.0/stacks/%s/regions/%s/deployments' % (app_name, region))
    TO_REVISION = {'to_revision': revision}

    r = requests.post(DREADNOT_DEPLOY, data=TO_REVISION,
                      auth=(username, password), verify=ssl_verify)
    print "%s - %s" % (r.status_code, r.content)


def main():
    parser = OptionParser(usage="usage: %prog [options] app_name ...")
    parser.add_option("-c", "--conf",
                      default='dreadnot.ini',
                      type='string',
                      help="Configuration File")
    parser.add_option("-e", "--environment",
                      default='dev',
                      type='string',
                      help="Environment you want to deploy to")
    parser.add_option("-r", "--revision",
                      default='origin/master',
                      type='string',
                      help="Git Revision")

    (options, args) = parser.parse_args()

    if len(args) < 1:
        parser.error("wrong number of arguments")

    config = configure(options.conf, options.environment)
    for app_name in args:
        print "Deploying " + app_name
        deploy(config['dreadnot'], config['username'], config['password'],
               config['region'], app_name, options.revision)

if __name__ == '__main__':
    main()
