# This is designed to be run from fig as part of a
# Marketplace development environment.

# NOTE: this is not provided for production usage.

FROM mozillamarketplace/centos-mysql-mkt:0.1

# Fix multilib issues when installing openssl-devel.
RUN yum install -y --enablerepo=centosplus libselinux-devel

RUN yum install -y redis \
    openssl-devel \
    libffi-devel \
    libjpeg-devel \
    gcc-c++

RUN mkdir -p /pip/{cache,build}

ADD requirements /pip/requirements

# Remove some compiled deps so we just use the packaged versions already installed.
RUN sed -i 's/M2Crypto.*$/# Removed in favour of packaged version/' /pip/requirements/compiled.txt

# This cd into /pip ensures egg-links for git installed deps are created in /pip/src
RUN cd /pip && pip install -b /pip/build --download-cache /pip/cache -r /pip/requirements/dev.txt --find-links https://pyrepo.addons.mozilla.org/

EXPOSE 2600
