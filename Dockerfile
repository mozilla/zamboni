# This is designed to be run from fig as part of a
# Marketplace development environment.

# NOTE: this is not provided for production usage.

FROM mozillamarketplace/centos-mysql-mkt:latest

# Fix multilib issues when installing openssl-devel.
RUN yum install -y --enablerepo=centosplus libselinux-devel && yum clean all

RUN yum install -y redis \
    openssl-devel \
    libffi-devel \
    libjpeg-devel \
    libxml2-devel \
    libxslt-devel \
    gcc-c++ \
    npm \
    wget \
    totem \
    supervisor && yum clean all

COPY requirements /srv/zamboni/requirements
RUN pip install --no-deps -r /srv/zamboni/requirements/test.txt --find-links https://pyrepo.stage.mozaws.net/

COPY . /srv/zamboni
RUN cd /srv/zamboni && git show -s --pretty="format:%h" > git-rev.txt

# Install the node_modules.
RUN mkdir -p /srv/zamboni-node
ADD package.json /srv/zamboni-node/package.json
WORKDIR /srv/zamboni-node
RUN npm install

# Override env vars for setup.
ENV CLEANCSS_BIN /srv/zamboni-node/node_modules/clean-css/bin/cleancss
ENV ES_HOST elasticsearch:9200
ENV MARKETPLACE_URL http://mp.dev
ENV MEMCACHE_URL memcached:11211
ENV MONOLITH_URL http://elasticsearch:9200
ENV REDIS_HOST redis
ENV SIGNING_SERVER http://signing:2606
ENV SOLITUDE_URL http://solitude:2602
ENV STYLUS_BIN /srv/zamboni-node/node_modules/stylus/bin/stylus
ENV UGLIFY_BIN /srv/zamboni-node/node_modules/uglify-js/bin/uglifyjs
ENV ZAMBONI_DATABASE mysql://root:@mysql:3306/zamboni
ENV CELERY_BROKER_URL redis://redis:6379/1
ENV CELERY_RESULT_BACKEND redis://redis:6379/2
# Required to run celery as root using pickle serialization.
# TODO: Remove when we move to json serialization.
ENV C_FORCE_ROOT 1

EXPOSE 2600
