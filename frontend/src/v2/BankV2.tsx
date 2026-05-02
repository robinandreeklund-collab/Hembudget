/**
 * V2 Bank · matchar /proposals/vol-7/elev.html#p-bank EXAKT.
 *
 * Layout (samma som prototypen):
 *   1. .actor-back tillbaka-länk
 *   2. .actor-head · pill + actor-name + actor-sub + actor-meta (BankID + signerade + kreditgräns)
 *   3. .acct-grid · alla konton som klickbara kort
 *   4. .act-grid (1.4fr 1fr):
 *       MAIN:
 *         - .cta-card · "Signera N fakturor via BankID"
 *         - .section-eye + .tx-list · senaste händelser
 *         - .section-eye + .biz-table · kommande dragningar
 *         - .peda · pedagogik-block med bullets + concepts + tip
 *       ASIDE:
 *         - 3 .side-card med kommande/tandläkare/kreditprövning
 *
 * All data hämtas via /v2/bank · ingen mock.
 */
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { v2Api, type BankData } from "./api";
import { V2Banner } from "./V2Banner";
import "./bank.css";

const SEK = (n: number) =>
  new Intl.NumberFormat("sv-SE", { maximumFractionDigits: 0 }).format(n);

const SHORT_DATE = (iso: string) => {
  const d = new Date(iso);
  return d.toLocaleDateString("sv-SE", { day: "numeric", month: "short" });
};

const DAYS_UNTIL = (iso: string) => {
  const d = new Date(iso);
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return Math.round((d.getTime() - today.getTime()) / (1000 * 60 * 60 * 24));
};

// Mappar account.type → svensk eyebrow-text för acct-card
const TYPE_EYE: Record<string, string> = {
  checking: "Lönekonto",
  savings: "Sparkonto",
  isk: "ISK · investering",
  credit: "Kreditkort",
  loan: "Lån",
};

export function BankV2() {
  const [bank, setBank] = useState<BankData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    v2Api
      .bank(40)
      .then(setBank)
      .catch((e) => setError(String((e as Error)?.message || e)));
  }, []);

  if (error) {
    return (
      <div className="v2-bank-root">
        <V2Banner status={{ role: "student", is_super_admin: false }} />
        <div className="bank-loading">
          <div>
            <div style={{ color: "#fca5a5", marginBottom: 8 }}>
              Kunde inte ladda bank-data
            </div>
            <pre style={{ fontSize: 11 }}>{error}</pre>
          </div>
        </div>
      </div>
    );
  }
  if (!bank) {
    return (
      <div className="v2-bank-root">
        <V2Banner status={{ role: "student", is_super_admin: false }} />
        <div className="bank-loading">Laddar bank-data…</div>
      </div>
    );
  }

  const { summary, accounts, recent_transactions, upcoming_bills } = bank;
  const accCount = accounts.length;
  const openBills = upcoming_bills.filter((b) => !b.is_paid);
  const billsToSign = openBills.length;

  // Hitta första akuta open-faktura för aside · "Tandläkaren idag"-kortet
  const urgentBill = openBills.find((b) => DAYS_UNTIL(b.expected_date) <= 7);
  const nextScheduled = openBills[0];

  return (
    <div className="v2-bank-root">
      <V2Banner status={{ role: "student", is_super_admin: false }} />

      <div className="shell" data-guide="bank-accounts">
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
            <span className="pill warm">Aktör 01 · Banken</span>
            <h1 className="actor-name" style={{ marginTop: 14 }}>
              Banken — <em>{accCount === 1 ? "ett konto" : `${accCount} konton`}</em>,{" "}
              ett dygn att signera.
            </h1>
            <p className="actor-sub">
              {accounts[0]?.bank || "Banken"} · privatkund · konton synkade just nu
            </p>
          </div>
          <div className="actor-meta">
            Inloggad via <strong>BankID</strong>
            <br />
            Signerade fakturor i kö: <strong>{billsToSign} st</strong>
            <br />
            Totalt saldo: <strong>{SEK(summary.total_balance)} kr</strong>
          </div>
        </header>

        {/* 4 konton som klickbara kort */}
        {accounts.length === 0 ? (
          <div
            style={{
              padding: "32px 24px",
              border: "1px solid var(--line)",
              borderRadius: 6,
              fontFamily: "var(--serif)",
              color: "var(--text-mid)",
              marginBottom: 26,
            }}
          >
            Inga konton än. Lärare seedar via lärar-vyn → kontoutdrag.
          </div>
        ) : (
          <div className="acct-grid">
            {accounts.map((a) => {
              const eye = TYPE_EYE[a.type] || a.type;
              const isCredit = a.type === "credit";
              const balance = a.total_value;
              return (
                <a key={a.id} className="acct" href="#">
                  <div>
                    <div className="acct-eye">{eye}</div>
                    <div className="acct-name">{a.name}</div>
                    {a.account_number && (
                      <div className="acct-num">{a.account_number}</div>
                    )}
                  </div>
                  <div>
                    <div
                      className="acct-bal"
                      style={
                        isCredit && balance < 0
                          ? { color: "#fca5a5" }
                          : undefined
                      }
                    >
                      {balance >= 0 && !isCredit ? (
                        <em>{SEK(balance)}</em>
                      ) : (
                        SEK(balance)
                      )}{" "}
                      kr
                    </div>
                    <div className="acct-bal-meta">
                      {a.fund_value > 0
                        ? `cash ${SEK(a.current_balance)} · fond ${SEK(
                            a.fund_value,
                          )}`
                        : a.bank}
                    </div>
                  </div>
                </a>
              );
            })}
          </div>
        )}

        <div className="act-grid">
          <div>
            {/* CTA: signera fakturor */}
            {billsToSign > 0 && (
              <article className="cta-card">
                <div className="cta-eye">Att signera</div>
                <div className="cta-h">
                  Signera <em>{billsToSign} fakturor</em> via BankID.
                </div>
                <p className="cta-prose">
                  Bankgirot har samlat dina inkommande fakturor. Vissa är vanor
                  som redan klassificerats (hyra, el, abonnemang), andra är nya
                  och kräver ditt val. Signera alla på en gång, eller hantera de
                  nya manuellt.
                </p>
                <button className="cta-btn" type="button">
                  Öppna BankID-signering →
                </button>
              </article>
            )}

            {/* Senaste händelser */}
            <div className="section-eye">Senaste händelser</div>
            {recent_transactions.length === 0 ? (
              <div
                style={{
                  padding: "20px",
                  border: "1px solid var(--line)",
                  borderRadius: 6,
                  fontFamily: "var(--serif)",
                  color: "var(--text-mid)",
                }}
              >
                Inga transaktioner än. Saldot uppdateras när läraren seedar
                månadsdata.
              </div>
            ) : (
              <div className="tx-list">
                {recent_transactions.slice(0, 12).map((t) => {
                  const isIncome = t.amount > 0;
                  return (
                    <div className="tx-row" key={t.id}>
                      <span className="tx-date">{SHORT_DATE(t.date)}</span>
                      <div>
                        <div className="tx-name">
                          {t.merchant || t.description}
                        </div>
                        <div className="tx-name-sub">{t.account_name}</div>
                      </div>
                      <span
                        className={`tx-cat${
                          t.category_id == null ? " unset" : ""
                        }`}
                      >
                        {t.category_id == null
                          ? "Okatt"
                          : t.is_transfer
                          ? "Överf."
                          : "Klassad"}
                      </span>
                      <span className={`tx-amt${isIncome ? " in" : ""}`}>
                        {isIncome ? (
                          <em>+ {SEK(t.amount)}</em>
                        ) : (
                          `− ${SEK(Math.abs(t.amount))}`
                        )}{" "}
                        kr
                      </span>
                    </div>
                  );
                })}
              </div>
            )}
            {recent_transactions.length > 12 && (
              <div
                style={{
                  fontFamily: "var(--mono)",
                  fontSize: 10,
                  color: "var(--text-dim)",
                  marginTop: 12,
                  letterSpacing: 0.6,
                  textTransform: "uppercase",
                }}
              >
                + {recent_transactions.length - 12} fler transaktioner i
                listan ·{" "}
                {recent_transactions.filter((t) => t.category_id == null).length}{" "}
                ovettade
              </div>
            )}

            {/* Kommande dragningar · biz-table */}
            <div className="section-eye" style={{ marginTop: 32 }}>
              Kommande dragningar &amp; betalningar
            </div>
            {upcoming_bills.length === 0 ? (
              <div
                style={{
                  padding: "20px",
                  border: "1px solid var(--line)",
                  borderRadius: 6,
                  fontFamily: "var(--serif)",
                  color: "var(--text-mid)",
                }}
              >
                Inga kommande fakturor framåt i tiden. Postlådan triggar nya.
              </div>
            ) : (
              <div className="biz-table">
                <div
                  className="biz-table-row head"
                  style={{
                    gridTemplateColumns:
                      "32px 1.8fr 110px 110px 110px",
                  }}
                >
                  <span></span>
                  <span>Mottagare</span>
                  <span>Belopp</span>
                  <span>Datum</span>
                  <span>Status</span>
                </div>
                {upcoming_bills.map((u) => {
                  const days = DAYS_UNTIL(u.expected_date);
                  const overdue = !u.is_paid && days < 0;
                  const urgent = !u.is_paid && days >= 0 && days <= 3;
                  const dotColor = overdue
                    ? "#dc4c2b"
                    : urgent
                    ? "var(--warm)"
                    : "var(--accent)";
                  const statusClass = u.is_paid
                    ? "paid"
                    : overdue
                    ? "overdue"
                    : urgent
                    ? "open"
                    : "sent";
                  const statusText = u.is_paid
                    ? "Betald"
                    : overdue
                    ? `${Math.abs(days)} d sen`
                    : urgent
                    ? "Bestäm"
                    : "Schemalagd";
                  return (
                    <a
                      key={u.id}
                      className="biz-table-row"
                      style={{
                        gridTemplateColumns:
                          "32px 1.8fr 110px 110px 110px",
                        ...(urgent || overdue
                          ? {
                              background: "rgba(220,76,43,0.06)",
                              borderLeft: "3px solid var(--warm)",
                            }
                          : {}),
                      }}
                      href="#"
                    >
                      <span
                        style={{
                          width: 8,
                          height: 8,
                          borderRadius: "50%",
                          background: dotColor,
                        }}
                      ></span>
                      <div>
                        <div
                          style={{
                            fontFamily: "var(--serif)",
                            fontSize: 14,
                            color: "#fff",
                            fontWeight: 700,
                          }}
                        >
                          {u.name}
                          {u.kind === "income" && (
                            <em
                              style={{
                                color: "#6ee7b7",
                                fontSize: 10,
                                marginLeft: 8,
                              }}
                            >
                              (inkomst)
                            </em>
                          )}
                        </div>
                        <div
                          style={{
                            fontFamily: "var(--mono)",
                            fontSize: 9,
                            color: "var(--text-dim)",
                            marginTop: 2,
                          }}
                        >
                          {u.autogiro
                            ? "Autogiro"
                            : u.bankgiro
                            ? `BG ${u.bankgiro}`
                            : u.plusgiro
                            ? `PG ${u.plusgiro}`
                            : "Faktura"}
                        </div>
                      </div>
                      <span
                        style={{
                          fontFamily: "var(--serif)",
                          fontStyle: urgent || overdue ? "italic" : "normal",
                          fontWeight: 700,
                          color: u.kind === "income" ? "#6ee7b7" : "#fff",
                          textAlign: "right",
                        }}
                      >
                        {u.kind === "income" ? "+ " : ""}
                        {SEK(u.amount)} kr
                      </span>
                      <span
                        style={{
                          fontFamily: "var(--mono)",
                          fontSize: 10,
                          color:
                            urgent || overdue
                              ? "var(--warm)"
                              : "var(--text-mid)",
                          fontWeight: urgent || overdue ? 700 : 400,
                        }}
                      >
                        {SHORT_DATE(u.expected_date)}
                      </span>
                      <span className={`biz-status ${statusClass}`}>
                        {statusText}
                      </span>
                    </a>
                  );
                })}
              </div>
            )}
            {upcoming_bills.length > 0 && (
              <div
                style={{
                  marginTop: 14,
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  flexWrap: "wrap",
                  gap: 12,
                }}
              >
                <div
                  style={{
                    fontFamily: "var(--mono)",
                    fontSize: 10,
                    color: "var(--text-mid)",
                    letterSpacing: 0.5,
                  }}
                >
                  Total kommande:{" "}
                  <strong style={{ color: "#fff" }}>
                    {SEK(summary.upcoming_open_total)} kr
                  </strong>{" "}
                  · {summary.upcoming_open_count} obetalda
                </div>
              </div>
            )}

            {/* Pedagogik */}
            <div className="peda">
              <div className="peda-eye">Pedagogik · vad du lär dig här</div>
              <div className="peda-h">
                Banken är din <em>infrastruktur</em>, inte din ekonomi.
              </div>
              <p className="peda-prose">
                En vanlig missuppfattning:{" "}
                <em>
                  "jag har {SEK(summary.total_balance)} kr på kontot, alltså
                  mår jag bra"
                </em>
                . Men kontot är bara <strong>tillgängligheten just nu</strong>{" "}
                — det säger inget om månadens åtaganden, skulden, sparmål
                eller dolda kostnader. Du lär dig läsa{" "}
                <code>tillgängligt saldo</code> i sammanhang av{" "}
                <code>kommande dragningar</code> och <code>sparmål</code>.
              </p>
              <ul className="peda-bullets">
                <li className="peda-bullet">
                  <strong>Konton</strong>Privatkonto · sparkonto · ISK ·
                  kreditkort. Olika syften.
                </li>
                <li className="peda-bullet">
                  <strong>Saldon</strong>Tillgängligt vs bokfört saldo —
                  skillnaden är reservationer.
                </li>
                <li className="peda-bullet">
                  <strong>Autogiro</strong>Hur återkommande betalningar dras
                  automatiskt — och risker.
                </li>
                <li className="peda-bullet">
                  <strong>Reservation</strong>Vad ett kortköp gör med saldot
                  innan boking.
                </li>
              </ul>
              <div className="peda-concepts">
                <span className="peda-concept">Likviditet</span>
                <span className="peda-concept">Sparkvot</span>
                <span className="peda-concept">Buffert</span>
                <span className="peda-concept">Räntenetto</span>
                <span className="peda-concept">Disponibel inkomst</span>
              </div>
              <div className="peda-tip">
                Klicka på ett konto för att se transaktioner. Klassa de
                ovettade — det är där medvetenhet börjar.
              </div>
            </div>
          </div>

          {/* ASIDE */}
          <aside>
            {nextScheduled && (
              <div className="side-card">
                <div className="side-card-eye">Kommande dragningar</div>
                <div className="side-card-h">
                  {SEK(nextScheduled.amount)} kr · {nextScheduled.name}
                </div>
                <div className="side-card-meta">
                  {SHORT_DATE(nextScheduled.expected_date)} ·{" "}
                  {nextScheduled.autogiro ? "autogiro" : "manuell"}
                </div>
              </div>
            )}
            {urgentBill && urgentBill.id !== nextScheduled?.id && (
              <div className="side-card">
                <div className="side-card-eye">Akut framåt</div>
                <div className="side-card-h">
                  {SEK(urgentBill.amount)} kr · {urgentBill.name}
                </div>
                <div className="side-card-meta">
                  {SHORT_DATE(urgentBill.expected_date)} · välj betaldatum
                </div>
                <a
                  className="side-card-link"
                  onClick={(e) => {
                    e.preventDefault();
                    navigate("/v2/hub");
                  }}
                  href="#"
                >
                  Se konsekvensen i pentagonen ↗
                </a>
              </div>
            )}
            <div className="side-card">
              <div className="side-card-eye">Saldo just nu</div>
              <div className="side-card-h">
                {SEK(summary.total_balance)} kr
              </div>
              <div className="side-card-meta">
                {summary.accounts_count} konton · cash + fond
              </div>
            </div>
            <div className="side-card">
              <div className="side-card-eye">Denna månad</div>
              <div className="side-card-h">
                + {SEK(summary.income_this_month)} kr
              </div>
              <div className="side-card-meta">
                in · ut {SEK(summary.expenses_this_month)} ·{" "}
                {summary.transactions_count} transaktioner
              </div>
            </div>
          </aside>
        </div>
      </div>
    </div>
  );
}
