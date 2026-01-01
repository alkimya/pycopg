# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

import os
import sys

# Add pycopg to path for autodoc
sys.path.insert(0, os.path.abspath('..'))

# -- Project information -----------------------------------------------------

project = 'pycopg'
copyright = '2026, Loc Cosnier <loc.cosnier@pm.me>'
author = 'Loc Cosnier'
release = '0.1.0'

# -- General configuration ---------------------------------------------------

extensions = [
    'myst_parser',           # Markdown support
    'sphinx.ext.autodoc',    # Auto-generate from docstrings
    'sphinx.ext.viewcode',   # Add links to source code
    'sphinx.ext.napoleon',   # Google/NumPy docstring support
    'sphinx.ext.intersphinx', # Link to other projects
]

# MyST parser settings
myst_enable_extensions = [
    "colon_fence",    # ::: fence for directives
    "deflist",        # Definition lists
    "tasklist",       # Task lists
]

templates_path = ['_templates']
exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']

# Source file suffixes
source_suffix = {
    '.rst': 'restructuredtext',
    '.md': 'markdown',
}

# The master toctree document
master_doc = 'index'

# -- Options for HTML output -------------------------------------------------

html_theme = 'furo'  # Modern, clean theme
html_static_path = ['_static']

# Theme options
html_theme_options = {
    "light_css_variables": {
        "color-brand-primary": "#4F46E5",
        "color-brand-content": "#4F46E5",
    },
    "dark_css_variables": {
        "color-brand-primary": "#818CF8",
        "color-brand-content": "#818CF8",
    },
}

# -- Options for autodoc -----------------------------------------------------

autodoc_default_options = {
    'members': True,
    'member-order': 'bysource',
    'special-members': '__init__',
    'undoc-members': True,
    'show-inheritance': True,
}

# -- Intersphinx configuration -----------------------------------------------

intersphinx_mapping = {
    'python': ('https://docs.python.org/3', None),
    'pandas': ('https://pandas.pydata.org/docs/', None),
    'geopandas': ('https://geopandas.org/en/stable/', None),
}
