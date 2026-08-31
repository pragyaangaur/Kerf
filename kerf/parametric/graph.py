"""The equation graph.

CAD models are held together by equations. A dimension is rarely a number.
It is `bolt_d/2`, and that expression is the design intent the author wrote
down. Kerf already reads those expressions to evaluate geometry, so the graph
they form is available for free, and it answers questions no file comparison
can reach.

The graph has two kinds of node. A parameter node is a named value, and it
may read other parameters. A field node is one numeric field on one feature,
such as the z component of a hole's centre, and it reads parameters only.
Edges point from what is read to what reads it, so following an edge forwards
answers "what does this drive".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .expr import expression_dependencies
from .features import ENUM_KEYS

RESERVED_FEATURE_KEYS = {"id", "type", "op", "name", "suppressed"} | ENUM_KEYS


@dataclass
class FieldRef:
    """One numeric field on one feature, and the parameters it reads."""

    feature_id: str
    feature_label: str
    key: str                 # "radius", or "center.z" for one part of a vector
    expression: Any
    reads: set[str] = field(default_factory=set)

    @property
    def name(self) -> str:
        return f"{self.feature_id}.{self.key}"


@dataclass
class ParameterRef:
    name: str
    expression: Any
    reads: set[str] = field(default_factory=set)

    @property
    def is_literal(self) -> bool:
        return not isinstance(self.expression, str)


@dataclass
class EquationGraph:
    parameters: dict[str, ParameterRef] = field(default_factory=dict)
    fields: list[FieldRef] = field(default_factory=list)

    def readers_of(self, name: str) -> list[str]:
        """Everything that reads this name directly."""
        found = [p.name for p in self.parameters.values() if name in p.reads]
        found += [f.name for f in self.fields if name in f.reads]
        return sorted(found)

    def downstream(self, name: str) -> set[str]:
        """Everything this name reaches, however many steps away."""
        seen: set[str] = set()
        frontier = [name]
        while frontier:
            current = frontier.pop()
            for reader in self.readers_of(current):
                if reader in seen:
                    continue
                seen.add(reader)
                if reader in self.parameters:
                    frontier.append(reader)
        return seen

    def upstream(self, name: str) -> set[str]:
        """Every parameter this name depends on, however many steps away."""
        seen: set[str] = set()
        start = self.parameters.get(name)
        frontier = list(start.reads) if start else []
        while frontier:
            current = frontier.pop()
            if current in seen:
                continue
            seen.add(current)
            parent = self.parameters.get(current)
            if parent:
                frontier.extend(parent.reads)
        return seen

    def feature_readers_of(self, name: str) -> list[str]:
        """Feature labels that end up depending on this parameter."""
        reached = self.downstream(name) | {name}
        labels = []
        for ref in self.fields:
            if ref.reads & reached:
                labels.append(ref.feature_label)
        seen: set[str] = set()
        ordered = []
        for label in labels:
            if label not in seen:
                seen.add(label)
                ordered.append(label)
        return ordered

    def dangling(self) -> list[tuple[str, str]]:
        """References to names the parameter table does not define.

        A part with one of these cannot be evaluated. In a CAD system this is
        the rebuild error that appears the moment somebody deletes a variable
        another dimension was using.
        """
        known = set(self.parameters)
        missing: list[tuple[str, str]] = []
        for ref in self.parameters.values():
            for name in sorted(ref.reads - known):
                missing.append((f"parameter {ref.name}", name))
        for ref in self.fields:
            for name in sorted(ref.reads - known):
                missing.append((ref.name, name))
        return missing

    def cycles(self) -> list[list[str]]:
        """Parameter loops, reported as the names that take part in each."""
        colour: dict[str, int] = {}
        found: list[list[str]] = []
        stack: list[str] = []

        def visit(name: str) -> None:
            colour[name] = 1
            stack.append(name)
            for read in sorted(self.parameters[name].reads):
                if read not in self.parameters:
                    continue
                if colour.get(read, 0) == 0:
                    visit(read)
                elif colour.get(read) == 1:
                    start = stack.index(read)
                    found.append(stack[start:] + [read])
            stack.pop()
            colour[name] = 2

        for name in sorted(self.parameters):
            if colour.get(name, 0) == 0:
                visit(name)
        return found

    def order(self) -> list[str]:
        """Parameters in an order where each comes after what it reads."""
        resolved: list[str] = []
        seen: set[str] = set()

        def visit(name: str, path: set[str]) -> None:
            if name in seen or name not in self.parameters:
                return
            if name in path:
                return                       # a cycle, reported separately
            for read in sorted(self.parameters[name].reads):
                visit(read, path | {name})
            seen.add(name)
            resolved.append(name)

        for name in sorted(self.parameters):
            visit(name, set())
        return resolved

    def roots(self) -> list[str]:
        """Parameters that read nothing, which is where a design starts."""
        return sorted(name for name, ref in self.parameters.items() if not ref.reads)

    def leaves(self) -> list[str]:
        """Parameters nothing reads. Often a leftover nobody removed."""
        return sorted(
            name for name in self.parameters if not self.readers_of(name)
        )


def build_graph(part) -> EquationGraph:
    """Read the equations out of a part."""
    graph = EquationGraph()
    for name, expression in part.parameters.items():
        graph.parameters[name] = ParameterRef(
            name=name, expression=expression, reads=expression_dependencies(expression)
        )

    for feature in part.features:
        label = feature.label()
        for key, value in feature.params.items():
            if key in RESERVED_FEATURE_KEYS:
                continue
            if isinstance(value, (list, tuple)):
                axes = "xyz"
                for index, item in enumerate(value):
                    reads = expression_dependencies(item)
                    if not reads:
                        continue
                    suffix = axes[index] if index < 3 else str(index)
                    graph.fields.append(
                        FieldRef(feature.id, label, f"{key}.{suffix}", item, reads)
                    )
            else:
                reads = expression_dependencies(value)
                if reads:
                    graph.fields.append(FieldRef(feature.id, label, key, value, reads))
    return graph


def format_graph(graph: EquationGraph, values: dict[str, float] | None = None) -> list[str]:
    """A readable listing of the equations, in dependency order."""
    values = values or {}
    lines: list[str] = []
    ordered = graph.order()
    remaining = [name for name in sorted(graph.parameters) if name not in ordered]
    for name in ordered + remaining:
        ref = graph.parameters[name]
        shown = f"{ref.expression}"
        if isinstance(ref.expression, str) and name in values:
            shown = f"{ref.expression} = {values[name]:g}"
        readers = graph.feature_readers_of(name)
        tail = ""
        if readers:
            listed = ", ".join(readers[:3])
            extra = f" and {len(readers) - 3} more" if len(readers) > 3 else ""
            tail = f"   drives {listed}{extra}"
        lines.append(f"{name} = {shown}{tail}")
    return lines
