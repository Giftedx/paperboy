SHELL := /usr/bin/bash
VENV := .venv
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
PYTEST := $(VENV)/bin/pytest

.PHONY: venv install run run-dry test clean

venv:
	# Try to create venv; ignore failure (e.g., ensurepip not available)
	python3 -m venv $(VENV) || true
	@if [ -x "$(PIP)" ]; then \
		$(PIP) install -U pip; \
		$(PIP) install -r requirements.txt; \
		$(PIP) install pytest; \
	else \
		echo "ERROR: Could not create a virtual environment. Please create one manually (e.g., python3 -m venv .venv) and re-run make."; \
		exit 1; \
	fi

install: venv

run: venv
	@if [ -x "$(PY)" ]; then \
		$(PY) main.py; \
	else \
		python3 main.py; \
	fi

run-dry: venv
	@if [ -x "$(PY)" ]; then \
		MAIN_PY_DRY_RUN=true $(PY) main.py; \
	else \
		MAIN_PY_DRY_RUN=true python3 main.py; \
	fi

test: venv
	@if [ -x "$(PYTEST)" ]; then \
		$(PYTEST) -q; \
	else \
		python3 -m pytest -q; \
	fi

clean:
	rm -rf $(VENV) .pytest_cache __pycache__