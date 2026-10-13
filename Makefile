.PHONY: install run test lint

install:
	python -m pip install -r requirements.txt

run:
	uvicorn src.main:app --reload

test:
	pytest

lint:
	ruff check src tests
