"""The native part format and the geometry it evaluates to."""

from .expr import (
    ExpressionError,
    evaluate_expression,
    expression_dependencies,
    resolve,
    resolve_vec,
)
from .features import ENUM_KEYS, FEATURE_TYPES, OPS, Feature
from .graph import EquationGraph, FieldRef, ParameterRef, build_graph, format_graph
from .part import Part
from .sdf import feature_bounds, feature_sdf
from .sweep import SweepPoint, SweepResult, default_range, sweep_all, sweep_parameter
from .tessellate import surface_nets
from .validity import (
    ModelIssue,
    check_equations,
    check_part,
    inspect_part,
    is_buildable,
    measure_solid,
)

__all__ = [
    "ENUM_KEYS",
    "EquationGraph",
    "ExpressionError",
    "FEATURE_TYPES",
    "Feature",
    "FieldRef",
    "ModelIssue",
    "OPS",
    "ParameterRef",
    "Part",
    "SweepPoint",
    "SweepResult",
    "build_graph",
    "check_equations",
    "check_part",
    "inspect_part",
    "default_range",
    "format_graph",
    "is_buildable",
    "measure_solid",
    "sweep_all",
    "sweep_parameter",
    "evaluate_expression",
    "expression_dependencies",
    "feature_bounds",
    "feature_sdf",
    "resolve",
    "resolve_vec",
    "surface_nets",
]
