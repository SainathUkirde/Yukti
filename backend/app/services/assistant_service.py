"""
backend/app/services/assistant_service.py
Local rule-based AI assistant — no external LLM required.
Maps well state + user query keywords to pre-defined engineering explanations.
Provenance: DEMO_RESULT (template-based, not generative AI)
"""
import logging
import re
from typing import Optional

logger = logging.getLogger("assistant_service")

# ── Knowledge base (keyword → engineering response) ────────────────────────────
KB: list[tuple[list[str], str]] = [
    (
        ["rod float", "rod floating", "n_rf", "buoyancy"],
        "**Rod Floating** occurs when crude viscosity is so high that buoyant force on the "
        "downstroke exceeds rod weight. The dimensionless Rod Float Index is:\n\n"
        "```\nN_rf = (μ × SPM × SL) / 6000\n```\n\n"
        "When N_rf ≥ 1.0, the rod string floats. **Action**: reduce SPM or wait for reservoir "
        "to re-heat. In Baghewala, this typically occurs when T_res < 55°C and viscosity > 500 cP."
    ),
    (
        ["css", "cyclic steam", "steam stimulation", "soak", "inject steam"],
        "**Cyclic Steam Stimulation (CSS)** has three phases:\n"
        "1. **Injection** — steam injected at ≥80% quality, 3500–7000 kPa\n"
        "2. **Soak** — well shut-in 7–21 days to allow heat diffusion (Marx-Langenheim model)\n"
        "3. **Production** — heated, lower-viscosity oil flows to pump\n\n"
        "Cycle efficiency degrades ~8% per cycle (Bursell 1975). "
        "Optimal SOR target for Baghewala: ≤4.5 bbl/bbl."
    ),
    (
        ["sor", "steam oil ratio", "steam-oil"],
        "**Steam-Oil Ratio (SOR)** = cumulative steam injected ÷ cumulative oil produced. "
        "Lower is better. Baghewala target: ≤4.5 bbl/bbl. High SOR (>6) indicates poor "
        "heat utilization — consider reducing steam volume, increasing soak time, or "
        "advancing the production cut-off."
    ),
    (
        ["viscosity", "viscous", "api", "heavy oil"],
        "Baghewala crude is 17–19° API with **Andrade viscosity** model:\n\n"
        "```\nln(μ) = A + B/T_K\n```\n\n"
        "Constants: A = -14.1659, B = 6968.65. At reservoir temperature (46–48°C): "
        "~2000 cP. At peak steam temperature (150°C): ~10 cP. "
        "This 200× viscosity reduction is the primary mechanism of CSS."
    ),
    (
        ["srp", "sucker rod", "pump", "spm", "stroke"],
        "**Sucker Rod Pump (SRP)** performance depends on viscosity-coupled fillage. "
        "Key parameters: SPM (strokes per minute, 1–15), stroke length (0.5–5 m), "
        "VFD frequency (20–60 Hz). At high viscosity, reduce SPM to avoid rod floating "
        "and fluid pound. Optimal SPM for Baghewala: 3–6 during early production phase."
    ),
    (
        ["pump efficiency", "fillage", "pump off"],
        "**Pump fillage fraction** = actual liquid displaced ÷ theoretical displacement. "
        "Values < 0.5 indicate pump-off (fluid level below pump) or gas interference. "
        "If fillage < 0.4 for >30 minutes, shut in the pump to allow fluid level recovery."
    ),
    (
        ["goodman", "fatigue", "rod failure", "failure risk"],
        "**Goodman fatigue criterion** checks if the rod load range falls within safe limits:\n\n"
        "```\nGoodman ratio = (σ_max - σ_min) / (2 × σ_endurance)\n```\n\n"
        "Ratio > 1.0 → fatigue failure likely. Rod failures in Baghewala are correlated "
        "with high viscosity periods (N_rf near 1) causing impact loading on downstroke."
    ),
    (
        ["heated zone", "marx", "langenheim", "heat", "temperature"],
        "The **Marx-Langenheim** model estimates heated zone radius from steam injection:\n\n"
        "```\nR_h = √(2 × Q_steam × h_steam / (π × h_res × φ × ρ_oil × Cp × ΔT))\n```\n\n"
        "After injection stops, reservoir cools exponentially. Soak time allows heat to "
        "diffuse further before production starts."
    ),
    (
        ["ipr", "inflow", "vogel", "productivity", "production rate"],
        "**Vogel IPR** for heavy oil (viscosity-coupled):\n\n"
        "```\nq/q_max = 1 - 0.2(Pwf/Pr) - 0.8(Pwf/Pr)²\n```\n\n"
        "Productivity Index (PI) is viscosity-coupled: PI_effective = PI_base × (μ_base/μ_current). "
        "As viscosity increases with cooling, effective PI drops sharply."
    ),
    (
        ["digital twin", "twin", "provenance", "synthetic"],
        "This **Digital Twin** uses a physics-based simulator (Marx-Langenheim, Vogel IPR, "
        "Gibbs wave equation, Andrade viscosity) to generate SIMULATED_LIVE data. "
        "All historical data is SYNTHETIC_HISTORICAL — generated from calibrated physics models. "
        "Every number carries a provenance badge. Data is NOT from real Baghewala field operations."
    ),
    (
        ["optimize", "optimization", "optuna", "recommend"],
        "The **Joint Optimizer** uses Optuna Bayesian TPE with 7 decision variables:\n"
        "- CSS: steam volume, soak days, injection pressure\n"
        "- SRP: SPM, stroke length, VFD frequency\n\n"
        "Objective: maximize oil rate + pump efficiency, minimize SOR + energy + rod risk. "
        "11 hard constraints enforced (C1–C11). Typical run: 60 trials in ~2s."
    ),
]


def answer(query: str, well_state: Optional[dict] = None) -> dict:
    """
    Match user query to knowledge base. Returns best matching response.
    Injects live well state values if available.
    """
    q = query.lower().strip()

    # Find best match
    best_score = 0
    best_answer = None

    for keywords, response in KB:
        score = sum(1 for kw in keywords if kw in q)
        if score > best_score:
            best_score = score
            best_answer = response

    if best_answer is None or best_score == 0:
        # Fallback
        best_answer = (
            "I can answer questions about: CSS, SRP, rod floating, viscosity, "
            "pump efficiency, Goodman criterion, IPR, heated zone, SOR, optimization, "
            "and the digital twin provenance system. Please rephrase your question."
        )
        best_score = 0

    # Inject live context if available
    context_note = ""
    if well_state and best_score > 0:
        context_note = (
            f"\n\n---\n**Current state for {well_state.get('well_id', 'selected well')}:** "
            f"T_res = {well_state.get('reservoir_temp_c', {}).get('value', 'N/A')}°C, "
            f"viscosity = {well_state.get('oil_viscosity_cp', {}).get('value', 'N/A')} cP, "
            f"phase = {well_state.get('phase', 'N/A')}, "
            f"risk = {well_state.get('rod_float_risk_score', {}).get('value', 'N/A')}/100"
        )

    return {
        "answer": best_answer + context_note,
        "match_score": best_score,
        "provenance": "DEMO_RESULT",
        "disclaimer": "Rule-based assistant. Not a validated AI model.",
    }
