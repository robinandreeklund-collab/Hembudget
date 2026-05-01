/**
 * Lärar-vy · full insyn i en elevs Bokföring (Verktyg 02).
 *
 * Använder /v2/teacher/students/{id}/bokforing-overview. Lärare ser
 * klassningsgrad + alla transaktioner per period (samma data som elev,
 * men kan inte klassa å elevens vägnar — bara observera).
 *
 * Routas via /teacher/v2/bokforing/:studentId.
 */
import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  v2Api,
  type V2TeacherBookkeepingOverview,
} from "./api";
import { V2Banner } from "./V2Banner";
import "./lan.css";

const SEK = (n: number) =>
  new Intl.NumberFormat("sv-SE", { maximumFractionDigits: 0 }).format(n);

const DATE_LABEL = (iso: string): string => {
  const d = new Date(iso);
  return d.toLocaleDateString("sv-SE", {
    day: "numeric",
    month: "short",
  });
};

function currentMonthIso(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

function buildPeriodOptions(): { value: string; label: string }[] {
  const now = new Date();
  const opts: { value: string; label: string }[] = [];
  for (let i = 0; i < 6; i++) {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
    const value = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
    const label = d.toLocaleDateString("sv-SE", {
      month: "long",
      year: "numeric",
    });
    opts.push({ value, label: label[0].toUpperCase() + label.slice(1) });
  }
  opts.push({ value: "all", label: "Hela perioden" });
  return opts;
}

export function TeacherBokforingOverviewPage() {
  const { studentId } = useParams<{ studentId: string }>();
  const sid = studentId ? parseInt(studentId, 10) : 0;
  const [data, setData] = useState<V2TeacherBookkeepingOverview | null>(
    null,
  );
  const [error, setError] = useState<string | null>(null);
  const [period, setPeriod] = useState(currentMonthIso());

  const navigate = useNavigate();

  useEffect(() => {
    if (!sid) return;
    v2Api
      .teacherBookkeepingOverview(sid, period)
      .then(setData)
      .catch((e) => setError(String((e as Error)?.message || e)));
  }, [sid, period]);

  if (error) {
    return (
      <div className="v2-lan-root">
        <V2Banner status={{ role: "teacher", is_super_admin: false }} />
        <div className="bank-loading">
          <div>
            <div style={{ color: "#fca5a5", marginBottom: 8 }}>
              Kunde inte ladda bokföring
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
        <div className="bank-loading">Laddar bokföring…</div>
      </div>
    );
  }

  const b = data.bokforing;
  const s = b.summary;

  const supportFlag =
    s.classification_rate_pct < 50 && s.total_transactions >= 5;

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
            <span className="pill warm">Lärar-vy · Bokföring</span>
            <h1 className="actor-name" style={{ marginTop: 14 }}>
              {data.student_name}s <em>klassningsgrad</em>.
            </h1>
            <p className="actor-sub">
              {s.total_transactions} transaktioner · {s.auto_classified}{" "}
              auto · {s.manual_classified} manuella ·{" "}
              {s.unclassified} ovettade ·{" "}
              {supportFlag ? (
                <strong style={{ color: "#fda594" }}>
                  ▲ behöver stöd ({s.classification_rate_pct} %)
                </strong>
              ) : (
                <span>klassningsgrad {s.classification_rate_pct} %</span>
              )}
            </p>
          </div>
          <div className="actor-meta">
            Inkomster: <strong>+ {SEK(s.income_total)} kr</strong>
            <br />
            Utgifter: <strong>− {SEK(s.expense_total)} kr</strong>
            <br />
            Sparat:{" "}
            <strong style={{ color: s.saved_total >= 0 ? "var(--warm)" : "#fda594" }}>
              {s.saved_total >= 0 ? "+" : ""} {SEK(s.saved_total)} kr ({s.saved_pct} %)
            </strong>
          </div>
        </header>

        {/* PERIOD-FILTER */}
        <div
          style={{
            display: "flex",
            gap: 10,
            alignItems: "center",
            marginBottom: 18,
            padding: "12px 16px",
            background: "rgba(15,21,37,0.7)",
            border: "1px solid var(--line)",
            borderRadius: 6,
          }}
        >
          <span
            style={{
              fontFamily: "var(--mono)",
              fontSize: 9.5,
              letterSpacing: "1.2px",
              textTransform: "uppercase",
              color: "var(--text-mid)",
            }}
          >
            Period:
          </span>
          <select
            value={period}
            onChange={(e) => setPeriod(e.target.value)}
            style={{
              background: "rgba(255,255,255,0.04)",
              border: "1px solid var(--line-strong)",
              color: "#fff",
              padding: "7px 11px",
              borderRadius: 6,
              fontFamily: "Inter, sans-serif",
              fontSize: 12.5,
            }}
          >
            {buildPeriodOptions().map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </div>

        {/* SAMMANFATTNING */}
        <div className="acct-grid">
          <div className="acct active">
            <div>
              <div className="acct-eye">Klassningsgrad</div>
              <div
                className="acct-name"
                style={{
                  color:
                    s.classification_rate_pct >= 80
                      ? "#6ee7b7"
                      : s.classification_rate_pct >= 50
                      ? "#fff"
                      : "#fda594",
                }}
              >
                {s.classification_rate_pct} %
              </div>
              <div className="acct-num">
                {s.total_transactions} totalt · {s.unclassified} ovettade
              </div>
            </div>
            <div>
              <div className="acct-bal">{s.manual_classified}</div>
              <div className="acct-bal-meta">manuella</div>
            </div>
          </div>
          <div className="acct">
            <div>
              <div className="acct-eye">Inkomster</div>
              <div
                className="acct-name"
                style={{ color: "#6ee7b7" }}
              >
                + {SEK(s.income_total)}
              </div>
              <div className="acct-num">kr {s.period_label}</div>
            </div>
            <div>
              <div className="acct-bal">{s.saved_pct} %</div>
              <div className="acct-bal-meta">sparkvot</div>
            </div>
          </div>
          <div className="acct">
            <div>
              <div className="acct-eye">Utgifter</div>
              <div className="acct-name">
                − {SEK(s.expense_total)}
              </div>
              <div className="acct-num">{b.categories.length} kategorier</div>
            </div>
            <div>
              <div className="acct-bal">{s.auto_classified}</div>
              <div className="acct-bal-meta">auto-klassade</div>
            </div>
          </div>
          <div className="acct">
            <div>
              <div className="acct-eye">Wellbeing</div>
              <div className="acct-name" style={{ color: "var(--warm)" }}>
                {s.classification_rate_pct >= 80
                  ? "+2"
                  : s.classification_rate_pct < 40 && s.total_transactions >= 5
                  ? "−1"
                  : "0"}
              </div>
              <div className="acct-num">economy</div>
            </div>
            <div>
              <div className="acct-bal">
                {s.last_classified_at
                  ? DATE_LABEL(s.last_classified_at)
                  : "—"}
              </div>
              <div className="acct-bal-meta">senast bokat</div>
            </div>
          </div>
        </div>

        <div className="act-grid">
          <div>
            {/* OVETTADE */}
            <div className="section-eye">
              Ovettade ({b.unclassified.length})
            </div>
            {b.unclassified.length === 0 ? (
              <div
                style={{
                  padding: "16px 20px",
                  border: "1px solid var(--line)",
                  borderRadius: 6,
                  fontFamily: "var(--serif)",
                  fontSize: 13,
                  color: "var(--text-mid)",
                  marginBottom: 22,
                }}
              >
                Alla transaktioner är klassade. Bra jobbat!
              </div>
            ) : (
              <div className="biz-table" style={{ marginBottom: 22 }}>
                <div
                  className="biz-table-row head"
                  style={{
                    gridTemplateColumns: "100px 1.6fr 1fr 90px",
                  }}
                >
                  <span>Datum</span>
                  <span>Beskrivning</span>
                  <span>Konto</span>
                  <span>Belopp</span>
                </div>
                {b.unclassified.slice(0, 30).map((t) => (
                  <div
                    className="biz-table-row"
                    key={t.id}
                    style={{
                      gridTemplateColumns: "100px 1.6fr 1fr 90px",
                    }}
                  >
                    <span
                      style={{ fontFamily: "var(--mono)", fontSize: 11 }}
                    >
                      {DATE_LABEL(t.date)}
                    </span>
                    <span style={{ fontFamily: "var(--serif)", fontSize: 13 }}>
                      {t.raw_description}
                    </span>
                    <span
                      style={{
                        fontFamily: "var(--mono)",
                        fontSize: 11,
                        color: "var(--text-mid)",
                      }}
                    >
                      {t.account_name}
                    </span>
                    <span
                      style={{
                        fontFamily: "var(--serif)",
                        textAlign: "right",
                      }}
                    >
                      {t.amount > 0 ? "+ " : "− "}
                      {SEK(Math.abs(t.amount))}
                    </span>
                  </div>
                ))}
              </div>
            )}

            {/* KLASSADE */}
            <div className="section-eye">
              Klassade ({b.classified.length})
            </div>
            {b.classified.length === 0 ? (
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
                Inga klassade transaktioner i {s.period_label}.
              </div>
            ) : (
              <div className="biz-table">
                <div
                  className="biz-table-row head"
                  style={{
                    gridTemplateColumns: "100px 1.4fr 1fr 80px 90px",
                  }}
                >
                  <span>Datum</span>
                  <span>Beskrivning</span>
                  <span>Kategori</span>
                  <span>Källa</span>
                  <span>Belopp</span>
                </div>
                {b.classified.slice(0, 50).map((t) => (
                  <div
                    className="biz-table-row"
                    key={t.id}
                    style={{
                      gridTemplateColumns: "100px 1.4fr 1fr 80px 90px",
                    }}
                  >
                    <span
                      style={{ fontFamily: "var(--mono)", fontSize: 11 }}
                    >
                      {DATE_LABEL(t.date)}
                    </span>
                    <span style={{ fontFamily: "var(--serif)", fontSize: 13 }}>
                      {t.raw_description}
                    </span>
                    <span
                      style={{
                        fontFamily: "var(--mono)",
                        fontSize: 11,
                        color: "var(--text-mid)",
                      }}
                    >
                      {t.category_name || "—"}
                    </span>
                    <span
                      style={{
                        fontFamily: "var(--mono)",
                        fontSize: 9,
                        color:
                          t.user_verified
                            ? "var(--warm)"
                            : "var(--text-dim)",
                        letterSpacing: "0.6px",
                        textTransform: "uppercase",
                      }}
                    >
                      {t.user_verified ? "manuell" : "auto"}
                    </span>
                    <span
                      style={{
                        fontFamily: "var(--serif)",
                        textAlign: "right",
                        color: t.amount > 0 ? "#6ee7b7" : "#fff",
                      }}
                    >
                      {t.amount > 0 ? "+ " : "− "}
                      {SEK(Math.abs(t.amount))}
                    </span>
                  </div>
                ))}
                {b.classified.length > 50 && (
                  <div
                    style={{
                      textAlign: "center",
                      padding: 12,
                      fontFamily: "var(--mono)",
                      fontSize: 10,
                      color: "var(--text-dim)",
                    }}
                  >
                    + {b.classified.length - 50} transaktioner till
                  </div>
                )}
              </div>
            )}
          </div>

          <aside>
            {supportFlag && (
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
                  ▲ Behöver stöd
                </div>
                <div className="side-card-h">
                  Klassningsgrad <em>{s.classification_rate_pct} %</em>
                </div>
                <div className="side-card-meta">
                  Under 50 % betyder eleven inte tittar på sina pengar.
                  Pratstund? Be eleven öppna /v2/bokforing och klicka
                  "Klassa alla X (AI)" — regelmotorn fixar 70-80 %.
                </div>
              </div>
            )}
            <div className="side-card">
              <div className="side-card-eye">Wellbeing-effekt</div>
              <div className="side-card-h">
                Klassning <em>räknas</em>
              </div>
              <div className="side-card-meta">
                Klassningsgrad ≥ 80 % → +2 economy. Under 40 % (med ≥ 5
                txs) → −1 economy. Pedagogiskt: "att se sina pengar"
                räknas som ekonomisk styrka.
              </div>
            </div>
            <div className="side-card">
              <div className="side-card-eye">Pedagogiskt syfte</div>
              <div className="side-card-h">
                Ovettade är <em>spegeln</em>
              </div>
              <div className="side-card-meta">
                När eleven själv väljer "Mat" eller "Restaurang" på 312
                kr Coop, sker självreflektion. Inte alla transaktioner
                ska automatiseras — det är poängen att eleven gör några
                själv.
              </div>
            </div>
          </aside>
        </div>
      </div>
    </div>
  );
}
