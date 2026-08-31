"""Grouping things that touch into connected components.

Two places need this. A mesh is split into separate bodies by following
shared vertices, and a voxel grid is split into regions by following shared
faces. Both were walking a union-find in Python, one edge at a time, which
is the slowest part of every diff on a mesh of any size.

The same answer comes out of repeated hooking and pointer jumping, which is
the array form of the same algorithm. Every edge is processed at once, and
the number of rounds is the depth of the tree rather than the number of
edges.
"""

from __future__ import annotations

import numpy as np


def connected_labels(count: int, edges: np.ndarray) -> tuple[np.ndarray, int]:
    """Label `count` nodes so that anything joined by an edge shares a label.

    Returns the label per node, numbered from zero and compacted, together
    with how many distinct groups there are. A node with no edges is its own
    group, so callers that only care about nodes in use should select those
    rows before counting.
    """
    root = np.arange(count, dtype=np.int64)
    if len(edges):
        left = np.asarray(edges[:, 0], dtype=np.int64)
        right = np.asarray(edges[:, 1], dtype=np.int64)
        while True:
            # Hook: every edge points the larger of its two roots at the
            # smaller one, so a group converges on its lowest member.
            a, b = root[left], root[right]
            nxt = root.copy()
            np.minimum.at(nxt, np.maximum(a, b), np.minimum(a, b))
            # Jump: follow each pointer to the end of its chain.
            while True:
                followed = nxt[nxt]
                if np.array_equal(followed, nxt):
                    break
                nxt = followed
            if np.array_equal(nxt, root):
                break
            root = nxt
    unique, compact = np.unique(root, return_inverse=True)
    return compact.reshape(count), len(unique)
