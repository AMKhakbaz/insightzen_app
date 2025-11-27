"""Core application for InsightZen.

This package contains the models, views, forms, templates and other
supporting code that powers the main functionality of the InsightZen
application. By grouping related logic into this app, the codebase stays
organised and easier to maintain.

The ``default_app_config`` attribute below tells Django to use our
custom ``CoreConfig`` class.  ``CoreConfig`` is intentionally
lightweight; tasks such as loading the respondent bank now live in
management commands (see ``import_respondent_bank``) so application
startup never prompts for input or queries the database unexpectedly.
"""

default_app_config = 'core.apps.CoreConfig'