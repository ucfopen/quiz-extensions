#!/bin/sh

docker compose run lti coverage run -m unittest discover
docker compose run lti coverage report
docker compose run lti coverage html
docker compose run lti flake8 .
docker compose run lti black --check . --exclude "env|migrations"
