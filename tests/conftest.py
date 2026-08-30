"""Helpers shared by the test modules."""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kerf.parametric import Part                     # noqa: E402

CUBE = [{"id": "b", "type": "box", "op": "add", "name": "body", "size": [20, 20, 20]}]


def part(features, params=None, name="p") -> Part:
    """Build a part from a list of feature dicts."""
    return Part.loads(json.dumps({
        "kerf_part": 1,
        "name": name,
        "units": "mm",
        "parameters": params or {},
        "features": features,
    }))
