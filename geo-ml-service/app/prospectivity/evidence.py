"""Evidence primitives for prospectivity analysis.

An *evidence item* is one piece of upstream geological information that has
already been reduced to a **favourability** in [0, 1] for a named criterion
(0 = unfavourable, 1 = highly favourable). This package never produces
observations itself: every item must carry a ``source`` (provenance), an
``evidence_type`` (how directly it was obtained) and, when known, the fraction
of the region the dataset covers.

Evidence types and their credibility weights (modelling assumptions):

    observed      1.00   direct measurement or mapping (assay, well log, field map)
    interpreted   0.75   expert or algorithmic interpretation of measurements
    modelled      0.50   predicted or inferred by a model, not directly measured

Dependency note: this module is the base of the package. It imports only the
shared numeric helpers from ``app.habitability.scoring``.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from ..habitability.scoring import is_valid_number

EvidenceType = Literal["observed", "interpreted", "modelled"]

EVIDENCE_CREDIBILITY: Mapping[str, float] = {
    "observed": 1.00,
    "interpreted": 0.75,
    "modelled": 0.50,
}


class EvidenceError(ValueError):
    """Raised when evidence, an occurrence or a geological input is invalid."""


# --------------------------------------------------------------------------- #
# Validation helpers
# --------------------------------------------------------------------------- #
def _clean_text(value: Any, field: str, max_length: int = 300) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EvidenceError(f"{field} must be a non-empty string.")
    text = value.strip()
    if len(text) > max_length:
        raise EvidenceError(f"{field} must be at most {max_length} characters.")
    return text


def _unit_interval(value: Any, field: str) -> float:
    if not is_valid_number(value):
        raise EvidenceError(f"{field} must be a finite number, got {value!r}.")
    number = float(value)
    if not 0.0 <= number <= 1.0:
        raise EvidenceError(f"{field} must be within [0, 1], got {number:g}.")
    return number


# --------------------------------------------------------------------------- #
# Types
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Criterion:
    """One weighted evidence criterion of a prospectivity model."""

    id: str
    label: str
    weight: float
    description: str

    def __post_init__(self) -> None:
        _clean_text(self.id, "criterion id", 64)
        _clean_text(self.label, "criterion label", 120)
        if not is_valid_number(self.weight) or self.weight <= 0:
            raise EvidenceError(f"criterion {self.id!r}: weight must be a positive number.")


@dataclass(frozen=True)
class EvidenceItem:
    """A validated, provenance-carrying favourability value for one criterion."""

    criterion: str
    favourability: float
    source: str
    evidence_type: EvidenceType
    coverage: float | None = None
    description: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "criterion", _clean_text(self.criterion, "criterion", 64).lower())
        object.__setattr__(self, "source", _clean_text(self.source, "source"))
        kind = _clean_text(self.evidence_type, "evidence_type", 32).lower()
        if kind not in EVIDENCE_CREDIBILITY:
            raise EvidenceError(
                f"evidence_type must be one of {', '.join(EVIDENCE_CREDIBILITY)}; got {kind!r}."
            )
        object.__setattr__(self, "evidence_type", kind)
        object.__setattr__(self, "favourability", _unit_interval(self.favourability, "favourability"))
        if self.coverage is not None:
            object.__setattr__(self, "coverage", _unit_interval(self.coverage, "coverage"))
        if self.description is not None:
            object.__setattr__(self, "description", _clean_text(self.description, "description", 500))

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> EvidenceItem:
        """Build from a plain mapping (e.g. parsed JSON); unknown keys are ignored."""
        return cls(
            criterion=data.get("criterion"),  # type: ignore[arg-type]
            favourability=data.get("favourability"),  # type: ignore[arg-type]
            source=data.get("source"),  # type: ignore[arg-type]
            evidence_type=data.get("evidence_type"),  # type: ignore[arg-type]
            coverage=data.get("coverage"),
            description=data.get("description"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "criterion": self.criterion,
            "favourability": self.favourability,
            "source": self.source,
            "evidence_type": self.evidence_type,
            "coverage": self.coverage,
            "description": self.description,
        }


@dataclass(frozen=True)
class ReportedOccurrence:
    """A previously *reported* occurrence from a named source.

    It is echoed in reports for context only. It is never verified by this
    system and never changes a score.
    """

    commodity: str
    source: str
    name: str | None = None
    reported_status: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "commodity", _clean_text(self.commodity, "commodity", 64))
        object.__setattr__(self, "source", _clean_text(self.source, "source"))
        if self.name is not None:
            object.__setattr__(self, "name", _clean_text(self.name, "name", 200))
        if self.reported_status is not None:
            object.__setattr__(
                self, "reported_status", _clean_text(self.reported_status, "reported_status", 120)
            )

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> ReportedOccurrence:
        return cls(
            commodity=data.get("commodity"),  # type: ignore[arg-type]
            source=data.get("source"),  # type: ignore[arg-type]
            name=data.get("name"),
            reported_status=data.get("reported_status"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "commodity": self.commodity,
            "source": self.source,
            "name": self.name,
            "reported_status": self.reported_status,
            "verified": False,
        }


# --------------------------------------------------------------------------- #
# Parsing and grouping
# --------------------------------------------------------------------------- #
def parse_evidence(
    raw: Iterable[EvidenceItem | Mapping[str, Any]],
) -> tuple[list[EvidenceItem], list[str]]:
    """Validate raw evidence; invalid entries are dropped and reported, never repaired."""
    items: list[EvidenceItem] = []
    issues: list[str] = []
    for index, entry in enumerate(raw):
        if isinstance(entry, EvidenceItem):
            items.append(entry)
        elif isinstance(entry, Mapping):
            try:
                items.append(EvidenceItem.from_mapping(entry))
            except EvidenceError as exc:
                issues.append(f"evidence[{index}]: {exc}")
        else:
            issues.append(f"evidence[{index}]: expected an EvidenceItem or mapping.")
    return items, issues


def parse_occurrences(
    raw: Iterable[ReportedOccurrence | Mapping[str, Any]],
) -> tuple[list[ReportedOccurrence], list[str]]:
    occurrences: list[ReportedOccurrence] = []
    issues: list[str] = []
    for index, entry in enumerate(raw):
        if isinstance(entry, ReportedOccurrence):
            occurrences.append(entry)
        elif isinstance(entry, Mapping):
            try:
                occurrences.append(ReportedOccurrence.from_mapping(entry))
            except EvidenceError as exc:
                issues.append(f"reported_occurrences[{index}]: {exc}")
        else:
            issues.append(f"reported_occurrences[{index}]: expected a ReportedOccurrence or mapping.")
    return occurrences, issues


def group_by_criterion(
    items: Sequence[EvidenceItem], criteria: Sequence[Criterion]
) -> tuple[dict[str, list[EvidenceItem]], list[str]]:
    """Group items by criterion id; items for unknown criteria are ignored and reported."""
    known = {c.id for c in criteria}
    grouped: dict[str, list[EvidenceItem]] = {}
    issues: list[str] = []
    for item in items:
        if item.criterion in known:
            grouped.setdefault(item.criterion, []).append(item)
        else:
            issues.append(
                f"Evidence for criterion {item.criterion!r} (source: {item.source}) "
                "is not part of this model; ignored."
            )
    return grouped, issues


def criterion_favourability(items: Sequence[EvidenceItem]) -> float:
    """Credibility-weighted mean favourability of the items for one criterion."""
    if not items:
        raise ValueError("At least one evidence item is required.")
    weights = [EVIDENCE_CREDIBILITY[i.evidence_type] for i in items]
    return sum(w * i.favourability for w, i in zip(weights, items)) / sum(weights)
