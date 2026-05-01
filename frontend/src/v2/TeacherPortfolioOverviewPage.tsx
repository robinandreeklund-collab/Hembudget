/**
 * Lärar-vy · elevens kompetens-portfolio.
 *
 * Routas via /teacher/v2/portfolio/:studentId.
 */
import { useEffect, useState } from "react";
import { Link, useParams, useNavigate } from "react-router-dom";
import {
  v2Api,
  type V2TeacherPortfolioOverview,
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

export function TeacherPortfolioOverviewPage() {
  const { studentId } = useParams<{ studentId: string }>();
  const sid = studentId ? parseInt(studentId, 10) : 0;
  const [data, setData] = useState<V2TeacherPortfolioOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    if (!sid) return;
    v2Api
      .teacherPortfolioOverview(sid)
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
              Kunde inte ladda portfolio
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
        <div className="bank-loading">Laddar portfolio…</div>
      </div>
    );
  }

  const p = data.portfolio;
  const s = p.summary;
  const wellbeingHealth =
    s.fordjup_count >= 5 ? "+3" : s.fordjup_count >= 2 ? "+1" : "0";

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
          Tillbaka till v2-rostern
        </a>

        <header className="actor-head">
          <div>
            <span className="pill warm">Lärar-vy · Portfolio</span>
            <h1 className="actor-name" style={{ marginTop: 14 }}>
              {data.student_name}s <em>kompetens-karta</em>.
            </h1>
            <p className="actor-sub">
              {s.total_competencies} kompetenser · {s.basis_count} B ·{" "}
              {s.grund_count} G ·{" "}
              <strong style={{ color: "#6ee7b7" }}>
                {s.fordjup_count} F
              </strong>{" "}
              · senaste händelse {SHORT_DATE(s.last_event_at)}
            </p>
          </div>
          <div className="actor-meta">
            Wellbeing-bonus:{" "}
            <strong style={{ color: "var(--warm)" }}>
              {wellbeingHealth} health
            </strong>
            <br />
            Mastery: <strong>algoritm + lärar-höjning</strong>
            <br />
            Sparas i portfolio
          </div>
        </header>

        {/* SAMMANFATTNING */}
        <div className="acct-grid">
          <div className="acct active">
            <div>
              <div className="acct-eye">BASIS</div>
              <div className="acct-name">{s.basis_count}</div>
              <div className="acct-num">grundläggande nivå</div>
            </div>
            <div>
              <div className="acct-bal">B</div>
              <div className="acct-bal-meta">&lt; 33 % mastery</div>
            </div>
          </div>
          <div className="acct">
            <div>
              <div className="acct-eye">GRUND</div>
              <div
                className="acct-name"
                style={{ color: "var(--accent)" }}
              >
                {s.grund_count}
              </div>
              <div className="acct-num">applicerar självständigt</div>
            </div>
            <div>
              <div className="acct-bal">G</div>
              <div className="acct-bal-meta">33–66 % mastery</div>
            </div>
          </div>
          <div className="acct">
            <div>
              <div className="acct-eye">FÖRDJUPNING</div>
              <div
                className="acct-name"
                style={{ color: "#6ee7b7" }}
              >
                {s.fordjup_count}
              </div>
              <div className="acct-num">reflekterar + lär ut</div>
            </div>
            <div>
              <div
                className="acct-bal"
                style={{ color: "#6ee7b7" }}
              >
                F
              </div>
              <div className="acct-bal-meta">≥ 66 % mastery</div>
            </div>
          </div>
          <div className="acct">
            <div>
              <div className="acct-eye">Wellbeing-effekt</div>
              <div
                className="acct-name"
                style={{ color: "var(--warm)" }}
              >
                {wellbeingHealth}
              </div>
              <div className="acct-num">health (självkänsla)</div>
            </div>
            <div>
              <div className="acct-bal">{s.total_competencies}</div>
              <div className="acct-bal-meta">totalt</div>
            </div>
          </div>
        </div>

        <div className="section-eye">
          {p.competencies.length} kompetenser · sorterat på nivå
        </div>
        {p.competencies.length === 0 ? (
          <div
            style={{
              padding: "20px 24px",
              border: "1px solid var(--line)",
              borderRadius: 6,
              fontFamily: "var(--serif)",
              color: "var(--text-mid)",
            }}
          >
            Inga kompetenser registrerade än.
          </div>
        ) : (
          <div className="biz-table">
            <div
              className="biz-table-row head"
              style={{
                gridTemplateColumns: "36px 1.4fr 110px 90px 1fr 110px",
              }}
            >
              <span></span>
              <span>Kompetens</span>
              <span>Nivå</span>
              <span>Mastery</span>
              <span>Senaste händelse</span>
              <span>Steg klara</span>
            </div>
            {p.competencies.map((c) => (
              <Link
                key={c.competency_id}
                to={`/teacher/v2/kompetens/${sid}/${c.competency_id}`}
                className="biz-table-row"
                style={{
                  gridTemplateColumns: "36px 1.4fr 110px 90px 1fr 110px",
                  textDecoration: "none",
                  color: "inherit",
                }}
              >
                <span
                  style={{
                    fontFamily: "var(--mono)",
                    fontSize: 11,
                    fontWeight: 700,
                    color: LEVEL_COLOR[c.level],
                  }}
                >
                  {c.level}
                </span>
                <div>
                  <div
                    style={{
                      fontFamily: "var(--serif)",
                      fontSize: 14,
                    }}
                  >
                    {c.name}
                  </div>
                  <div
                    style={{
                      fontFamily: "var(--mono)",
                      fontSize: 9,
                      color: "var(--text-dim)",
                    }}
                  >
                    {c.is_system ? "system" : "lärar-egen"} · key:{" "}
                    {c.key}
                  </div>
                </div>
                <span
                  style={{
                    fontFamily: "var(--mono)",
                    fontSize: 9.5,
                    color: LEVEL_COLOR[c.level],
                    fontWeight: 700,
                  }}
                >
                  {c.level_label}
                </span>
                <span
                  style={{
                    fontFamily: "var(--mono)",
                    fontSize: 11,
                  }}
                >
                  {Math.round(c.mastery * 100)} %
                </span>
                <span
                  style={{
                    fontSize: 12,
                    color: "var(--text-mid)",
                  }}
                >
                  {SHORT_DATE(c.last_event_at)}
                </span>
                <span
                  style={{
                    fontFamily: "var(--mono)",
                    fontSize: 11,
                    color: "var(--text-mid)",
                  }}
                >
                  {c.completed_steps} st
                </span>
              </Link>
            ))}
          </div>
        )}

        <div className="peda" style={{ marginTop: 22 }}>
          <div className="peda-eye">Pedagogik · vad du ser här</div>
          <div className="peda-h">
            Mastery är <em>algoritm</em> — du gör <em>höjningen</em>.
          </div>
          <p className="peda-prose">
            Mastery beräknas auto från modul-steg klar × steg-vikt mot
            kompetensen. Men nivå-höjningar (B → G → F) görs manuellt av
            dig som lärare när du ser kvalitet i elevens arbete.
            Algoritmen ger en indikator — du gör bedömningen.
          </p>
          <div className="peda-tip">
            Wellbeing-koppling: 5+ FÖRDJUPNING → +3 health. 2-4 → +1
            health. Eleven ser detta i sin pentagon.
          </div>
        </div>
      </div>
    </div>
  );
}
