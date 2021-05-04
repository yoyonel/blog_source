#!/bin/bash

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
x-www-browser 127.0.0.1:8081 && PORT=8081 poetry run make devserver

popd