.PHONY: help install demo cycle run bench bench-baseline test lint typecheck web api up clean

SPEC ?= specs/razorpay-settlement.yaml
DATASET ?= datasets/seed
SCENARIO ?= d2c
RECORDS ?= 800
SEED ?= 42

help:
	@echo "Arbiter — make targets"
	@echo "  install    uv sync + pnpm install"
	@echo "  demo       generate a seed dataset, run reconciliation, print the scorecard"
	@echo "  cycle      3 monthly closes: resolve once, learn a rule, watch it carry forward"
	@echo "  run        arbiter run --spec \$$(SPEC) --dataset \$$(DATASET)"
	@echo "  bench      arbiter bench (matching + agent scorecard vs ground truth)"
	@echo "  api        run the FastAPI backend on :8000"
	@echo "  web        run the Next.js cockpit on :3000 (needs the api running)"
	@echo "  up         api + web together"
	@echo "  test       pytest (engine + datagen + api)"
	@echo "  lint       ruff check + web lint"
	@echo "  typecheck  mypy + tsc"
	@echo "  clean      remove data/ and generated datasets"

install:
	uv sync --all-packages
	cd web && pnpm install --frozen-lockfile

$(DATASET)/manifest.json:
	uv run arbiter-datagen gen --scenario $(SCENARIO) --records $(RECORDS) --seed $(SEED) --out $(DATASET)

demo: install $(DATASET)/manifest.json
	uv run arbiter run --spec $(SPEC) --dataset $(DATASET)
	uv run arbiter bench --spec $(SPEC) --dataset $(DATASET)
	@echo "\n→ cockpit: run 'make up' (API :8000 + cockpit :3000)"

cycle:
	uv run arbiter cycle-demo --out data/cycle

run:
	uv run arbiter run --spec $(SPEC) --dataset $(DATASET)

bench:
	uv run arbiter bench --spec $(SPEC) --dataset $(DATASET) --gate bench/baseline-800.json

bench-baseline:
	uv run arbiter bench --spec $(SPEC) --dataset $(DATASET) --out bench/baseline-800.json

gen:
	uv run arbiter-datagen gen --scenario $(SCENARIO) --records $(RECORDS) --seed $(SEED) --out $(DATASET)

api:
	uv run arbiter-api

web:
	cd web && pnpm dev

up:
	( uv run arbiter-api & cd web && pnpm dev ) ; wait

test: install
	uv run pytest -m "not live"

lint:
	uv run ruff check . && uv run ruff format --check .
	cd web && pnpm lint

typecheck:
	uv run mypy packages/engine/arbiter_engine packages/datagen/arbiter_datagen packages/api/arbiter_api
	cd web && pnpm typecheck

clean:
	rm -rf data/ datasets/generated/ web/.next
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
