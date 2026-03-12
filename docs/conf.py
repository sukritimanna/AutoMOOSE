"""Sphinx configuration for AutoMOOSE documentation."""

import os
import sys

# -- Path setup --------------------------------------------------------------
sys.path.insert(0, os.path.abspath('..'))

# -- Project information -----------------------------------------------------
project = 'AutoMOOSE'
copyright = '2026, AutoMOOSE Contributors'
author = 'AutoMOOSE Contributors'
release = '2.0'
version = '2.0'

# -- General configuration ---------------------------------------------------
extensions = [
    'sphinx.ext.autodoc',
    'sphinx.ext.napoleon',
    'sphinx.ext.viewcode',
    'sphinx.ext.intersphinx',
    'sphinx.ext.autosummary',
    'myst_parser',
]

templates_path = ['_templates']
exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']
source_suffix = {
    '.rst': 'restructuredtext',
    '.md': 'markdown',
}

# -- Options for HTML output -------------------------------------------------
html_theme = 'furo'
html_static_path = ['_static']
html_logo = '_static/AutoMOOSE.png'
html_title = 'AutoMOOSE'
html_favicon = '_static/AutoMOOSE.png'

html_theme_options = {
    "light_css_variables": {
        "color-brand-primary": "#1a2744",      # deep navy
        "color-brand-content": "#c0392b",      # burnt orange/red
    },
    "dark_css_variables": {
        "color-brand-primary": "#e07b54",
        "color-brand-content": "#e07b54",
    },
    "sidebar_hide_name": False,
    "navigation_with_keys": True,
}

# -- Autodoc -----------------------------------------------------------------
autodoc_default_options = {
    'members': True,
    'undoc-members': False,
    'show-inheritance': True,
}
napoleon_google_docstring = True
napoleon_numpy_docstring = True

# -- Intersphinx -------------------------------------------------------------
intersphinx_mapping = {
    'python': ('https://docs.python.org/3', None),
}
