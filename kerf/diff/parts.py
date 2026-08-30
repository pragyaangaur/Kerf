"""Comparing two versions of a feature tree.

This is the layer that produces a sentence a designer can act on. A mesh
comparison can say that material moved. A feature comparison can say that
bolt_d went from 3.4 to 3.6 and name the four holes that followed it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from ..parametric import Feature, Part, expression_dependencies, resolve


@dataclass
class FieldChange:
    """One value that differs, with both forms and both resolved numbers."""

    key: str
    old: Any
    new: Any
    old_value: Optional[float] = None
    new_value: Optional[float] = None

    @property
    def delta(self) -> Optional[float]:
        if self.old_value is None or self.new_value is None:
            return None
        return self.new_value - self.old_value

    @property
    def pct(self) -> Optional[float]:
        if self.old_value in (None, 0) or self.new_value is None:
            return None
        return (self.new_value - self.old_value) / abs(self.old_value) * 100.0

    def describe(self) -> str:
        def show(raw, value):
            if isinstance(raw, str) and value is not None:
                return f"{raw} = {value:g}"
            if isinstance(value, float):
                return f"{value:g}"
            return str(raw)

        text = f"{self.key}: {show(self.old, self.old_value)} -> {show(self.new, self.new_value)}"
        percent = self.pct
        if percent is not None and abs(percent) > 1e-9:
            text += f" ({percent:+.1f}%)"
        return text


@dataclass
class FeatureChange:
    id: str
    status: str          # added, removed, modified, reordered, suppressed, resumed
    label: str = ""
    changes: list[FieldChange] = field(default_factory=list)
    old_index: Optional[int] = None
    new_index: Optional[int] = None
    feature_type: str = ""


@dataclass
class ParametricDiff:
    parameters: list[FieldChange] = field(default_factory=list)
    parameters_added: dict[str, Any] = field(default_factory=dict)
    parameters_removed: dict[str, Any] = field(default_factory=dict)
    features: list[FeatureChange] = field(default_factory=list)
    renamed: list[tuple[str, str, str]] = field(default_factory=list)
    impact: dict[str, list[str]] = field(default_factory=dict)
    name_changed: Optional[tuple[str, str]] = None
    units_changed: Optional[tuple[str, str]] = None

    def empty(self) -> bool:
        return not (
            self.parameters
            or self.parameters_added
            or self.parameters_removed
            or self.features
            or self.renamed
            or self.name_changed
            or self.units_changed
        )


def _values(part: Part) -> dict[str, float]:
    try:
        return part.resolved_parameters()
    except Exception:                                # noqa: BLE001
        return {}


def _numeric(raw: Any, params: dict[str, float]) -> Optional[float]:
    try:
        return resolve(raw, params)
    except Exception:                                # noqa: BLE001
        return None


def diff_parts(old: Part, new: Part) -> ParametricDiff:
    """Compare two parts feature by feature and parameter by parameter."""
    result = ParametricDiff()
    old_values, new_values = _values(old), _values(new)

    if old.name != new.name:
        result.name_changed = (old.name, new.name)
    if old.units != new.units:
        result.units_changed = (old.units, new.units)

    for key in sorted(set(old.parameters) | set(new.parameters)):
        if key not in new.parameters:
            result.parameters_removed[key] = old.parameters[key]
        elif key not in old.parameters:
            result.parameters_added[key] = new.parameters[key]
        elif old.parameters[key] != new.parameters[key]:
            result.parameters.append(
                FieldChange(
                    key,
                    old.parameters[key],
                    new.parameters[key],
                    old_values.get(key),
                    new_values.get(key),
                )
            )

    changed_parameters = {change.key for change in result.parameters} | set(result.parameters_removed)
    if changed_parameters:
        for item in new.features:
            reads: set[str] = set()
            for value in item.params.values():
                if isinstance(value, (list, tuple)):
                    for element in value:
                        reads |= expression_dependencies(element)
                else:
                    reads |= expression_dependencies(value)
            for name in reads & changed_parameters:
                result.impact.setdefault(name, []).append(item.label())
        for key, value in new.parameters.items():
            for name in expression_dependencies(value) & changed_parameters:
                result.impact.setdefault(name, []).append(f"parameter {key}")

    old_ids = [item.id for item in old.features]
    new_ids = [item.id for item in new.features]
    old_position = {feature_id: i for i, feature_id in enumerate(old_ids)}
    new_position = {feature_id: i for i, feature_id in enumerate(new_ids)}

    for item in new.features:
        if item.id not in old_position:
            result.features.append(
                FeatureChange(
                    item.id, "added", item.label(),
                    new_index=new_position[item.id], feature_type=item.type,
                )
            )
    for item in old.features:
        if item.id not in new_position:
            result.features.append(
                FeatureChange(
                    item.id, "removed", item.label(),
                    old_index=old_position[item.id], feature_type=item.type,
                )
            )

    for feature_id in new_ids:
        if feature_id not in old_position:
            continue
        before, after = old.feature(feature_id), new.feature(feature_id)
        assert before and after
        if before.name != after.name:
            result.renamed.append((feature_id, before.name, after.name))
        changes = diff_feature_fields(before, after, old_values, new_values)
        if before.suppressed != after.suppressed:
            result.features.append(
                FeatureChange(
                    feature_id,
                    "suppressed" if after.suppressed else "resumed",
                    after.label(), changes,
                    old_position[feature_id], new_position[feature_id], after.type,
                )
            )
        elif changes:
            result.features.append(
                FeatureChange(
                    feature_id, "modified", after.label(), changes,
                    old_position[feature_id], new_position[feature_id], after.type,
                )
            )

    common = [feature_id for feature_id in new_ids if feature_id in old_position]
    if common != sorted(common, key=lambda fid: old_position[fid]):
        already = {change.id for change in result.features}
        as_before = sorted(common, key=lambda fid: old_position[fid])
        for feature_id in common:
            if as_before.index(feature_id) != common.index(feature_id) and feature_id not in already:
                item = new.feature(feature_id)
                result.features.append(
                    FeatureChange(
                        feature_id, "reordered", item.label(),
                        old_index=old_position[feature_id],
                        new_index=new_position[feature_id],
                        feature_type=item.type,
                    )
                )
    result.features.sort(
        key=lambda change: (change.new_index if change.new_index is not None else 1e9, change.id)
    )
    return result


def diff_feature_fields(
    before: Feature, after: Feature, old_values: dict, new_values: dict
) -> list[FieldChange]:
    """Compare the fields of one feature, splitting vectors per axis."""
    changes: list[FieldChange] = []
    if before.type != after.type:
        changes.append(FieldChange("type", before.type, after.type))
    if before.op != after.op:
        changes.append(FieldChange("op", before.op, after.op))
    for key in sorted(set(before.params) | set(after.params)):
        old_value, new_value = before.params.get(key), after.params.get(key)
        if old_value == new_value:
            continue
        if isinstance(old_value, (list, tuple)) or isinstance(new_value, (list, tuple)):
            old_list = list(old_value) if isinstance(old_value, (list, tuple)) else [old_value]
            new_list = list(new_value) if isinstance(new_value, (list, tuple)) else [new_value]
            axes = "xyz"
            for index in range(max(len(old_list), len(new_list))):
                a = old_list[index] if index < len(old_list) else None
                b = new_list[index] if index < len(new_list) else None
                if a != b:
                    suffix = axes[index] if index < 3 else index
                    changes.append(
                        FieldChange(f"{key}.{suffix}", a, b,
                                    _numeric(a, old_values), _numeric(b, new_values))
                    )
        else:
            changes.append(
                FieldChange(key, old_value, new_value,
                            _numeric(old_value, old_values), _numeric(new_value, new_values))
            )
    return changes
