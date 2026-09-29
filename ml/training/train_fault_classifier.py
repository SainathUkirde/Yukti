"""
ml/training/train_fault_classifier.py
Train the dyno card fault classifier on synthetic labeled cards.

Usage: python ml/training/train_fault_classifier.py
"""
import sys, os, json
from pathlib import Path
ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd
import numpy as np

def main():
    print("[fault_clf] Loading dyno cards dataset...")
    df = pd.read_parquet(ROOT / "data" / "synthetic" / "dyno_cards_labeled.parquet")
    print(f"[fault_clf] {len(df)} cards, class distribution:")
    print(df["fault_label"].value_counts().to_string())

    print("[fault_clf] Extracting features...")
    from ml.features.dyno_features import extract_features_batch, FEATURE_NAMES
    X = extract_features_batch(df)
    y = df["fault_label"].values
    print(f"[fault_clf] Feature matrix: {X.shape}")

    print("[fault_clf] Training classifier...")
    from ml.models.fault_classifier import DynoFaultClassifier
    clf = DynoFaultClassifier()
    metrics = clf.fit(X, y, feature_names=FEATURE_NAMES)

    print("[fault_clf] Metrics:")
    print(f"  Accuracy : {metrics['accuracy']:.4f}")
    print(f"  F1 Macro : {metrics['f1_macro']:.4f}")
    print(f"  Backend  : {metrics['backend']}")
    print("  Per-class F1:")
    for cls, f1 in metrics["f1_per_class"].items():
        print(f"    {cls:<20}: {f1:.4f}")

    print("[fault_clf] Saving artifacts...")
    clf.save()
    metrics_path = ROOT / "models" / "artifacts" / "fault_classifier_metrics.json"
    with open(metrics_path, "w") as f:
        json.dump(metrics, f, indent=2)
    print("[fault_clf] Done.")

if __name__ == "__main__":
    main()
