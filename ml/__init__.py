"""
ml/__init__.py
ML package for YUKTI.

Models (all CPU-only, no PyTorch required by default):
  1. Forecaster      — GBM quantile regression (q10, q50, q90)
  2. FaultClassifier — Feature-based gradient boosting, 6 fault classes
  3. FailureRisk     — XGBoost risk scorer 0-100 with SHAP explanations
"""
