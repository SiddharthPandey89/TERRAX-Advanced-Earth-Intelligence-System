"""Natural gas prospectivity.

Uses the same petroleum-system elements and non-compensatory combination rule as
the petroleum module (shared through ``geology``), with gas-specific parts:

* a gas-window maturity definition (thermogenic gas generation occurs at higher
  maturity than oil), and
* a higher seal weight (0.25 vs 0.20), because gas migrates more readily and
  seal integrity is more critical. This is a heuristic assumption.

The gas window below is a heuristic: 0 favourability at 0.8 %Ro rising to full
at 1.3 %Ro, full until 3.0 %Ro, falling to 0 at 4.5 %Ro.

Results are potential only (``unconfirmed_potential``). No gas accumulation is
confirmed or quantified by this analysis.
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

GAS_WINDOW = MaturityWindow(zero_low=0.8, full_low=1.3, full_high=3.0, zero_high=4.5)

GAS_MODEL = ProspectivityModel(
    kind="gas",
    commodity="natural_gas",
    criteria=hydrocarbon_system_criteria(
        source_description="Quantity and quality (for example TOC, gas-prone kerogen) of gas-prone source rock.",
        maturity_description="Thermal maturity within the thermogenic gas-generation window.",
        seal_weight=0.25,
    ),
    essential=HYDROCARBON_ESSENTIAL,
    rule="necessary_elements",
    min_weight_coverage=HYDROCARBON_MIN_WEIGHT_COVERAGE,
    rationale=HYDROCARBON_RATIONALE,
)


def gas_maturity_evidence(
    ro_percent: float,
    source: str,
    evidence_type: EvidenceType = "observed",
    coverage: float | None = None,
) -> EvidenceItem:
    """Thermal-maturity evidence from a vitrinite reflectance value, scored against the gas window."""
    return maturity_evidence(ro_percent, GAS_WINDOW, source, evidence_type, coverage)


def evaluate_gas(
    evidence: Iterable[EvidenceItem | Mapping[str, Any]],
) -> ProspectivityResult:
    """Evaluate natural gas prospectivity from supplied evidence."""
    return evaluate_model(GAS_MODEL, evidence)
