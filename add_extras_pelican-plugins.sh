#!/usr/bin/env bash
set -e

pushd pelican-plugins

git submodule add --force https://notabug.org/jorgesumle/pelican-css.git
git submodule add --force https://notabug.org/jorgesumle/pelican-js.git

popd
