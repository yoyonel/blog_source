#!/usr/bin/env python
# -*- coding: utf-8 -*- #
from __future__ import unicode_literals

AUTHOR = 'YoYoNeL'
SITENAME = '💻🎸🎞️ Bloggy le Blog 🎦🎼🖥️'
SITEURL = ''

PATH = 'content'

THEME = 'blueidea-custom'

TIMEZONE = 'Europe/Paris'

DEFAULT_LANG = 'fr'

# Feed generation is usually not desired when developing
FEED_ALL_ATOM = None
CATEGORY_FEED_ATOM = None
TRANSLATION_FEED_ATOM = None
AUTHOR_FEED_ATOM = None
AUTHOR_FEED_RSS = None

# Blogroll
LINKS = (('Pelican', 'http://getpelican.com/'),
         ('Python.org', 'http://python.org/'),
         ('Jinja2', 'http://jinja.pocoo.org/'),
         )

# Social widget
SOCIAL = (('Twitter', 'https://twitter.com/RenellYoyonel'),
          ('Github', 'https://github.com/yoyonel'),)

DEFAULT_PAGINATION = 10

# Uncomment following line if you want document-relative URLs when developing
#RELATIVE_URLS = True

# Comments
DISQUS_SITENAME = "yoyonel"

# Plugings
PLUGIN_PATHS = ["../pelican-plugins"]
PLUGINS = ['pelican-js', 'pelican-css']

# Theme settings
DISPLAY_AUTHOR_ON_POSTINFO = True
DISPLAY_CATEGORIES_ON_POSTINFO = True
DISPLAY_CATEGORIES_ON_SUBMENU = False