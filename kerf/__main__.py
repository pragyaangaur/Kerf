"""Allow `python -m kerf` to run the command line."""

from .cli import main

raise SystemExit(main())
