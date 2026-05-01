/**
 * Lärar-vy · alla elevens lönesamtal med Maria.
 *
 * Visar varje rond i full text (läraren ser exakt vad eleven skrev
 * och vad Maria svarade) — pedagogiskt värdefullt för bedömning.
 */
import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  v2Api,
  type V2TeacherMariaOverview,
  type V2MariaNegotiation,
} from "./api";
import { V2Banner } from "./V2Banner";
import "./lan.css";

const SEK = (n: number) =>
  new Intl.NumberFormat("sv-SE", { maximumFractionDigits: 0 }).format(n);

const SHORT_DATE = (iso: string): string => {
  const d = new Date(iso);
  return d.toLocaleDateString("sv-SE", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
};

export function TeacherMariaOverviewPage() {
  const { studentId } = useParams<{ studentId: string }>();
  const sid = studentId ? parseInt(studentId, 10) : 0;
  const [data, setData] = useState<V2TeacherMariaOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    if (!sid) return;
    v2Api
      .teacherMariaOverview(sid)
      .then(setData)
      .catch((e) => setError(String((e as Error)?.message || e)));
  }, [sid]);

  if (error) {
    return (
      <div className="v2-lan-root">
        <V2Banner status={{ role: "teacher", is_super_admin: false }} />
        <div className="bank-loading">
          <div>
            <div style={{ color: "#fca5a5", marginBottom: 8 }}>
              Kunde inte ladda lönesamtal
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
        <V2Banner status={{ role: "teacher", is_super_admin: false }} />
        <div className="bank-loading">Laddar Maria-historik…</div>
      </div>
    );
  }

  const m = data.maria;
  const all = [
    ...(m.active ? [m.active] : []),
    ...m.history,
  ];

  return (
    <div className="v2-lan-root">
      <V2Banner status={{ role: "teacher", is_super_admin: false }} />

      <div className="shell">
        <a
          className="actor-back"
          onClick={(e) => {
            e.preventDefault();
            navigate("/teacher/v2");
          }}
          href="#"
        >
          Tillbaka till klass-hubben
        </a>

        <header className="actor-head">
          <div>
            <span className="pill warm">Lärar-vy · Maria-AI lönesamtal</span>
            <h1 className="actor-name" style={{ marginTop: 14 }}>
              {data.student_name}s <em>förhandlings-historik</em>.
            </h1>
            <p className="actor-sub">
              {all.length} samtal totalt · {m.has_active ? "1 aktivt" : "0 aktiva"}
              · läraren ser varje rond i full text för bedömning
            </p>
          </div>
          <div className="actor-meta">
            Aktivt: <strong>{m.has_active ? "Ja" : "Nej"}</strong>
            <br />
            Historik: <strong>{m.history.length} samtal</strong>
            <br />
            Modell: <strong>Sonnet 4.6</strong>
          </div>
        </header>

        {all.length === 0 ? (
          <div
            style={{
              padding: "20px 24px",
              border: "1px solid var(--line)",
              borderRadius: 6,
              fontFamily: "var(--serif)",
              color: "var(--text-mid)",
              marginBottom: 22,
            }}
          >
            Eleven har inte startat något lönesamtal med Maria än.
          </div>
        ) : (
          all.map((n) => <NegotiationCard key={n.id} n={n} />)
        )}

        <div className="peda" style={{ marginTop: 28 }}>
          <div className="peda-eye">Pedagogik · vad du ser här</div>
          <div className="peda-h">
            Argumenterande är <em>språk</em>, inte instinkt.
          </div>
          <p className="peda-prose">
            Varje rond är full text. Läs vad eleven skrev — anchoring?
            BATNA? Hänvisade till data eller känslor? Marias svar är
            AI-genererat (Sonnet 4.6) men följer realistisk HR-logik.
            Pedagogiskt: titta efter om eleven står kvar vid press,
            eller sänker direkt.
          </p>
          <div className="peda-tip">
            Wellbeing-koppling: aktivt samtal +2 economy, klart med
            löneökning +economy (max +8), avbrutet -3 economy. Eleven
            ser sina egna effekter. Du ser kvalitet, inte bara siffra.
          </div>
        </div>
      </div>
    </div>
  );
}

function NegotiationCard({ n }: { n: V2MariaNegotiation }) {
  return (
    <article
      style={{
        background: "rgba(15,21,37,0.7)",
        border: "1px solid var(--line)",
        borderRadius: 8,
        padding: "20px 24px",
        marginBottom: 18,
      }}
    >
      <header
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "baseline",
          flexWrap: "wrap",
          gap: 12,
          marginBottom: 14,
          paddingBottom: 14,
          borderBottom: "1px solid var(--line)",
        }}
      >
        <div>
          <div
            style={{
              fontFamily: "var(--mono)",
              fontSize: 9.5,
              letterSpacing: "1.2px",
              textTransform: "uppercase",
              color: "var(--warm)",
              marginBottom: 4,
            }}
          >
            ● {SHORT_DATE(n.started_at)} · {n.profession}
          </div>
          <div
            style={{
              fontFamily: "var(--serif)",
              fontSize: 18,
              fontWeight: 700,
            }}
          >
            {n.employer}
          </div>
          <div
            style={{
              fontFamily: "var(--mono)",
              fontSize: 10,
              color: "var(--text-mid)",
              marginTop: 2,
            }}
          >
            Startlön: {SEK(n.starting_salary)} kr ·{" "}
            {n.avtal_norm_pct != null
              ? `avtals-norm ${n.avtal_norm_pct.toFixed(1)} %`
              : "ingen avtals-norm"}
            {n.avtal_code ? ` · ${n.avtal_code}` : ""}
          </div>
        </div>
        <div style={{ textAlign: "right" }}>
          <span
            className={`biz-status ${
              n.status === "completed"
                ? "delta-up"
                : n.status === "abandoned"
                ? "delta-down"
                : "open"
            }`}
          >
            {n.status === "completed"
              ? "Klart"
              : n.status === "abandoned"
              ? "Avbrutet"
              : "Aktivt"}
          </span>
          <div
            style={{
              fontFamily: "var(--mono)",
              fontSize: 10,
              color: "var(--text-mid)",
              marginTop: 4,
            }}
          >
            {n.rounds.length} / {n.max_rounds} ronder
            {n.final_pct != null
              ? ` · slutbud +${n.final_pct.toFixed(1)} %`
              : ""}
          </div>
        </div>
      </header>

      {n.teacher_summary_md && (
        <div
          style={{
            background: "rgba(99,102,241,0.06)",
            border: "1px solid rgba(99,102,241,0.3)",
            borderRadius: 4,
            padding: "10px 14px",
            marginBottom: 14,
            fontFamily: "var(--serif)",
            fontSize: 13,
            lineHeight: 1.6,
            color: "#c7d2fe",
            whiteSpace: "pre-wrap",
          }}
        >
          <div
            style={{
              fontFamily: "var(--mono)",
              fontSize: 9.5,
              letterSpacing: "1.2px",
              textTransform: "uppercase",
              color: "#a5b4fc",
              marginBottom: 4,
            }}
          >
            ● Auto-sammanfattning
          </div>
          {n.teacher_summary_md}
        </div>
      )}

      {n.rounds.length === 0 ? (
        <div
          style={{
            fontFamily: "var(--serif)",
            fontSize: 13,
            color: "var(--text-mid)",
          }}
        >
          Inga ronder ännu.
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          {n.rounds.map((r) => (
            <div key={r.round_no}>
              <div
                style={{
                  background: "rgba(220,76,43,0.08)",
                  borderLeft: "3px solid var(--accent)",
                  padding: "10px 14px",
                  borderRadius: 4,
                  marginBottom: 6,
                }}
              >
                <div
                  style={{
                    fontFamily: "var(--mono)",
                    fontSize: 9.5,
                    letterSpacing: "1.2px",
                    textTransform: "uppercase",
                    color: "var(--accent)",
                    marginBottom: 4,
                  }}
                >
                  Eleven · runda {r.round_no}
                </div>
                <p
                  style={{
                    fontFamily: "var(--serif)",
                    fontSize: 13.5,
                    lineHeight: 1.5,
                    margin: 0,
                    fontStyle: "italic",
                  }}
                >
                  {r.student_message}
                </p>
              </div>
              <div
                style={{
                  background: "rgba(251,191,36,0.06)",
                  borderLeft: "3px solid var(--warm)",
                  padding: "10px 14px",
                  borderRadius: 4,
                }}
              >
                <div
                  style={{
                    fontFamily: "var(--mono)",
                    fontSize: 9.5,
                    letterSpacing: "1.2px",
                    textTransform: "uppercase",
                    color: "var(--warm)",
                    marginBottom: 4,
                  }}
                >
                  Maria (AI) · runda {r.round_no}
                  {r.proposed_pct != null
                    ? ` · bud +${r.proposed_pct.toFixed(1)} %`
                    : ""}
                </div>
                <p
                  style={{
                    fontFamily: "var(--serif)",
                    fontSize: 13.5,
                    lineHeight: 1.5,
                    margin: 0,
                    fontStyle: "italic",
                  }}
                >
                  {r.employer_response}
                </p>
              </div>
            </div>
          ))}
        </div>
      )}
    </article>
  );
}
