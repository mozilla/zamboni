# You can set these variables from the command line.
PYTHON := $(shell which python)
DJANGO = $(PYTHON) manage.py
SETTINGS = mkt.settings
SHELL := /usr/bin/env bash
JENKINS_URL = https://deploy.mktadm.ops.services.phx1.mozilla.com/view/Stage/job/Deploy%20Marketplace%20Stage/build

.PHONY: help docs test test_force_db test_api test_api_force_db tdd test_failed update_code update_deps update_db full_update reindex release

help:
	@echo "Please use \`make <target>' where <target> is one of"
	@echo "  docs                to builds the docs for Zamboni"
	@echo "  test                to run all the test suite"
	@echo "  test_force_db       to run all the test suite with a new database"
	@echo "  test_api            to run all the API tests in the suite"
	@echo "  test_api_force_db   to run all the API tests in the suite with a new database"
	@echo "  tdd                 to run all the test suite, but stop on the first error"
	@echo "  test_failed         to rerun the failed tests from the previous run"
	@echo "  update_code         to update the git repository and submodules"
	@echo "  update_deps         to update the python and npm dependencies"
	@echo "  update_db           to run the database migrations"
	@echo "  full_update         to run a full update of zamboni and commonplace"
	@echo "  reindex             to reindex everything in elasticsearch"
	@echo "  release             to tag and stage a weekly code release"
	@echo "Check the Makefile to know exactly what each target is doing. If you see a "
	@echo "target using something like $(SETTINGS), you can make it use another value:"
	@echo "  make SETTINGS=settings_mine docs"

docs:
	$(MAKE) -C docs html

test:
	$(DJANGO) test --settings=$(SETTINGS) -P -s --noinput --logging-clear-handlers --with-id --with-blockage $(ARGS)

test_force_db:
	FORCE_DB=1 $(DJANGO) test --settings=$(SETTINGS) -P -s --noinput --logging-clear-handlers --with-id --with-blockage $(ARGS)

test_api:
	$(DJANGO) test --settings=$(SETTINGS) -P -s --noinput --logging-clear-handlers --with-id --config=mkt/api/tests/nose.cfg --with-blockage $(ARGS)

test_api_force_db:
	FORCE_DB=1 $(DJANGO) test --settings=$(SETTINGS) -P -s --noinput --logging-clear-handlers --config=mkt/api/tests/nose.cfg --with-id --with-blockage $(ARGS)

tdd:
	$(DJANGO) test --settings=$(SETTINGS) -P -s --noinput --failfast --pdb --with-id --with-blockage $(ARGS)

test_failed:
	$(DJANGO) test --settings=$(SETTINGS) -P -s --noinput --logging-clear-handlers --with-id --failed --with-blockage $(ARGS)

update_code:
	git checkout master && git pull && git submodule update --init --recursive
	cd vendor && git pull . && git submodule update --init && cd -

update_deps:
	pip install --no-deps --exists-action=w --download-cache=/tmp/pip-cache -r requirements/dev.txt --find-links https://pyrepo.addons.mozilla.org/
	npm install

update_db:
	$(DJANGO) migrate

full_update: update_code update_deps update_db

reindex:
	$(DJANGO) reindex --settings=$(SETTINGS) $(ARGS)

tagz.py:
	curl -O https://raw.githubusercontent.com/cvan/tagz/master/tagz.py

tag_release: tagz.py
	$(eval RELEASE_DATE := $(shell $(PYTHON) -c 'import datetime; now = datetime.datetime.utcnow(); tue = now + datetime.timedelta(days=(1 - now.weekday()) % 7); print tue.strftime("%Y.%m.%d")'))
	@echo "Tagging release $(RELEASE_DATE)"
	$(PYTHON) tagz.py -r mozilla/solitude,mozilla/spartacus,mozilla/webpay,mozilla/commbadge,mozilla/fireplace,mozilla/marketplace-operator-dashboard,mozilla/marketplace-stats,mozilla/monolith-aggregator,mozilla/transonic,mozilla/zamboni -c create -t $(RELEASE_DATE)
	@echo "Tag complete."

deploy_release: check_deploy_env
	$(eval RELEASE_DATE := $(shell $(PYTHON) -c 'import datetime; now = datetime.datetime.utcnow(); tue = now + datetime.timedelta(days=(1 - now.weekday()) % 7); print tue.strftime("%Y.%m.%d")'))
	@echo "Pushing to stage now with the command:"
	curl -k -X POST $(JENKINS_URL) \
		--user $(JENKINS_USERNAME):$(JENKINS_API_TOKEN) \
		--data-urlencode json='{"parameter": [{"name":"DeployRef", "value":"$(RELEASE_DATE)"}]}'

check_deploy_env:
ifndef JENKINS_USERNAME
	$(error JENKINS_USERNAME ENV variable not set)
endif
ifndef JENKINS_API_TOKEN
	$(error JENKINS_API_TOKEN ENV variable not set)
endif

release: tag_release deploy_release
