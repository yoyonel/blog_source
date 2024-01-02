#!/bin/bash

# This script sets up the blog development environment

if [[ ! -d .git ]]; then
    git init
    git remote add origin git@github.com:yoyonel/blog_source.git
fi


# $ git flow init --help
# usage: git flow init [-h] [-d] [-f]
# 
#     Setup a git repository for git flow usage. Can also be used to start a git repository.
#    -d, --[no]defaults    Use default branch naming conventions
#    -f, --[no]force       Force setting of gitflow branches, even if already configured
git flow init -d -f


if [[ ! -d pelican-plugins ]]; then
    git clone https://github.com/getpelican/pelican-plugins.git pelican-plugins
fi

if [[ ! -d pelican-themes ]]; then
    git clone https://github.com/getpelican/pelican-themes.git pelican-themes
fi

if [[ ! -d deploy ]]; then
    mkdir deploy
    cd deploy
    git init
    git remote add origin git@github.com:yoyonel/yoyonel.github.io.git
fi

