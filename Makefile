# You can set these variables from the command line.
PYTHON := $(shell which python)
DJANGO = $(PYTHON) manage.py
SETTINGS = mkt.settings
SHELL := /usr/bin/env bash

.PHONY: help docs test test_force_db tdd test_failed update_code update_deps update_db update_landfill update_commonplace full_update reindex release

help:
	@echo "Please use \`make <target>' where <target> is one of"
	@echo "  docs                to builds the docs for Zamboni"
	@echo "  test                to run all the test suite"
	@echo "  test_force_db       to run all the test suite with a new database"
	@echo "  tdd                 to run all the test suite, but stop on the first error"
	@echo "  test_failed         to rerun the failed tests from the previous run"
	@echo "  update_code         to update the git repository and submodules"
	@echo "  update_deps         to update the python and npm dependencies"
	@echo "  update_db           to run the database migrations"
	@echo "  update_commonplace  to update commonplace projects"
	@echo "  full_update         to run a full update of zamboni and commonplace"
	@echo "  update_landfill     to load the landfill database data"
	@echo "  reindex             to reindex everything in elasticsearch"
	@echo "  release             to tag and stage a weekly code release"
	@echo "Check the Makefile to know exactly what each target is doing. If you see a "
	@echo "target using something like $(SETTINGS), you can make it use another value:"
	@echo "  make SETTINGS=settings_mine docs"

docs:
	$(MAKE) -C docs html

test:
	$(DJANGO) test --settings=$(SETTINGS) --noinput --logging-clear-handlers --with-id $(ARGS)

test_force_db:
	FORCE_DB=1 $(DJANGO) test --settings=$(SETTINGS) --noinput --logging-clear-handlers --with-id $(ARGS)

tdd:
	$(DJANGO) test --settings=$(SETTINGS) --noinput --failfast --pdb --with-id $(ARGS)

test_failed:
	$(DJANGO) test --settings=$(SETTINGS) --noinput --logging-clear-handlers --with-id --failed $(ARGS)

update_code:
	git checkout master && git pull && git submodule update --init --recursive
	cd vendor && git pull . && git submodule update --init && cd -

update_deps:
	pip install --no-deps --exists-action=w --download-cache=/tmp/pip-cache -r requirements/dev.txt --find-links https://pyrepo.addons.mozilla.org/
	npm install

update_db:
	schematic migrations

update_commonplace:
	commonplace fiddle

full_update: update_code update_deps update_db update_commonplace

update_landfill:
	$(DJANGO) install_landfill --settings=$(SETTINGS) $(ARGS)

reindex:
	$(DJANGO) reindex_mkt --settings=$(SETTINGS) $(ARGS)

tagz.py:
	curl -O https://raw.githubusercontent.com/cvan/tagz/master/tagz.py

release: tagz.py
	$(eval RELEASE_DATE := $(shell $(PYTHON) -c 'import datetime; now = datetime.datetime.utcnow(); tue = now + datetime.timedelta(days=(1 - now.weekday()) % 7); print tue.strftime("%Y.%m.%d")'))
	$(PYTHON) tagz.py -r mozilla/solitude,mozilla/webpay,mozilla/commbadge,mozilla/fireplace,mozilla/marketplace-stats,mozilla/monolith-aggregator,mozilla/rocketfuel,mozilla/zamboni -c create -t $(RELEASE_DATE)
	$(PYTHON) scripts/dreadnot-deploy.py			\
	-c dreadnot-stage.ini -e stage -r $(RELEASE_DATE)	\
		payments.allizom.org-solitude			\
		payments-proxy.allizom.org-solitude		\
		marketplace.allizom.org-webpay			\
		monolith.allizom.org-aggregator			\
		marketplace.allizom.org-rocketfuel		\
		marketplace.allizom.org-marketplace-stats	\
		marketplace.allizom.org-commbadge		\
		marketplace.allizom.org-fireplace		\
		marketplace.allizom.org-zamboni
