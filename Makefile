PY := .venv/bin

.PHONY: setup data cuad test eval api web web-build demo up clean

setup:            ## Python venv + deps, and web app deps
	uv venv --python 3.12 && uv pip install -e ".[dev]"
	cd frontend && npm install

data:             ## regenerate the synthetic seed dataset
	$(PY)/conexus generate-data

test:             ## Python unit + API tests, and web typecheck
	$(PY)/pytest -q
	cd frontend && npx tsc -b --noEmit

cuad:             ## download CUAD (real contracts) and build the clause benchmark
	$(PY)/conexus fetch-cuad

eval:             ## run RO2 (synthetic + CUAD) and RO3/RO5 evaluations (results in runs/)
	$(PY)/conexus eval-escalation && $(PY)/conexus eval-cuad && $(PY)/conexus eval-negotiation

api:              ## API on :8000 (also serves the built web app; docs at /docs)
	$(PY)/conexus-api

web:              ## web app dev server with hot reload on :5173 (needs `make api`)
	cd frontend && npm run dev

web-build:        ## production build of the web app into frontend/dist
	cd frontend && npm run build

demo:             ## CLI demo negotiation with escalation
	$(PY)/conexus demo contract_010

up:               ## everything in one Docker container on :8000
	docker compose up --build

clean:            ## delete runtime state (DB, audit logs, envelopes)
	rm -rf runs/*
