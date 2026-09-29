"""
simulator/sensor/noise.py
Sensor noise, drift, spikes and dropout simulation layer.

Applied on top of the physics simulator output to produce realistic
"measured" values that mimic real field sensor behavior.

Default parameters are based on published industry practice
(Holloway et al., 2012; typical SCADA sensor specs).
Volve calibration is applied if VOLVE_DATA_PATH is set (see docs/data_strategy.md).

Noise model per sensor channel:
  measured = true_value + Gaussian(0, σ) + drift_accumulator
  With probability p_spike  → add a spike of magnitude spike_mag
  With probability p_dropout → return NaN (missing data)
"""

import numpy as np
from ..config import (
    NOISE_OIL_RATE_SIGMA_FRAC,
    NOISE_TEMP_SIGMA_C,
    NOISE_PRESSURE_SIGMA_KPA,
    NOISE_CURRENT_SIGMA_FRAC,
    NOISE_SPIKE_PROB,
    NOISE_DROPOUT_PROB,
    NOISE_DRIFT_RATE,
)


class SensorChannel:
    """
    Stateful sensor channel: maintains drift accumulator between ticks.
    """

    def __init__(
        self,
        sigma_abs: float = 0.0,
        sigma_frac: float = 0.0,
        spike_prob: float = NOISE_SPIKE_PROB,
        spike_mag_frac: float = 0.10,
        dropout_prob: float = NOISE_DROPOUT_PROB,
        drift_rate: float = NOISE_DRIFT_RATE,
        rng: np.random.Generator | None = None,
    ) -> None:
        """
        Parameters
        ----------
        sigma_abs     : float   Absolute Gaussian noise std dev (e.g. °C)
        sigma_frac    : float   Fractional noise (fraction of reading)
        spike_prob    : float   Probability of a spike each tick
        spike_mag_frac: float   Spike magnitude as fraction of reading
        dropout_prob  : float   Probability of a dropout (NaN) each tick
        drift_rate    : float   Drift per tick as fraction of reading
        rng           : np.random.Generator   Seeded RNG for reproducibility
        """
        self.sigma_abs = sigma_abs
        self.sigma_frac = sigma_frac
        self.spike_prob = spike_prob
        self.spike_mag_frac = spike_mag_frac
        self.dropout_prob = dropout_prob
        self.drift_rate = drift_rate
        self._drift = 0.0
        self._rng = rng or np.random.default_rng()

    def measure(self, true_value: float) -> float | None:
        """
        Apply noise model to true_value and return measured value.
        Returns None on dropout.
        """
        # Dropout
        if self._rng.random() < self.dropout_prob:
            return None

        # Noise
        sigma = self.sigma_abs + self.sigma_frac * abs(true_value)
        noise = self._rng.normal(0.0, sigma) if sigma > 0 else 0.0

        # Drift (accumulates slowly)
        self._drift += self._rng.normal(0.0, self.drift_rate * abs(true_value))
        self._drift *= 0.995   # slow reversion

        # Spike
        spike = 0.0
        if self._rng.random() < self.spike_prob:
            spike = self._rng.choice([-1, 1]) * self.spike_mag_frac * abs(true_value)

        return float(true_value + noise + self._drift + spike)

    def reset_drift(self) -> None:
        """Reset drift accumulator (e.g. after sensor calibration)."""
        self._drift = 0.0


class WellSensorLayer:
    """
    Complete sensor layer for one well.
    Maintains one SensorChannel per sensor type.
    """

    def __init__(self, seed: int = 42) -> None:
        rng_root = np.random.default_rng(seed)

        def _child(extra: int) -> np.random.Generator:
            return np.random.default_rng(seed + extra)

        self.oil_rate = SensorChannel(
            sigma_frac=NOISE_OIL_RATE_SIGMA_FRAC, rng=_child(1)
        )
        self.temperature = SensorChannel(
            sigma_abs=NOISE_TEMP_SIGMA_C, rng=_child(2)
        )
        self.pressure = SensorChannel(
            sigma_abs=NOISE_PRESSURE_SIGMA_KPA, rng=_child(3)
        )
        self.motor_current = SensorChannel(
            sigma_frac=NOISE_CURRENT_SIGMA_FRAC, rng=_child(4)
        )
        self.rod_load = SensorChannel(
            sigma_frac=0.015, rng=_child(5)
        )
        self.water_rate = SensorChannel(
            sigma_frac=NOISE_OIL_RATE_SIGMA_FRAC * 1.2, rng=_child(6)
        )

    def apply(self, true_state: dict) -> dict:
        """
        Apply noise to a dict of true physics values.
        Keys not in the mapping are passed through unchanged.
        Returns a new dict with measured (noisy) values.
        None values indicate sensor dropout.
        """
        measured = dict(true_state)
        _map = {
            "oil_rate_m3d": self.oil_rate,
            "water_rate_m3d": self.water_rate,
            "reservoir_temp_c": self.temperature,
            "reservoir_pressure_kpa": self.pressure,
            "motor_current_a": self.motor_current,
            "polished_rod_load_kn": self.rod_load,
        }
        for key, channel in _map.items():
            if key in true_state and true_state[key] is not None:
                measured[key] = channel.measure(true_state[key])
        return measured


def twin_sensor_deviation_pct(
    true_values: dict[str, float],
    measured_values: dict[str, float],
    keys: list[str] | None = None,
) -> float:
    """
    Compute average absolute percentage deviation between true (twin) and
    measured (sensor) values.  Used for the "Twin vs Sensor" accuracy badge.

    deviation = mean(|true - measured| / |true|) × 100 [%]
    """
    if keys is None:
        keys = [k for k in true_values if k in measured_values]
    deviations = []
    for k in keys:
        tv = true_values.get(k)
        mv = measured_values.get(k)
        if tv is None or mv is None or abs(tv) < 1e-9:
            continue
        deviations.append(abs(tv - mv) / abs(tv) * 100.0)
    return float(np.mean(deviations)) if deviations else 0.0
