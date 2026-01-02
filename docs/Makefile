# Minimal makefile for Sphinx documentation

# You can set these variables from the command line, and also
# from the environment for the first two.
SPHINXOPTS    ?=
SPHINXBUILD   ?= sphinx-build
SOURCEDIR     = .
BUILDDIR      = _build

# Put it first so that "make" without argument is like "make help".
help:
	@$(SPHINXBUILD) -M help "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)

.PHONY: help Makefile

# Catch-all target: route all unknown targets to Sphinx using the new
# "make mode" option.  $(O) is meant as a shortcut for $(SPHINXOPTS).
%: Makefile
	@$(SPHINXBUILD) -M $@ "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)

# Custom targets
livehtml:
	sphinx-autobuild "$(SOURCEDIR)" "$(BUILDDIR)/html" $(SPHINXOPTS) $(O)

# Internationalization targets
gettext:
	@$(SPHINXBUILD) -b gettext "$(SOURCEDIR)" "$(BUILDDIR)/gettext" $(SPHINXOPTS) $(O)

# Update .po files for a language (usage: make update-po LANG=fr)
update-po: gettext
	sphinx-intl update -p "$(BUILDDIR)/gettext" -l $(LANG)

# Build HTML for a specific language (usage: make html-fr)
html-%:
	@$(SPHINXBUILD) -b html -D language=$* "$(SOURCEDIR)" "$(BUILDDIR)/html/$*" $(SPHINXOPTS) $(O)

# Initialize French translation
init-fr: gettext
	sphinx-intl update -p "$(BUILDDIR)/gettext" -l fr

# Build all languages (EN + FR)
html-all: html-en html-fr
	@echo "Creating index redirect..."
	@echo '<!DOCTYPE html><html><head><meta http-equiv="refresh" content="0; url=en/index.html"></head></html>' > "$(BUILDDIR)/html/index.html"

.PHONY: gettext update-po init-fr html-all
