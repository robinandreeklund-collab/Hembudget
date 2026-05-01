/**
 * Lärar-vy · alla elevens BankID-signeringar.
 *
 * Visar varje session med beloppen, varaktighet, status. Pedagogiskt
 * intressant: snabb signering = "fingret fick inte veta", avbrutna =
 * eleven läste och tänkte.
 */
import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  v2Api,
  type V2TeacherBankIDOverview,
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

export function TeacherBankIDOverviewPage() {
  const { studentId } = useParams<{ studentId: string }>();
  const sid = studentId ? parseInt(studentId, 10) : 0;
  const [data, setData] = useState<V2TeacherBankIDOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    if (!sid) return;
    v2Api
      .teacherBankIDOverview(sid)
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
              Kunde inte ladda BankID-data
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
        <div className="bank-loading">Laddar BankID-historik…</div>
      </div>
    );
  }

  const b = data.bankid;
  const rushedSessions = b.sessions.filter(
    (s) =>
      s.status === "signed" &&
      s.duration_seconds != null &&
      s.duration_seconds < 5,
  );
  const rushFlag = rushedSessions.length >= 2;

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
            <span className="pill warm">Lärar-vy · BankID-signeringar</span>
            <h1 className="actor-name" style={{ marginTop: 14 }}>
              {data.student_name}s <em>signerings-historik</em>.
            </h1>
            <p className="actor-sub">
              {b.sessions.length} sessioner · {b.signed_count} signerade ·{" "}
              {b.cancelled_count} avbrutna ·{" "}
              {rushFlag ? (
                <strong style={{ color: "#fda594" }}>
                  ▲ {rushedSessions.length} snabb-signeringar (&lt; 5
                  sek)
                </strong>
              ) : (
                "läser sammandragen"
              )}
            </p>
          </div>
          <div className="actor-meta">
            Signerat: <strong>{SEK(b.total_signed_amount)} kr</strong>
            <br />
            Pending: <strong>{b.pending_count}</strong>
            <br />
            Avbrutna: <strong>{b.cancelled_count}</strong>
          </div>
        </header>

        {/* SAMMANFATTNING */}
        <div className="acct-grid">
          <div className="acct active">
            <div>
              <div className="acct-eye">Signerade</div>
              <div className="acct-name">{b.signed_count}</div>
              <div className="acct-num">av {b.sessions.length} totalt</div>
            </div>
            <div>
              <div className="acct-bal">{SEK(b.total_signed_amount)}</div>
              <div className="acct-bal-meta">kr signerat</div>
            </div>
          </div>
          <div className="acct">
            <div>
              <div className="acct-eye">Pending</div>
              <div
                className="acct-name"
                style={{ color: b.pending_count > 0 ? "var(--warm)" : "#fff" }}
              >
                {b.pending_count}
              </div>
              <div className="acct-num">väntar på signering</div>
            </div>
            <div>
              <div className="acct-bal">{b.cancelled_count}</div>
              <div className="acct-bal-meta">avbrutna</div>
            </div>
          </div>
          <div className="acct">
            <div>
              <div className="acct-eye">Snabb-signeringar</div>
              <div
                className="acct-name"
                style={{
                  color: rushFlag ? "#fda594" : "#6ee7b7",
                }}
              >
                {rushedSessions.length}
              </div>
              <div className="acct-num">
                &lt; 5 sek · "fingret fick inte veta"
              </div>
            </div>
            <div>
              <div className="acct-bal">
                {b.signed_count > 0
                  ? Math.round(
                      b.sessions
                        .filter(
                          (s) =>
                            s.status === "signed" &&
                            s.duration_seconds != null,
                        )
                        .reduce(
                          (acc, s) => acc + (s.duration_seconds || 0),
                          0,
                        ) / Math.max(1, b.signed_count),
                    )
                  : "—"}
              </div>
              <div className="acct-bal-meta">snitt-tid sek</div>
            </div>
          </div>
          <div className="acct">
            <div>
              <div className="acct-eye">Wellbeing-effekt</div>
              <div
                className="acct-name"
                style={{
                  color:
                    b.signed_count >= 1
                      ? "var(--warm)"
                      : "var(--text-mid)",
                }}
              >
                {b.signed_count >= 1 ? "+2" : "0"}
              </div>
              <div className="acct-num">economy</div>
            </div>
            <div>
              <div
                className="acct-bal"
                style={{ color: rushFlag ? "#fda594" : "#fff" }}
              >
                {rushFlag ? "−1" : "0"}
              </div>
              <div className="acct-bal-meta">safety (rushed)</div>
            </div>
          </div>
        </div>

        <div className="act-grid">
          <div>
            <div className="section-eye">
              Sessioner ({b.sessions.length})
            </div>
            {b.sessions.length === 0 ? (
              <div
                style={{
                  padding: "16px 20px",
                  border: "1px solid var(--line)",
                  borderRadius: 6,
                  fontFamily: "var(--serif)",
                  fontSize: 13,
                  color: "var(--text-mid)",
                }}
              >
                Eleven har inte startat någon BankID-session än.
              </div>
            ) : (
              <div className="biz-table">
                <div
                  className="biz-table-row head"
                  style={{
                    gridTemplateColumns:
                      "100px 60px 110px 80px 100px 90px",
                  }}
                >
                  <span>Datum</span>
                  <span>#</span>
                  <span>Belopp</span>
                  <span>Tid</span>
                  <span>Steg</span>
                  <span>Status</span>
                </div>
                {b.sessions.map((sess) => (
                  <div
                    className="biz-table-row"
                    key={sess.id}
                    style={{
                      gridTemplateColumns:
                        "100px 60px 110px 80px 100px 90px",
                    }}
                  >
                    <span
                      style={{
                        fontFamily: "var(--mono)",
                        fontSize: 11,
                        color: "var(--text-mid)",
                      }}
                    >
                      {SHORT_DATE(sess.created_at)}
                    </span>
                    <span style={{ fontFamily: "var(--mono)", fontSize: 11 }}>
                      {sess.invoice_count}
                    </span>
                    <span
                      style={{
                        fontFamily: "var(--mono)",
                        fontSize: 12,
                      }}
                    >
                      {SEK(sess.total_amount)} kr
                    </span>
                    <span
                      style={{
                        fontFamily: "var(--mono)",
                        fontSize: 11,
                        color:
                          sess.duration_seconds != null &&
                          sess.duration_seconds < 5
                            ? "#fda594"
                            : "var(--text-mid)",
                      }}
                    >
                      {sess.duration_seconds != null
                        ? `${sess.duration_seconds}s`
                        : "—"}
                    </span>
                    <span style={{ fontFamily: "var(--mono)", fontSize: 11 }}>
                      {sess.current_step}/6
                    </span>
                    <span
                      className={`biz-status ${
                        sess.status === "signed"
                          ? "delta-up"
                          : sess.status === "cancelled"
                          ? "delta-down"
                          : "open"
                      }`}
                    >
                      {sess.status === "signed"
                        ? "Signerat"
                        : sess.status === "cancelled"
                        ? "Avbrutet"
                        : "Pending"}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>

          <aside>
            {rushFlag && (
              <div
                className="side-card"
                style={{
                  background: "rgba(220,76,43,0.06)",
                  borderColor: "rgba(220,76,43,0.25)",
                }}
              >
                <div
                  className="side-card-eye"
                  style={{ color: "var(--accent)" }}
                >
                  ▲ Snabb-signering
                </div>
                <div className="side-card-h">
                  {rushedSessions.length} sessioner &lt; 5 sek
                </div>
                <div className="side-card-meta">
                  Eleven trycker bara enter utan att läsa sammandraget.
                  Pedagogiskt: pratstund om "vad signerar du"-medvetenhet.
                  Kanske öppna en signering tillsammans?
                </div>
              </div>
            )}
            <div className="side-card">
              <div className="side-card-eye">Wellbeing-effekt</div>
              <div className="side-card-h">
                Signering <em>räknas</em>
              </div>
              <div className="side-card-meta">
                1+ signerad session senaste 90 dgr → +2 economy
                ("autogiro-flöde aktivt"). 2+ snabb-signeringar
                (&lt; 5 sek) → -1 safety ("fingret fick inte veta").
                Avbrutna sessioner = hälsosam vana, ingen impact.
              </div>
            </div>
            <div className="side-card">
              <div className="side-card-eye">Pedagogiskt syfte</div>
              <div className="side-card-h">
                Friktion <em>är poängen</em>
              </div>
              <div className="side-card-meta">
                BankID:s 6 steg är inte i vägen — det är muskel-
                träning. Vana vuxna har lärt sig att stanna upp och
                läsa innan PIN. Vi tränar samma vana här.
              </div>
            </div>
          </aside>
        </div>
      </div>
    </div>
  );
}
