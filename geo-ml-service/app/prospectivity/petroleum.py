"""Petroleum (oil) prospectivity.

Evaluates the six elements of a petroleum system (source, maturity, reservoir,
seal, trap, migration and timing) with a non-compensatory weighted geometric
mean. Source rock, reservoir and seal are essential: without valid evidence for
all three no score is produced.

Element definitions and the combination rule are shared with the gas module
through ``geology``; this module supplies the oil-specific parts: element
descriptions, weights and the oil-window maturity definition.

Results are potential only (``unconfirmed_potential``). No accumulation is
confirmed or quantified by this analysis (that requires drilling, testing and
PRMS classification).

The oil window below is a heuristic: 0 favourability at 0.5 %Ro rising to full
at 0.7 %Ro, full until 1.1 %Ro, falling to 0 at 1.5 %Ro.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from .evidence import EvidenceItem, EvidenceType
from .geology import (
    HYDROCARBON_ESSENTIAL,
    HYDROCARBON_MIN_WEIGHT_COVERAGE,
    HYDROCARBON_RATIONALE,
    MaturityWindow,
    ProspectivityModel,
    ProspectivityResult,
    evaluate_model,
    hydrocarbon_system_criteria,
    maturity_evidence,
)

OIL_WINDOW = MaturityWindow(zero_low=0.5, full_low=0.7, full_high=1.1, zero_high=1.5)

PETROLEUM_MODEL = ProspectivityModel(
    kind="petroleum",
    commodity="oil",
    criteria=hydrocarbon_system_criteria(
        source_description="Quantity and quality (for example TOC, kerogen type) of oil-prone source rock.",
        maturity_description="Thermal maturity within the oil-generation window.",
        seal_weight=0.20,
    ),
    essential=HYDROCARBON_ESSENTIAL,
    rule="necessary_elements",
    min_weight_coverage=HYDROCARBON_MIN_WEIGHT_COVERAGE,
    rationale=HYDROCARBON_RATIONALE,
)


def oil_maturity_evidence(
    ro_percent: float,
    source: str,
    evidence_type: EvidenceType = "observed",
    coverage: float | None = None,
) -> EvidenceItem:
    """Thermal-maturity evidence from a vitrinite reflectance value, scored against the oil window."""
    return maturity_evidence(ro_percent, OIL_WINDOW, source, evidence_type, coverage)


def evaluate_petroleum(
    evidence: Iterable[EvidenceItem | Mapping[str, Any]],
) -> ProspectivityResult:
    """Evaluate oil prospectivity from supplied evidence."""
    return evaluate_model(PETROLEUM_MODEL, evidence)
