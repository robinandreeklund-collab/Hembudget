/**
 * Lärar-hub V2 · klass-dashboard.
 *
 * Speglar prototypen /proposals/vol-7/larare.html#p-hub:
 * - Header med klass-info, period-label, snabb-actions
 * - 5 stat-kort: Klass-balans, Behöver stöd, Pågående moduler,
 *   Lönesamtal i Maria, Olästa reflektioner
 * - Klass-pentagon (aggregerad) + side-stack med:
 *   · Behöver stöd nu (problembarn först)
 *   · Pågående lönesamtal (klickbara)
 *   · Postlådor topp-N (mest ohanterade)
 *   · Nivå-progression (ready_for_promotion)
 *   · Olästa reflektioner
 * - 28 mini-pentagoner sorterat på pent-värde (problem först)
 *
 * Allt läses från /v2/teacher/klass-overview · ingen mock-data.
 */
import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { v2Api, type V2KlassOverview, type V2KlassMiniPentagon } from "./api";
import { V2Banner } from "./V2Banner";
import "./larare.css";

function fmtSEK(n: number | null): string {
  if (n === null) return "—";
  return Math.round(n).toLocaleString("sv-SE");
}

function colorClassForPent(p: number): "green" | "amber" | "red" | "" {
  if (p >= 70) return "green";
  if (p >= 50) return "amber";
  if (p >= 35) return "";
  return "red";
}

/** Beräkna 5-axel-pentagon-koordinater (radius * value/100). */
function pentagonPoints(
  cx: number,
  cy: number,
  radius: number,
  values: number[],
): string {
  // 5 punkter: top, top-right, bottom-right, bottom-left, top-left
  const angles = [-90, -18, 54, 126, 198];
  return values
    .map((v, i) => {
      const r = (radius * Math.max(0, Math.min(100, v))) / 100;
      const a = (angles[i] * Math.PI) / 180;
      const x = cx + r * Math.cos(a);
      const y = cy + r * Math.sin(a);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
}

export function TeacherHubV2() {
  const [data, setData] = useState<V2KlassOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    v2Api
      .teacherKlassOverview()
      .then(setData)
      .catch((e) => setError(String((e as Error)?.message || e)));
  }, []);

  if (error && !data) {
    return (
      <div className="v2-larare-root">
        <V2Banner status={{ role: "teacher", is_super_admin: false }} />
        <div className="larare-loading">
          <div>
            <div style={{ color: "#fca5a5", marginBottom: 8 }}>
              Kunde inte ladda lärar-hubben
            </div>
            <pre style={{ fontSize: 11 }}>{error}</pre>
          </div>
        </div>
      </div>
    );
  }
  if (!data) {
    return (
      <div className="v2-larare-root">
        <V2Banner status={{ role: "teacher", is_super_admin: false }} />
        <div className="larare-loading">Laddar klass-dashboarden…</div>
      </div>
    );
  }

  return (
    <div className="v2-larare-root">
      <V2Banner status={{ role: "teacher", is_super_admin: false }} />

      <div className="shell">
        <header className="larare-head">
          <div>
            <span className="pill">
              {data.total_students} elever · {data.period_label}
            </span>
            <h1 className="larare-head-h1">
              Klassens <em>pentagon</em> i rörelse.
            </h1>
            <div className="larare-actions">
              <Link to="/teacher/v2/roster" className="larare-tb-btn solid">
                + Skapa elev / generera kod
              </Link>
              <Link to="/teacher/v2/roster" className="larare-tb-btn">
                v2-roster ✦
              </Link>
            </div>
          </div>
          <div className="larare-head-meta">
            {data.teacher_name}
            <br />
            {data.active_today} / {data.total_students}{" "}
            <strong>aktiva idag</strong>
            <br />
            {data.reflections_unread_count} reflektioner att läsa
          </div>
        </header>

        <KlassStats stats={data.klass_stats} />

        <div className="class-stage">
          <KlassPentagon data={data} />
          <SideStack data={data} navigate={navigate} />
        </div>

        <div className="section-title">
          {data.total_students} elever · klicka för att zooma
        </div>
        <div className="mini-grid">
          {data.mini_pentagons.map((mp) => (
            <MiniPentagon key={mp.student_id} mp={mp} />
          ))}
        </div>
      </div>
    </div>
  );
}

function KlassStats({ stats }: { stats: V2KlassOverview["klass_stats"] }) {
  return (
    <div className="larare-stats">
      {stats.map((s, i) => (
        <div key={i} className="larare-stat">
          <div className="larare-stat-eye">{s.eye}</div>
          <div className={`larare-stat-num${s.accent ? " accent" : ""}`}>
            {s.accent ? <em>{s.num_value}</em> : s.num_value}
          </div>
          <div className="larare-stat-sub">{s.sub}</div>
        </div>
      ))}
    </div>
  );
}

function KlassPentagon({ data }: { data: V2KlassOverview }) {
  const p = data.klass_pentagon;
  const radius = 230;
  const cx = 300;
  const cy = 300;

  // Values mapped 1:1 to axis order: top=economy, top-right=safety,
  // bottom-right=health, bottom-left=social, top-left=leisure
  const values = [p.economy, p.safety, p.health, p.social, p.leisure];
  const ringValues = [100, 75, 50, 25];
  const tippedTowards = useMemo(() => {
    const axes: { name: string; v: number }[] = [
      { name: "ekonomi", v: p.economy },
      { name: "karriär", v: p.safety },
      { name: "hälsa", v: p.health },
      { name: "relation", v: p.social },
      { name: "fritid", v: p.leisure },
    ];
    const max = axes.reduce((a, b) => (a.v >= b.v ? a : b));
    return max.name;
  }, [p]);

  return (
    <article className="class-pent">
      <div className="class-pent-eye">
        Klassens aggregerade pentagon · {data.period_label}
      </div>
      <h2 className="class-pent-h">
        {p.total_score} av 100 — <em>tippad</em> mot {tippedTowards}.
      </h2>
      <svg className="pent-svg" viewBox="0 0 600 600">
        {/* Ring-polygons (decorative concentric pentagons) */}
        {ringValues.map((rv) => (
          <polygon
            key={rv}
            className="p-axis-line"
            points={pentagonPoints(cx, cy, radius, [rv, rv, rv, rv, rv])}
          />
        ))}
        {/* Axis lines */}
        {[0, 1, 2, 3, 4].map((i) => {
          const a =
            (([-90, -18, 54, 126, 198][i] as number) * Math.PI) / 180;
          const x2 = cx + radius * Math.cos(a);
          const y2 = cy + radius * Math.sin(a);
          return (
            <line
              key={i}
              className="p-axis-line"
              x1={cx}
              y1={cy}
              x2={x2.toFixed(1)}
              y2={y2.toFixed(1)}
            />
          );
        })}
        {/* Klass-pentagon */}
        <polygon
          className="p-class"
          points={pentagonPoints(cx, cy, radius, values)}
        />
        <text
          x={cx}
          y={cy + 6}
          textAnchor="middle"
          fontFamily="Source Serif 4"
          fontStyle="italic"
          fontWeight="700"
          fontSize="64"
          fill="#fbbf24"
        >
          {p.total_score}
        </text>
        <text
          x={cx}
          y={cy + 26}
          textAnchor="middle"
          fontFamily="JetBrains Mono"
          fontSize="9"
          fill="rgba(255,255,255,0.55)"
          letterSpacing="2"
        >
          AV 100
        </text>
      </svg>
      <div className="axis-tags">
        <span>
          Ekonomi
          <strong>{p.economy}</strong>
        </span>
        <span>
          Karriär
          <strong>{p.safety}</strong>
        </span>
        <span>
          Hälsa
          <strong>{p.health}</strong>
        </span>
        <span>
          Relation
          <strong>{p.social}</strong>
        </span>
        <span>
          Fritid
          <strong>{p.leisure}</strong>
        </span>
      </div>
    </article>
  );
}

function SideStack({
  data,
  navigate,
}: {
  data: V2KlassOverview;
  navigate: ReturnType<typeof useNavigate>;
}) {
  return (
    <aside className="side-stack">
      {/* Behöver stöd nu */}
      {data.students_needing_help.length > 0 && (
        <div className="s-card alert">
          <div className="s-card-eye accent">Behöver stöd nu</div>
          <div className="s-card-h">
            {data.students_needing_help.length} <em>elever</em> idag
          </div>
          <ul className="attn-list">
            {data.students_needing_help.map((h) => (
              <li key={h.student_id}>
                <div>
                  <div className="attn-name">{h.student_name}</div>
                  <div className="attn-why">{h.reason}</div>
                </div>
                <Link
                  className="attn-go"
                  to={`/teacher/v2/elev/${h.student_id}`}
                >
                  öppna →
                </Link>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Pågående lönesamtal */}
      {data.pending_negotiations.length > 0 && (
        <div className="s-card">
          <div className="s-card-eye">Pågående lönesamtal</div>
          <div className="s-card-h">
            {data.pending_negotiations.length} elever <em>i Maria</em>
          </div>
          {data.pending_negotiations.slice(0, 3).map((n) => (
            <button
              key={n.negotiation_id}
              className="maria-mini"
              onClick={() => navigate(`/teacher/v2/maria/${n.student_id}`)}
              type="button"
              style={{ width: "100%", textAlign: "left" }}
            >
              <div className="maria-mini-name">
                {n.student_name} · runda {n.round_no} / {n.max_rounds}
              </div>
              <div className="maria-mini-meta">
                start {fmtSEK(n.starting_salary)}
                {n.last_proposed_salary
                  ? ` · senaste bud ${fmtSEK(n.last_proposed_salary)}`
                  : " · ej budat än"}
              </div>
            </button>
          ))}
          <Link
            className="attn-go"
            to="/teacher/v2/maria"
            style={{ display: "block", paddingTop: 6 }}
          >
            Se alla {data.pending_negotiations.length} förhandlingar →
          </Link>
        </div>
      )}

      {/* Reflektioner att läsa */}
      {data.reflections_unread_count > 0 && (
        <div className="s-card">
          <div className="s-card-eye">Reflektioner att läsa</div>
          <div className="s-card-h">
            {data.reflections_unread_count} <em>nya</em>
          </div>
          <p
            style={{
              fontFamily: "Source Serif 4, Georgia, serif",
              fontSize: 13,
              color: "rgba(255,255,255,0.6)",
              lineHeight: 1.5,
              margin: "0 0 8px",
            }}
          >
            Eleven har klarat reflect-steg som väntar på din kommentar.
          </p>
          <Link
            className="attn-go"
            to="/teacher/v2/reflektioner"
            style={{ display: "block", paddingTop: 6 }}
          >
            Öppna alla {data.reflections_unread_count} reflektioner →
          </Link>
        </div>
      )}

      {/* Nivå-progression */}
      <div className="s-card green">
        <div className="s-card-eye green">Klassens nivå-progression</div>
        <div className="s-card-h">
          {data.total_students} elever ·{" "}
          <em className="green">3 nivåer</em>
        </div>
        <div className="level-grid">
          <div className="level-cell l1">
            <div className="level-cell-num">
              {data.level_distribution.level_1_count}
            </div>
            <div className="level-cell-bar">▰▱▱ NIVÅ 1</div>
          </div>
          <div className="level-cell l2">
            <div className="level-cell-num">
              {data.level_distribution.level_2_count}
            </div>
            <div className="level-cell-bar">▰▰▱ NIVÅ 2</div>
          </div>
          <div className="level-cell l3">
            <div className="level-cell-num">
              {data.level_distribution.level_3_count}
            </div>
            <div className="level-cell-bar">▰▰▰ NIVÅ 3</div>
          </div>
        </div>
        {data.level_distribution.ready_for_promotion.length > 0 && (
          <ul className="attn-list">
            {data.level_distribution.ready_for_promotion.map((r) => (
              <li key={r.student_id}>
                <div>
                  <div className="attn-name">
                    {r.student_name} · klar för Nivå {r.target_level}
                  </div>
                  <div className="attn-why">
                    {r.weeks_at_level} v · {r.progress_pct} % progression
                  </div>
                </div>
                <Link
                  className="attn-go"
                  to={`/teacher/v2/elev/${r.student_id}`}
                >
                  se →
                </Link>
              </li>
            ))}
          </ul>
        )}
        <div
          style={{
            marginTop: 10,
            fontFamily: "JetBrains Mono, monospace",
            fontSize: 9,
            color: "rgba(255,255,255,0.4)",
            letterSpacing: 0.5,
          }}
        >
          Promotion-heuristik: pent ≥ 65, aktiv senaste 2 v.
        </div>
      </div>

      {/* Postlådor */}
      {data.mailbox_top.length > 0 && (
        <div className="s-card alert">
          <div className="s-card-eye accent">Postlådor</div>
          <div className="s-card-h">
            {data.mailbox_total_unhandled} <em>ohanterade</em> brev
          </div>
          <ul className="attn-list">
            {data.mailbox_top.map((m) => (
              <li key={m.student_id}>
                <div>
                  <div className="attn-name">{m.student_name}</div>
                  <div className="attn-why">
                    {m.unhandled_count} ohanterade
                    {m.oldest_days != null
                      ? ` · äldsta ${m.oldest_days} dgr`
                      : ""}
                    {m.has_authority ? " · myndighetspost oöppnat" : ""}
                  </div>
                </div>
                <Link
                  className="attn-go"
                  to={`/teacher/v2/elev/${m.student_id}`}
                >
                  →
                </Link>
              </li>
            ))}
          </ul>
          <Link
            className="attn-go"
            to="/teacher/v2/postlador"
            style={{ display: "block", paddingTop: 8 }}
          >
            Se alla {data.total_students} postlådor →
          </Link>
        </div>
      )}
    </aside>
  );
}

function MiniPentagon({ mp }: { mp: V2KlassMiniPentagon }) {
  const cx = 50;
  const cy = 50;
  const radius = 38;
  const values = [
    mp.economy,
    mp.safety,
    mp.health,
    mp.social,
    mp.leisure,
  ];
  const colorClass = colorClassForPent(mp.pent_total);
  const isAlert = mp.pent_total < 35;

  return (
    <Link
      to={`/teacher/v2/elev/${mp.student_id}`}
      className={`mini${isAlert ? " alert" : colorClass === "green" ? " green" : ""}`}
      title={`${mp.student_name} · pent ${mp.pent_total}`}
    >
      <svg className="mini-svg" viewBox="0 0 100 100">
        {/* Bakre axlar */}
        <polygon
          className="mini-axes"
          points={pentagonPoints(cx, cy, radius, [100, 100, 100, 100, 100])}
        />
        <polygon
          className="mini-axes"
          points={pentagonPoints(cx, cy, radius, [50, 50, 50, 50, 50])}
        />
        {/* Studentens pentagon */}
        <polygon
          className={`mini-pent${colorClass ? ` ${colorClass}` : ""}`}
          points={pentagonPoints(cx, cy, radius, values)}
        />
      </svg>
      <div className="mini-name">{firstName(mp.student_name)}</div>
      <div className="mini-num">
        {mp.pent_total}
        {mp.days_since_last_activity != null
          ? ` · ${mp.days_since_last_activity}d`
          : ""}
      </div>
    </Link>
  );
}

function firstName(name: string): string {
  const parts = name.trim().split(/\s+/);
  if (parts.length === 1) return parts[0];
  // "Sara Anderson" → "Sara A."
  return `${parts[0]} ${parts[parts.length - 1].charAt(0)}.`;
}
