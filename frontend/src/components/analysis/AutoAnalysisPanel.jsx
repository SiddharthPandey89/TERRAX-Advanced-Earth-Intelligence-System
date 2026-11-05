import { useCallback, useEffect, useRef, useState } from 'react';
import { downloadReportPdf, requestModule, requestProspectivity } from '../../services/analysisService.js';
import { AspectRose, ClimateChart, HBars, Ring, Sparkline, StackBar } from '../charts/MiniCharts.jsx';

const BASE = ['climate', 'terrain', 'soil', 'vegetation', 'water'];
const LABELS = { climate: 'Climate', terrain: 'Terrain', soil: 'Soil', vegetation: 'Vegetation & forest cover', water: 'Water', suitability: 'Suitability', resources: 'Geology & mineral records' };
const n = (v, d = 1) => (typeof v === 'number' && Number.isFinite(v) ? v.toLocaleString(undefined, { maximumFractionDigits: d }) : '—');
const sign = (v) => (v > 0 ? `+${v}` : `${v}`);

function Card({ title, icon, source, children, wide }) {
  return (
    <article className={`gi-card${wide ? ' gi-card--wide' : ''}`}>
      <header><span className="gi-card__icon" aria-hidden="true">{icon}</span><h3>{title}</h3></header>
      {children}
      {source && <footer>{source}</footer>}
    </article>
  );
}
const Skeleton = ({ title }) => <article className="gi-card gi-card--loading" aria-busy="true"><header><h3>{title}</h3></header><i /><i /><i /></article>;
const Kpi = ({ label, value, unit, hint }) => <div className="gi-kpi"><span>{label}</span><strong>{value}<small>{unit}</small></strong>{hint && <em>{hint}</em>}</div>;
const Chip = ({ children, tone = 'neutral' }) => <span className={`gi-chip gi-chip--${tone}`}>{children}</span>;
const toneFor = (c) => (c === 'high' || c === 'High' ? 'good' : c === 'moderate' || c === 'Moderate' ? 'mid' : 'neutral');

function ClimateCard({ d }) {
  const t = d.trends?.temperature_c; const r = d.trends?.rainfall_mm;
  return (
    <Card title="Climate" icon="◐" source={`${d.source}. ${d.period}.`} wide>
      <div className="gi-kpis">
        <Kpi label="Mean temperature" value={n(d.mean_temperature_c)} unit=" °C" />
        <Kpi label="Annual rainfall" value={n(d.annual_rainfall_mm, 0)} unit=" mm" />
        <Kpi label="Humidity" value={n(d.mean_humidity_pct, 0)} unit=" %" />
        {d.wind && <Kpi label="Wind" value={n(d.wind.mean_daily_max_kmh, 0)} unit=" km/h" hint={`mostly from ${d.wind.prevailing_direction}`} />}
        {d.aridity_class && <Kpi label="Aridity" value={n(d.aridity_index, 2)} unit="" hint={d.aridity_class} />}
      </div>
      <div className="gi-split">
        <div><h4>Seasonal pattern <small>bars: rain · line: temperature</small></h4><ClimateChart monthly={d.monthly} />
          <p className="gi-note">Hottest {d.seasons.hottest_month}, coolest {d.seasons.coolest_month}; wettest quarter {d.seasons.wettest_quarter}{d.seasons.wettest_quarter_share_pct ? ` (${d.seasons.wettest_quarter_share_pct}% of rain)` : ''}.</p></div>
        <div><h4>Annual mean temperature</h4><Sparkline points={d.yearly.map((y) => ({ year: y.year, value: y.mean_temperature_c }))} unit=" °C" />
          <div className="gi-trends">
            {t && <Chip tone={t.significant ? 'mid' : 'neutral'}>Temp {sign(t.per_decade)} °C/decade{t.significant ? '' : ' · not significant'}</Chip>}
            {r && <Chip tone={r.significant ? 'mid' : 'neutral'}>Rain {sign(r.per_decade)} mm/decade{r.significant ? '' : ' · not significant'}</Chip>}
          </div>
          <p className="gi-note">Trends are linear fits over {d.years_used} complete years; short records are weak evidence of climate change.</p></div>
      </div>
    </Card>
  );
}

function TerrainCard({ d }) {
  return (
    <Card title="Terrain" icon="△" source={`${d.source}. ${d.grid}.`}>
      <div className="gi-kpis">
        <Kpi label="Elevation" value={`${n(d.elevation_m.min, 0)}–${n(d.elevation_m.max, 0)}`} unit=" m" hint={`mean ${n(d.elevation_m.mean, 0)} m`} />
        <Kpi label="Relief" value={n(d.relief_m, 0)} unit=" m" hint={d.terrain_class} />
        <Kpi label="Mean slope" value={n(d.mean_slope_deg)} unit="°" hint={d.slope_class} />
      </div>
      <div className="gi-split gi-split--tight">
        <HBars items={Object.entries(d.slope_distribution_pct).map(([label, value]) => ({ label, value }))} max={100} unit="%" />
        <AspectRose shares={d.aspect_share_pct} />
      </div>
    </Card>
  );
}

function VegetationCard({ d }) {
  const lc = d.land_cover; const nd = d.ndvi; const ch = d.change;
  const group = (g, label, color) => ({ label: `${label} · ${n(g.area_km2, 2)} km²`, value: g.pct, color });
  return (
    <Card title="Vegetation & forest cover" icon="❋" source={`${d.source}. Sentinel-2 ${d.scene.date} (${d.scene.ids.length > 1 ? `${d.scene.ids.length} tiles` : d.scene.ids[0]}), cloud ${n(d.scene.cloud_cover_pct, 0)}%; native 10 m, analysed at ~${n(d.scene.analysis_cell_m, 0)} m cells.`} wide>
      <div className="gi-kpis">
        <Kpi label="Selected region" value={n(d.region.area_km2, 1)} unit=" km²" hint={d.region.grid} />
        {lc ? <Kpi label="Forest cover" value={n(lc.forest.pct, 1)} unit=" %" hint={`${n(lc.forest.area_km2, 2)} km² (tree cover)`} /> : <Kpi label="Forest cover" value="not reported" unit="" hint="no valid classification" />}
        {lc && <Kpi label="Other vegetation" value={n(lc.other_vegetation.pct, 1)} unit=" %" hint={`${n(lc.other_vegetation.area_km2, 2)} km²`} />}
        {lc && <Kpi label="Non-vegetated" value={n(lc.non_vegetated.pct, 1)} unit=" %" hint={`${n(lc.non_vegetated.area_km2, 2)} km²`} />}
        <Kpi label="Mean NDVI" value={n(nd.mean_ndvi, 2)} unit="" hint={`p10–p90 ${nd.p10_p90[0]} to ${nd.p10_p90[1]}`} />
        <Kpi label="Valid satellite data" value={n(nd.valid_cloud_free_pct_of_region, 0)} unit=" %" hint={`${n(nd.cloud_or_invalid_pct_of_region, 0)}% cloud / no-data excluded`} />
      </div>
      {lc ? (
        <div className="gi-split">
          <div><h4>Land cover (ESA WorldCover {lc.year})</h4>
            <StackBar parts={[group(lc.forest, 'Forest', '#0b6e2d'), group(lc.other_vegetation, 'Other vegetation', '#a8cf54'), group(lc.non_vegetated, 'Non-vegetated', '#cdb282')]} />
            <p className="gi-note">Shares are of the {n(lc.classified_area_km2, 1)} km² validly classified ({n(lc.valid_classified_pct_of_region, 0)}% of the region). Forest = tree cover + mangroves.</p></div>
          <div><h4>Classes</h4><HBars items={lc.classes.slice(0, 6).map((c) => ({ label: c.name, value: c.pct }))} max={100} unit="%" /></div>
        </div>
      ) : <p className="gi-note">{d.forest_note}</p>}
      <div className="gi-split">
        <div><h4>Current greenness (NDVI, cloud-free land)</h4>
          <StackBar parts={[{ label: `Green vegetation ≥0.30 · ${n(nd.greenness.green_vegetation.area_km2, 2)} km²`, value: nd.greenness.green_vegetation.pct, color: '#3fa34d' }, { label: `Sparse 0.15–0.30 · ${n(nd.greenness.sparse_vegetation.area_km2, 2)} km²`, value: nd.greenness.sparse_vegetation.pct, color: '#d6cd6e' }, { label: `Bare / built <0.15 · ${n(nd.greenness.bare_or_built.area_km2, 2)} km²`, value: nd.greenness.bare_or_built.pct, color: '#a98d62' }]} />
          <p className="gi-note">NDVI shows greenness only; it does not distinguish forest from crops or grass. Surface water: {n(nd.surface_water.area_km2, 2)} km² ({nd.surface_water.pct_of_valid}% of valid pixels).</p></div>
        {ch && (
          <div className="gi-callout"><strong>Change vs {ch.previous_scene_date}</strong>
            <span>Mean NDVI {sign(ch.mean_ndvi_change)}; {ch.declined_pct}% of pixels declined, {ch.improved_pct}% improved{ch.tree_pixels_with_decline_pct != null ? `; ${ch.tree_pixels_with_decline_pct}% of tree-cover pixels declined` : ''}.</span><small>{ch.note}</small></div>
        )}
      </div>
      <p className="gi-note">Map: choose “Forest & vegetation map” in the map’s Layers panel.</p>
    </Card>
  );
}

function WaterCard({ d }) {
  const f = d.mapped_features; const sw = d.surface_water; const st = d.stress;
  return (
    <Card title="Water" icon="≈" source={[f?.source, sw && `Sentinel-2 scene ${sw.scene_date}`].filter(Boolean).join(' · ')}>
      {st && <div className="gi-stress"><Chip tone={st.level === 'low' ? 'good' : st.level === 'moderate' ? 'mid' : 'warn'}>Water stress: {st.level}</Chip><span>{st.aridity_class}, aridity {st.aridity_index}; balance {n(st.climatic_water_balance_mm, 0)} mm/yr</span></div>}
      <div className="gi-kpis">
        {f && <Kpi label="Rivers" value={f.river_segments} unit=" segments" hint={`${f.streams_and_canals} streams/canals`} />}
        {f && <Kpi label="Lakes & reservoirs" value={f.lakes_and_water_bodies + f.reservoirs} unit="" hint="mapped features" />}
        {sw && <Kpi label="Surface water" value={n(sw.water_fraction_pct, 1)} unit=" %" hint={sw.change_vs_last_year_pp != null ? `${sign(sw.change_vs_last_year_pp)} pp vs last year` : 'Sentinel-2'} />}
      </div>
      {st && <details className="gi-details"><summary>How water stress is derived</summary><p>{st.method}</p></details>}
    </Card>
  );
}

function SoilCard({ d }) {
  const p = d.properties; const f = d.fertility;
  return (
    <Card title="Soil" icon="◍" source={`${d.source}. Depth ${d.depth}.`}>
      <div className="gi-kpis">
        {d.texture_class && <Kpi label="Texture" value={d.texture_class} unit="" />}
        {d.classification && <Kpi label="WRB class" value={d.classification.wrb_class} unit="" hint="most probable" />}
        <Kpi label="pH" value={n(p.ph)} unit="" />
        <Kpi label="Organic carbon" value={n(p.organic_carbon_g_per_kg)} unit=" g/kg" />
      </div>
      {p.clay_pct != null && <StackBar parts={[{ label: 'Clay', value: Math.round(p.clay_pct), color: '#b07a5b' }, { label: 'Silt', value: Math.round(p.silt_pct), color: '#c9b79c' }, { label: 'Sand', value: Math.round(p.sand_pct), color: '#e8d9a8' }]} />}
      {f?.status === 'scored' && <details className="gi-details"><summary>Fertility index {f.score}/100 · {f.class}</summary><p>{f.method}</p></details>}
    </Card>
  );
}

function AgricultureCard({ d }) {
  return (
    <Card title="Agricultural & crop suitability" icon="✿" source="Climate normals (ERA5) + SoilGrids pH">
      <div className="gi-split gi-split--ring"><Ring value={d.score} label={`${d.class} suitability`} tone="#4fd1a5" />
        <HBars items={d.crops.slice(0, 5).map((c) => ({ label: `${c.crop} · limited by ${c.limiting_factor}`, value: c.score }))} max={100} /></div>
      <details className="gi-details"><summary>How it is calculated</summary><p>{d.method}</p></details>
    </Card>
  );
}

const KIND = { occurrence: 'Occurrence', prospect: 'Prospect', mine_record: 'Mine record (historic)', mapped_site: 'Mapped mining site', major_deposit: 'Listed major deposit' };

function ProspectRow({ item }) {
  const [open, setOpen] = useState(false);
  const label = item.kind === 'mineral' ? item.commodity : item.kind === 'petroleum' ? 'Petroleum' : 'Natural gas';
  return (
    <li className="gi-res">
      <button type="button" onClick={() => setOpen(!open)} aria-expanded={open}>
        <strong>{label}</strong><div className="gi-res__bar"><em style={{ width: `${item.potential_score}%` }} /></div><span>{n(item.potential_score, 0)}</span><Chip tone={toneFor(item.classification)}>{item.classification}</Chip>
      </button>
      {open && <div className="gi-res__detail"><p>Confidence: <b>{item.confidence?.label || '—'}</b> · evidence coverage {n(100 * (item.weight_coverage || 0), 0)}%</p>{(item.supporting_evidence || []).map((e) => <p key={e}>• {e}</p>)}</div>}
    </li>
  );
}

function GeologyCard({ data }) {
  const g = data.geology; const o = data.occurrences; const res = data.results || [];
  const minerals = res.filter((r) => r.kind === 'mineral'); const hc = res.filter((r) => r.kind !== 'mineral');
  const mines = (o?.records || []).filter((r) => ['mine_record', 'major_deposit', 'mapped_site'].includes(r.kind));
  const occs = (o?.records || []).filter((r) => ['occurrence', 'prospect'].includes(r.kind));
  const list = (rows) => rows.slice(0, 8).map((r, i) => <li key={`${i}-${r.id}-${r.lon}`}><b>{r.name}</b> — {(r.commodities || []).join(', ')} · {KIND[r.kind]}{r.status && !['mapped site', 'listed major deposit'].includes(r.status) ? ` (${r.status})` : ''} · {r.in_region ? 'inside region' : `${n(r.distance_km, 0)} km from centre`} <small>{r.source}</small></li>);
  return (
    <Card title="Geology & mineral records" icon="◆" source={(data.sources || []).map((s) => `${s.name}${s.available ? '' : ' (no data returned)'}`).join(' · ')} wide>
      {g && (
        <section><h4>Geological evidence <small>{g.map_scale_note}</small></h4>
          <StackBar parts={g.composition.map((c) => ({ label: c.lithology, value: c.pct }))} />
          <details className="gi-details"><summary>Mapped units ({g.units.length})</summary><ul>{g.units.map((u, i) => <li key={`${i}-${u.name}`}>{u.name}{u.lithology ? ` — ${u.lithology}` : ''}{u.age ? ` · ${u.age}` : ''}</li>)}</ul></details>
        </section>
      )}
      {o && (
        <section><h4>Recorded occurrences <small>historical records, not verified deposits</small></h4>
          {o.by_commodity.length > 0 ? (
            <table className="gi-table"><thead><tr><th>Commodity</th><th>Inside region</th><th>Within 25 km buffer</th><th>Occurrences / prospects</th><th>Mine / deposit records</th></tr></thead>
              <tbody>{o.by_commodity.map((r) => <tr key={r.commodity}><td>{r.commodity}</td><td>{r.in_region}</td><td>{r.nearby}</td><td>{r.occurrences_prospects}</td><td>{r.mine_or_deposit_records}</td></tr>)}</tbody></table>
          ) : <p className="gi-note">No records for iron ore, copper, gold, bauxite, coal, limestone or manganese were found in or near this region in the queried sources ({o.providers.filter((p) => p.ok).map((p) => p.name).join(', ') || 'none responded'}). This does not prove absence.</p>}
          {occs.length > 0 && <details className="gi-details"><summary>Occurrence & prospect records ({occs.length})</summary><ul>{list(occs)}</ul></details>}
          {mines.length > 0 && <details className="gi-details"><summary>Mine / deposit records ({mines.length})</summary><ul>{list(mines)}</ul></details>}
          <p className="gi-note">{o.caveat}{o.truncated ? ' Results were truncated by the provider; counts are minimums.' : ''}</p>
        </section>
      )}
      {res.length > 0 && (
        <section><h4>Prospectivity assessment <small>only where evidence was sufficient</small></h4>
          <div className="gi-split">{minerals.length > 0 && <div><ul className="gi-reslist">{minerals.map((i) => <ProspectRow item={i} key={i.model} />)}</ul></div>}{hc.length > 0 && <div><ul className="gi-reslist">{hc.map((i) => <ProspectRow item={i} key={i.model} />)}</ul></div>}</div>
          <p className="gi-note">A screening estimate from coarse mapped geology and records. It is not a deposit, reserve or commercial-availability claim.</p>
        </section>
      )}
      <details className="gi-details"><summary>Data limitations</summary><ul>{(data.limitations || []).map((l) => <li key={l}>{l}</li>)}</ul></details>
    </Card>
  );
}

export default function AutoAnalysisPanel({ region, regionError, analyzeSignal = 0, onOverlays = () => {} }) {
  const [mods, setMods] = useState({});
  const [resources, setResources] = useState(null);
  const [pdfBusy, setPdfBusy] = useState(false);
  const [pdfError, setPdfError] = useState('');
  const run = useRef(0);
  const started = Object.keys(mods).length > 0;

  const load = useCallback(async (name, id, bbox, geometry = null) => {
    setMods((m) => ({ ...m, [name]: { status: 'loading' } }));
    let result;
    try { result = await requestModule(bbox, name, geometry); } catch (e) { result = { status: 'na', reason: e.message }; }
    if (id === run.current) setMods((m) => ({ ...m, [name]: result }));
    return result;
  }, []);

  const analyze = useCallback(async () => {
    if (!region || region.tooLarge) return;
    const id = ++run.current; const { bbox } = region;
    setMods({}); setResources({ status: 'loading' }); setPdfError('');
    requestProspectivity(region).then((r) => { if (id === run.current) setResources({ status: 'ok', data: r }); })
      .catch((e) => { if (id === run.current) setResources({ status: 'na', reason: e.message }); });
    await Promise.allSettled(BASE.map((m) => load(m, id, bbox, region.geometry)));
    if (id === run.current) load('suitability', id, bbox, region.geometry);
  }, [region, load]);

  useEffect(() => { if (analyzeSignal > 0) analyze(); }, [analyzeSignal]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { setMods({}); setResources(null); run.current += 1; }, [region]);
  useEffect(() => { onOverlays(Object.values(mods).flatMap((m) => m.overlays || [])); }, [mods]); // eslint-disable-line react-hooks/exhaustive-deps

  const ok = (k) => mods[k]?.status === 'ok';
  const d = (k) => mods[k]?.data;
  const loading = Object.values(mods).some((m) => m.status === 'loading') || resources?.status === 'loading';
  const failed = [...BASE.filter((k) => mods[k]?.status === 'na').map((k) => [k, mods[k].reason])];
  if (resources?.status === 'na') failed.push(['resources', resources.reason]);
  const suit = d('suitability'); const hab = suit?.habitability; const ag = suit?.agriculture;

  const pdf = async () => {
    setPdfBusy(true); setPdfError('');
    try {
      const modules = Object.fromEntries(Object.entries(mods).filter(([, v]) => v.status === 'ok').map(([k, v]) => [k, v.data]));
      await downloadReportPdf({ region: { name: region.name, bbox: region.bbox, boundarySource: region.boundarySource }, modules, overlays: Object.values(mods).flatMap((m) => m.overlays || []).filter((o) => o.id === 'vegmap'), prospectivity: resources?.data });
    } catch (e) { setPdfError(e.message); } finally { setPdfBusy(false); }
  };

  return (
    <section className="gi-analysis" id="region-analysis" aria-labelledby="gi-title">
      <div className="gi-head">
        <div><p className="eyebrow">REGION INTELLIGENCE</p><h2 id="gi-title">{region ? region.name : 'Select a region'}</h2>
          {region ? <p className="gi-sub">W {n(region.bbox[0], 3)} · S {n(region.bbox[1], 3)} · E {n(region.bbox[2], 3)} · N {n(region.bbox[3], 3)} — {region.boundarySource}</p>
            : <p className="gi-sub">Search a place, click the map, or draw an area, then analyze.</p>}
        </div>
        <div className="gi-actions">
          <button type="button" className="gi-btn gi-btn--primary" onClick={analyze} disabled={!region || region.tooLarge || loading}>{loading ? 'Analyzing…' : started ? 'Re-run analysis' : 'Analyze region'}</button>
          {started && !loading && <button type="button" className="gi-btn" onClick={pdf} disabled={pdfBusy}>{pdfBusy ? 'Preparing PDF…' : 'Download PDF report'}</button>}
        </div>
      </div>
      {regionError && <p className="gi-hint" role="status">{regionError}</p>}
      {pdfError && <p className="gi-hint" role="status">{pdfError}</p>}
      {loading && <div className="gi-progress" role="progressbar" aria-label="Analysis in progress"><i /></div>}

      {(hab?.status === 'scored' || ag?.score != null) && (
        <div className="gi-summary">
          {hab?.status === 'scored' && <div className="gi-summary__item"><Ring value={hab.score} label={`Habitability · ${hab.class}`} />
            <div><h3>Regional suitability</h3><ul className="gi-comp">{hab.components.map((c) => <li key={c.name}><span>{c.name}</span><div><em style={{ width: `${c.score}%` }} /></div><b>{n(c.score, 0)}</b><small>{c.basis}</small></li>)}</ul>
              <details className="gi-details"><summary>How this score is calculated</summary><p>{hab.method}</p></details></div></div>}
        </div>
      )}

      <div className="gi-grid">
        {mods.climate?.status === 'loading' && <Skeleton title="Climate" />}{ok('climate') && <ClimateCard d={d('climate')} />}
        {mods.vegetation?.status === 'loading' && <Skeleton title="Vegetation & forest cover" />}{ok('vegetation') && <VegetationCard d={d('vegetation')} />}
        {mods.water?.status === 'loading' && <Skeleton title="Water" />}{ok('water') && <WaterCard d={d('water')} />}
        {mods.terrain?.status === 'loading' && <Skeleton title="Terrain" />}{ok('terrain') && <TerrainCard d={d('terrain')} />}
        {mods.soil?.status === 'loading' && <Skeleton title="Soil" />}{ok('soil') && <SoilCard d={d('soil')} />}
        {ag?.score != null && <AgricultureCard d={ag} />}
        {resources?.status === 'loading' && <Skeleton title="Geology & mineral records" />}{resources?.status === 'ok' && (resources.data.geology || resources.data.occurrences) && <GeologyCard data={resources.data} />}
      </div>

      {!loading && failed.length > 0 && (
        <div className="gi-quiet" role="status">
          <span>Some public data sources did not respond for this region:</span>
          {failed.map(([k, reason]) => (
            <span key={k} className="gi-quiet__item" title={reason}>{LABELS[k]}{k !== 'resources' && <button type="button" onClick={() => load(k, run.current, region.bbox, region.geometry)}>retry</button>}</span>
          ))}
        </div>
      )}
    </section>
  );
}
