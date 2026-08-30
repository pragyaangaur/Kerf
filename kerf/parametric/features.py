"""One feature in a part's history.

The id is the important field. It is the key a three way merge uses, so it
tells kerf the difference between "this hole moved" and "that hole was
deleted and a new one added". Renaming the human label is cosmetic, and
changing the id is not.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

FEATURE_TYPES = {"box", "cylinder", "sphere", "torus"}
OPS = {"add", "subtract", "intersect"}


@dataclass
class Feature:
    id: str
    type: str
    op: str = "add"
    name: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    suppressed: bool = False

    @staticmethod
    def from_dict(raw: dict) -> "Feature":
        reserved = {"id", "type", "op", "name", "suppressed"}
        feature_id = raw.get("id")
        if not feature_id:
            raise ValueError("every feature needs a stable 'id'")
        if raw.get("type") not in FEATURE_TYPES:
            raise ValueError(f"feature {feature_id}: unknown type {raw.get('type')!r}")
        if raw.get("op", "add") not in OPS:
            raise ValueError(f"feature {feature_id}: unknown op {raw.get('op')!r}")
        return Feature(
            id=str(feature_id),
            type=raw["type"],
            op=raw.get("op", "add"),
            name=raw.get("name", ""),
            suppressed=bool(raw.get("suppressed", False)),
            params={k: v for k, v in raw.items() if k not in reserved},
        )

    def to_dict(self) -> dict:
        out: dict[str, Any] = {"id": self.id, "type": self.type, "op": self.op}
        if self.name:
            out["name"] = self.name
        if self.suppressed:
            out["suppressed"] = True
        out.update(self.params)
        return out

    def label(self) -> str:
        """What a person should see in a diff."""
        return self.name or f"{self.type}:{self.id}"

    def fields(self) -> dict[str, Any]:
        """Everything about the feature except its identity, for comparison."""
        out = dict(self.params)
        out["_type"] = self.type
        out["_op"] = self.op
        out["_suppressed"] = self.suppressed
        return out
