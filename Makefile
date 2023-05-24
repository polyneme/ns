init:
	pip install --upgrade pip-tools pip setuptools
	pip install --upgrade -r requirements/main.txt  -r requirements/dev.txt
	pip install --editable .

update-deps:
	pip install --upgrade pip-tools pip setuptools
	pip-compile --upgrade --build-isolation --output-file \
		requirements/main.txt requirements/main.in
	pip-compile --upgrade --build-isolation --output-file \
		requirements/dev.txt requirements/dev.in

update: update-deps init

up-dev:
	uvicorn --reload --port=8000 xyz_polyneme_ns.main:app

.PHONY: init update-deps update up-dev