"""
Cardinality Control Module

Provides cardinality tracking and enforcement to prevent series explosions.
"""

from .tracker import (
    CardinalityTracker,
    get_cardinality_tracker,
    initialize_cardinality_tracker,
    LABEL_DENYLIST,
    LABEL_ALLOWLIST
)

__all__ = [
    'CardinalityTracker',
    'get_cardinality_tracker',
    'initialize_cardinality_tracker',
    'LABEL_DENYLIST',
    'LABEL_ALLOWLIST'
]
