#!/bin/bash

PELICAN_PORT=${PELICAN_PORT:-8081}

# (git) repos dependencies
./setup.sh

# python environment
poetry install

# [Semantic Versioning 2.0.0](https://semver.org/)
# [notice] A new release of pip is available: major.minor.patch -> new_major.new_minor.new_patch
# [notice] To update, run: pip install --upgrade pip
pip install --upgrade pip

# pelican themes & plugins
./add_extras_pelican-themes.sh
./add_extras_pelican-plugins.sh
# set custom theme
poetry run pelican-themes -vi pelican-themes/blueidea-custom

pushd pelican

# launch local dev server
x-www-browser 127.0.0.1:"$PELICAN_PORT" && PORT="$PELICAN_PORT" poetry run make devserver

popd