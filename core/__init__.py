"""Core application for InsightZen.

This package contains the models, views, forms, templates and other
supporting code that powers the main functionality of the InsightZen
application. By grouping related logic into this app, the codebase stays
organised and easier to maintain.

The ``default_app_config`` attribute below tells Django to use our
custom ``CoreConfig`` class.  ``CoreConfig`` implements a ``ready()``
method which prompts the developer on first run to optionally load
sample data from a remote PostgreSQL database into the local
``Person`` and ``Mobile`` tables.  Without this line, Django would
fallback to a default configuration and the prompt would never run.
"""

default_app_config = 'core.apps.CoreConfig'