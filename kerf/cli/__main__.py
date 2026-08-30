"""Allow `python -m kerf.cli` to run the command line."""

from .parser import main

raise SystemExit(main())
