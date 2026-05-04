/**
 * Företagets pentagon — 5 axlar matchat mot vol-7-prototypen.
 *
 * Spec p-biz-hub:
 *   01 Omsättning · 4-veckors mot rolling baseline
 *   02 Kundbas · aktiva kunder + offertförfrågningar
 *   03 Likviditet · företagets kassa + nästa moms-due
 *   04 Tidsåtgång · debiterbara/admin-timmar
 *   05 Vinst · marginal senaste 4 v
 *
 * Center-score 0-100 är snitt över axlarna.
 */
import type { BizPentagon as BizPentagonData } from "./api";


const SEK = (n: number) =>
  new Intl.NumberFormat("sv-SE", { maximumFractionDigits: 0 }).format(n);


export function BizPentagon({ data }: { data: BizPentagonData }) {
  const { axes, total_score, metrics } = data;

  // Pentagon-koordinater (5 axlar, börjar uppåt)
  const cx = 300;
  const cy = 300;
  const R = 200;
  const points = [0, 1, 2, 3, 4].map((i) => {
    const angle = -Math.PI / 2 + (i * 2 * Math.PI) / 5;
    return { x: cx + R * Math.cos(angle), y: cy + R * Math.sin(angle), angle };
  });

  // Aktuell pentagon (skalat efter axlarnas score)
  const axesArr = [
    axes.omsattning,
    axes.kundbas,
    axes.likviditet,
    axes.tidsatgang,
    axes.vinst,
  ];
  const nowPath = axesArr.map((v, i) => {
    const r = R * (v / 100);
    const angle = -Math.PI / 2 + (i * 2 * Math.PI) / 5;
    return `${cx + r * Math.cos(angle)},${cy + r * Math.sin(angle)}`;
  }).join(" ");

  // Bakgrunds-rings (50/100/150/200)
  const ringPath = (radius: number) =>
    points.map((p) => {
      const a = p.angle;
      return `${cx + radius * Math.cos(a)},${cy + radius * Math.sin(a)}`;
    }).join(" ");

  const labels: Array<[string, string, string, number]> = [
    ["Omsättning", `${SEK(metrics.income_4w)} kr/4v`, axes.omsattning >= 60 ? "↑ aktiv" : axes.omsattning >= 40 ? "→ stabil" : "↓ låg", axes.omsattning],
    ["Kundbas", `${metrics.n_invoices_active} aktiva fakturor`, "", axes.kundbas],
    ["Likviditet", `${SEK(metrics.kassa)} kr på företagskontot`, metrics.kassa < 5000 ? "⚠ tunn" : "OK", axes.likviditet],
    ["Tidsåtgång", "Förenklat 60/40 split", "— stabil", axes.tidsatgang],
    ["Vinst", `${metrics.margin_4w_pct.toFixed(0)}% marginal`, `${SEK(metrics.profit_4w)} kr/4v`, axes.vinst],
  ];

  return (
    <div style={{ position: "relative", width: "100%", maxWidth: 720, margin: "0 auto" }}>
      <svg viewBox="0 0 600 600" style={{ width: "100%", height: "auto" }}>
        {/* Bakgrunds-axel-linjer */}
        {points.map((p, i) => (
          <line
            key={i}
            x1={cx} y1={cy} x2={p.x} y2={p.y}
            stroke="rgba(99,102,241,0.2)"
            strokeWidth="1"
          />
        ))}
        {/* Bakgrunds-rings */}
        {[0.25, 0.5, 0.75, 1].map((scale) => (
          <polygon
            key={scale}
            points={ringPath(R * scale)}
            fill="none"
            stroke="rgba(99,102,241,0.15)"
            strokeWidth="1"
          />
        ))}
        {/* Aktuell pentagon */}
        <polygon
          points={nowPath}
          fill="rgba(129,140,248,0.18)"
          stroke="#818cf8"
          strokeWidth="2.5"
        />
        {/* Center-score */}
        <circle cx={cx} cy={cy} r="60" fill="rgba(15,21,37,0.95)" stroke="rgba(99,102,241,0.4)" strokeWidth="2" />
        <text
          x={cx} y={cy - 6}
          textAnchor="middle"
          fill="#c7d2fe"
          fontSize="32"
          fontWeight="700"
          fontFamily="JetBrains Mono, monospace"
        >
          {total_score}
        </text>
        <text
          x={cx} y={cy + 14}
          textAnchor="middle"
          fill="rgba(255,255,255,0.5)"
          fontSize="9"
          letterSpacing="1.2"
        >
          AV 100
        </text>
      </svg>

      {/* Axel-labels positionerat ut runt pentagonen */}
      {labels.map(([name, val, sub, score], i) => {
        const angle = -Math.PI / 2 + (i * 2 * Math.PI) / 5;
        const r = 285;
        // Procent-koordinater så det skalar med svg
        const xPct = ((cx + r * Math.cos(angle)) / 600) * 100;
        const yPct = ((cy + r * Math.sin(angle)) / 600) * 100;

        // Alignment beroende på position
        const isLeft = Math.cos(angle) < -0.3;
        const isRight = Math.cos(angle) > 0.3;
        const transform = isLeft
          ? "translate(-100%, -50%)"
          : isRight
            ? "translate(0, -50%)"
            : "translate(-50%, " + (Math.sin(angle) < 0 ? "-100%" : "0") + ")";

        return (
          <div
            key={i}
            style={{
              position: "absolute",
              left: `${xPct}%`,
              top: `${yPct}%`,
              transform,
              maxWidth: 180,
              textAlign: isLeft ? "right" : isRight ? "left" : "center",
              padding: "4px 8px",
            }}
          >
            <div
              style={{
                fontFamily: "JetBrains Mono, monospace",
                fontSize: 9,
                color: "#818cf8",
                fontWeight: 700,
                letterSpacing: 1.3,
                textTransform: "uppercase",
              }}
            >
              Axel {String(i + 1).padStart(2, "0")} · {score}/100
            </div>
            <div
              style={{
                color: "white",
                fontSize: "0.95rem",
                fontWeight: 600,
                marginTop: 2,
              }}
            >
              {name}
            </div>
            <div
              style={{
                fontSize: "0.78rem",
                color: "rgba(255,255,255,0.6)",
                marginTop: 2,
              }}
            >
              {val}
            </div>
            {sub && (
              <div
                style={{
                  fontSize: "0.75rem",
                  color: score >= 60 ? "#6ee7b7" : score >= 40 ? "var(--warm)" : "#fda594",
                  marginTop: 1,
                }}
              >
                {sub}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
