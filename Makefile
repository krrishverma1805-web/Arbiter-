.PHONY: help install demo run bench test lint typecheck clean

SPEC ?= specs/razorpay-settlement.yaml
DATASET ?= datasets/seed
SCENARIO ?= d2c
RECORDS ?= 120
SEED ?= 42

help:
	@echo "Arbiter — make targets"
	@echo "  install    uv sync (create the dev environment)"
	@echo "  demo       generate a seed dataset, run reconciliation, print the summary"
	@echo "  run        arbiter run --spec \$$(SPEC) --dataset \$$(DATASET)"
	@echo "  test       pytest (all packages)"
	@echo "  lint       ruff check"
	@echo "  typecheck  mypy the engine"
	@echo "  clean      remove data/ and generated datasets"

install:
	uv sync --all-packages

$(DATASET)/manifest.json:
	uv run arbiter-datagen gen --scenario $(SCENARIO) --records $(RECORDS) --seed $(SEED) --out $(DATASET)

demo: install $(DATASET)/manifest.json
	uv run arbiter run --spec $(SPEC) --dataset $(DATASET)

run:
	uv run arbiter run --spec $(SPEC) --dataset $(DATASET)

gen:
	uv run arbiter-datagen gen --scenario $(SCENARIO) --records $(RECORDS) --seed $(SEED) --out $(DATASET)

test: install
	uv run pytest

lint:
	uv run ruff check .

typecheck:
	uv run mypy packages/engine/arbiter_engine

clean:
	rm -rf data/ datasets/generated/
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
