"""Prospectivity engine: the single entry point for the package.

Dispatches each requested target (mineral commodity, petroleum, natural gas) to
its model and collects the results into one report. It adds no scoring logic of
its own; all evaluation lives in ``geology.evaluate_model``.

Dependency order (no cycles):
    evidence -> confidence -> geology -> mineral / petroleum / gas -> engine

Every result and the report itself carry ``resource_status="unconfirmed_potential"``
and a disclaimer. Reported occurrences supplied by the caller are echoed for
context, are marked unverified, and never influence a score.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .evidence import (
    EvidenceItem,
    ReportedOccurrence,
    parse_occurrences,
)
from .gas import GAS_MODEL
from .geology import (
    RESOURCE_DISCLAIMER,
    RESOURCE_STATUS,
    ProspectivityKind,
    ProspectivityModel,
    ProspectivityResult,
    evaluate_model,
)
from .mineral import build_mineral_model, normalize_commodity
from .petroleum import PETROLEUM_MODEL

SUPPORTED_KINDS: tuple[str, ...] = ("mineral", "petroleum", "gas")

OCCURRENCE_NOTE = (
    "Reported occurrences are taken from the named sources as supplied. They are not verified "
    "by this system and do not influence potential scores."
)


@dataclass(frozen=True)
class ProspectivityTarget:
    """What to assess: a mineral commodity, petroleum (oil) or natural gas."""

    kind: ProspectivityKind
    commodity: str | None = None  # required for mineral, not allowed otherwise

    def __post_init__(self) -> None:
        if self.kind not in SUPPORTED_KINDS:
            raise ValueError(f"kind must be one of {', '.join(SUPPORTED_KINDS)}; got {self.kind!r}.")
        if self.kind == "mineral":
            if self.commodity is None:
                raise ValueError("A mineral target requires a commodity.")
            object.__setattr__(self, "commodity", normalize_commodity(self.commodity))
        elif self.commodity is not None:
            raise ValueError(f"commodity is only valid for mineral targets, not {self.kind!r}.")

    @property
    def key(self) -> str:
        return f"mineral:{self.commodity}" if self.kind == "mineral" else self.kind


@dataclass(frozen=True)
class TargetRequest:
    """A target together with the evidence supplied for it."""

    target: ProspectivityTarget
    evidence: Sequence[EvidenceItem | Mapping[str, Any]]


@dataclass(frozen=True)
class ProspectivityReport:
    results: tuple[ProspectivityResult, ...]
    reported_occurrences: tuple[ReportedOccurrence, ...]
    issues: tuple[str, ...]
    resource_status: str = RESOURCE_STATUS
    disclaimer: str = RESOURCE_DISCLAIMER
    occurrence_note: str = OCCURRENCE_NOTE

    def to_dict(self) -> dict[str, Any]:
        return {
            "results": [r.to_dict() for r in self.results],
            "reported_occurrences": [o.to_dict() for o in self.reported_occurrences],
            "occurrence_note": self.occurrence_note,
            "issues": list(self.issues),
            "resource_status": self.resource_status,
            "disclaimer": self.disclaimer,
        }


def resolve_model(target: ProspectivityTarget) -> ProspectivityModel:
    """Return the model for ``target``."""
    if target.kind == "mineral":
        return build_mineral_model(target.commodity)  # type: ignore[arg-type]
    if target.kind == "petroleum":
        return PETROLEUM_MODEL
    return GAS_MODEL


def parse_request(data: Mapping[str, Any]) -> TargetRequest:
    """Build a ``TargetRequest`` from a plain mapping.

    Expected keys: ``kind``, ``commodity`` (mineral only) and ``evidence`` (a list
    of evidence mappings). Raises ``ValueError`` for a malformed request.
    """
    if not isinstance(data, Mapping):
        raise ValueError("A target request must be a mapping.")
    evidence = data.get("evidence", [])
    if isinstance(evidence, (str, bytes)) or not isinstance(evidence, Sequence):
        raise ValueError("'evidence' must be a list of evidence entries.")
    target = ProspectivityTarget(kind=data.get("kind"), commodity=data.get("commodity"))  # type: ignore[arg-type]
    return TargetRequest(target=target, evidence=evidence)


def analyze_prospectivity(
    requests: Sequence[TargetRequest],
    reported_occurrences: Iterable[ReportedOccurrence | Mapping[str, Any]] = (),
) -> ProspectivityReport:
    """Evaluate every requested target and return one report.

    Raises ``ValueError`` for an empty request list or duplicate targets. Missing
    or invalid evidence never raises: it yields an ``insufficient_data`` result
    that lists the reasons.
    """
    if not requests:
        raise ValueError("At least one target request is required.")

    seen: set[str] = set()
    results: list[ProspectivityResult] = []
    for request in requests:
        key = request.target.key
        if key in seen:
            raise ValueError(f"Duplicate target {key!r}; supply each target once.")
        seen.add(key)
        results.append(evaluate_model(resolve_model(request.target), request.evidence))

    occurrences, issues = parse_occurrences(reported_occurrences)
    return ProspectivityReport(
        results=tuple(results),
        reported_occurrences=tuple(occurrences),
        issues=tuple(issues),
    )
