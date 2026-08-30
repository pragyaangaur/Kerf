"""Three way merge for parts, and the checks that make it safe."""

from .conflicts import Conflict, FileMerge, MergeResult
from .equations import detect_equation_breaks, introduced_issues
from .interference import detect_interference
from .parts import merge_feature, merge_parts, merge_vector
from .trees import merge_trees

__all__ = [
    "Conflict",
    "FileMerge",
    "MergeResult",
    "detect_equation_breaks",
    "detect_interference",
    "introduced_issues",
    "merge_feature",
    "merge_parts",
    "merge_trees",
    "merge_vector",
]
