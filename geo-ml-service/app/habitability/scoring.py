"""Habitability scoring: shared primitives, factor combination, assessment.

Dependency direction (no circular imports)
------------------------------------------
``scoring`` is the base module. ``temperature_factor``, ``water_factor``,
``terrain_factor`` and ``risk_factor`` import it. ``scoring`` imports the
factor modules only inside ``assess_habitability`` and
``inputs_from_indicator_results`` (deferred imports), never at module level.

Scoring model
-------------
* Every factor returns a *suitability* score in [0, 100] (higher is better),
  or is reported as unavailable. Nothing is estimated or defaulted.
* A factor needs at least ``MIN_FACTOR_COMPLETENESS`` of its measurements.
* An overall score is produced only when the essential factors (temperature
  and water) are available and the weighted factor coverage is at least
  ``MIN_COVERAGE``. Otherwise ``score`` is ``None`` and the reasons are listed.
* Overall score = weighted mean of the available factors, capped at the weakest
  available factor + ``LIMITING_CAP_MARGIN`` so one failing factor cannot be
  averaged away.

All thresholds and weights in this package are documented *modelling
assumptions* (heuristics), not values calibrated against observed settlement
data. They should be reviewed by a domain expert before results are presented
as scientific findings.
"""

from __future__ import annotations

import math
import numbers
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:  # type hints only; avoids runtime circular imports
    from .risk_factor import RiskInput
    from .temperature_factor import TemperatureInput
    from .terrain_factor import TerrainInput
    from .water_factor import WaterInput

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #
FACTOR_WEIGHTS: dict[str, float] = {
    "temperature": 0.30,
    "water": 0.30,
    "terrain": 0.20,
    "risk": 0.20,
}
ESSENTIAL_FACTORS: tuple[str, ...] = ("temperature", "water")
MIN_COVERAGE = 0.7  # essentials alone (0.6) are not enough; one more factor is
MIN_FACTOR_COMPLETENESS = 0.5
LIMITING_CAP_MARGIN = 30.0
MIN_ANNUAL_PERIOD_DAYS = 330  # shorter periods are not annual climatology

MODEL_LIMITATION = (
    "Heuristic model: thresholds and weights are modelling assumptions, "
    "not calibrated against observed settlement data."
)


# --------------------------------------------------------------------------- #
# Numeric helpers
# --------------------------------------------------------------------------- #
def is_valid_number(value: Any) -> bool:
    """True for finite real numbers; rejects bool, str, None, NaN and inf."""
    return (
        isinstance(value, numbers.Real)
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def ramp_score(value: float, zero_at: float, full_at: float) -> float:
    """Linear 0-100 score: 0 at ``zero_at``, 100 at ``full_at`` (either direction)."""
    if zero_at == full_at:
        raise ValueError("zero_at and full_at must differ.")
    fraction = (value - zero_at) / (full_at - zero_at)
    return 100.0 * clamp(fraction, 0.0, 1.0)


def plateau_score(
    value: float, zero_low: float, full_low: float, full_high: float, zero_high: float
) -> float:
    """0 at ``zero_low``, rising to 100 on [full_low, full_high], back to 0 at ``zero_high``."""
    if not zero_low < full_low <= full_high < zero_high:
        raise ValueError("Require zero_low < full_low <= full_high < zero_high.")
    if value < full_low:
        return ramp_score(value, zero_low, full_low)
    if value > full_high:
        return ramp_score(value, zero_high, full_high)
    return 100.0


def categorize(score: float) -> str:
    if score < 20:
        return "very_low"
    if score < 40:
        return "low"
    if score < 60:
        return "moderate"
    if score < 80:
        return "high"
    return "very_high"


def confidence_label(confidence: float) -> str:
    if confidence >= 0.8:
        return "high"
    if confidence >= 0.5:
        return "medium"
    return "low"


# --------------------------------------------------------------------------- #
# Factor result types
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Component:
    """One scored measurement inside a factor."""

    name: str
    value: float
    unit: str
    score: float
    weight: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "unit": self.unit,
            "score": round(self.score, 2),
            "weight": self.weight,
        }


@dataclass(frozen=True)
class FactorResult:
    """Outcome of one factor: a 0-100 suitability score or an explicit gap."""

    name: str
    status: Literal["available", "unavailable"]
    score: float | None
    confidence: float
    components: tuple[Component, ...] = ()
    missing: tuple[str, ...] = ()
    issues: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()
    reason: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.status == "available":
            if self.score is None or not 0.0 <= self.score <= 100.0:
                raise ValueError("An available factor needs a score in [0, 100].")
            if self.reason is not None:
                raise ValueError("An available factor must not carry a reason.")
        else:
            if self.score is not None or self.confidence != 0.0:
                raise ValueError("An unavailable factor has no score and zero confidence.")
            if not self.reason:
                raise ValueError("An unavailable factor must state a reason.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "score": None if self.score is None else round(self.score, 2),
            "confidence": round(self.confidence, 3),
            "components": [c.to_dict() for c in self.components],
            "missing": list(self.missing),
            "issues": list(self.issues),
            "notes": list(self.notes),
            "reason": self.reason,
            "details": dict(self.details),
        }


@dataclass(frozen=True)
class MetricSpec:
    """Definition of one measurement: valid range, weight and scoring function."""

    name: str
    unit: str
    weight: float
    valid_range: tuple[float, float]
    scorer: Callable[[float], float]


def score_metrics(
    raw: Mapping[str, Any], specs: Sequence[MetricSpec]
) -> tuple[list[Component], list[str]]:
    """Validate and score the supplied measurements.

    Absent (``None``) values are skipped silently; they show up later as
    ``missing``. Present but invalid values are discarded and reported as issues.
    No value is ever repaired, clamped or defaulted.
    """
    components: list[Component] = []
    issues: list[str] = []
    for spec in specs:
        value = raw.get(spec.name)
        if value is None:
            continue
        if not is_valid_number(value):
            issues.append(f"{spec.name}: expected a finite number, got {value!r}; ignored.")
            continue
        number = float(value)
        low, high = spec.valid_range
        if not low <= number <= high:
            issues.append(
                f"{spec.name}={number:g} is outside the valid range [{low:g}, {high:g}]; ignored."
            )
            continue
        components.append(
            Component(spec.name, number, spec.unit, clamp(spec.scorer(number)), spec.weight)
        )
    return components, issues


def weighted_mean_score(components: Sequence[Component]) -> float:
    total = sum(c.weight for c in components)
    return sum(c.weight * c.score for c in components) / total


def unavailable_factor(
    name: str,
    reason: str,
    missing: Iterable[str] = (),
    issues: Iterable[str] = (),
) -> FactorResult:
    return FactorResult(
        name=name,
        status="unavailable",
        score=None,
        confidence=0.0,
        missing=tuple(missing),
        issues=tuple(issues),
        reason=reason,
    )


def finalize_factor(
    name: str,
    components: Sequence[Component],
    specs: Sequence[MetricSpec],
    issues: Iterable[str] = (),
    notes: Iterable[str] = (),
    aggregate: Callable[[Sequence[Component]], float] | None = None,
) -> FactorResult:
    """Turn scored components into a FactorResult, enforcing minimum completeness."""
    issues = tuple(issues)
    total_weight = sum(s.weight for s in specs)
    scored = {c.name for c in components}
    missing = tuple(s.name for s in specs if s.name not in scored)
    completeness = sum(c.weight for c in components) / total_weight

    if not components or completeness < MIN_FACTOR_COMPLETENESS:
        return unavailable_factor(
            name,
            f"Insufficient measurements: {completeness:.0%} of the factor's inputs are "
            f"valid (minimum {MIN_FACTOR_COMPLETENESS:.0%}).",
            missing=missing,
            issues=issues,
        )

    score = clamp((aggregate or weighted_mean_score)(components))
    notes = list(notes)
    if missing:
        notes.append(
            f"Score based on {len(components)} of {len(specs)} inputs; "
            f"missing or invalid: {', '.join(missing)}."
        )
    return FactorResult(
        name=name,
        status="available",
        score=score,
        confidence=completeness,
        components=tuple(components),
        missing=missing,
        issues=issues,
        notes=tuple(notes),
    )


# --------------------------------------------------------------------------- #
# Overall assessment
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class HabitabilityInputs:
    """Optional per-factor inputs; ``None`` means the data was not supplied."""

    temperature: TemperatureInput | None = None
    water: WaterInput | None = None
    terrain: TerrainInput | None = None
    risk: RiskInput | None = None


@dataclass(frozen=True)
class HabitabilityAssessment:
    status: Literal["scored", "insufficient_data"]
    score: float | None
    category: str | None
    confidence: float | None
    confidence_label: str | None
    coverage: float
    factors: Mapping[str, FactorResult]
    unavailable_factors: tuple[str, ...]
    limiting_factor: str | None
    cap_applied: bool
    reasons: tuple[str, ...]
    limitations: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "score": None if self.score is None else round(self.score, 2),
            "category": self.category,
            "confidence": None if self.confidence is None else round(self.confidence, 3),
            "confidence_label": self.confidence_label,
            "coverage": round(self.coverage, 3),
            "factors": {name: f.to_dict() for name, f in self.factors.items()},
            "unavailable_factors": list(self.unavailable_factors),
            "limiting_factor": self.limiting_factor,
            "cap_applied": self.cap_applied,
            "reasons": list(self.reasons),
            "limitations": list(self.limitations),
        }


def combine_factors(
    factors: Mapping[str, FactorResult], extra_limitations: Iterable[str] = ()
) -> HabitabilityAssessment:
    """Combine factor results into one assessment (pure; evaluates nothing itself)."""
    unknown = set(factors) - set(FACTOR_WEIGHTS)
    if unknown:
        raise ValueError(f"Unknown factor(s): {', '.join(sorted(unknown))}")

    ordered: dict[str, FactorResult] = {
        name: factors.get(name) or unavailable_factor(name, "Factor was not evaluated.")
        for name in FACTOR_WEIGHTS
    }
    available = {n: f for n, f in ordered.items() if f.status == "available"}
    unavailable = tuple(n for n in ordered if n not in available)
    coverage = sum(FACTOR_WEIGHTS[n] for n in available)

    limitations = [MODEL_LIMITATION]
    for name in unavailable:
        limitations.append(f"{name}: unavailable ({ordered[name].reason})")
    for name, factor in ordered.items():
        limitations.extend(f"{name}: {issue}" for issue in factor.issues)
    limitations.extend(extra_limitations)

    reasons: list[str] = []
    for name in ESSENTIAL_FACTORS:
        if name not in available:
            reasons.append(f"Essential factor '{name}' is unavailable: {ordered[name].reason}")
    if coverage < MIN_COVERAGE:
        reasons.append(
            f"Weighted factor coverage {coverage:.0%} is below the required {MIN_COVERAGE:.0%}."
        )

    if reasons:
        return HabitabilityAssessment(
            status="insufficient_data",
            score=None,
            category=None,
            confidence=None,
            confidence_label=None,
            coverage=coverage,
            factors=ordered,
            unavailable_factors=unavailable,
            limiting_factor=None,
            cap_applied=False,
            reasons=tuple(reasons),
            limitations=tuple(limitations),
        )

    weight_sum = coverage
    base = sum(FACTOR_WEIGHTS[n] * f.score for n, f in available.items()) / weight_sum  # type: ignore[operator]
    limiting_factor = min(available, key=lambda n: available[n].score)  # type: ignore[arg-type,return-value]
    cap = available[limiting_factor].score + LIMITING_CAP_MARGIN  # type: ignore[operator]
    cap_applied = base > cap
    score = clamp(min(base, cap))

    confidence = sum(FACTOR_WEIGHTS[n] * f.confidence for n, f in available.items()) / sum(
        FACTOR_WEIGHTS.values()
    )
    if cap_applied:
        limitations.append(
            f"Overall score capped by the weakest factor '{limiting_factor}' "
            f"(weakest score + {LIMITING_CAP_MARGIN:g})."
        )

    return HabitabilityAssessment(
        status="scored",
        score=score,
        category=categorize(score),
        confidence=confidence,
        confidence_label=confidence_label(confidence),
        coverage=coverage,
        factors=ordered,
        unavailable_factors=unavailable,
        limiting_factor=limiting_factor,
        cap_applied=cap_applied,
        reasons=(),
        limitations=tuple(limitations),
    )


def assess_habitability(
    inputs: HabitabilityInputs, extra_limitations: Iterable[str] = ()
) -> HabitabilityAssessment:
    """Evaluate every factor from ``inputs`` and combine them."""
    # Deferred imports: factor modules import this module, so importing them at
    # module level here would create a cycle.
    from .risk_factor import evaluate_risk
    from .temperature_factor import evaluate_temperature
    from .terrain_factor import evaluate_terrain
    from .water_factor import evaluate_water

    factors = {
        "temperature": evaluate_temperature(inputs.temperature),
        "water": evaluate_water(inputs.water),
        "terrain": evaluate_terrain(inputs.terrain),
        "risk": evaluate_risk(inputs.risk),
    }
    return combine_factors(factors, extra_limitations)


# --------------------------------------------------------------------------- #
# Adapter for /indicators/analyze results
# --------------------------------------------------------------------------- #
_FRACTION_UNITS = {"index", "fraction", "ratio", "0-1"}
_PERCENT_UNITS = {"%", "percent", "pct"}


def _period_days(period: Any) -> int | None:
    if not isinstance(period, Mapping):
        return None
    try:
        start = date.fromisoformat(str(period["start"])[:10])
        end = date.fromisoformat(str(period["end"])[:10])
    except (KeyError, ValueError):
        return None
    return (end - start).days + 1


def inputs_from_indicator_results(
    results: Iterable[Mapping[str, Any]],
) -> tuple[HabitabilityInputs, list[str]]:
    """Map ``IndicatorResult``-shaped dicts to habitability inputs.

    Only unambiguous mappings are made; everything else is reported in the
    returned notes (pass them as ``extra_limitations``). Terrain and risk have
    no corresponding indicator today, so they must be supplied directly.
    """
    from .temperature_factor import TemperatureInput, to_celsius
    from .water_factor import WaterInput

    notes: list[str] = []
    temperature: TemperatureInput | None = None
    water: WaterInput | None = None

    for item in results:
        name = item.get("indicator")
        status = item.get("status")
        if status != "available":
            notes.append(f"Indicator '{name}' is {status}; not used.")
            continue

        if name == "temperature":
            value, unit = item.get("value"), item.get("unit")
            try:
                celsius = to_celsius(value, unit)  # type: ignore[arg-type]
            except ValueError as exc:
                notes.append(f"Temperature indicator not used: {exc}")
                continue
            days = _period_days(item.get("period"))
            if days is not None and days < MIN_ANNUAL_PERIOD_DAYS:
                notes.append(
                    f"Temperature indicator not used: its period ({days} days) is shorter "
                    "than a year and is not representative of annual climate."
                )
                continue
            if days is None:
                notes.append("Temperature indicator period is unknown; treated as an annual mean.")
            temperature = TemperatureInput(mean_c=celsius)

        elif name == "water_availability":
            value = item.get("value")
            unit = str(item.get("unit") or "").strip().lower()
            if unit in _FRACTION_UNITS and is_valid_number(value):
                water = WaterInput(availability_index=float(value))
            elif unit in _PERCENT_UNITS and is_valid_number(value):
                water = WaterInput(availability_index=float(value) / 100.0)
            else:
                notes.append(
                    f"Water availability indicator not used: unit {item.get('unit')!r} "
                    "cannot be mapped to a 0-1 index."
                )

        else:
            notes.append(f"Indicator '{name}' has no defined mapping in the habitability model; not used.")

    return HabitabilityInputs(temperature=temperature, water=water), notes
