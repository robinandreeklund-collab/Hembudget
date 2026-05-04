/**
 * Skola · Kompetens-detalj — elev-vy.
 *
 * Speglar prototypen /proposals/vol-7/elev.html (p-komp):
 * - actor-head med pill, current/next-nivå
 * - cc_summary med Resa, Mastery %, completed steg, mål till nästa
 * - timeline: vad eleven gjort (modul-completions, klarade steg)
 * - krav-listan för nästa nivå (checkmarks)
 * - side-cards: anslutna moduler, Echo-tips
 * - peda "Kompetens är spårbar"
 *
 * Routas via /v2/kompetens/:competencyId.
 */
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  v2Api,
  type V2KompetensDetail,
  type V2KompetensTimelineEvent,
  type V2KompetensModuleStatus,
  type V2KompetensRequirement,
} from "./api";
import { V2Banner } from "./V2Banner";
import "./lan.css";

const SHORT_DATE = (iso: string | null): string => {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleDateString("sv-SE", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
};

const LEVEL_COLOR: Record<string, string> = {
  B: "var(--text-dim)",
  G: "var(--accent)",
  F: "#6ee7b7",
};

const EVENT_BADGE_COLOR: Record<string, string> = {
  step_completed: "var(--warm)",
  module_completed: "#6ee7b7",
  level_reached: "var(--accent)",
  assigned: "var(--text-mid)",
};

export function KompetensV2() {
  const { competencyId } = useParams<{ competencyId: string }>();
  const cid = competencyId ? parseInt(competencyId, 10) : 0;
  const [data, setData] = useState<V2KompetensDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!cid) return;
    v2Api
      .kompetensDetail(cid)
      .then(setData)
      .catch((e) => setError(String((e as Error)?.message || e)));
  }, [cid]);

  if (error && !data) {
    return (
      <div className="v2-lan-root">
        <V2Banner status={{ role: "student", is_super_admin: false }} />
        <div className="bank-loading">
          <div>
            <div style={{ color: "#fca5a5", marginBottom: 8 }}>
              Kunde inte ladda kompetensen
            </div>
            <pre style={{ fontSize: 11 }}>{error}</pre>
          </div>
        </div>
      </div>
    );
  }
  if (!data) {
    return (
      <div className="v2-lan-root">
        <V2Banner status={{ role: "student", is_super_admin: false }} />
        <div className="bank-loading">Laddar kompetens…</div>
      </div>
    );
  }

  const masteryPct = Math.round(data.mastery * 100);
  const progressPct = Math.round(data.progress_to_next * 100);
  const color = LEVEL_COLOR[data.level];
  const nextColor = data.next_level
    ? LEVEL_COLOR[data.next_level]
    : color;

  return (
    <div className="v2-lan-root" data-guide="kompetens-detail">
      <V2Banner status={{ role: "student", is_super_admin: false }} />

      <div className="shell">
        <Link className="actor-back" to="/v2/portfolio">
          Tillbaka till portfolio
        </Link>

        <header className="actor-head">
          <div>
            <span className="pill">Kompetens · {data.name}</span>
            <h1 className="actor-name" style={{ marginTop: 14 }}>
              {data.name} — nivå <em style={{ color }}>{data.level_label}</em>.
            </h1>
            <p className="actor-sub">
              {data.description || "Spårbar resa B → G → F · uppdateras när du klarar steg och moduler."}
            </p>
          </div>
          <div className="actor-meta">
            Nuvarande:{" "}
            <strong style={{ color }}>{data.level_label}</strong>
            <br />
            Nästa:{" "}
            <strong style={{ color: nextColor }}>
              {data.next_level_label || "max-nivå"}
            </strong>
            <br />
            Senaste händelse:{" "}
            <strong>
              {data.last_event_at ? SHORT_DATE(data.last_event_at) : "—"}
            </strong>
          </div>
        </header>

        {/* CC SUMMARY · 4 kort */}
        <div
          className="cc-summary"
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(4, 1fr)",
            gap: 10,
            marginBottom: 22,
          }}
        >
          <SummaryCard
            eyeColor="#c7d2fe"
            eye="Resa hittills"
            num={`${data.level_label}`}
            sub={
              data.last_event_at
                ? `Senast aktiv ${SHORT_DATE(data.last_event_at)}`
                : "Inga händelser än"
            }
            italic
            highlightLeft="#818cf8"
            background="rgba(99,102,241,0.06)"
          />
          <SummaryCard
            eye="Mastery"
            num={`${masteryPct}%`}
            sub={`${data.completed_steps} av ${data.total_steps} steg klara`}
          />
          <SummaryCard
            eye="Progress till nästa"
            num={data.next_level ? `${progressPct}%` : "—"}
            sub={
              data.next_level
                ? `Krävs för ${data.next_level_label}`
                : "Du är på fördjupningsnivå"
            }
          />
          <SummaryCard
            eye="Mål till nästa"
            num={
              data.next_level
                ? `${Math.max(
                    0,
                    Math.round(
                      (data.next_level === "G" ? 33 : 66) - masteryPct,
                    ),
                  )}%-enheter`
                : "✓"
            }
            sub={
              data.next_level
                ? `behöver för ${data.next_level_label}`
                : "Maxnivå nådd"
            }
            highlightWarm
          />
        </div>

        <div
          className="act-grid"
          style={{
            display: "grid",
            gridTemplateColumns: "1.6fr 1fr",
            gap: 22,
          }}
        >
          <div>
            <div className="section-eye">
              Vad du har <em>gjort</em> · timeline
            </div>
            {data.timeline.length === 0 ? (
              <div
                style={{
                  padding: "16px 20px",
                  border: "1px solid var(--line)",
                  borderRadius: 6,
                  fontFamily: "var(--serif)",
                  color: "var(--text-mid)",
                  marginBottom: 22,
                }}
              >
                Inga händelser än. Klara steg i en modul som tränar
                kompetensen så syns de här.
              </div>
            ) : (
              <div className="biz-table" style={{ marginBottom: 22 }}>
                {data.timeline.map((ev, i) => (
                  <TimelineRow key={`${ev.event_type}-${i}`} ev={ev} />
                ))}
              </div>
            )}

            {data.next_level && (
              <>
                <div className="section-eye" style={{ marginTop: 24 }}>
                  Vad krävs för{" "}
                  <em style={{ color: nextColor }}>{data.next_level_label}</em>
                </div>
                <div className="biz-table" style={{ marginBottom: 22 }}>
                  {data.requirements_for_next.map((req, i) => (
                    <RequirementRow key={i} req={req} />
                  ))}
                </div>
              </>
            )}
          </div>

          <aside>
            <div className="side-card">
              <div className="side-card-eye">Anslutna moduler</div>
              <div className="side-card-h">
                {data.connected_modules.filter((m) => m.completed).length}{" "}
                av {data.connected_modules.length} klara
              </div>
              {data.connected_modules.length === 0 ? (
                <div
                  className="side-card-meta"
                  style={{ marginTop: 8 }}
                >
                  Inga moduler är ännu kopplade till {data.name} —
                  läraren kopplar moduler via lärar-vyn.
                </div>
              ) : (
                <ul
                  style={{
                    listStyle: "none",
                    padding: 0,
                    margin: "8px 0 0",
                    fontFamily: "Inter, sans-serif",
                    fontSize: 12.5,
                  }}
                >
                  {data.connected_modules.map((m) => (
                    <ModuleListItem key={m.module_id} m={m} />
                  ))}
                </ul>
              )}
            </div>

            {data.last_event_at && (
              <div className="side-card">
                <div className="side-card-eye">Senast aktiv</div>
                <div className="side-card-h">
                  <em>{SHORT_DATE(data.last_event_at)}</em>
                </div>
                <div className="side-card-meta">
                  Aktivitet räknas så fort du markerar ett steg som
                  klart, oavsett vilken modul. Ny aktivitet räknar mot
                  3-mån-snitt.
                </div>
              </div>
            )}

            <div
              className="side-card"
              style={{
                background: "rgba(251,191,36,0.06)",
                borderColor: "rgba(251,191,36,0.25)",
              }}
            >
              <div
                className="side-card-eye"
                style={{ color: "var(--warm)" }}
              >
                Echo · sokratiskt
              </div>
              <div className="side-card-h">
                "Är {masteryPct} % bra?"
              </div>
              <div className="side-card-meta">
                Det betyder att {Math.max(0, 100 - masteryPct)} % av de
                kopplade stegen är ej klarade. Räcker det? Eller vill
                du klara fler steg och höja {data.name} till{" "}
                {data.next_level_label || "max"}?
              </div>
            </div>
          </aside>
        </div>

        <div className="peda">
          <div className="peda-eye">Pedagogik · vad du lär dig här</div>
          <div className="peda-h">
            Kompetens är <em>spårbar</em>, inte hemlig.
          </div>
          <p className="peda-prose">
            Du ser exakt vad du gjort som lett dig hit, vad läraren sagt
            vid varje höjning, och vad nästa nivå kräver. Ingen black
            box. Detta är skolans uppdaterade syn på bedömning:{" "}
            <em>transparens</em>, formativ feedback, och eleven äger sin
            egen läranderesa. Du kan visa det här för en arbetsgivare
            om 5 år.
          </p>
        </div>
      </div>
    </div>
  );
}

function SummaryCard({
  eye,
  eyeColor,
  num,
  sub,
  italic,
  highlightLeft,
  highlightWarm,
  background,
}: {
  eye: string;
  eyeColor?: string;
  num: string;
  sub: string;
  italic?: boolean;
  highlightLeft?: string;
  highlightWarm?: boolean;
  background?: string;
}) {
  return (
    <div
      style={{
        padding: "16px 20px",
        border: "1px solid var(--line)",
        borderRadius: 6,
        borderLeftWidth: highlightLeft ? 3 : 1,
        borderLeftColor: highlightLeft || "var(--line)",
        background,
      }}
    >
      <div
        style={{
          fontFamily: "var(--mono)",
          fontSize: 9.5,
          letterSpacing: "1.2px",
          textTransform: "uppercase",
          color: eyeColor || "var(--text-dim)",
        }}
      >
        {eye}
      </div>
      <div
        style={{
          fontFamily: "var(--serif)",
          fontSize: 24,
          fontWeight: 700,
          fontStyle: italic ? "italic" : "normal",
          marginTop: 6,
          color: highlightWarm ? "var(--warm)" : "#fff",
        }}
      >
        {num}
      </div>
      <div
        style={{
          fontFamily: "var(--mono)",
          fontSize: 10,
          color: "var(--text-mid)",
          marginTop: 4,
        }}
      >
        {sub}
      </div>
    </div>
  );
}

function TimelineRow({ ev }: { ev: V2KompetensTimelineEvent }) {
  const badgeColor =
    EVENT_BADGE_COLOR[ev.event_type] || "var(--text-mid)";
  return (
    <div
      className="biz-table-row"
      style={{ gridTemplateColumns: "100px 1fr 120px" }}
    >
      <span
        style={{
          fontFamily: "var(--mono)",
          fontSize: 10,
          color: "var(--text-mid)",
        }}
      >
        {SHORT_DATE(ev.occurred_at)}
      </span>
      <div>
        <div
          style={{
            fontFamily: "var(--serif)",
            fontSize: 14,
            color: "#fff",
          }}
        >
          {ev.title}
        </div>
        {ev.detail && (
          <div
            style={{
              fontFamily: "var(--mono)",
              fontSize: 9.5,
              color: "var(--text-dim)",
              marginTop: 2,
            }}
          >
            {ev.detail}
          </div>
        )}
      </div>
      <span
        style={{
          fontFamily: "var(--mono)",
          fontSize: 9,
          fontWeight: 700,
          color: badgeColor,
          letterSpacing: 1,
        }}
      >
        {ev.badge || ev.event_type}
      </span>
    </div>
  );
}

function RequirementRow({ req }: { req: V2KompetensRequirement }) {
  return (
    <div
      className="biz-table-row"
      style={{ gridTemplateColumns: "32px 1fr 90px" }}
    >
      <span
        style={{
          fontFamily: "var(--mono)",
          fontSize: 12,
          color: req.met ? "#6ee7b7" : "var(--text-dim)",
        }}
      >
        {req.met ? "✓" : "○"}
      </span>
      <div>
        <div
          style={{
            fontFamily: "var(--serif)",
            fontSize: 13.5,
            color: "#fff",
          }}
        >
          {req.label}
        </div>
        {req.description && (
          <div
            style={{
              fontFamily: "var(--mono)",
              fontSize: 9,
              color: "var(--text-dim)",
            }}
          >
            {req.description}
          </div>
        )}
      </div>
      <span
        style={{
          fontFamily: "var(--mono)",
          fontSize: 10,
          color: req.met ? "#6ee7b7" : "var(--warm)",
        }}
      >
        {req.value_label}
      </span>
    </div>
  );
}

function ModuleListItem({ m }: { m: V2KompetensModuleStatus }) {
  return (
    <li
      style={{
        display: "flex",
        gap: 8,
        padding: "5px 0",
        borderBottom: "1px dashed var(--line)",
        alignItems: "center",
      }}
    >
      <span style={{ color: m.completed ? "#6ee7b7" : "var(--text-dim)" }}>
        {m.completed ? "✓" : "○"}
      </span>
      <span style={{ flex: 1 }}>{m.title}</span>
      <span
        style={{
          fontFamily: "var(--mono)",
          fontSize: 9,
          color: "var(--text-dim)",
        }}
      >
        {m.completed_steps}/{m.total_steps}
      </span>
    </li>
  );
}
