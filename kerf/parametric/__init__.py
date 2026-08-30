"""The native part format and the geometry it evaluates to."""

from .expr import (
    ExpressionError,
    evaluate_expression,
    expression_dependencies,
    resolve,
    resolve_vec,
)
from .features import FEATURE_TYPES, OPS, Feature
from .part import Part
from .sdf import feature_bounds, feature_sdf
from .tessellate import surface_nets

__all__ = [
    "ExpressionError",
    "FEATURE_TYPES",
    "Feature",
    "OPS",
    "Part",
    "evaluate_expression",
    "expression_dependencies",
    "feature_bounds",
    "feature_sdf",
    "resolve",
    "resolve_vec",
    "surface_nets",
]
