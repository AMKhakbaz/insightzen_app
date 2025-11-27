"""Application configuration for the core app.

This module defines a custom ``AppConfig`` for the ``core`` app.  The
configuration is intentionally lightweight so Django can start without
performing database access or prompting for console input during
``ready()`` execution.  Data-import utilities live in dedicated
management commands.
"""

from __future__ import annotations

from django.apps import AppConfig


class CoreConfig(AppConfig):
    """Custom AppConfig for the core application."""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'

    def ready(self) -> None:
        """Perform application setup.

        ``ready()`` intentionally avoids touching the database or prompting
        for input.  Data-import flows live in management commands so
        startup remains safe in interactive and non-interactive contexts.
        """
        return None