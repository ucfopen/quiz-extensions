#!/bin/sh

coverage run -m unittest discover
coverage report
coverage html
flake8 .
black --check . --exclude env
