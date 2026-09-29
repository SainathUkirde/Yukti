"""
ml/training/train_forecaster.py
Train the production forecaster on synthetic dataset.

Usage: python ml/training/train_forecaster.py
"""
import sys, os, json
from pathlib import Path
ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd

def main():
    print("[forecaster] Loading datasets...")
    prod_df = pd.read_parquet(ROOT / "data" / "synthetic" / "production_history.parquet")
    srp_df  = pd.read_parquet(ROOT / "data" / "synthetic" / "srp_operating_data.parquet")

    print("[forecaster] Building features...")
    from ml.features.production_features import build_forecaster_features
    X, y = build_forecaster_features(prod_df, srp_df, horizon=7)
    print(f"[forecaster] Training set: {len(X)} rows, {X.shape[1]-1} features, 3 targets")

    print("[forecaster] Training quantile models (q10/q50/q90 per target)...")
    from ml.models.forecaster import ProductionForecaster
    fc = ProductionForecaster()
    metrics = fc.fit(X, y)

    print("[forecaster] Metrics:")
    for target, m in metrics.items():
        print(f"  {target}: MAE={m['q50_mae']:.4f}  RMSE={m['q50_rmse']:.4f}  "
              f"Coverage80={m['coverage_80pct']:.3f}  backend={m['backend']}")

    print("[forecaster] Saving artifacts...")
    fc.save()
    metrics_path = ROOT / "models" / "artifacts" / "forecaster_metrics.json"
    with open(metrics_path, "w") as f:
        json.dump(metrics, f, indent=2)
    print(f"[forecaster] Done. Artifacts in models/artifacts/")

if __name__ == "__main__":
    main()
