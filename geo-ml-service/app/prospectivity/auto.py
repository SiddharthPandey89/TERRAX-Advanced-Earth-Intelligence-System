"""Automatic, evidence-based prospectivity for a selected region.

Collects real geological evidence (Macrostrat mapped units, USGS MRDS reported
occurrences) and converts it into sourced favourability values for the existing
prospectivity engine. Nothing is fabricated: criteria without data stay missing,
and the engine withholds the score when evidence is insufficient.

The lithology -> favourability tables are expert heuristics (labelled
"interpreted"); structural and trap criteria use lithological-contact diversity
as a coarse proxy (labelled "modelled", lowest credibility). Results are
unconfirmed screening potential, never a discovery or reserves claim.
"""
from __future__ import annotations

import re
from typing import Any, Callable

from ..ingestion.geodata import fetch_occurrences, fetch_units
from .engine import ProspectivityTarget, TargetRequest, analyze_prospectivity

UNIT_SRC = "Macrostrat geologic_units/map (sampled grid)"
OCC_SRC = "USGS MRDS reported occurrences"
HEURISTIC = "expert lithology-favourability heuristic (needs geoscientist review)"

MINERALS: dict[str, dict[str, Any]] = {
    "iron ore": {"words": ["iron"], "rules": [
        (r"banded iron|iron formation|itabirite|ironstone|hematite|magnetite", 1.0),
        (r"laterit|ferrugin", 0.6), (r"greenstone|metavolcan|amphibolite", 0.5),
        (r"quartzite|phyllite|schist|metasediment|chert", 0.4)]},
    "copper": {"words": ["copper"], "rules": [
        (r"porphyr|skarn|volcanogenic", 0.9), (r"andesit|diorite|granodiorite|dacit|rhyolit|volcanic", 0.55),
        (r"basalt|greenstone|amphibolite|mafic", 0.5), (r"red.?bed|arkose|sandstone|shale", 0.4),
        (r"schist|phyllite|gneiss|metavolcan", 0.4)]},
    "gold": {"words": ["gold"], "rules": [
        (r"greenstone|quartz vein|auriferous", 0.85), (r"banded iron|conglomerate", 0.6),
        (r"schist|phyllite|slate|metasediment|metavolcan|turbidite", 0.55),
        (r"volcanic|andesit|rhyolit|granite|granodiorite|diorite", 0.4)]},
    "bauxite": {"words": ["bauxite", "alumin"], "rules": [
        (r"bauxit", 1.0), (r"laterit", 0.85), (r"basalt|trap\b|deccan", 0.55),
        (r"khondalite|gneiss|granite|syenite|nepheline|alkalin", 0.4), (r"limestone|dolo|karst", 0.35)]},
    "coal": {"words": ["coal", "lignite", "anthracite"], "rules": [
        (r"coal|lignite|anthracite", 1.0), (r"carbonaceous|coaly|gondwana", 0.8), (r"shale|mudstone|siltstone|sandstone", 0.3)]},
    "limestone": {"words": ["limestone", "dolomite", "cement", "carbonate"], "rules": [
        (r"limestone|dolomit|marble|chalk|calcarenite|carbonate", 1.0), (r"marl|calcareous|calc.?silicate", 0.65)]},
    "manganese": {"words": ["manganese"], "rules": [
        (r"mangan|gondite|psilomelane", 1.0), (r"banded iron|laterit", 0.5),
        (r"phyllite|quartzite|chert|shale|metasediment", 0.4), (r"volcan|greenstone", 0.35)]},
}
BASELINE_MINERAL = 0.1  # mapped unit with no favourable keyword

HC_RULES = {
    "source_rock": [(r"black shale|carbonaceous|oil shale|coal|lignite", 1.0), (r"shale|mudstone|claystone|marl", 0.75),
                    (r"siltstone", 0.4), (r"limestone|dolomit", 0.3)],
    "reservoir": [(r"sandstone|arkose|quartz arenite|greywacke|graywacke", 0.9), (r"dolomit", 0.85),
                  (r"limestone|carbonate|calcarenite|reef", 0.7), (r"conglomerate|gravel|sand\b", 0.6), (r"siltstone", 0.35)],
    "seal": [(r"evaporit|salt|halite|anhydrite|gypsum", 1.0), (r"shale|claystone|mudstone", 0.9), (r"marl", 0.6), (r"clay", 0.6)],
}
CRYSTALLINE = r"granit|gneiss|basalt|schist|quartzite|diorite|gabbro|rhyolit|andesit|migmatit|charnockit|amphibolit|phyllite|slate|metamorph|igneous|volcanic"
SEDIMENTARY = r"sandstone|shale|mudstone|limestone|dolomit|siltstone|conglomerate|evaporit|marl|claystone|coal|sediment|alluvi|clastic"


def _text(unit: dict[str, Any]) -> str:
    return " ".join(str(unit.get(k) or "") for k in ("lith", "name", "strat_name", "descrip", "comments")).lower()


def _unique_units(units_per_point: list) -> list[dict[str, Any]]:
    seen: dict[Any, dict[str, Any]] = {}
    for units in units_per_point:
        for u in units or []:
            key = u.get("map_id") or u.get("name") or id(u)
            seen.setdefault(key, u)
    return list(seen.values())


def _best(text: str, rules: list[tuple[str, float]]) -> float | None:
    hits = [score for pattern, score in rules if re.search(pattern, text)]
    return max(hits) if hits else None


def _aggregate(scores: list[float]) -> float:
    return 0.6 * max(scores) + 0.4 * (sum(scores) / len(scores))


def _label(u: dict[str, Any]) -> str:
    return str(u.get("name") or u.get("strat_name") or "unnamed unit")[:80] + (f" [{str(u.get('lith'))[:50]}]" if u.get("lith") else "")


def _classify(score: float | None) -> str:
    if score is None:
        return "Insufficient evidence"
    return "Low" if score < 40 else "Moderate" if score < 60 else "High"


import math

LITH_CLASSES = [
    ("Coal-bearing / carbonaceous", r"coal|lignite|carbonaceous|coaly"), ("Limestone / dolomite / carbonate", r"limestone|dolomit|carbonate|chalk|marl|calcareous"),
    ("Sandstone / conglomerate", r"sandstone|conglomerate|arkose|greywacke|graywacke|quartz arenite"), ("Shale / mudstone / siltstone", r"shale|mudstone|claystone|siltstone|argillite"),
    ("Evaporite", r"evaporit|halite|gypsum|anhydrite"), ("Laterite / bauxite", r"laterit|bauxit"), ("Basalt / volcanic", r"basalt|volcan|andesit|rhyol|dacit|trap\b|tuff|lava"),
    ("Granite / gneiss (crystalline)", r"granit|gneiss|migmatit|charnockit|diorite|gabbro|syenite|plutonic|intrusive"), ("Schist / quartzite / metamorphic", r"schist|phyllite|slate|quartzite|amphibolit|metamorph|marble|banded iron"),
    ("Alluvium / unconsolidated", r"alluvi|sand\b|gravel|silt\b|clay\b|colluvi|unconsolidated|sediment|quaternary"),
]
SCALE_NOTE = {"tiny": "global small-scale map (very coarse; regional context only)", "small": "continental small-scale map (coarse)", "medium": "regional-scale map", "large": "local-scale map"}


def _km(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    p = math.radians
    a = math.sin(p(lat2 - lat1) / 2) ** 2 + math.cos(p(lat1)) * math.cos(p(lat2)) * math.sin(p(lon2 - lon1) / 2) ** 2
    return 12742.0 * math.asin(math.sqrt(a))


def _lith_class(text: str) -> str:
    for name, pat in LITH_CLASSES:
        if re.search(pat, text):
            return name
    return "Other / unclassified"


def _geology_summary(unit_data: dict[str, Any], units: list[dict[str, Any]]) -> dict[str, Any] | None:
    primaries = [pts[0] for pts in unit_data["units_per_point"] if pts]
    if not primaries:
        return None
    counts: dict[str, int] = {}
    for u in primaries:
        counts[_lith_class(_text(u))] = counts.get(_lith_class(_text(u)), 0) + 1
    comp = sorted(({"lithology": k, "pct": round(100 * v / len(primaries), 1)} for k, v in counts.items()), key=lambda x: -x["pct"])
    uniq, seen = [], set()
    for u in units:
        sig = (str(u.get('name')), str(u.get('lith')))
        if sig in seen or len(uniq) >= 12:
            continue
        seen.add(sig)
        uniq.append({"name": str(u.get("name") or u.get("strat_name") or "unnamed unit")[:90], "lithology": str(u.get("lith") or "")[:90], "age": str(u.get("b_int_name") or u.get("age") or "")[:40], "map_scale": u.get("_scale")})
    sc = unit_data.get("scale")
    return {"composition": comp, "units": uniq, "points_sampled": len(primaries), "map_scale": sc, "map_scale_note": SCALE_NOTE.get(sc, ""), "source": unit_data.get("source")}


def _commodity_match(rec: dict[str, Any], words: list[str]) -> bool:
    text = " ".join(rec.get("commodities") or []).lower()
    return any(w in text for w in words)


def _occurrence_summary(occ: dict[str, Any], bbox: list[float]) -> dict[str, Any]:
    cx, cy = (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2
    recs = []
    for r in occ["records"]:
        r = dict(r)
        r["in_region"] = bbox[0] <= r["lon"] <= bbox[2] and bbox[1] <= r["lat"] <= bbox[3]
        r["distance_km"] = round(_km(cx, cy, r["lon"], r["lat"]), 1)
        recs.append(r)
    rows = []
    for name, spec in MINERALS.items():
        m = [r for r in recs if _commodity_match(r, spec["words"])]
        if not m:
            continue
        rows.append({"commodity": name, "in_region": sum(r["in_region"] for r in m), "nearby": sum(not r["in_region"] for r in m),
                     "occurrences_prospects": sum(r["kind"] in ("occurrence", "prospect") for r in m), "mine_or_deposit_records": sum(r["kind"] in ("mine_record", "major_deposit", "mapped_site") for r in m)})
    rows.sort(key=lambda x: -(x["in_region"] * 100 + x["nearby"]))
    shown = sorted([r for r in recs if any(_commodity_match(r, v["words"]) for v in MINERALS.values())], key=lambda r: (not r["in_region"], r["distance_km"]))[:60]
    return {"by_commodity": rows, "records": shown, "total_records_found": len(recs), "providers": occ["providers"], "truncated": occ.get("truncated", False),
            "caveat": "Records are historical or volunteer-mapped reports. An occurrence or past-producer record does not establish a commercially viable deposit, reserves, or current production."}


def _occurrence_evidence(commodity: str, summary_rows: list[dict[str, Any]]) -> tuple[dict | None, str | None]:
    row = next((r for r in summary_rows if r["commodity"] == commodity), None)
    if not row:
        return None, None
    if row["in_region"]:
        fav = min(1.0, 0.6 + 0.1 * row["in_region"]); text = f"{row['in_region']} recorded {commodity} occurrence/site record(s) inside the region"
    else:
        fav = 0.35 + min(0.2, 0.05 * row["nearby"]); text = f"{row['nearby']} recorded {commodity} record(s) within ~0.25 deg of the region"
    return {"criterion": "occurrence_proximity", "favourability": round(fav, 3), "source": OCC_SRC, "evidence_type": "interpreted", "description": text + "; records are unverified."}, text


def run_auto(bbox: list[float], geometry: dict | None = None, minerals: list[str] | None = None,
             units_fn: Callable[..., dict] = fetch_units, occ_fn: Callable[..., dict] = fetch_occurrences) -> dict[str, Any]:
    names = [m for m in (minerals or list(MINERALS)) if m in MINERALS]
    unit_data = units_fn(bbox, geometry)
    occ = occ_fn(bbox)
    units = _unique_units(unit_data["units_per_point"])
    cov = round(unit_data["coverage"], 3)
    geology = _geology_summary(unit_data, units)
    occurrences = _occurrence_summary(occ, bbox) if occ.get("available") else None
    limits = list(unit_data["notes"])
    if unit_data.get("scale") in ("tiny", "small"):
        limits.append(f"Geology comes from a {SCALE_NOTE[unit_data['scale']]}; it is too coarse for deposit-scale targeting.")
    limits += [f"{p['name']}: {p['detail']}" for p in occ["providers"] if not p["ok"]]
    limits += ["Lithology is sampled on a regular grid of points inside the region (each point stands for an equal share of area).",
               "No geophysical, geochemical, alteration or fault-map datasets are integrated; those criteria stay missing.",
               "Scores are relative screening favourability, not probabilities, reserves or discovery claims."]

    structure = None
    if unit_data["with_units"] >= 2 and units:
        diversity = (len(units) - 1) / max(1, unit_data["with_units"] - 1)
        structure = round(0.2 + 0.8 * min(1.0, diversity), 3)
    struct_ev = None if structure is None else {"criterion": "structural_control", "favourability": structure, "source": UNIT_SRC, "evidence_type": "modelled", "coverage": cov,
                                                 "description": f"Proxy: {len(units)} distinct mapped unit(s) over {unit_data['with_units']} sampled points (lithological contacts); no fault map used."}
    requests: list[TargetRequest] = []
    support: dict[str, list[str]] = {}
    rows = occurrences["by_commodity"] if occurrences else []
    for m in names:
        ev: list[dict] = []; sup: list[str] = []
        scored = [(_best(_text(u), MINERALS[m]["rules"]), u) for u in units if _text(u).strip()]
        scores = [BASELINE_MINERAL if sc is None else sc for sc, _ in scored]
        if scores:
            hits = sorted([(sc, u) for sc, u in scored if sc is not None], key=lambda x: -x[0])[:3]
            ev.append({"criterion": "host_lithology", "favourability": round(_aggregate(scores), 3), "source": UNIT_SRC, "evidence_type": "interpreted", "coverage": cov, "description": f"{len(scores)} mapped unit(s); rules: {HEURISTIC}"})
            sup += [f"Favourable host unit: {_label(u)} (rule score {sc:.2f})" for sc, u in hits] or ["No mapped unit matches a favourable host rock for this commodity."]
        if struct_ev:
            ev.append(struct_ev); sup.append(struct_ev["description"])
        oe, ot = _occurrence_evidence(m, rows)
        if oe:
            ev.append(oe); sup.append(ot)
        requests.append(TargetRequest(ProspectivityTarget("mineral", m), ev)); support[f"mineral:{m}"] = sup

    hc_ev: list[dict] = []; hc_sup: list[str] = []; hc: dict[str, float] = {}
    for crit, rules in HC_RULES.items():
        vals = []
        for u in units:
            t = _text(u)
            if not t.strip():
                continue
            sc = _best(t, rules)
            if sc is None and re.search(CRYSTALLINE, t) and not re.search(SEDIMENTARY, t):
                sc = 0.03
            if sc is not None:
                vals.append(sc)
        if vals:
            hc[crit] = _aggregate(vals)
    if hc:
        sed = sum(1 for u in units if re.search(SEDIMENTARY, _text(u)))
        hc_sup.append(f"{sed} of {len(units)} mapped unit(s) are sedimentary (basin-fill indicator).")
        for crit, fav in hc.items():
            hc_ev.append({"criterion": crit, "favourability": round(fav, 3), "source": UNIT_SRC, "evidence_type": "interpreted", "coverage": cov, "description": f"Lithology-derived {crit.replace('_', ' ')}; rules: {HEURISTIC}"})
        if {"reservoir", "seal"} <= set(hc) and structure is not None:
            hc_ev.append({"criterion": "trap", "favourability": round(0.5 * structure + 0.5 * min(hc["reservoir"], hc["seal"]), 3), "source": UNIT_SRC, "evidence_type": "modelled", "coverage": cov,
                          "description": "Proxy from contact diversity and reservoir/seal co-occurrence; no seismic or structure map used."})
            hc_sup.append("Trap potential is a coarse proxy (no seismic/structural data).")
        hc_sup += [f"{c.replace('_', ' ').capitalize()} favourability {v:.2f}" for c, v in hc.items()]
    requests += [TargetRequest(ProspectivityTarget("petroleum"), hc_ev), TargetRequest(ProspectivityTarget("gas"), list(hc_ev))]
    support["petroleum"] = support["gas"] = hc_sup

    report = analyze_prospectivity(requests).to_dict()
    scored_results = []
    for r in report["results"]:
        if r["status"] != "scored" or r["potential_score"] is None:
            continue  # no evidence-backed score -> not shown anywhere
        key = f"mineral:{r['commodity']}" if r["kind"] == "mineral" else r["kind"]
        r["classification"] = _classify(r["potential_score"])
        r["supporting_evidence"] = support.get(key, [])
        r["limitations"] = limits + ([] if r["kind"] == "mineral" else ["Thermal maturity, migration and charge timing need well or basin data that is not integrated."])
        scored_results.append(r)
    return {"success": True, "bbox": bbox, "geology": geology, "occurrences": occurrences, "results": scored_results,
            "sampling": {"points": unit_data["points"], "points_with_units": unit_data["with_units"], "distinct_units": len(units), "coverage": cov, "map_scale": unit_data.get("scale")},
            "sources": [{"name": unit_data.get("source") or UNIT_SRC, "available": unit_data["with_units"] > 0}] + [{"name": p["name"], "available": p["ok"], "detail": p.get("detail")} for p in occ["providers"]],
            "limitations": list(dict.fromkeys(limits)), "disclaimer": report["disclaimer"], "discovery_claim": False}
