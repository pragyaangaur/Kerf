"""Errors the repository raises."""

from __future__ import annotations


class RepoError(Exception):
    """Something the user asked for cannot be done, with a reason attached."""
