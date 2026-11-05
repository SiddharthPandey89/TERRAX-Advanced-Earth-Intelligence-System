"""Temperature suitability factor.

Scores the thermal suitability of a region for human habitation from supplied
temperature statistics (degrees Celsius). Nothing is estimated: statistics that
are absent are reported as missing, and invalid ones are discarded and reported.

Inputs (all optional, deg C):
    mean_c   mean annual temperature       weight 0.6  plateau 10-25 -> 100, zero at -15 / 38
    min_c    coldest observed temperature  weight 0.2  100 at >= -5, 0 at <= -40
    max_c    hottest observed temperature  weight 0.2  100 at <= 35, 0 at >= 50

Thresholds are heuristics (see ``scoring`` module note). Humidity, diurnal
range and seasonality are not considered.
"""

from __future__ import annotations

from dataclasses import dataclass

from .scoring import (
    FactorResult,
    MetricSpec,
    finalize_factor,
    is_valid_number,
    plateau_score,
    ramp_score,
    score_metrics,
    unavailable_factor,
)

FACTOR_NAME = "temperature"

# Physically plausible near-surface range on Earth (record low about -89 C, high about 57 C).
PLAUSIBLE_RANGE_C = (-95.0, 65.0)

SPECS: tuple[MetricSpec, ...] = (
    MetricSpec("mean_c", "°C", 0.6, PLAUSIBLE_RANGE_C,
               lambda v: plateau_score(v, -15.0, 10.0, 25.0, 38.0)),
    MetricSpec("min_c", "°C", 0.2, PLAUSIBLE_RANGE_C,
               lambda v: ramp_score(v, -40.0, -5.0)),
    MetricSpec("max_c", "°C", 0.2, PLAUSIBLE_RANGE_C,
               lambda v: ramp_score(v, 50.0, 35.0)),
)

_NOTE = "Thermal suitability only; humidity, diurnal range and seasonality are not considered."

_CELSIUS = {"c", "celsius", "centigrade"}
_KELVIN = {"k", "kelvin"}
_FAHRENHEIT = {"f", "fahrenheit"}


@dataclass(frozen=True)
class TemperatureInput:
    mean_c: float | None = None
    min_c: float | None = None
    max_c: float | None = None


def to_celsius(value: float, unit: str) -> float:
    """Convert a temperature to deg C. Raises ``ValueError`` for bad values or units."""
    if not is_valid_number(value):
        raise ValueError(f"temperature value must be a finite number, got {value!r}")
    if not isinstance(unit, str):
        raise ValueError(f"temperature unit must be a string, got {unit!r}")
    key = unit.strip().lower().replace("°", "").replace("deg", "").replace("_", "").replace(" ", "")
    if key in _CELSIUS:
        return float(value)
    if key in _KELVIN:
        return float(value) - 273.15
    if key in _FAHRENHEIT:
        return (float(value) - 32.0) * 5.0 / 9.0
    raise ValueError(f"unsupported temperature unit {unit!r}")


def evaluate_temperature(data: TemperatureInput | None) -> FactorResult:
    """Evaluate temperature suitability, or report why it is unavailable."""
    if data is None:
        return unavailable_factor(
            FACTOR_NAME, "No temperature data was supplied.", missing=(s.name for s in SPECS)
        )

    components, issues = score_metrics(
        {"mean_c": data.mean_c, "min_c": data.min_c, "max_c": data.max_c}, SPECS
    )

    # Statistics must be mutually consistent: min <= mean <= max.
    values = {c.name: c.value for c in components}
    for low, high in (("min_c", "mean_c"), ("mean_c", "max_c"), ("min_c", "max_c")):
        if low in values and high in values and values[low] > values[high]:
            issues.append(f"{low}={values[low]:g} exceeds {high}={values[high]:g}.")
            return unavailable_factor(
                FACTOR_NAME,
                "Inconsistent temperature statistics (expected min <= mean <= max).",
                missing=(s.name for s in SPECS),
                issues=issues,
            )

    return finalize_factor(FACTOR_NAME, components, SPECS, issues, notes=(_NOTE,))
