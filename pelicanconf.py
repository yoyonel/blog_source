AUTHOR = "YoYoNeL"
SITENAME = "Bloggy le Blog"
SITEURL = ""

PATH = "content"

THEME = "themes/Flex"
THEME_TEMPLATES_OVERRIDES = ["templates"]

TIMEZONE = "Europe/Paris"
DEFAULT_LANG = "fr"

# i18n
I18N_UNTRANSLATED_ARTICLES = "keep"
I18N_UNTRANSLATED_PAGES = "keep"

# Feeds (disabled in dev)
FEED_ALL_ATOM = None
CATEGORY_FEED_ATOM = None
TRANSLATION_FEED_ATOM = None
AUTHOR_FEED_ATOM = None
AUTHOR_FEED_RSS = None

# Blogroll
LINKS = (
    ("Pelican", "https://getpelican.com/"),
    ("Python.org", "https://python.org/"),
)

# Social
SOCIAL = (("github", "https://github.com/yoyonel"),)

DEFAULT_PAGINATION = 10

# Comments
DISQUS_SITENAME = "yoyonel"

# Plugins
PLUGIN_PATHS = ["plugins"]
PLUGINS = ["css_js_injector", "i18n_subsites"]

# i18n subsites
JINJA_ENVIRONMENT = {
    "extensions": ["jinja2.ext.i18n"],
}

I18N_SUBSITES = {
    "en": {
        "SITENAME": "Bloggy le Blog",
        "SITETITLE": "Bloggy le Blog",
        "SITESUBTITLE": "💻🎸🎞️ Dev, music & tinkering 🎦🎼🖥️",
        "SITEDESCRIPTION": "YoYoNeL's technical blog",
        "MENUITEMS": (
            ("Archives", "/en/archives.html"),
            ("Categories", "/en/categories.html"),
            ("Tags", "/en/tags.html"),
        ),
    },
}

# Static files
STATIC_PATHS = ["css", "js", "python", "images"]
ARTICLE_EXCLUDES = ["css", "js", "python", "images"]

# --- Flex theme settings ---
SITETITLE = "Bloggy le Blog"
SITESUBTITLE = "💻🎸🎞️ Dev, musique & bidouilles 🎦🎼🖥️"
SITEDESCRIPTION = "Blog technique de YoYoNeL"
SITELOGO = "/images/avatar.gif"

# Dark mode auto-detect (follows OS preference)
THEME_COLOR_AUTO_DETECT_BROWSER_PREFERENCE = True
THEME_COLOR_ENABLE_USER_OVERRIDE = True

# Markdown extensions
MARKDOWN = {
    "extension_configs": {
        "markdown.extensions.codehilite": {"css_class": "highlight"},
        "markdown.extensions.extra": {},
        "markdown.extensions.meta": {},
        "markdown.extensions.toc": {"permalink": False},
    },
    "output_format": "html5",
}

# Code highlighting
PYGMENTS_STYLE = "github"
PYGMENTS_STYLE_DARK = "monokai"

# Navbar
MAIN_MENU = True
MENUITEMS = (
    ("Archives", "/archives.html"),
    ("Catégories", "/categories.html"),
    ("Tags", "/tags.html"),
)
