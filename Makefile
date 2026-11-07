PYTHON ?= python

.PHONY: all format lint test update-golden

all: format lint test

format:
	$(PYTHON) -m ruff format .

lint:
	$(PYTHON) -m ruff check .
	$(PYTHON) -m mypy .

test:
	$(PYTHON) -m coverage run -m pytest -v
	$(PYTHON) -m coverage report

update-golden:
	$(PYTHON) -m pytest --update-goldens
