#!/usr/bin/env python
"""Django's command-line utility for the SSRM demo project."""
import os
import sys
from pathlib import Path


def main():
    # Make the demo project importable when running this script directly.
    here = Path(__file__).resolve().parent
    sys.path.insert(0, str(here))
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'demo_project.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Run `uv sync --extra demo` first."
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
