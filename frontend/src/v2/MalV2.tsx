/**
 * V2 Sparmål · matchar /proposals/vol-7/elev.html#p-mal EXAKT.
 *
 * Layout (samma som prototypen):
 *   1. .actor-back tillbaka-länk → /v2/hub
 *   2. .actor-head · "Verktyg 04 · Mål & sparande"-pill +
 *      actor-name "N mål — räkningar till dig själv" + sub +
 *      actor-meta (Totalt sparat / Mål-värde / Avsätter/mån)
 *   3. .mal-strip · 4 nyckeltal (sparat/mål/snitt-progress/pace)
 *   4. .cc-summary · grid med ett .cc-stat-kort per mål med:
 *      eye + status-tag + cc-stat-num (current/target) + sub +
 *      progress-bar (färg från goal.color)
 *   5. .peda · pedagogik-block med 4 bullets + 5 koncept-pills + tip
 *
 * All data hämtas via /v2/mal — riktiga Goal-rader från scope-DB.
 */
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { v2Api, type GoalsData, type V2GoalRow } from "./api";
import { V2Banner } from "./V2Banner";
import "./mal.css";

const SEK = (n: number) =>
  new Intl.NumberFormat("sv-SE", { maximumFractionDigits: 0 }).format(n);

const SHORT_DATE = (iso: string | null): string => {
  if (!iso) return "ingen deadline";
  const d = new Date(iso);
  return d.toLocaleDateString("sv-SE", {
    month: "short",
    year: "numeric",
  });
};

function statusLabel(s: V2GoalRow["status"]): string {
  switch (s) {
    case "complete":
      return "klart";
    case "ahead":
      return "ligger före";
    case "on_track":
      return "i tid";
    case "behind":
      return "ligger efter";
    case "new":
      return "nystartat";
    default:
      return s;
  }
}

export function MalV2() {
  const [goals, setGoals] = useState<GoalsData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    v2Api
      .goals()
      .then(setGoals)
      .catch((e) => setError(String((e as Error)?.message || e)));
  }, []);

  if (error) {
    return (
      <div className="v2-mal-root">
        <V2Banner status={{ role: "student", is_super_admin: false }} />
        <div className="bank-loading">
          <div>
            <div style={{ color: "#fca5a5", marginBottom: 8 }}>
              Kunde inte ladda mål-data
            </div>
            <pre style={{ fontSize: 11 }}>{error}</pre>
          </div>
        </div>
      </div>
    );
  }
  if (!goals) {
    return (
      <div className="v2-mal-root">
        <V2Banner status={{ role: "student", is_super_admin: false }} />
        <div className="bank-loading">Laddar mål-data…</div>
      </div>
    );
  }

  const { summary, goals: rows } = goals;
  const count = rows.length;

  return (
    <div className="v2-mal-root">
      <V2Banner status={{ role: "student", is_super_admin: false }} />

      <div className="shell">
        <a
          className="actor-back"
          onClick={(e) => {
            e.preventDefault();
            navigate("/v2/hub");
          }}
          href="#"
        >
          Tillbaka till pentagonen
        </a>

        <header className="actor-head">
          <div>
            <span className="pill">Verktyg 04 · Mål &amp; sparande</span>
            <h1 className="actor-name" style={{ marginTop: 14 }}>
              {count === 0 ? (
                <>Inga mål än — <em>räkningar till dig själv</em>.</>
              ) : (
                <>
                  {count} mål — <em>räkningar till dig själv</em>.
                </>
              )}
            </h1>
            <p className="actor-sub">
              {count === 0
                ? "Buffert · körkort · interrail · kontantinsats — sparmål är åtaganden, inte rester"
                : "Sparmål är inte rest, det är åtagande · pay yourself first"}
            </p>
          </div>
          <div className="actor-meta">
            Totalt sparat: <strong>{SEK(summary.total_saved)} kr</strong>
            <br />
            Mål-värde: <strong>{SEK(summary.total_target)} kr</strong>
            <br />
            Avsätter/mån:{" "}
            <strong>{SEK(summary.monthly_pace_total)} kr</strong>
          </div>
        </header>

        {/* SUMMARY-STRIPE */}
        <div className="mal-strip">
          <div className="mal-strip-cell">
            <div className="mal-strip-eye">Antal mål</div>
            <div className="mal-strip-num">
              <em>{summary.goals_count}</em>
            </div>
            <div className="mal-strip-sub">
              {summary.on_track_count} i tid · {summary.behind_count} efter
            </div>
          </div>
          <div className="mal-strip-cell">
            <div className="mal-strip-eye">Snittprogress</div>
            <div className="mal-strip-num">
              {summary.overall_progress_pct.toFixed(1)} %
            </div>
            <div className="mal-strip-sub">av totalt mål-värde</div>
          </div>
          <div className="mal-strip-cell">
            <div className="mal-strip-eye">Sparat</div>
            <div className="mal-strip-num">{SEK(summary.total_saved)} kr</div>
            <div className="mal-strip-sub">
              av {SEK(summary.total_target)} kr
            </div>
          </div>
          <div className="mal-strip-cell">
            <div className="mal-strip-eye">Behov/mån</div>
            <div className="mal-strip-num">
              {SEK(summary.monthly_pace_total)} kr
            </div>
            <div className="mal-strip-sub">för att hinna deadlines</div>
          </div>
        </div>

        {/* GOAL-CARDS */}
        {rows.length === 0 ? (
          <div
            style={{
              padding: "32px 28px",
              border: "1px solid var(--line)",
              borderRadius: 6,
              fontFamily: "var(--serif)",
              color: "var(--text-mid)",
              marginBottom: 22,
            }}
          >
            Inga sparmål än. Lägg till buffert (3 mån-hyror), körkort,
            kontantinsats — vad du sparar för. Sparmål blir räkningar i
            bokföringen.
          </div>
        ) : (
          <div className="cc-summary">
            {rows.map((g) => {
              const remaining = Math.max(0, g.target_amount - g.current_amount);
              const widthPct = Math.min(100, Math.max(0, g.progress_pct));
              const dl = SHORT_DATE(g.target_date);
              const paceText =
                g.monthly_pace_target != null && g.monthly_pace_target > 0
                  ? `· ${SEK(g.monthly_pace_target)}/mån för deadline`
                  : "";
              const completeText = g.status === "complete" ? "✓ klart" : "";

              return (
                <article
                  key={g.id}
                  className="cc-stat bordered"
                  style={{
                    borderLeftColor: g.color,
                    background:
                      g.status === "complete"
                        ? "rgba(110,231,183,0.06)"
                        : g.status === "behind"
                        ? "rgba(220,76,43,0.06)"
                        : "rgba(255,255,255,0.04)",
                  }}
                >
                  <div
                    className="cc-stat-eye"
                    style={{ color: g.color }}
                  >
                    {g.icon} {g.name}
                    <span className={`status-tag ${g.status}`}>
                      {statusLabel(g.status)}
                    </span>
                  </div>
                  <div className="cc-stat-num">
                    <em>{SEK(g.current_amount)}</em>
                    <span style={{ fontSize: 14, color: "var(--text-mid)" }}>
                      /{SEK(g.target_amount)} kr
                    </span>
                  </div>
                  <div className="cc-stat-sub">
                    {g.progress_pct.toFixed(1)} % {completeText}
                    {!completeText && remaining > 0 && (
                      <> · {SEK(remaining)} kr kvar</>
                    )}
                    {g.target_date && <> · klar {dl}</>}
                    {paceText && <> {paceText}</>}
                    {g.account_name && <> · på {g.account_name}</>}
                  </div>
                  <div className="goal-bar">
                    <div
                      className="goal-bar-fill"
                      style={{
                        width: `${widthPct}%`,
                        background: g.color,
                      }}
                    />
                  </div>
                </article>
              );
            })}
          </div>
        )}

        {/* PEDAGOGIK */}
        <div className="peda">
          <div className="peda-eye">Pedagogik · vad du lär dig här</div>
          <div className="peda-h">
            Sparmål blir <em>räkningar</em> i bokföringen.
          </div>
          <p className="peda-prose">
            När du sätter ett mål på 600 kr/mån till buffert dyker det upp som
            planerad utgående överföring i banken — likställd med hyra och el.
            I budgeten som egen rad. <em>Sparande är inte rest, det är
            åtagande.</em> Den här filosofin är "pay yourself first" — du är
            din viktigaste leverantör.
          </p>
          <ul className="peda-bullets">
            <li className="peda-bullet">
              <strong>Buffert</strong>Riktvärde: 3 mån-hyror. Att klara
              oförutsett.
            </li>
            <li className="peda-bullet">
              <strong>Sparmål</strong>Konkret · deadline · belopp. Annars
              fluff.
            </li>
            <li className="peda-bullet">
              <strong>Pay yourself first</strong>Drag spar-överföring direkt
              vid lön.
            </li>
            <li className="peda-bullet">
              <strong>Kontantinsats</strong>15 % av bostadens värde. För 1,2
              Mkr-bo: 180 000.
            </li>
          </ul>
          <div className="peda-concepts">
            <span className="peda-concept">Buffert</span>
            <span className="peda-concept">Pay yourself first</span>
            <span className="peda-concept">SMART-mål</span>
            <span className="peda-concept">Tidshorisont</span>
            <span className="peda-concept">Likviditetsreserv</span>
          </div>
          <div className="peda-tip">
            {summary.behind_count > 0
              ? `Echo: "${summary.behind_count} mål ligger efter. Vad händer om bilen behövs lagas eller du blir sjuk innan bufferten är klar?" Det är reflektionsfrågan som tvingar prioritering.`
              : summary.goals_count === 0
              ? `Echo: "Du har inga mål än — och det är OK. Men utan deadline blir sparande ofta rest. Sätt ett första: buffert på 3 mån-hyror."`
              : `Echo: "Hur mycket är 600 kr/mån till buffert värt nästa kris? Sparande för det oförutsedda är osynligt — tills det räddar dig."`}
          </div>
        </div>
      </div>
    </div>
  );
}
