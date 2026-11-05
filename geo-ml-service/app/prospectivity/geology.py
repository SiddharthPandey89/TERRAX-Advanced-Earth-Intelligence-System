"""Geological reasoning core for prospectivity analysis.

Contents
--------
* Combination rules that encode how geological evidence is combined:
    - ``combine_additive``: index-overlay style weighted mean. Used for mineral
      systems, where strong evidence for one criterion can partly compensate for
      weak evidence for another.
    - ``combine_necessary_elements``: weighted geometric mean. Used for
      hydrocarbon systems, where source, reservoir, seal, trap, migration and
      timing must ALL be present, so a near-zero element drives the result toward
      zero instead of being averaged away.
* ``ProspectivityModel`` / ``evaluate_model``: the single evaluation routine used
  by the mineral, petroleum and gas modules.
* Shared converters from raw geochemical measurements (TOC, vitrinite
  reflectance) to evidence items.

Result semantics
----------------
A ``potential_score`` (0-100) is a RELATIVE FAVOURABILITY INDEX computed from the
supplied evidence. It is not a probability, a resource estimate, or confirmation
of a deposit or accumulation. Every result carries
``resource_status="unconfirmed_potential"`` and a disclaimer. A score is returned
only when the model's essential criteria are present and enough of the criterion
weight is covered; otherwise it is ``None`` with explicit reasons.

All weights and thresholds are heuristic modelling assumptions that need review
by a qualified geoscientist.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Literal

from ..habitability.scoring import categorize, clamp, is_valid_number, plateau_score, ramp_score
from .confidence import ConfidenceReport, assess_confidence
from .evidence import (
    Criterion,
    EvidenceError,
    EvidenceItem,
    EvidenceType,
    criterion_favourability,
    group_by_criterion,
    parse_evidence,
)

ProspectivityKind = Literal["mineral", "petroleum", "gas"]
CombinationRule = Literal["additive", "necessary_elements"]

RESOURCE_STATUS = "unconfirmed_potential"
RESOURCE_DISCLAIMER = (
    "Potential scores are relative favourability indices computed from the supplied evidence. "
    "They are not probabilities of occurrence, resource or reserve estimates, or confirmation of "
    "any deposit or accumulation. Confirmation requires direct exploration (for example sampling, "
    "drilling and testing) and classification under a recognised standard such as JORC or "
    "NI 43-101 (minerals) or PRMS (petroleum)."
)

ELEMENT_FLOOR = 0.01  # keeps ln() finite; a 0 element still drives the score to ~0


# --------------------------------------------------------------------------- #
# Combination rules
# --------------------------------------------------------------------------- #
def _check_combination_inputs(
    favourability: Mapping[str, float], weights: Mapping[str, float]
) -> float:
    if not favourability:
        raise ValueError("favourability must not be empty.")
    total = 0.0
    for key, value in favourability.items():
        if key not in weights:
            raise ValueError(f"No weight for criterion {key!r}.")
        if not is_valid_number(value) or not 0.0 <= value <= 1.0:
            raise ValueError(f"Favourability for {key!r} must be within [0, 1], got {value!r}.")
        if not is_valid_number(weights[key]) or weights[key] <= 0:
            raise ValueError(f"Weight for {key!r} must be positive.")
        total += weights[key]
    return total


def combine_additive(favourability: Mapping[str, float], weights: Mapping[str, float]) -> float:
    """Weighted arithmetic mean of favourabilities, in [0, 1]."""
    total = _check_combination_inputs(favourability, weights)
    return sum(weights[k] * v for k, v in favourability.items()) / total


def combine_necessary_elements(
    favourability: Mapping[str, float], weights: Mapping[str, float]
) -> float:
    """Weighted geometric mean of favourabilities, in [0, 1] (non-compensatory)."""
    total = _check_combination_inputs(favourability, weights)
    log_sum = sum(weights[k] * math.log(max(v, ELEMENT_FLOOR)) for k, v in favourability.items())
    return math.exp(log_sum / total)


_RULES: Mapping[str, Callable[[Mapping[str, float], Mapping[str, float]], float]] = {
    "additive": combine_additive,
    "necessary_elements": combine_necessary_elements,
}


# --------------------------------------------------------------------------- #
# Model and result types
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ProspectivityModel:
    """A weighted-criteria model for one commodity."""

    kind: ProspectivityKind
    commodity: str
    criteria: tuple[Criterion, ...]
    essential: tuple[str, ...]
    rule: CombinationRule
    min_weight_coverage: float
    rationale: str

    def __post_init__(self) -> None:
        ids = [c.id for c in self.criteria]
        if not ids:
            raise ValueError("A model needs at least one criterion.")
        if len(set(ids)) != len(ids):
            raise ValueError("Criterion ids must be unique.")
        unknown = set(self.essential) - set(ids)
        if unknown:
            raise ValueError(f"Essential criteria not in model: {', '.join(sorted(unknown))}")
        if self.rule not in _RULES:
            raise ValueError(f"Unknown combination rule {self.rule!r}.")
        if not 0.0 < self.min_weight_coverage <= 1.0:
            raise ValueError("min_weight_coverage must be within (0, 1].")

    @property
    def name(self) -> str:
        return f"{self.kind}:{self.commodity}"


@dataclass(frozen=True)
class CriterionAssessment:
    id: str
    label: str
    weight: float
    favourability: float | None  # None = no valid evidence
    evidence_count: int
    sources: tuple[str, ...]
    evidence_types: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "weight": self.weight,
            "favourability": None if self.favourability is None else round(self.favourability, 4),
            "evidence_count": self.evidence_count,
            "sources": list(self.sources),
            "evidence_types": list(self.evidence_types),
        }


@dataclass(frozen=True)
class ProspectivityResult:
    kind: ProspectivityKind
    commodity: str
    model_name: str
    status: Literal["scored", "insufficient_data"]
    potential_score: float | None
    category: str | None
    confidence: ConfidenceReport
    criteria: tuple[CriterionAssessment, ...]
    missing_criteria: tuple[str, ...]
    weight_coverage: float
    limiting_criterion: str | None
    combination_rule: CombinationRule
    rationale: str
    reasons: tuple[str, ...]
    issues: tuple[str, ...]
    resource_status: str = RESOURCE_STATUS
    disclaimer: str = RESOURCE_DISCLAIMER

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "commodity": self.commodity,
            "model": self.model_name,
            "status": self.status,
            "potential_score": None if self.potential_score is None else round(self.potential_score, 2),
            "category": self.category,
            "confidence": self.confidence.to_dict(),
            "criteria": [c.to_dict() for c in self.criteria],
            "missing_criteria": list(self.missing_criteria),
            "weight_coverage": round(self.weight_coverage, 3),
            "limiting_criterion": self.limiting_criterion,
            "combination_rule": self.combination_rule,
            "rationale": self.rationale,
            "reasons": list(self.reasons),
            "issues": list(self.issues),
            "resource_status": self.resource_status,
            "disclaimer": self.disclaimer,
        }


# --------------------------------------------------------------------------- #
# Evaluation
# --------------------------------------------------------------------------- #
def evaluate_model(
    model: ProspectivityModel, evidence: Iterable[EvidenceItem | Mapping[str, Any]]
) -> ProspectivityResult:
    """Evaluate ``evidence`` against ``model``.

    Invalid evidence is dropped and reported in ``issues``; absent criteria are
    reported in ``missing_criteria``. Nothing is defaulted or estimated.
    """
    items, issues = parse_evidence(evidence)
    grouped, group_issues = group_by_criterion(items, model.criteria)
    issues.extend(group_issues)

    favourability = {cid: criterion_favourability(group) for cid, group in grouped.items()}
    weights = {c.id: c.weight for c in model.criteria}
    present_weights = {cid: weights[cid] for cid in favourability}
    weight_coverage = sum(present_weights.values()) / sum(weights.values())

    assessments = tuple(
        CriterionAssessment(
            id=c.id,
            label=c.label,
            weight=c.weight,
            favourability=favourability.get(c.id),
            evidence_count=len(grouped.get(c.id, ())),
            sources=tuple(dict.fromkeys(i.source for i in grouped.get(c.id, ()))),
            evidence_types=tuple(dict.fromkeys(i.evidence_type for i in grouped.get(c.id, ()))),
        )
        for c in model.criteria
    )
    missing = tuple(c.id for c in model.criteria if c.id not in favourability)
    confidence = assess_confidence(model.criteria, grouped)

    reasons: list[str] = []
    for cid in model.essential:
        if cid not in favourability:
            reasons.append(f"Essential criterion '{cid}' has no valid evidence.")
    if weight_coverage < model.min_weight_coverage:
        reasons.append(
            f"Evidence covers {weight_coverage:.0%} of the model's criterion weight; "
            f"at least {model.min_weight_coverage:.0%} is required."
        )

    score: float | None = None
    category: str | None = None
    limiting: str | None = None
    if not reasons:
        raw = _RULES[model.rule](favourability, present_weights)
        score = clamp(100.0 * raw)
        category = categorize(score)
        limiting = min(
            (c.id for c in model.criteria if c.id in favourability),
            key=favourability.__getitem__,
        )

    return ProspectivityResult(
        kind=model.kind,
        commodity=model.commodity,
        model_name=model.name,
        status="scored" if score is not None else "insufficient_data",
        potential_score=score,
        category=category,
        confidence=confidence,
        criteria=assessments,
        missing_criteria=missing,
        weight_coverage=weight_coverage,
        limiting_criterion=limiting,
        combination_rule=model.rule,
        rationale=model.rationale,
        reasons=tuple(reasons),
        issues=tuple(issues),
    )


# --------------------------------------------------------------------------- #
# Shared hydrocarbon-system definition (used by petroleum.py and gas.py)
# --------------------------------------------------------------------------- #
def hydrocarbon_system_criteria(
    *, source_description: str, maturity_description: str, seal_weight: float
) -> tuple[Criterion, ...]:
    """The six petroleum-system elements; commodity modules supply what differs."""
    return (
        Criterion("source_rock", "Source rock", 0.20, source_description),
        Criterion("thermal_maturity", "Thermal maturity", 0.15, maturity_description),
        Criterion("reservoir", "Reservoir rock", 0.20,
                  "Presence and quality (porosity, permeability, thickness) of reservoir rock."),
        Criterion("seal", "Seal / cap rock", seal_weight,
                  "Presence and integrity of a sealing rock above the reservoir."),
        Criterion("trap", "Trap", 0.15,
                  "Structural or stratigraphic closure able to retain hydrocarbons."),
        Criterion("migration", "Migration pathway", 0.05,
                  "Connection between the mature source and the trap."),
        Criterion("timing", "Charge timing", 0.05,
                  "Hydrocarbon generation and expulsion after trap formation."),
    )


HYDROCARBON_ESSENTIAL: tuple[str, ...] = ("source_rock", "reservoir", "seal")
HYDROCARBON_MIN_WEIGHT_COVERAGE = 0.7
HYDROCARBON_RATIONALE = (
    "Weighted geometric mean of petroleum-system elements: all elements are necessary, so a "
    "very unfavourable element strongly lowers the score."
)


# --------------------------------------------------------------------------- #
# Geochemical converters
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class MaturityWindow:
    """Vitrinite reflectance (%Ro) plateau: 0 at zero_low, 1 on [full_low, full_high], 0 at zero_high."""

    zero_low: float
    full_low: float
    full_high: float
    zero_high: float


def _positive_number(value: Any, field: str, upper: float) -> float:
    if not is_valid_number(value):
        raise EvidenceError(f"{field} must be a finite number, got {value!r}.")
    number = float(value)
    if not 0.0 <= number <= upper:
        raise EvidenceError(f"{field} must be within [0, {upper:g}], got {number:g}.")
    return number


def toc_favourability(toc_wt_percent: float) -> float:
    """Source-rock richness from total organic carbon (wt %): 0 at <= 0.5, 1 at >= 4.0 (linear)."""
    toc = _positive_number(toc_wt_percent, "toc_wt_percent", 100.0)
    return ramp_score(toc, 0.5, 4.0) / 100.0


def maturity_favourability(ro_percent: float, window: MaturityWindow) -> float:
    """Thermal-maturity favourability of a vitrinite reflectance value against a window."""
    ro = _positive_number(ro_percent, "ro_percent", 10.0)
    return plateau_score(ro, window.zero_low, window.full_low, window.full_high, window.zero_high) / 100.0


def source_rock_evidence(
    toc_wt_percent: float,
    source: str,
    evidence_type: EvidenceType = "observed",
    coverage: float | None = None,
) -> EvidenceItem:
    """Evidence item for the ``source_rock`` criterion from a TOC measurement."""
    return EvidenceItem(
        criterion="source_rock",
        favourability=toc_favourability(toc_wt_percent),
        source=source,
        evidence_type=evidence_type,
        coverage=coverage,
        description=f"Derived from TOC = {toc_wt_percent:g} wt %.",
    )


def maturity_evidence(
    ro_percent: float,
    window: MaturityWindow,
    source: str,
    evidence_type: EvidenceType = "observed",
    coverage: float | None = None,
) -> EvidenceItem:
    """Evidence item for the ``thermal_maturity`` criterion from a vitrinite reflectance value."""
    return EvidenceItem(
        criterion="thermal_maturity",
        favourability=maturity_favourability(ro_percent, window),
        source=source,
        evidence_type=evidence_type,
        coverage=coverage,
        description=f"Derived from vitrinite reflectance = {ro_percent:g} %Ro.",
    )
