"""PDF report of a completed regional analysis (reportlab). Only modules that returned data are included."""
from __future__ import annotations

import base64
import io
import re
from datetime import datetime, timezone
from typing import Any
from xml.sax.saxutils import escape

from fastapi import APIRouter
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.shapes import Drawing, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

router = APIRouter(prefix="/report", tags=["report"])
M = ["J", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"]


class ReportRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    region: dict[str, Any] = {}
    modules: dict[str, Any] = {}
    overlays: list[dict[str, Any]] = []
    prospectivity: dict[str, Any] | None = None


def _f(v: Any, nd: int = 1) -> str:
    return "n/a" if v is None else f"{v:,.{nd}f}" if isinstance(v, (int, float)) else str(v)


def _chart(title: str, values: list, color: Any) -> Drawing:
    d = Drawing(240, 110)
    ch = VerticalBarChart(); ch.x, ch.y, ch.width, ch.height = 28, 18, 200, 70
    ch.data = [[v or 0 for v in values]]; ch.categoryAxis.categoryNames = M
    ch.bars[0].fillColor = color; ch.valueAxis.labels.fontSize = 6; ch.categoryAxis.labels.fontSize = 6
    d.add(ch); d.add(String(28, 98, title, fontSize=8))
    return d


def build_pdf(d: ReportRequest) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=14 * mm, bottomMargin=14 * mm, title="GeoIntelligence Regional Report")
    st = getSampleStyleSheet()
    P = lambda t, s="BodyText": Paragraph(escape(str(t)), st[s])  # noqa: E731

    def table(rows: list[list[Any]], widths: list[float]) -> Table:
        t = Table([[Paragraph(escape(str(c)), st["BodyText"]) for c in r] for r in rows], colWidths=widths, repeatRows=1)
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dfe8ee")), ("GRID", (0, 0), (-1, -1), 0.3, colors.grey), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
        return t

    r, mods = d.region, d.modules
    out: list[Any] = [P("GeoIntelligence Regional Report", "Title"), P(f"Generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC. Screening-level information from public datasets; not a survey or resource estimate.", "Italic"),
                      P("1. Region", "Heading2"),
                      table([["Name", r.get("name", "n/a")], ["Bounding box (W, S, E, N)", ", ".join(_f(x, 4) for x in r.get("bbox", [])) or "n/a"], ["Boundary", r.get("boundarySource", "bounding box")]], [48 * mm, 126 * mm])]
    W = [46 * mm, 50 * mm, 78 * mm]
    c = mods.get("climate")
    if c:
        rows = [["Indicator", "Value", "Source / note"], ["Annual mean temperature", f"{_f(c.get('mean_temperature_c'))} C", c.get("period", "")], ["Annual rainfall", f"{_f(c.get('annual_rainfall_mm'), 0)} mm", c.get("source", "")],
                ["Mean humidity", f"{_f(c.get('mean_humidity_pct'))} %", ""], ["Aridity", f"{_f(c.get('aridity_index'), 2)} ({c.get('aridity_class', 'n/a')})", "rainfall / reference evapotranspiration"]]
        if c.get("wind"):
            rows.append(["Wind", f"{_f(c['wind']['mean_daily_max_kmh'])} km/h, from {c['wind']['prevailing_direction']}", "mean daily maximum, prevailing direction"])
        for k, lab in (("temperature_c", "Temperature trend"), ("rainfall_mm", "Rainfall trend")):
            tr = (c.get("trends") or {}).get(k)
            if tr:
                rows.append([lab, f"{tr['per_decade']:+} per decade", "statistically significant (p<0.1)" if tr["significant"] else "not statistically significant"])
        s = c.get("seasons") or {}
        rows.append(["Seasons", f"Hottest {s.get('hottest_month')}, wettest {s.get('wettest_month')}", f"Wettest quarter {s.get('wettest_quarter')} ({_f(s.get('wettest_quarter_share_pct'), 0)}% of rain)"])
        out += [P("2. Climate", "Heading2"), table(rows, W)]
        mo = c.get("monthly") or {}
        out += [Table([[ _chart("Monthly temperature (C)", mo.get("temperature_c", [0] * 12), colors.HexColor("#e07a3f")), _chart("Monthly rainfall (mm)", mo.get("rainfall_mm", [0] * 12), colors.HexColor("#3f8fe0"))]])]
    t = mods.get("terrain")
    if t:
        e = t["elevation_m"]
        out += [P("3. Terrain", "Heading2"), table([["Indicator", "Value", "Source / note"], ["Elevation min / mean / max", f"{_f(e['min'], 0)} / {_f(e['mean'], 0)} / {_f(e['max'], 0)} m", t.get("source", "")],
                                                     ["Relief / class", f"{_f(t['relief_m'], 0)} m / {t['terrain_class']}", ""], ["Slope", f"mean {t['mean_slope_deg']} deg, 99th pct {t['max_slope_deg']} deg ({t['slope_class']})", t.get("grid", "")],
                                                     ["Aspect share (%)", ", ".join(f"{k} {v:.0f}" for k, v in (t.get("aspect_share_pct") or {}).items()), ""]], W)]
    v = mods.get("vegetation")
    if v:
        sc, nd, lc, rg = v["scene"], v["ndvi"], v.get("land_cover"), v["region"]
        rows = [["Indicator", "Value", "Source / note"], ["Region area", f"{_f(rg['area_km2'], 2)} km2", f"analysis grid {rg['grid']}"],
                ["Sentinel-2 acquisition", f"{sc['date']} (cloud {_f(sc.get('cloud_cover_pct'), 0)}%)", f"{', '.join(sc['ids'])}; native {sc['native_resolution_m']} m, analysed at ~{_f(sc['analysis_cell_m'], 0)} m cells"],
                ["Valid cloud-free data", f"{_f(nd['valid_cloud_free_pct_of_region'], 0)}% of region", f"{_f(nd['cloud_or_invalid_pct_of_region'], 0)}% cloud/shadow/no-data excluded (not counted as non-vegetated)"],
                ["NDVI mean / median / p10-p90", f"{_f(nd['mean_ndvi'], 3)} / {_f(nd['median_ndvi'], 3)} / {nd['p10_p90'][0]} to {nd['p10_p90'][1]}", nd["denominator_note"]]]
        gr = nd["greenness"]
        rows.append(["Greenness (cloud-free land)", "; ".join(f"{k.replace('_', ' ')} {x['pct']}% ({x['area_km2']} km2)" for k, x in gr.items()), "NDVI indicator only; not a forest classification"])
        if lc:
            for key, lab in (("forest", "Forest cover"), ("other_vegetation", "Other vegetation"), ("non_vegetated", "Non-vegetated")):
                rows.append([lab, f"{lc[key]['pct']}% ({_f(lc[key]['area_km2'], 2)} km2)", lc[key]["definition"]])
            rows.append(["Valid classified area", f"{_f(lc['classified_area_km2'], 2)} km2 ({_f(lc['valid_classified_pct_of_region'], 0)}% of region)", lc["source"] + "; shares are of this area"])
            rows.append(["Land-cover classes", "; ".join(f"{c['name']} {c['pct']}%" for c in lc["classes"][:7]), ""])
        else:
            rows.append(["Forest cover", "not reported", v.get("forest_note", "")])
        if v.get("change"):
            ch = v["change"]
            rows.append(["Change vs one year earlier", f"mean NDVI {ch['mean_ndvi_change']:+}; {ch['declined_pct']}% of pixels declined >0.2", f"{ch.get('previous_scene_date')}. {ch.get('note', '')}"])
        out += [P("4. Vegetation and forest cover", "Heading2"), table(rows, W)]
    w = mods.get("water")
    if w:
        rows = [["Indicator", "Value", "Source / note"]]
        if w.get("mapped_features"):
            f = w["mapped_features"]; rows.append(["Mapped rivers / streams / lakes / reservoirs", f"{f['river_segments']} / {f['streams_and_canals']} / {f['lakes_and_water_bodies']} / {f['reservoirs']}", f["source"]])
        if w.get("surface_water"):
            sw = w["surface_water"]; rows.append(["Surface water (Sentinel-2)", f"{sw['water_fraction_pct']} % of valid pixels", f"scene {sw.get('scene_date')}" + (f"; {sw['change_vs_last_year_pp']:+} pp vs {sw.get('previous_scene_date')}" if sw.get("change_vs_last_year_pp") is not None else "")])
        if w.get("stress"):
            ws = w["stress"]; rows.append(["Climatic water stress", f"{ws['level']} (balance {_f(ws.get('climatic_water_balance_mm'), 0)} mm/yr)", ws["method"]])
        out += [P("5. Water", "Heading2"), table(rows, W)]
    s = mods.get("soil")
    if s:
        p = s["properties"]
        rows = [["Indicator", "Value", "Source / note"], ["Texture (clay/sand/silt %)", f"{_f(p['clay_pct'], 0)} / {_f(p['sand_pct'], 0)} / {_f(p['silt_pct'], 0)} ({s.get('texture_class', 'n/a')})", s["depth"]], ["pH / organic C / N / CEC", f"{_f(p['ph'])} / {_f(p['organic_carbon_g_per_kg'])} g/kg / {_f(p['nitrogen_g_per_kg'], 2)} g/kg / {_f(p['cec_cmol_per_kg'])} cmol/kg", s["source"]]]
        if s.get("classification"):
            rows.append(["WRB soil class", s["classification"]["wrb_class"], ""])
        if (s.get("fertility") or {}).get("status") == "scored":
            rows.append(["Fertility index", f"{s['fertility']['score']:.0f}/100 ({s['fertility']['class']})", s["fertility"]["method"]])
        out += [P("6. Soil", "Heading2"), table(rows, W)]
    su = mods.get("suitability") or {}
    hab, ag = su.get("habitability"), su.get("agriculture")
    if hab and hab.get("status") == "scored":
        out += [P("7. Habitability and regional suitability", "Heading2"), P(f"Score {hab['score']:.0f}/100 ({hab['class']}). {hab['method']}"),
                table([["Component", "Score", "Weight %", "Basis"]] + [[x["name"], _f(x["score"], 0), _f(x["weight_pct"], 0), x["basis"]] for x in hab["components"]], [40 * mm, 20 * mm, 22 * mm, 92 * mm])]
    if ag and ag.get("crops"):
        out += [P("Agricultural and crop suitability", "Heading3"), P(f"Overall {ag['score']:.0f}/100 ({ag['class']}). {ag['method']}"),
                table([["Crop", "Score", "Class", "Limiting factor"]] + [[x["crop"], _f(x["score"], 0), x["class"], x["limiting_factor"]] for x in ag["crops"]], [50 * mm, 25 * mm, 30 * mm, 69 * mm])]
    for ov in d.overlays[:3]:
        m = re.match(r"data:image/png;base64,(.+)", ov.get("image", ""))
        if m:
            img = Image(io.BytesIO(base64.b64decode(m.group(1))), width=80 * mm, height=80 * mm, kind="proportional")
            out.append(KeepTogether([P(f"Map: {ov.get('label')} ({ov.get('note', '')})", "Heading4"), img]))
    pr = d.prospectivity or {}
    g, oc, res = pr.get("geology"), pr.get("occurrences"), pr.get("results") or []
    if g or oc or res:
        out.append(P("8. Geology and mineral records", "Heading2"))
    if g:
        out += [P(f"Geological evidence ({g.get('map_scale_note', '')})", "Heading4"), table([["Lithology class", "Share of sampled area"]] + [[c["lithology"], f"{c['pct']}%"] for c in g["composition"]], [110 * mm, 60 * mm]),
                P("Mapped units: " + "; ".join(f"{u['name']} ({u['lithology']})" if u["lithology"] else u["name"] for u in g["units"][:8]))]
    if oc:
        out.append(P("Recorded occurrences (historical records; not verified deposits, reserves or production)", "Heading4"))
        if oc["by_commodity"]:
            out.append(table([["Commodity", "Inside region", "Within ~25 km buffer", "Occurrences / prospects", "Mine / deposit records"]] + [[r["commodity"], r["in_region"], r["nearby"], r["occurrences_prospects"], r["mine_or_deposit_records"]] for r in oc["by_commodity"]], [38 * mm, 28 * mm, 36 * mm, 36 * mm, 36 * mm]))
            kinds = {"occurrence": "Occurrence", "prospect": "Prospect", "mine_record": "Mine record (historic)", "mapped_site": "Mapped mining site", "major_deposit": "Listed major deposit"}
            out.append(table([["Record", "Commodity", "Type", "Location"]] + [[r["name"], ", ".join(r["commodities"]), kinds.get(r["kind"], r["kind"]) + (f" ({r['status']})" if r.get("status") and r["kind"] in ("occurrence", "prospect", "mine_record") else ""), "inside region" if r["in_region"] else f"{r['distance_km']:.0f} km from centre"] for r in oc["records"][:15]], [50 * mm, 42 * mm, 44 * mm, 38 * mm]))
        else:
            out.append(P("No records for the supported commodities were found in or near this region in the queried sources. This does not prove absence."))
        out.append(P(oc["caveat"], "Italic"))
    if res:
        out.append(P("Prospectivity assessment (only where evidence was sufficient)", "Heading4"))
        for x in res:
            out.append(P(f"{x['commodity']}: {x.get('classification')} (score {_f(x.get('potential_score'), 0)}); confidence {(x.get('confidence') or {}).get('label', 'n/a')}; evidence coverage {_f(100 * (x.get('weight_coverage') or 0), 0)}%", "Heading4"))
            for line in (x.get("supporting_evidence") or [])[:4]:
                out.append(P("- " + line))
        out.append(P(pr.get("disclaimer", ""), "Italic"))
    if g or oc or res:
        out += [P("Geology limitations", "Heading3")] + [P("- " + l) for l in pr.get("limitations", [])]
    srcs = [(mods.get(k) or {}).get("source") for k in ("climate", "terrain", "soil", "vegetation")] + [x["name"] for x in (pr.get("sources") or []) if x.get("available")]
    out += [P("Data sources", "Heading3")] + [P("- " + x) for x in dict.fromkeys(x for x in srcs if x)]
    doc.build(out)
    return buf.getvalue()


@router.post("/pdf")
async def pdf(payload: ReportRequest) -> Response:
    return Response(build_pdf(payload), media_type="application/pdf", headers={"Content-Disposition": 'attachment; filename="geointelligence-report.pdf"'})
