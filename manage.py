#!/usr/bin/env python
"""Django management entrypoint. Defaults to dev settings; prod overrides via env."""

import os
import sys


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Activate the .venv and install requirements.txt first."
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
