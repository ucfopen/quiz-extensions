include .env

COMPOSE_FILE=docker-compose.yml
DOCKER_COMPOSE=docker compose -f $(COMPOSE_FILE)

BLACK        := $(shell tput -Txterm setaf 0)
RED          := $(shell tput -Txterm setaf 1)
GREEN        := $(shell tput -Txterm setaf 2)
YELLOW       := $(shell tput -Txterm setaf 3)
LIGHTPURPLE  := $(shell tput -Txterm setaf 4)
PURPLE       := $(shell tput -Txterm setaf 5)
BLUE         := $(shell tput -Txterm setaf 6)
WHITE        := $(shell tput -Txterm setaf 7)
RESET := $(shell tput -Txterm sgr0)

default: build

#==============================================
# Building and cleaning the Docker environment
#==============================================
build: ## Build all Docker images
	@echo "Building Quiz Extensions LTI Docker images"
	@$(DOCKER_COMPOSE) build

clean:  ## Stops and removes existing existing containers and volumes
	@echo "${YELLOW}Stopping running containers and purging existing volumes${RESET}"
	$(DOCKER_COMPOSE) down -v
	@echo "Rebuilding images"

#================================================================================
# Managing the Docker environment (e.g. starting, stopping, deleting containers)
#================================================================================

start: start-daemon ## Start Quiz Extensions LTI (default: daemon mode)

start-attached: ## Start Quiz Extensions LTI in attached mode
	@echo "${GREEN}Starting Quiz Extensions LTI in attached mode${RESET}"
	$(DOCKER_COMPOSE) up

start-daemon: ## Start Quiz Extensions LTI in daemon mode
	@echo "${GREEN}Starting Quiz Extensions LTI in daemon mode${RESET}"
	@echo "Run \`make start-attached\` to run in attached mode, or view container logs with \`make logs\`"
	$(DOCKER_COMPOSE) up -d

stop: ## Stop all containers
	@echo "${YELLOW}Stopping all containers${RESET}"
	$(DOCKER_COMPOSE) stop

logs: ## View container logs (optionally specifying a service name, like `quiz_extensions` or `quiz_db`)
	$(DOCKER_COMPOSE) logs --tail 10 -f $(filter-out $@,$(MAKECMDGOALS))

#==============================================
# Application management commands
#==============================================

test-all: ## Run all unit tests
	$(DOCKER_COMPOSE) run --rm quiz_extensions python -m unittest

lint: ## Run Python linter (flake8)
	${DOCKER_COMPOSE} run --rm quiz_extensions flake8 .

format: ## Run Python code formatter (black) and import sorter (isort). Will fix formatting errors.
	${DOCKER_COMPOSE} run --rm quiz_extensions sh -c "black . && isort ."

format-check: ## Run Python code formatter (black) and import sorter (isort) in check mode. Will not alter files.
	${DOCKER_COMPOSE} run --rm quiz_extensions sh -c "black . --check && isort . --check-only"

lint-format: ## Run Python code formatter (black), import sorter (isort), and linter (flake8). Will fix formatting errors but not linting errors.
	${DOCKER_COMPOSE} run --rm quiz_extensions sh -c "black . && isort . && flake8 ."

lint-format-check: ## Run Python code formatter (black) and import sorter (isort) in check mode, and linter (flake8). Will not alter files.
	${DOCKER_COMPOSE} run --rm quiz_extensions sh -c "black . --check && isort . --check-only && flake8 ."

migrate-create: ## Create a new DB migration
	${DOCKER_COMPOSE} run --rm quiz_extensions flask db migrate

migrate-run: ## Run an existing DB migration
	${DOCKER_COMPOSE} run --rm quiz_extensions flask db upgrade

shell: ## Run shell in Flask context
	${DOCKER_COMPOSE} run --rm quiz_extensions flask shell

generate-keys: ## Create new public and private keys and assign them to a keyset
	${DOCKER_COMPOSE} run --rm quiz_extensions flask generate_keys

register: ## Add a new registration for Quiz Extensions in a platform
	${DOCKER_COMPOSE} run --rm quiz_extensions flask register

deploy: ## Add a new deployment for Quiz Extensions to an existing registration
	${DOCKER_COMPOSE} run --rm quiz_extensions flask deploy

.PHONY: help
help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'
