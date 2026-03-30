import os
import sys

sys.path.append(os.curdir)
from pelicanconf import *

SITEURL = os.environ.get("PELICAN_SITEURL", "https://yoyonel.github.io")
RELATIVE_URLS = False

FEED_ALL_ATOM = "feeds/all.atom.xml"
CATEGORY_FEED_ATOM = "feeds/{slug}.atom.xml"

DELETE_OUTPUT_DIRECTORY = True

DISQUS_SITENAME = "yoyonel"
# NOTE: Universal Analytics (UA-) is deprecated since July 2024.
# Replace with a GA4 Measurement ID (G-XXXXXXXXXX) if needed.
GOOGLE_ANALYTICS = "UA-155727660-1"
