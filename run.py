"""
run.py — one-command backend launcher.
Run from inside digital-twin/:
    python run.py
"""
import os
import sys

# Ensure this directory (digital-twin/) is on sys.path so all packages resolve
HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import uvicorn

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--reload", action="store_true", default=False)
    port_env = int(os.environ.get("PORT", "8000"))
    parser.add_argument("--port", type=int, default=port_env)
    args = parser.parse_args()

    uvicorn.run(
        "backend.app.main:app",
        host="0.0.0.0",
        port=args.port,
        reload=args.reload,
    )
