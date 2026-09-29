"""
ml/training/train_failure_risk.py
Train the rod failure risk scorer.

Usage: python ml/training/train_failure_risk.py
"""
import sys, os, json
from pathlib import Path
ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd
import numpy as np

def main():
    print("[risk] Loading datasets...")
    srp_df  = pd.read_parquet(ROOT / "data" / "synthetic" / "srp_operating_data.parquet")
    fail_df = pd.read_parquet(ROOT / "data" / "synthetic" / "rod_failure_history.parquet")
    print(f"[risk] SRP records: {len(srp_df)}, Failure events: {len(fail_df)}")

    print("[risk] Building risk dataset...")
    from ml.models.failure_risk import build_risk_dataset, RISK_FEATURE_COLS, FailureRiskScorer
    X, y = build_risk_dataset(srp_df, fail_df)
    available_feats = [c for c in RISK_FEATURE_COLS if c in srp_df.columns]
    print(f"[risk] Dataset: {X.shape}, target range: [{y.min():.1f}, {y.max():.1f}]")
    print(f"[risk] High-risk samples (>60): {(y > 60).sum()} ({(y > 60).mean()*100:.1f}%)")

    print("[risk] Training risk scorer...")
    rs = FailureRiskScorer()
    metrics = rs.fit(X, y, feature_names=available_feats)

    print("[risk] Metrics:")
    print(f"  MAE               : {metrics['mae']:.3f}")
    print(f"  RMSE              : {metrics['rmse']:.3f}")
    print(f"  High-risk Prec    : {metrics['high_risk_precision']:.3f}")
    print(f"  High-risk Recall  : {metrics['high_risk_recall']:.3f}")
    print(f"  Backend           : {metrics['backend']}")

    print("[risk] Saving artifacts...")
    rs.save()
    metrics_path = ROOT / "models" / "artifacts" / "failure_risk_metrics.json"
    with open(metrics_path, "w") as f:
        json.dump(metrics, f, indent=2)
    print("[risk] Done.")

if __name__ == "__main__":
    main()
