"""
Rate and Query Functions Module

Provides PromQL-equivalent functions for time-series analysis.
"""

from .rate import (
    calculate_rate,
    calculate_irate,
    calculate_increase,
    calculate_delta,
    calculate_deriv,
    get_counter_state_manager,
    CounterStateManager
)

from .histogram import (
    histogram_quantile,
    get_quantiles
)

__all__ = [
    'calculate_rate',
    'calculate_irate', 
    'calculate_increase',
    'calculate_delta',
    'calculate_deriv',
    'get_counter_state_manager',
    'CounterStateManager',
    'histogram_quantile',
    'get_quantiles'
]

