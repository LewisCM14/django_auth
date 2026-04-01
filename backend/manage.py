#!/usr/bin/env python
"""Django management command entry point.

Provides a command-line interface for running Django management tasks
(e.g., 'python manage.py runserver', 'python manage.py migrate').
"""
import os
import sys


def main() -> None:
    """Execute Django management command from command-line arguments.
    
    Raises:
        ImportError: If Django is not installed or not on PYTHONPATH.
    """
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and available on your "
            "PYTHONPATH environment variable? Did you forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
