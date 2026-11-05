"""Mineral and metal prospectivity.

A generic mineral-system model: favourable host rock, structural control,
geochemical and geophysical anomalies, and hydrothermal alteration are combined
with an additive (index-overlay) rule, because strong evidence for one criterion
can partly compensate for weak evidence for another.

The model contains no commodity-specific thresholds. The caller must supply
favourability values (0-1) that were already derived for the target commodity or
deposit type; ``commodity`` only labels the result. Mineral deposits are not
confirmed by this analysis: results are always ``unconfirmed_potential``.

Weights are heuristic modelling assumptions. At least three criteria are needed
for a score (minimum 60 % of the criterion weight).
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any

from .evidence import Criterion, EvidenceItem
from .geology import ProspectivityModel, ProspectivityResult, evaluate_model

MINERAL_CRITERIA: tuple[Criterion, ...] = (
    Criterion("host_lithology", "Host lithology", 0.25,
              "Favourability of the mapped host rocks for the target deposit type."),
    Criterion("structural_control", "Structural control", 0.20,
              "Favourability of faults, shear zones, folds or contacts that control mineralisation."),
    Criterion("occurrence_proximity", "Reported occurrences", 0.20,
              "Density and proximity of previously reported occurrences of the commodity (unverified records)."),
    Criterion("geochemical_anomaly", "Geochemical anomaly", 0.15,
              "Strength of soil, stream-sediment or rock geochemical anomalies for the commodity."),
    Criterion("geophysical_anomaly", "Geophysical anomaly", 0.10,
              "Magnetic, gravity, radiometric or electrical anomalies consistent with the deposit type."),
    Criterion("hydrothermal_alteration", "Hydrothermal alteration", 0.10,
              "Presence of alteration assemblages associated with the deposit type."),
)

MINERAL_RATIONALE = (
    "Weighted arithmetic mean (index overlay) of mineral-system criteria; evidence for one "
    "criterion can partly compensate for another."
)
MINERAL_MIN_WEIGHT_COVERAGE = 0.6
_COMMODITY_PATTERN = re.compile(r"^[a-z0-9][a-z0-9 _.\-]{0,63}$")


def normalize_commodity(commodity: str) -> str:
    """Lower-case, trim and validate a commodity label (for example ``"Gold"`` -> ``"gold"``)."""
    if not isinstance(commodity, str):
        raise ValueError("commodity must be a string.")
    value = commodity.strip().lower()
    if not _COMMODITY_PATTERN.match(value):
        raise ValueError(
            "commodity must be 1-64 characters: letters, digits, spaces, '-', '_' or '.'."
        )
    return value


def build_mineral_model(commodity: str) -> ProspectivityModel:
    """Build the mineral-system model labelled for ``commodity``."""
    return ProspectivityModel(
        kind="mineral",
        commodity=normalize_commodity(commodity),
        criteria=MINERAL_CRITERIA,
        essential=(),
        rule="additive",
        min_weight_coverage=MINERAL_MIN_WEIGHT_COVERAGE,
        rationale=MINERAL_RATIONALE,
    )


def evaluate_mineral(
    commodity: str, evidence: Iterable[EvidenceItem | Mapping[str, Any]]
) -> ProspectivityResult:
    """Evaluate mineral prospectivity for ``commodity`` from supplied evidence."""
    return evaluate_model(build_mineral_model(commodity), evidence)
