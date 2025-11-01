#!/usr/bin/env python
"""
Entry point for the InsightZen Django project.

This script sets the default settings module for the ``django`` program and
then delegates execution to ``django.core.management.execute_from_command_line``.

It exists so that administrative commands (e.g. ``runserver``, ``migrate``)
can be executed from the command line. See Django's documentation for more
information on this file and its usage.
"""
import os
import sys


def main() -> None:
    """Run administrative tasks."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'insightzen.settings')
    try:
        from django.core.management import execute_from_command_line  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()