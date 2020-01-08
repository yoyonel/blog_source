#!/usr/bin/env bash
set -e

pushd pelican-themes

git submodule add --force git@github.com:yoyonel/pelican-blueidea.git blueidea-custom

popd
