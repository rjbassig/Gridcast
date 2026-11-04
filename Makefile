install:
	python -m pip install -e '.[dev,deep]'
ingest:
	./scripts/python.sh -m gridcast.cli ingest
prepare:
	./scripts/python.sh -m gridcast.cli prepare
train:
	./scripts/python.sh -m gridcast.cli train
report:
	./scripts/python.sh -m gridcast.cli report
test:
	./scripts/python.sh -m pytest -q
lint:
	ruff check src api tests
serve:
	./scripts/python.sh -m uvicorn api.main:app --host 127.0.0.1 --port 8000
web:
	cd dashboard && npm run dev
