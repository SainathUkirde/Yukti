"""
backend/app/services/carbon_service.py
Feature 5 — Carbon & Energy Tracker

Computes CO₂ emissions, energy cost, and carbon intensity per well and field.

Physics / emissions model:
  Steam generation fuel (natural gas):
    E_steam [GJ] = steam_volume_m3 × steam_density_kg_m3 × (Cp_water × ΔT + Q_lat × steam_quality)
    Q_fuel  [GJ] = E_steam / boiler_efficiency
    CO2_steam [tCO2] = Q_fuel × emission_factor_gas_kg_GJ / 1000

  Electrical energy (SRP motor):
    CO2_elec [tCO2] = motor_kwh × grid_emission_factor_kg_kwh / 1000

  Total CO2 per barrel:
    CO2_per_bbl [kgCO2/bbl] = (CO2_steam + CO2_elec) * 1000 / max(cum_oil_bbl, 1)

  Cost per barrel:
    gas_cost = Q_fuel_GJ × gas_price_inr_per_GJ
    elec_cost = motor_kwh × elec_price_inr_per_kwh
    cost_per_bbl = (gas_cost + elec_cost) / max(cum_oil_bbl, 1)

Default assumptions (all LITERATURE_ASSUMPTION / editable by user):
  boiler_efficiency            = 0.85        [LITERATURE_ASSUMPTION — typical field boiler]
  emission_factor_gas_kg_GJ   = 56.1        [IPCC 2006 Guidelines, Table 2.2 — natural gas]
  grid_emission_factor_kg_kwh = 0.82        [CEA India, average 2022-23 grid factor]
  steam_density_kg_m3         = 0.8         [CWE water density approximation]
  gas_price_inr_per_GJ        = 400.0       [LITERATURE_ASSUMPTION — approx India gas price]
  elec_price_inr_per_kwh      = 6.5         [LITERATURE_ASSUMPTION — approx India industrial tariff]

PROVENANCE: LITERATURE_ASSUMPTION for all emission factors and prices.
NOT validated against real Baghewala field energy or emissions records.

References:
  [A] IPCC 2006 Guidelines for National Greenhouse Gas Inventories, Vol. 2, Ch. 2.
  [B] CEA (2023) CO₂ Baseline Database for the Indian Power Sector, Version 18.
  [C] Butler, R.M. (1991) Thermal Recovery of Oil and Bitumen, Ch. 3 (steam enthalpy).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("carbon_service")

# ── Default editable assumptions ─────────────────────────────────────────────
@dataclass
class CarbonAssumptions:
    boiler_efficiency: float = 0.85
    emission_factor_gas_kg_per_gj: float = 56.1
    grid_emission_factor_kg_per_kwh: float = 0.82
    steam_density_kg_per_m3: float = 0.8
    gas_price_inr_per_gj: float = 400.0
    elec_price_inr_per_kwh: float = 6.5
    # Steam enthalpy parameters (Butler 1991 [C])
    cp_water_kj_per_kg_k: float = 4.187
    steam_temp_c: float = 200.0
    water_inlet_temp_c: float = 25.0
    latent_heat_kj_per_kg: float = 2000.0


# Global mutable assumptions (updated by PUT /carbon/assumptions)
_assumptions = CarbonAssumptions()


@dataclass
class WellCarbonReport:
    """Carbon and energy intensity report for one well."""
    well_id: str
    # Fuel energy
    steam_volume_m3: float
    steam_energy_gj: float
    fuel_energy_gj: float
    # Electricity
    motor_kwh: float
    # Emissions
    co2_steam_t: float
    co2_elec_t: float
    co2_total_t: float
    co2_per_bbl_kg: float
    co2_delta_vs_baseline_pct: float
    # Costs
    gas_cost_inr: float
    elec_cost_inr: float
    total_cost_inr: float
    cost_per_bbl_inr: float
    # Production context
    cum_oil_m3: float
    cum_oil_bbl: float
    sor: float
    period_days: float
    # Meta
    assumptions_used: dict
    provenance: str = "LITERATURE_ASSUMPTION"


def _compute_well_carbon(
    steam_volume_m3: float,
    steam_quality: float,
    motor_kwh: float,
    cum_oil_m3: float,
    sor: float,
    a: CarbonAssumptions,
) -> dict:
    """Core per-well carbon calculation. Returns dict of all metrics."""
    # Steam energy (heat required to produce steam from inlet water)
    delta_T = a.steam_temp_c - a.water_inlet_temp_c
    steam_enthalpy_kj_per_kg = (
        a.cp_water_kj_per_kg_k * delta_T
        + steam_quality * a.latent_heat_kj_per_kg
    )  # [kJ/kg]
    steam_mass_kg = steam_volume_m3 * a.steam_density_kg_per_m3  # CWE
    steam_energy_gj = steam_mass_kg * steam_enthalpy_kj_per_kg / 1e6

    fuel_energy_gj = steam_energy_gj / max(a.boiler_efficiency, 0.01)
    co2_steam_t = fuel_energy_gj * a.emission_factor_gas_kg_per_gj / 1000.0

    # Electrical
    co2_elec_t = motor_kwh * a.grid_emission_factor_kg_per_kwh / 1000.0

    co2_total_t = co2_steam_t + co2_elec_t
    cum_oil_bbl = cum_oil_m3 * 6.2898
    co2_per_bbl_kg = (co2_total_t * 1000) / max(cum_oil_bbl, 1.0)

    # Baseline CO₂/bbl (industry typical CSS heavy oil: ~60 kg CO₂/bbl [LITERATURE_ASSUMPTION])
    BASELINE_CO2_PER_BBL_KG = 60.0
    co2_delta_pct = (co2_per_bbl_kg - BASELINE_CO2_PER_BBL_KG) / BASELINE_CO2_PER_BBL_KG * 100.0

    # Costs
    gas_cost_inr = fuel_energy_gj * a.gas_price_inr_per_gj
    elec_cost_inr = motor_kwh * a.elec_price_inr_per_kwh
    total_cost_inr = gas_cost_inr + elec_cost_inr
    cost_per_bbl_inr = total_cost_inr / max(cum_oil_bbl, 1.0)

    # Round components first, then derive total from rounded values to avoid
    # 1-ULP mismatch when the test checks co2_total == co2_steam + co2_elec.
    co2_steam_r = round(co2_steam_t, 4)
    co2_elec_r = round(co2_elec_t, 4)
    return {
        "steam_volume_m3": round(steam_volume_m3, 1),
        "steam_energy_gj": round(steam_energy_gj, 3),
        "fuel_energy_gj": round(fuel_energy_gj, 3),
        "motor_kwh": round(motor_kwh, 2),
        "co2_steam_t": co2_steam_r,
        "co2_elec_t": co2_elec_r,
        "co2_total_t": round(co2_steam_r + co2_elec_r, 4),
        "co2_per_bbl_kg": round(co2_per_bbl_kg, 3),
        "co2_delta_vs_baseline_pct": round(co2_delta_pct, 2),
        "gas_cost_inr": round(gas_cost_inr, 2),
        "elec_cost_inr": round(elec_cost_inr, 2),
        "total_cost_inr": round(total_cost_inr, 2),
        "cost_per_bbl_inr": round(cost_per_bbl_inr, 2),
        "cum_oil_m3": round(cum_oil_m3, 3),
        "cum_oil_bbl": round(cum_oil_bbl, 2),
        "sor": round(sor, 3),
    }


def compute_well_carbon(
    well_id: str,
    state,       # WellStateSnapshot
    params,      # WellParameters
    period_days: float = 1.0,
) -> dict:
    """
    Compute carbon report for a single well from its latest simulation state.
    PROVENANCE: LITERATURE_ASSUMPTION (all emission factors / prices)
    """
    a = _assumptions

    # Motor energy over period: power_kw × period_days × 24
    motor_kwh = float(state.motor_power_kw) * period_days * 24.0

    # Use current simulation state values
    steam_volume_m3 = float(params.steam_volume_cwe_m3)
    steam_quality = float(getattr(params, "steam_quality", 0.75))
    cum_oil_m3 = float(state.cum_oil_m3)
    sor = float(state.sor)

    metrics = _compute_well_carbon(
        steam_volume_m3=steam_volume_m3,
        steam_quality=steam_quality,
        motor_kwh=motor_kwh,
        cum_oil_m3=cum_oil_m3,
        sor=sor,
        a=a,
    )

    return {
        "well_id": well_id,
        "period_days": period_days,
        **metrics,
        "assumptions_used": {
            "boiler_efficiency": a.boiler_efficiency,
            "emission_factor_gas_kg_per_gj": a.emission_factor_gas_kg_per_gj,
            "grid_emission_factor_kg_per_kwh": a.grid_emission_factor_kg_per_kwh,
            "gas_price_inr_per_gj": a.gas_price_inr_per_gj,
            "elec_price_inr_per_kwh": a.elec_price_inr_per_kwh,
        },
        "provenance": "LITERATURE_ASSUMPTION",
        "disclaimer": (
            "All emission factors and prices are LITERATURE_ASSUMPTION. "
            "NOT validated against real Baghewala field energy or emissions data. "
            "Edit assumptions via PUT /carbon/assumptions."
        ),
    }


def compute_field_carbon(well_reports: list[dict]) -> dict:
    """
    Aggregate per-well carbon reports into a field-level summary.
    PROVENANCE: LITERATURE_ASSUMPTION
    """
    if not well_reports:
        return {"wells": [], "field_totals": {}, "provenance": "LITERATURE_ASSUMPTION"}

    total_co2_t = sum(w["co2_total_t"] for w in well_reports)
    total_oil_bbl = sum(w["cum_oil_bbl"] for w in well_reports)
    total_cost_inr = sum(w["total_cost_inr"] for w in well_reports)
    total_steam_m3 = sum(w["steam_volume_m3"] for w in well_reports)
    total_motor_kwh = sum(w["motor_kwh"] for w in well_reports)

    field_co2_per_bbl = (total_co2_t * 1000) / max(total_oil_bbl, 1.0)
    field_cost_per_bbl = total_cost_inr / max(total_oil_bbl, 1.0)

    BASELINE_CO2_PER_BBL_KG = 60.0
    field_co2_delta_pct = (
        (field_co2_per_bbl - BASELINE_CO2_PER_BBL_KG) / BASELINE_CO2_PER_BBL_KG * 100.0
    )

    return {
        "wells": well_reports,
        "field_totals": {
            "total_co2_t": round(total_co2_t, 3),
            "total_oil_bbl": round(total_oil_bbl, 2),
            "total_cost_inr": round(total_cost_inr, 2),
            "total_steam_m3": round(total_steam_m3, 1),
            "total_motor_kwh": round(total_motor_kwh, 2),
            "field_co2_per_bbl_kg": round(field_co2_per_bbl, 3),
            "field_cost_per_bbl_inr": round(field_cost_per_bbl, 2),
            "co2_delta_vs_baseline_pct": round(field_co2_delta_pct, 2),
            "n_wells": len(well_reports),
        },
        "provenance": "LITERATURE_ASSUMPTION",
        "disclaimer": (
            "All emission factors and prices are LITERATURE_ASSUMPTION. "
            "NOT validated against real Baghewala field energy or emissions records."
        ),
    }


def get_assumptions() -> dict:
    """Return current carbon assumptions."""
    a = _assumptions
    return {
        "boiler_efficiency": a.boiler_efficiency,
        "emission_factor_gas_kg_per_gj": a.emission_factor_gas_kg_per_gj,
        "grid_emission_factor_kg_per_kwh": a.grid_emission_factor_kg_per_kwh,
        "steam_density_kg_per_m3": a.steam_density_kg_per_m3,
        "gas_price_inr_per_gj": a.gas_price_inr_per_gj,
        "elec_price_inr_per_kwh": a.elec_price_inr_per_kwh,
        "cp_water_kj_per_kg_k": a.cp_water_kj_per_kg_k,
        "steam_temp_c": a.steam_temp_c,
        "water_inlet_temp_c": a.water_inlet_temp_c,
        "latent_heat_kj_per_kg": a.latent_heat_kj_per_kg,
        "provenance": "LITERATURE_ASSUMPTION",
        "sources": (
            "[A] IPCC 2006 National GHG Inventories Vol.2 Ch.2 (emission factors); "
            "[B] CEA India Grid Factor 2023; "
            "[C] Butler 1991 (steam enthalpy)."
        ),
    }


def update_assumptions(updates: dict) -> dict:
    """
    Update carbon assumptions in-memory.
    Accepts any subset of CarbonAssumptions fields.
    PROVENANCE: USER_UPLOADED (user-provided values override LITERATURE_ASSUMPTION)
    """
    a = _assumptions
    allowed = {f.name for f in CarbonAssumptions.__dataclass_fields__.values()}  # type: ignore
    applied: dict = {}
    for key, val in updates.items():
        if key in allowed:
            try:
                setattr(a, key, float(val))
                applied[key] = float(val)
            except (ValueError, TypeError) as e:
                logger.warning(f"Skipping invalid assumption {key}={val}: {e}")
    return {**get_assumptions(), "updated_keys": list(applied.keys()), "provenance": "USER_UPLOADED"}
