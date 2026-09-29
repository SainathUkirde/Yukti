"""
simulator — Physics engine for YUKTI.

Sub-packages:
  reservoir  — heated zone, cooling decay, IPR
  wellbore   — viscosity-temperature model
  srp        — wave equation, dyno cards, rod floating, faults
  sensor     — noise, drift, dropouts
  surrogate  — fast vectorized surrogate of the full simulator

Entry point: simulator.well_system.WellSystem
"""
from .well_system import WellSystem
from .config import WellParameters, make_well_fleet

__all__ = ["WellSystem", "WellParameters", "make_well_fleet"]
