#!/usr/bin/env bash
set -eo pipefail

pip install twine
# From https://pypi.org/project/twine/
rm -fr dist/
python setup.py sdist bdist_wheel
twine upload dist/*
