"""
simulator/surrogate/__init__.py
"""
from .fast_surrogate import evaluate as surrogate_evaluate, SurrogateResult, evaluate_batch

__all__ = ["surrogate_evaluate", "SurrogateResult", "evaluate_batch"]
