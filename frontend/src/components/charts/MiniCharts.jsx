// Small dependency-free SVG charts used by the intelligence dashboard.
const PALETTE = ['#5ee1ff', '#8b7bff', '#4fd1a5', '#ffc857', '#ff8f6b', '#c78bff', '#7aa2ff', '#9aa9bd'];

export function Ring({ value, label, tone = '#5ee1ff', size = 112 }) {
  const r = 44; const c = 2 * Math.PI * r; const v = Math.max(0, Math.min(100, value));
  return (
    <figure className="gi-ring" style={{ width: size }}>
      <svg viewBox="0 0 110 110" width={size} height={size} role="img" aria-label={`${label}: ${Math.round(v)} of 100`}>
        <circle cx="55" cy="55" r={r} className="gi-ring__track" />
        <circle cx="55" cy="55" r={r} className="gi-ring__bar" style={{ stroke: tone, strokeDasharray: `${(v / 100) * c} ${c}` }} transform="rotate(-90 55 55)" />
        <text x="55" y="53" textAnchor="middle" className="gi-ring__value">{Math.round(v)}</text>
        <text x="55" y="70" textAnchor="middle" className="gi-ring__unit">/ 100</text>
      </svg>
      <figcaption>{label}</figcaption>
    </figure>
  );
}

export function StackBar({ parts, unit = '%' }) {
  const items = parts.filter((p) => p.value > 0);
  return (
    <div className="gi-stack">
      <div className="gi-stack__bar" role="img" aria-label={items.map((p) => `${p.label} ${p.value}${unit}`).join(', ')}>
        {items.map((p, i) => <span key={p.label} style={{ width: `${p.value}%`, background: p.color || PALETTE[i % PALETTE.length] }} title={`${p.label} ${p.value}${unit}`} />)}
      </div>
      <ul>{items.map((p, i) => <li key={p.label}><i style={{ background: p.color || PALETTE[i % PALETTE.length] }} />{p.label}<b>{p.value}{unit}</b></li>)}</ul>
    </div>
  );
}

export function HBars({ items, max, unit = '' }) {
  const top = max || Math.max(...items.map((i) => i.value), 1);
  return (
    <div className="gi-hbars">
      {items.map((i) => (
        <div key={i.label}><span>{i.label}</span><div><em style={{ width: `${Math.max(2, (i.value / top) * 100)}%` }} /></div><b>{i.value}{unit}</b></div>
      ))}
    </div>
  );
}

const MONTHS = ['J', 'F', 'M', 'A', 'M', 'J', 'J', 'A', 'S', 'O', 'N', 'D'];

export function ClimateChart({ monthly }) {
  const rain = monthly.rainfall_mm.map((v) => v ?? 0); const temp = monthly.temperature_c;
  const maxR = Math.max(...rain, 1);
  const tv = temp.filter((v) => v != null); const tMin = Math.min(...tv) - 2; const tMax = Math.max(...tv) + 2;
  const x = (i) => 28 + i * 24.5; const yT = (v) => 8 + (1 - (v - tMin) / (tMax - tMin)) * 84;
  const line = temp.map((v, i) => (v == null ? null : `${i ? 'L' : 'M'}${x(i) + 8},${yT(v)}`)).filter(Boolean).join(' ');
  return (
    <svg viewBox="0 0 320 120" className="gi-chart" role="img" aria-label="Monthly rainfall and temperature">
      {rain.map((v, i) => <rect key={i} x={x(i)} y={100 - (v / maxR) * 88} width="16" height={(v / maxR) * 88} rx="3" className="gi-chart__rain"><title>{`${MONTHS[i]}: ${v} mm`}</title></rect>)}
      <path d={line} className="gi-chart__temp" />
      {temp.map((v, i) => (v == null ? null : <circle key={i} cx={x(i) + 8} cy={yT(v)} r="2.6" className="gi-chart__dot"><title>{`${v} °C`}</title></circle>))}
      {MONTHS.map((m, i) => <text key={i} x={x(i) + 8} y="114" textAnchor="middle" className="gi-chart__axis">{m}</text>)}
      <text x="2" y="12" className="gi-chart__axis">{Math.round(tMax)}°</text><text x="2" y="96" className="gi-chart__axis">{Math.round(tMin)}°</text>
    </svg>
  );
}

export function Sparkline({ points, unit = '' }) {
  const v = points.map((p) => p.value); const lo = Math.min(...v); const hi = Math.max(...v); const span = hi - lo || 1;
  const d = points.map((p, i) => `${i ? 'L' : 'M'}${6 + (i / Math.max(1, points.length - 1)) * 208},${40 - ((p.value - lo) / span) * 34}`).join(' ');
  return (
    <svg viewBox="0 0 220 52" className="gi-spark" role="img" aria-label={`Yearly values ${points[0].year} to ${points[points.length - 1].year}`}>
      <path d={d} />{points.map((p, i) => <circle key={p.year} cx={6 + (i / Math.max(1, points.length - 1)) * 208} cy={40 - ((p.value - lo) / span) * 34} r="2.4"><title>{`${p.year}: ${p.value}${unit}`}</title></circle>)}
      <text x="4" y="51">{points[0].year}</text><text x="216" y="51" textAnchor="end">{points[points.length - 1].year}</text>
    </svg>
  );
}

export function AspectRose({ shares }) {
  const dirs = [['N', 0], ['E', 90], ['S', 180], ['W', 270]];
  return (
    <svg viewBox="0 0 110 110" className="gi-rose" role="img" aria-label="Slope aspect share">
      <circle cx="55" cy="55" r="38" className="gi-rose__ring" />
      {dirs.map(([d, deg]) => {
        const v = (shares?.[d] || 0) / 100; const a = (deg * Math.PI) / 180;
        return <g key={d}><line x1="55" y1="55" x2={55 + Math.sin(a) * (6 + v * 40)} y2={55 - Math.cos(a) * (6 + v * 40)} className="gi-rose__spoke" />
          <text x={55 + Math.sin(a) * 50} y={58 - Math.cos(a) * 48} textAnchor="middle">{d}</text></g>;
      })}
    </svg>
  );
}

export const colors = PALETTE;
