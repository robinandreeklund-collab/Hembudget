/**
 * Företagets pentagon — exakt prototyp-match (proposals/vol-7 p-biz-hub).
 *
 * Spec p-biz-hub:
 *   01 Omsättning · 4-veckors mot rolling baseline · klick → bokföring
 *   02 Kundbas · aktiva kunder + offertförfrågningar · klick → kunder
 *   03 Likviditet · företagets kassa + nästa moms-due
 *   04 Tidsåtgång · debiterbara/admin-timmar
 *   05 Vinst · marginal senaste 4 v · klick → bokföring
 *
 * SVG geometri matchar prototypen (rad 5345-5359):
 *   - 5 hörn på radius 260 i 600x600 viewbox
 *   - 4 koncentriska polygoner som bakgrund (260 / 195 / 130 / 65)
 *   - 5 axel-linjer från center
 *   - biz-pent-prev: dashed jämförelse-polygon (förra 4-vecka-fönstret)
 *   - biz-pent-now: fylld nuvarande pentagon med "breathe"-animation
 *   - center-card med score 0-100
 *
 * Axel-labels positioneras med absolute via CSS-klasserna ax-eko/rel/har/fri/kar
 * (matchar prototypen rad 381-385). Labels är klickbara där relevant.
 */
import type { BizPentagon as BizPentagonData, BizAxis } from "./api";


const SEK = (n: number) =>
  new Intl.NumberFormat("sv-SE", { maximumFractionDigits: 0 }).format(n);


function corner(i: number, r: number): { x: number; y: number } {
  // 5 hörn, börjar uppåt (-90°), kloka mot 90°-stegg per ax
  const angle = -Math.PI / 2 + (i * 2 * Math.PI) / 5;
  return {
    x: Math.round(Math.cos(angle) * r),
    y: Math.round(Math.sin(angle) * r),
  };
}

function polygonPoints(scale: number, R = 260): string {
  return [0, 1, 2, 3, 4]
    .map((i) => {
      const c = corner(i, R * scale);
      return `${c.x},${c.y}`;
    })
    .join(" ");
}

function dataPolygonPoints(
  axes: number[],
  R = 260,
): string {
  return axes
    .map((v, i) => {
      const c = corner(i, R * (Math.max(0, Math.min(100, v)) / 100));
      return `${c.x},${c.y}`;
    })
    .join(" ");
}


export function BizPentagon({
  data,
  onAxisClick,
}: {
  data: BizPentagonData;
  onAxisClick?: (axis: BizAxis) => void;
}) {
  const { axes, axes_prev, total_score, metrics } = data;

  const axesArr = [
    axes.omsattning,
    axes.kundbas,
    axes.likviditet,
    axes.tidsatgang,
    axes.vinst,
  ];
  const nowPath = dataPolygonPoints(axesArr);

  const prevPath = axes_prev
    ? dataPolygonPoints([
        axes_prev.omsattning,
        axes_prev.kundbas,
        axes_prev.likviditet,
        axes_prev.tidsatgang,
        axes_prev.vinst,
      ])
    : null;

  // Pre-compute label-data så JSX nedan blir lättläst.
  const oms_trend = axes.omsattning - (axes_prev?.omsattning ?? axes.omsattning);
  const vinst_trend = axes.vinst - (axes_prev?.vinst ?? axes.vinst);

  return (
    <div className="pentagon-stage">
      <svg
        className="pentagon-svg"
        viewBox="0 0 600 600"
        aria-label="Företagets pentagon"
      >
        <g transform="translate(300,300)">
          {/* 4 bakgrundsringar (matchar prototyp) */}
          <polygon points={polygonPoints(1.0)} className="p-axis-line" />
          <polygon points={polygonPoints(0.75)} className="p-axis-line" />
          <polygon points={polygonPoints(0.5)} className="p-axis-line" />
          <polygon points={polygonPoints(0.25)} className="p-axis-line" />
          {/* 5 axel-linjer från center till hörn */}
          {[0, 1, 2, 3, 4].map((i) => {
            const c = corner(i, 260);
            return (
              <line
                key={i}
                x1="0"
                y1="0"
                x2={c.x}
                y2={c.y}
                className="p-axis-line"
              />
            );
          })}
          {/* Föregående 4-veckor (dashed) — om data finns */}
          {prevPath && (
            <polygon points={prevPath} className="biz-pent-prev" />
          )}
          {/* Aktuell pentagon */}
          <polygon points={nowPath} className="biz-pent-now" />
        </g>
      </svg>

      {/* Axel 01 · Omsättning · klick → flip-kort med detalj */}
      <a
        href="#"
        onClick={(e) => {
          e.preventDefault();
          onAxisClick?.("omsattning");
        }}
        className="biz-axis-label ax-eko"
      >
        <div className="biz-axis-label-eye">Axel 01</div>
        <div className="biz-axis-label-name">Omsättning</div>
        <div className="biz-axis-label-meta">
          {SEK(metrics.income_4w)} kr/4v
        </div>
        <div
          className="biz-axis-label-meta"
          style={{
            color:
              oms_trend > 0 ? "#6ee7b7" : oms_trend < 0 ? "#fca5a5"
                : "var(--text-mid)",
          }}
        >
          {oms_trend > 0
            ? `↑ +${oms_trend} mot v-4`
            : oms_trend < 0
            ? `↓ ${oms_trend} mot v-4`
            : "— stabil"}
        </div>
      </a>

      {/* Axel 02 · Kundbas · klick → flip-kort */}
      <a
        href="#"
        onClick={(e) => {
          e.preventDefault();
          onAxisClick?.("kundbas");
        }}
        className="biz-axis-label ax-rel"
      >
        <div className="biz-axis-label-eye">Axel 02</div>
        <div className="biz-axis-label-name">Kundbas</div>
        <div className="biz-axis-label-meta">
          {metrics.n_invoices_active} aktiva fakturor
        </div>
      </a>

      {/* Axel 03 · Likviditet · klick → flip-kort */}
      <a
        href="#"
        onClick={(e) => {
          e.preventDefault();
          onAxisClick?.("likviditet");
        }}
        className="biz-axis-label ax-har"
      >
        <div className="biz-axis-label-eye">Axel 03</div>
        <div className="biz-axis-label-name">Likviditet</div>
        <div className="biz-axis-label-meta">
          {SEK(metrics.kassa)} kr på företagskontot
        </div>
        {metrics.kassa < 5000 && (
          <div
            className="biz-axis-label-meta"
            style={{ color: "#fbbf24" }}
          >
            ⚠ tunn marginal
          </div>
        )}
      </a>

      {/* Axel 04 · Tidsåtgång · klick → flip-kort */}
      <a
        href="#"
        onClick={(e) => {
          e.preventDefault();
          onAxisClick?.("tidsatgang");
        }}
        className="biz-axis-label ax-fri"
      >
        <div className="biz-axis-label-eye">Axel 04</div>
        <div className="biz-axis-label-name">Tidsåtgång</div>
        <div className="biz-axis-label-meta">
          Förenklat 60/40 split
        </div>
        <div
          className="biz-axis-label-meta"
          style={{ color: "var(--text-mid)" }}
        >
          — stabil
        </div>
      </a>

      {/* Axel 05 · Vinst · klick → flip-kort */}
      <a
        href="#"
        onClick={(e) => {
          e.preventDefault();
          onAxisClick?.("vinst");
        }}
        className="biz-axis-label ax-kar"
      >
        <div className="biz-axis-label-eye">Axel 05</div>
        <div className="biz-axis-label-name">Vinst</div>
        <div className="biz-axis-label-meta">
          {SEK(metrics.profit_4w)} kr/4v · marginal{" "}
          {metrics.margin_4w_pct.toFixed(0)}%
        </div>
        <div
          className="biz-axis-label-meta"
          style={{
            color:
              vinst_trend > 0 ? "#6ee7b7" : vinst_trend < 0 ? "#fca5a5"
                : "var(--text-mid)",
          }}
        >
          {vinst_trend > 0
            ? `↑ +${vinst_trend} mot v-4`
            : vinst_trend < 0
            ? `↓ ${vinst_trend} mot v-4`
            : "— stabil"}
        </div>
      </a>

      {/* Center-card */}
      <div className="center-card">
        <div className="center-eye">Företag</div>
        <div className="center-num">{total_score}</div>
        <div className="center-meta">av 100</div>
      </div>
    </div>
  );
}
