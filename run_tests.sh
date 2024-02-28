#!/bin/sh

# Run the commands in a new container
docker compose run --rm lti sh -c "
    coverage run -m unittest discover &&
    coverage report &&
    coverage html &&
    flake8 . &&
    black --check . --exclude 'env|migrations'
"
docker compose down
