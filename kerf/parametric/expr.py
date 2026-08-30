"""Parameter expressions.

Any numeric field in a part file may be written as an expression over the
parameter table, so `"radius": "bolt_d/2"` stays correct when bolt_d moves.
Expressions are read by walking a parsed syntax tree. Python's eval is never
called, because a part file is data that arrives from other people.
"""

from __future__ import annotations

import ast
import math
from typing import Any

import numpy as np

ALLOWED_FUNCTIONS = {
    "sqrt": math.sqrt, "sin": math.sin, "cos": math.cos, "tan": math.tan,
    "abs": abs, "min": min, "max": max, "round": round, "floor": math.floor,
    "ceil": math.ceil, "atan2": math.atan2, "radians": math.radians,
    "degrees": math.degrees, "hypot": math.hypot, "pow": math.pow,
}

ALLOWED_CONSTANTS = {"pi": math.pi, "tau": math.tau, "e": math.e}

BINARY_OPERATORS = {
    ast.Add: lambda a, b: a + b,
    ast.Sub: lambda a, b: a - b,
    ast.Mult: lambda a, b: a * b,
    ast.Div: lambda a, b: a / b,
    ast.Pow: lambda a, b: a ** b,
    ast.Mod: lambda a, b: a % b,
    ast.FloorDiv: lambda a, b: a // b,
}


class ExpressionError(ValueError):
    """Raised when an expression is malformed or uses something not allowed."""


def evaluate_expression(expression: str, params: dict[str, float]) -> float:
    """Evaluate one expression against a parameter table."""
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as error:
        raise ExpressionError(f"cannot parse expression {expression!r}: {error}") from error

    def walk(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return walk(node.body)
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
                return float(node.value)
            raise ExpressionError(f"unsupported constant {node.value!r}")
        if isinstance(node, ast.Name):
            if node.id in params:
                return float(params[node.id])
            if node.id in ALLOWED_CONSTANTS:
                return ALLOWED_CONSTANTS[node.id]
            raise ExpressionError(f"unknown parameter {node.id!r}")
        if isinstance(node, ast.BinOp) and type(node.op) in BINARY_OPERATORS:
            return BINARY_OPERATORS[type(node.op)](walk(node.left), walk(node.right))
        if isinstance(node, ast.UnaryOp):
            if isinstance(node.op, ast.USub):
                return -walk(node.operand)
            if isinstance(node.op, ast.UAdd):
                return walk(node.operand)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            function = ALLOWED_FUNCTIONS.get(node.func.id)
            if function is None:
                raise ExpressionError(f"function {node.func.id!r} is not allowed")
            return float(function(*[walk(argument) for argument in node.args]))
        raise ExpressionError(f"unsupported syntax in expression {expression!r}")

    return walk(tree)


def resolve(value: Any, params: dict[str, float]) -> float:
    """Turn a literal or an expression into a number."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, str):
        return evaluate_expression(value, params)
    raise ExpressionError(f"expected a number or expression, got {value!r}")


def resolve_vec(value: Any, params: dict[str, float], default=(0.0, 0.0, 0.0)) -> np.ndarray:
    """Turn a three element list of literals or expressions into a vector."""
    if value is None:
        return np.asarray(default, dtype=float)
    return np.asarray([resolve(item, params) for item in value], dtype=float)


def expression_dependencies(value: Any) -> set[str]:
    """Names an expression reads.

    This is what lets kerf answer "what does this parameter drive". When
    bolt_d changes, the features whose expressions mention bolt_d are the
    features that changed with it.
    """
    if not isinstance(value, str):
        return set()
    try:
        tree = ast.parse(value, mode="eval")
    except SyntaxError:
        return set()
    return {
        node.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Name)
        and node.id not in ALLOWED_CONSTANTS
        and node.id not in ALLOWED_FUNCTIONS
    }
