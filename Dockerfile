# This is designed to be run from fig as part of a
# Marketplace development environment.

# NOTE: this is not provided for production usage.

FROM mozillamarketplace/centos-mysql-mkt:0.2

# Fix multilib issues when installing openssl-devel.
RUN yum install -y --enablerepo=centosplus libselinux-devel && yum clean all

RUN yum install -y redis \
    openssl-devel \
    libffi-devel \
    libjpeg-devel \
    gcc-c++ \
    npm \
    wget \
    totem \
    supervisor && yum clean all

RUN mkdir -p /pip/{cache,build}

ADD requirements /pip/requirements

# Remove some compiled deps so we just use the packaged versions already installed.
RUN sed -i 's/M2Crypto.*$/# Removed in favour of packaged version/' /pip/requirements/compiled.txt

# This cd into /pip ensures egg-links for git installed deps are created in /pip/src
RUN cd /pip && pip install -b /pip/build --no-deps --download-cache /pip/cache -r /pip/requirements/dev.txt --find-links https://pyrepo.addons.mozilla.org/

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

EXPOSE 2600
