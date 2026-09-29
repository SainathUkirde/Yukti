"""
backend/app/services/optimizer_service.py
Thin wrapper around JointOptimizer — called by API layer.
Handles import errors gracefully so backend still starts if optimizer is missing.
"""
import logging
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, ROOT)

logger = logging.getLogger("optimizer_service")


class OptimizerService:
    """Lazily imports and runs JointOptimizer."""

    def run(self, params, n_trials: int = 60) -> dict:
        try:
            from optimizer.joint_optimizer import JointOptimizer
            # JointOptimizer takes WellParameters directly; no FastSurrogate wrapper needed
            opt = JointOptimizer(params, n_trials=n_trials)
            result = opt.optimize()
            return {
                "best_css": result.best_css,
                "best_srp": result.best_srp,
                "predicted_kpis": {
                    "oil_rate_m3d": result.predicted_oil_rate_m3d,
                    "sor": result.predicted_sor,
                    "kwh_per_bbl": result.predicted_kwh_per_bbl,
                    "pump_efficiency": result.predicted_pump_efficiency,
                    "rod_float_risk": result.predicted_rod_float_risk,
                    "cost_per_bbl_inr": result.predicted_cost_per_bbl_inr,
                },
                "kpi_deltas": {
                    "oil_rate_delta_pct": result.delta_oil_pct,
                    "sor_delta_pct": result.delta_sor_pct,
                    "energy_delta_pct": result.delta_energy_pct,
                    "cost_per_bbl_delta_pct": result.delta_cost_per_bbl_pct,
                },
                "objective_value": result.best_trial_value,
                "constraints_passed": result.constraints_passed,
                "constraint_audit": [v["name"] for v in result.constraint_violations],
            }
        except Exception as e:
            logger.error(f"Optimizer run failed: {e}")
            return {"error": str(e)}


optimizer_service = OptimizerService()
