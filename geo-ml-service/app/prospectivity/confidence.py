"""Confidence scoring for prospectivity results.

Confidence describes how well the *evidence base* supports a potential score.
It is NOT a probability of discovery and is reported separately from the score
(the two are never multiplied).

Methodology (all weights are modelling assumptions)
---------------------------------------------------
confidence = weighted mean of the applicable components below.

    criteria_completeness  0.40  share of criterion weight with at least one valid
                                 evidence item
    evidence_credibility   0.25  criterion-weighted mean of the mean credibility of
                                 each criterion's items (observed 1.0, interpreted
                                 0.75, modelled 0.5), over criteria with evidence
    data_coverage          0.20  criterion-weighted mean of the best reported spatial
                                 coverage per criterion, over criteria with evidence.
                                 Unreported coverage counts as 0 (unverified)
    evidence_agreement     0.15  criterion-weighted mean of (1 - spread) for criteria
                                 with two or more items, where spread = max - min
                                 favourability. Not applicable (excluded and the
                                 remaining weights renormalised) when no criterion
                                 has multiple items

Every component, its value and its weight are returned so the figure can be
audited. Limitations are listed in plain language.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from ..habitability.scoring import clamp, confidence_label
from .evidence import EVIDENCE_CREDIBILITY, Criterion, EvidenceItem

COMPONENT_WEIGHTS: Mapping[str, float] = {
    "criteria_completeness": 0.40,
    "evidence_credibility": 0.25,
    "data_coverage": 0.20,
    "evidence_agreement": 0.15,
}

CONFIDENCE_NOTE = (
    "Confidence reflects the completeness, directness, coverage and consistency of the "
    "supplied evidence. It is not a probability of discovery."
)


@dataclass(frozen=True)
class ConfidenceComponent:
    name: str
    value: float | None  # None = not applicable
    weight: float
    explanation: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "value": None if self.value is None else round(self.value, 3),
            "weight": self.weight,
            "applicable": self.value is not None,
            "explanation": self.explanation,
        }


@dataclass(frozen=True)
class ConfidenceReport:
    score: float  # 0-1
    label: str  # low | medium | high
    components: tuple[ConfidenceComponent, ...]
    limitations: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": round(self.score, 3),
            "label": self.label,
            "components": [c.to_dict() for c in self.components],
            "limitations": list(self.limitations),
        }


def assess_confidence(
    criteria: Sequence[Criterion], grouped: Mapping[str, Sequence[EvidenceItem]]
) -> ConfidenceReport:
    """Compute the transparent confidence report for one model evaluation.

    ``grouped`` maps criterion id to its (non-empty) evidence items, as produced
    by ``evidence.group_by_criterion``.
    """
    total_weight = sum(c.weight for c in criteria)
    present = [c for c in criteria if grouped.get(c.id)]
    missing = [c for c in criteria if not grouped.get(c.id)]
    present_weight = sum(c.weight for c in present)

    completeness = present_weight / total_weight

    if present:
        credibility = sum(
            c.weight
            * sum(EVIDENCE_CREDIBILITY[i.evidence_type] for i in grouped[c.id])
            / len(grouped[c.id])
            for c in present
        ) / present_weight
        coverage = sum(
            c.weight * max((i.coverage or 0.0) for i in grouped[c.id]) for c in present
        ) / present_weight
    else:
        credibility = coverage = 0.0

    multi = [c for c in present if len(grouped[c.id]) >= 2]
    agreement: float | None = None
    if multi:
        multi_weight = sum(c.weight for c in multi)
        agreement = sum(
            c.weight
            * (
                1.0
                - (
                    max(i.favourability for i in grouped[c.id])
                    - min(i.favourability for i in grouped[c.id])
                )
            )
            for c in multi
        ) / multi_weight

    components = (
        ConfidenceComponent(
            "criteria_completeness",
            completeness,
            COMPONENT_WEIGHTS["criteria_completeness"],
            "Share of criterion weight that has at least one valid evidence item.",
        ),
        ConfidenceComponent(
            "evidence_credibility",
            credibility,
            COMPONENT_WEIGHTS["evidence_credibility"],
            "Directness of the evidence (observed 1.0, interpreted 0.75, modelled 0.5).",
        ),
        ConfidenceComponent(
            "data_coverage",
            coverage,
            COMPONENT_WEIGHTS["data_coverage"],
            "Best reported spatial coverage per criterion; unreported coverage counts as 0.",
        ),
        ConfidenceComponent(
            "evidence_agreement",
            agreement,
            COMPONENT_WEIGHTS["evidence_agreement"],
            "Consistency between multiple evidence items for the same criterion "
            "(not applicable when every criterion has a single item).",
        ),
    )

    applicable = [c for c in components if c.value is not None]
    score = clamp(
        sum(c.weight * c.value for c in applicable) / sum(c.weight for c in applicable),  # type: ignore[operator]
        0.0,
        1.0,
    )

    limitations: list[str] = [CONFIDENCE_NOTE]
    if missing:
        limitations.append(
            "No valid evidence for: " + ", ".join(c.label for c in missing) + "."
        )
    present_items = [i for c in present for i in grouped[c.id]]
    unreported = sum(1 for i in present_items if i.coverage is None)
    if unreported:
        limitations.append(
            f"Spatial coverage not reported for {unreported} evidence item(s); treated as 0 (unverified)."
        )
    single = [c.label for c in present if len(grouped[c.id]) == 1]
    if single:
        limitations.append("Single evidence layer (no corroboration) for: " + ", ".join(single) + ".")
    if present_items and not any(i.evidence_type == "observed" for i in present_items):
        limitations.append("No directly observed evidence was supplied.")

    return ConfidenceReport(
        score=score,
        label=confidence_label(score),
        components=components,
        limitations=tuple(limitations),
    )
