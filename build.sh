#!/usr/bin/env bash
set -e

echo "=================================================="
echo "==> YUKTI Digital Twin — Render Build Process"
echo "=================================================="

# 1. Install Python dependencies
echo "==> [1/3] Installing Python dependencies..."
pip install -r requirements.txt

# 2. Build Frontend (if npm is available)
if command -v npm &> /dev/null && [ -d "frontend" ]; then
  echo "==> [2/3] Building React Frontend..."
  npm --prefix frontend install --prefer-offline --no-audit
  npm --prefix frontend run build
  echo "==> Frontend built successfully."
else
  echo "==> [2/3] Skipping frontend npm build (npm not found or already built)."
fi

# 3. Check for pre-trained model artifacts or generate baseline
echo "==> [3/3] Checking ML model artifacts..."
if [ ! -f "models/artifacts/fault_classifier.joblib" ] || [ ! -f "models/artifacts/forecaster_oil_rate_m3d_q50.joblib" ]; then
  echo "==> Artifacts missing. Generating synthetic data and training baseline models..."
  python data/generate.py --wells 3 --cycles 2 --cards 500
  python ml/training/train_forecaster.py
  python ml/training/train_fault_classifier.py
  python ml/training/train_failure_risk.py
  echo "==> Models trained successfully."
else
  echo "==> Pre-trained model artifacts found. Ready for serving."
fi

echo "=================================================="
echo "==> Build finished successfully!"
echo "=================================================="
