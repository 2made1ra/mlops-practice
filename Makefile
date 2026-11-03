#################################################################################
# GLOBALS                                                                       #
#################################################################################

PROJECT_NAME = mlops-practice
# Use uv from PATH; fall back to the location where the official installer puts it.
UV ?= $(shell command -v uv 2>/dev/null || echo $(HOME)/.local/bin/uv)

#################################################################################
# COMMANDS                                                                      #
#################################################################################


## Set up the environment from scratch: uv, Python, all deps and git pre-commit hooks
.PHONY: setup
setup:
	@command -v $(UV) >/dev/null 2>&1 || curl -LsSf https://astral.sh/uv/install.sh | sh
	$(UV) sync --locked
	$(UV) run --locked pre-commit install --install-hooks


## Run all checks (style and types) without modifying files
.PHONY: check
check:
	$(UV) run --locked ruff check
	$(UV) run --locked ruff format --check
	$(UV) run --locked mypy


## Auto-fix lint issues and reformat code (modifies files)
.PHONY: format
format:
	$(UV) run --locked ruff check --fix
	$(UV) run --locked ruff format


## Build the processed dataset from raw/ and publish it to S3 (VERSION, SEED, VAL_SIZE)
VERSION ?= v1
SEED ?= 42
VAL_SIZE ?= 5000
.PHONY: data
data:
	$(UV) run --locked python -m mlops_practice.publish --version $(VERSION) --check
	$(UV) run --locked python -m mlops_practice.download
	$(UV) run --locked python -m mlops_practice.convert
	$(UV) run --locked python -m mlops_practice.split --val-size $(VAL_SIZE) --seed $(SEED)
	$(UV) run --locked python -m mlops_practice.stats
	$(UV) run --locked python -m mlops_practice.publish --version $(VERSION)


## Delete all compiled Python files and tool caches
.PHONY: clean
clean:
	find . -type f -name "*.py[co]" -delete
	find . -type d -name "__pycache__" -delete
	rm -rf .mypy_cache .ruff_cache


#################################################################################
# Self Documenting Commands                                                     #
#################################################################################

.DEFAULT_GOAL := help

define PRINT_HELP_PYSCRIPT
import re, sys; \
lines = '\n'.join([line for line in sys.stdin]); \
matches = re.findall(r'\n## (.*)\n[\s\S]+?\n([a-zA-Z_-]+):', lines); \
print('Available rules:\n'); \
print('\n'.join(['{:25}{}'.format(*reversed(match)) for match in matches]))
endef
export PRINT_HELP_PYSCRIPT

.PHONY: help
help:
	@$(UV) run --no-project python -c "${PRINT_HELP_PYSCRIPT}" < $(MAKEFILE_LIST)
