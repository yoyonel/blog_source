#!/bin/bash

PELICAN_PORT=${PELICAN_PORT:-8081}

# (git) repos dependencies
./setup.sh

# python environment
poetry install

# pelican themes & plugins
./add_extras_pelican-themes.sh
./add_extras_pelican-plugins.sh
# set custom theme
poetry run pelican-themes -vi pelican-themes/blueidea-custom

pushd pelican

# launch local dev server
x-www-browser 127.0.0.1:"$PELICAN_PORT" && PORT="$PELICAN_PORT" poetry run make devserver

popd