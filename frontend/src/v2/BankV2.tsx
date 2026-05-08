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
import { Link, useNavigate } from "react-router-dom";
import { v2Api, type BankData, type BankUpcoming } from "./api";
import { V2Banner } from "./V2Banner";
import "./bank.css";

const SEK = (n: number) =>
  new Intl.NumberFormat("sv-SE", { maximumFractionDigits: 0 }).format(n);

const SHORT_DATE = (iso: string) => {
  const d = new Date(iso);
  return d.toLocaleDateString("sv-SE", { day: "numeric", month: "short" });
};

// DAYS_UNTIL är borta · backend skickar nu BankUpcoming.days_until_expected
// räknat mot SPEL-tid (current_game_date()). Jämförelse mot new Date()
// (= real-tid maj 2026) gjorde att osignerade fakturor med spel-januari-
// förfallodag visades som "−120 dagar".

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
  const [signing, setSigning] = useState(false);
  const [savingDate, setSavingDate] = useState<number | null>(null);
  const [transferOpen, setTransferOpen] = useState(false);
  const [hasPin, setHasPin] = useState<boolean | null>(null);
  const [pinValue, setPinValue] = useState("");
  const [pinConfirm, setPinConfirm] = useState("");
  const [pinSaving, setPinSaving] = useState(false);
  const [pinMsg, setPinMsg] = useState<string | null>(null);
  const navigate = useNavigate();

  function refresh() {
    v2Api
      .bank(40)
      .then(setBank)
      .catch((e) => setError(String((e as Error)?.message || e)));
  }

  useEffect(() => {
    refresh();
    v2Api.bankidPinStatus()
      .then((s) => setHasPin(s.has_pin))
      .catch(() => setHasPin(null));
  }, []);

  async function savePin() {
    if (!/^\d{4}$/.test(pinValue)) {
      setPinMsg("PIN måste vara 4 siffror");
      return;
    }
    if (pinValue !== pinConfirm) {
      setPinMsg("PIN-koderna matchar inte");
      return;
    }
    setPinSaving(true);
    setPinMsg(null);
    try {
      await v2Api.bankidSetPin(pinValue);
      setHasPin(true);
      setPinValue("");
      setPinConfirm("");
      setPinMsg("✓ PIN sparad. Du kan nu signera fakturor via BankID.");
    } catch (e) {
      setPinMsg(`Fel: ${String((e as Error)?.message || e)}`);
    } finally {
      setPinSaving(false);
    }
  }

  async function startBankID() {
    if (!bank) return;
    const openIds = bank.upcoming_bills
      .filter((b) => !b.is_paid)
      .map((b) => b.id);
    if (openIds.length === 0) return;
    setSigning(true);
    try {
      const session = await v2Api.bankidStart(openIds);
      navigate(`/v2/bankid/${session.id}`);
    } catch (e) {
      setError(String((e as Error)?.message || e));
    } finally {
      setSigning(false);
    }
  }

  async function changeUpcomingDate(upcomingId: number, newDate: string) {
    setSavingDate(upcomingId);
    try {
      await v2Api.upcomingUpdate(upcomingId, { expected_date: newDate });
      refresh();
    } catch (e) {
      setError(String((e as Error)?.message || e));
    } finally {
      setSavingDate(null);
    }
  }

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
  // Osignerade = exporterade från postlådan, väntar på BankID-signering
  const unsignedBills = openBills.filter((b) => !b.is_signed);
  // Schemalagda = signerade/autogiro, dras automatiskt
  const scheduledBills = openBills.filter((b) => b.is_signed);
  const billsToSign = unsignedBills.length;

  // Använd backend:s SPEL-tid-räknade days_until_expected · annars
  // jämförs mot real-tid (new Date()) och fakturor med spel-januari-
  // förfallodag visas som "−120 dagar" trots att eleven är på Jan 2.
  const urgentBill = openBills.find((b) => b.days_until_expected <= 7);
  const nextScheduled = openBills[0];

  // Helper · renderar EN rad i Osignerade/Schemalagda-tabellen.
  function renderBillRow(u: BankUpcoming) {
    const days = u.days_until_expected;
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
      : u.is_signed
      ? "sent"
      : "open";
    const statusText = u.is_paid
      ? "Betald"
      : overdue
      ? `${Math.abs(days)} d sen`
      : !u.is_signed
      ? "Osignerad"
      : "Schemalagd";
    const target = u.mail_id
      ? `/v2/postladan/${u.mail_id}`
      : `/v2/postladan`;
    return (
      <div
        key={u.id}
        className="biz-table-row"
        style={{
          gridTemplateColumns:
            "32px 1.8fr 110px 130px 110px",
          textDecoration: "none",
          color: "inherit",
          ...(urgent || overdue || !u.is_signed
            ? {
                background: "rgba(220,76,43,0.06)",
                borderLeft: "3px solid var(--warm)",
              }
            : {}),
        }}
      >
        <Link
          to={target}
          style={{
            display: "contents",
            textDecoration: "none",
            color: "inherit",
            cursor: "pointer",
          }}
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
        </Link>
        <input
          type="date"
          value={u.expected_date}
          // Signerade fakturor (autogiro/BankID) eller redan betalda
          // dragningar låses — bindande bankavtal kan inte flyttas
          // utan ny signering.
          disabled={savingDate === u.id || u.is_paid || u.is_signed}
          onChange={(e) =>
            changeUpcomingDate(u.id, e.target.value)
          }
          title={
            u.is_paid
              ? "Fakturan är redan betald — datum kan inte ändras."
              : u.is_signed
              ? "Signerad via BankID — avsigna i postlådan först om du behöver flytta datumet."
              : "Tryck för att flytta förfallodatumet."
          }
          style={{
            background: "rgba(255,255,255,0.04)",
            border:
              urgent || overdue || !u.is_signed
                ? "1px solid var(--warm)"
                : "1px solid var(--line-strong)",
            color: "#fff",
            padding: "5px 7px",
            borderRadius: 6,
            fontFamily: "var(--mono)",
            fontSize: 10.5,
            width: "100%",
            cursor:
              u.is_paid || u.is_signed
                ? "not-allowed"
                : "pointer",
            opacity: u.is_paid || u.is_signed ? 0.55 : 1,
          }}
        />
        <Link
          to={target}
          style={{
            textDecoration: "none",
            display: "block",
          }}
        >
          <span className={`biz-status ${statusClass}`}>
            {statusText}
          </span>
        </Link>
      </div>
    );
  }

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
              Banken — <em>{accCount === 1 ? "ett konto" : `${accCount} konton`}</em>
              {billsToSign > 0
                ? `, ett dygn att signera.`
                : `, allt rullar.`}
            </h1>
            <p className="actor-sub">
              {accounts[0]?.bank || "Banken"} · privatkund · konton synkade just nu
            </p>
          </div>
          <div className="actor-meta">
            Inloggad via <strong>BankID</strong>
            <br />
            Fakturor att signera: <strong>{billsToSign} st</strong>
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
                <Link
                  key={a.id}
                  className="acct"
                  to={`/v2/bokforing?account=${a.id}`}
                  style={{ textDecoration: "none", color: "inherit" }}
                >
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
                </Link>
              );
            })}
          </div>
        )}

        <div className="act-grid">
          <div>
            {/* PIN-setup · visas om eleven inte har satt sin BankID-PIN */}
            {hasPin === false && (
              <article
                className="cta-card"
                style={{
                  borderColor: "var(--accent)",
                  background: "rgba(220,76,43,0.06)",
                }}
              >
                <div className="cta-eye">● BankID-PIN saknas</div>
                <div className="cta-h">
                  Sätt din <em>4-siffriga PIN</em>.
                </div>
                <p className="cta-prose">
                  PIN är 'något du vet' som binder dig till varje
                  signering. Den används när du signerar fakturor på
                  mobilen efter att ha scannat QR-koden i banken.
                  Aldrig dela den med någon — inte ens läraren.
                </p>
                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: "1fr 1fr",
                    gap: 10,
                    marginBottom: 10,
                  }}
                >
                  <input
                    type="password"
                    inputMode="numeric"
                    pattern="[0-9]*"
                    maxLength={4}
                    placeholder="•••• (PIN)"
                    value={pinValue}
                    onChange={(e) =>
                      setPinValue(e.target.value.replace(/[^0-9]/g, ""))
                    }
                    style={{
                      padding: "12px 16px",
                      fontSize: 22,
                      textAlign: "center",
                      letterSpacing: "0.4em",
                      background: "rgba(255,255,255,0.04)",
                      border: "1px solid var(--line-strong)",
                      borderRadius: 8,
                      color: "#fff",
                      fontFamily: "var(--mono)",
                      fontWeight: 700,
                    }}
                  />
                  <input
                    type="password"
                    inputMode="numeric"
                    pattern="[0-9]*"
                    maxLength={4}
                    placeholder="•••• (upprepa)"
                    value={pinConfirm}
                    onChange={(e) =>
                      setPinConfirm(e.target.value.replace(/[^0-9]/g, ""))
                    }
                    style={{
                      padding: "12px 16px",
                      fontSize: 22,
                      textAlign: "center",
                      letterSpacing: "0.4em",
                      background: "rgba(255,255,255,0.04)",
                      border: "1px solid var(--line-strong)",
                      borderRadius: 8,
                      color: "#fff",
                      fontFamily: "var(--mono)",
                      fontWeight: 700,
                    }}
                  />
                </div>
                {pinMsg && (
                  <div
                    style={{
                      padding: "8px 12px",
                      borderRadius: 6,
                      fontFamily: "var(--mono)",
                      fontSize: 11,
                      marginBottom: 10,
                      color: pinMsg.startsWith("Fel") ? "#fca5a5" : "#6ee7b7",
                      background: pinMsg.startsWith("Fel")
                        ? "rgba(252,165,165,0.06)"
                        : "rgba(110,231,183,0.06)",
                      border: pinMsg.startsWith("Fel")
                        ? "1px solid rgba(252,165,165,0.4)"
                        : "1px solid rgba(110,231,183,0.4)",
                    }}
                  >
                    {pinMsg}
                  </div>
                )}
                <button
                  type="button"
                  className="cta-btn"
                  disabled={pinSaving || pinValue.length !== 4
                    || pinConfirm.length !== 4}
                  onClick={savePin}
                >
                  {pinSaving ? "Sparar…" : "Spara PIN"}
                </button>
              </article>
            )}

            {hasPin === true && pinMsg && (
              <div
                style={{
                  padding: "8px 14px",
                  borderRadius: 6,
                  fontFamily: "var(--mono)",
                  fontSize: 11,
                  marginBottom: 14,
                  color: "#6ee7b7",
                  background: "rgba(110,231,183,0.06)",
                  border: "1px solid rgba(110,231,183,0.4)",
                }}
              >
                {pinMsg}
              </div>
            )}

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
                <button
                  className="cta-btn"
                  type="button"
                  disabled={signing}
                  onClick={startBankID}
                >
                  {signing
                    ? "Skapar BankID-session…"
                    : `Öppna BankID-signering (${billsToSign} st) →`}
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
                {summary.next_release_at ? (
                  <>
                    Inga transaktioner synliga än.{" "}
                    {(() => {
                      const t = new Date(summary.next_release_at).getTime();
                      const sec = Math.round((t - Date.now()) / 1000);
                      if (sec <= 0) return "Nästa släpps strax — ladda om sidan.";
                      if (sec < 60) return `Nästa släpps om ${sec} s.`;
                      if (sec < 3600) return `Nästa släpps om ${Math.round(sec/60)} min.`;
                      if (sec < 86400) return `Nästa släpps om ${Math.round(sec/3600)} h.`;
                      const d = Math.floor(sec/86400);
                      const h = Math.round((sec - d*86400)/3600);
                      return h > 0
                        ? `Nästa släpps om ${d} d ${h} h.`
                        : `Nästa släpps om ${d} d.`;
                    })()}
                    {summary.pending_count > 1 && (
                      <> ({summary.pending_count} st väntar totalt)</>
                    )}
                  </>
                ) : (
                  <>
                    Inga transaktioner än. Den här månaden har precis börjat —
                    lön och utgifter rullar in när månaden tickas fram.
                  </>
                )}
              </div>
            ) : (
              <div className="tx-list">
                {recent_transactions.slice(0, 12).map((t) => {
                  const isIncome = t.amount > 0;
                  return (
                    <Link
                      className="tx-row"
                      key={t.id}
                      to={`/v2/tx/${t.id}`}
                      style={{
                        textDecoration: "none",
                        color: "inherit",
                        cursor: "pointer",
                      }}
                    >
                      <span className="tx-date">{SHORT_DATE(t.date)}</span>
                      <div>
                        <div className="tx-name">
                          {t.merchant || t.description}
                        </div>
                        <div className="tx-name-sub">{t.account_name}</div>
                      </div>
                      <span
                        className={`tx-cat${
                          t.category_id == null && !t.is_transfer
                            && !((t.description || "").toLowerCase()
                              .startsWith("lön "))
                            ? " unset"
                            : ""
                        }`}
                      >
                        {t.is_transfer
                          ? "Överf."
                          : (t.description || "").toLowerCase()
                              .startsWith("lön ")
                          ? "Lön"
                          : t.category_id == null
                          ? "Okatt"
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
                    </Link>
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
                {recent_transactions.filter((t) =>
                  t.category_id == null
                  && !t.is_transfer
                  && !((t.description || "").toLowerCase()
                    .startsWith("lön "))
                ).length}{" "}
                ovettade
              </div>
            )}

            {/* OSIGNERADE · exporterade från postlådan, väntar BankID */}
            <div className="section-eye" style={{ marginTop: 32 }}>
              Osignerade fakturor · väntar BankID-signering
            </div>
            {unsignedBills.length === 0 ? (
              <div
                style={{
                  padding: "16px 20px",
                  border: "1px solid var(--line)",
                  borderRadius: 6,
                  fontFamily: "var(--serif)",
                  color: "var(--text-mid)",
                  marginBottom: 16,
                }}
              >
                Inga osignerade fakturor. Exportera fakturor från postlådan
                så hamnar de här tills du signerar dem via BankID.
              </div>
            ) : (
              <div className="biz-table" style={{ marginBottom: 16 }}>
                <div
                  className="biz-table-row head"
                  style={{
                    gridTemplateColumns:
                      "32px 1.8fr 110px 130px 110px",
                  }}
                >
                  <span></span>
                  <span>Mottagare</span>
                  <span>Belopp</span>
                  <span>Datum</span>
                  <span>Status</span>
                </div>
                {unsignedBills.map((u) => {
                  return renderBillRow(u);
                })}
              </div>
            )}

            {/* SCHEMALAGDA · signerade/autogiro */}
            <div className="section-eye" style={{ marginTop: 24 }}>
              Kommande dragningar &amp; betalningar
            </div>
            {scheduledBills.length === 0 ? (
              <div
                style={{
                  padding: "16px 20px",
                  border: "1px solid var(--line)",
                  borderRadius: 6,
                  fontFamily: "var(--serif)",
                  color: "var(--text-mid)",
                }}
              >
                Inga schemalagda dragningar. När du signerar fakturor via
                BankID hamnar de här som autogiro.
              </div>
            ) : (
              <div className="biz-table">
                <div
                  className="biz-table-row head"
                  style={{
                    gridTemplateColumns:
                      "32px 1.8fr 110px 130px 110px",
                  }}
                >
                  <span></span>
                  <span>Mottagare</span>
                  <span>Belopp</span>
                  <span>Datum</span>
                  <span>Status</span>
                </div>
                {scheduledBills.map((u) => {
                  return renderBillRow(u);
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
                {billsToSign > 0 && (
                  <button
                    type="button"
                    className="cta-btn"
                    disabled={signing}
                    onClick={startBankID}
                  >
                    {signing
                      ? "Skapar BankID-session…"
                      : `Signera alla schemalagda → BankID`}
                  </button>
                )}
              </div>
            )}

            {/* Schemalagda överföringar mellan egna konton */}
            <div className="section-eye" style={{ marginTop: 32 }}>
              Flytta pengar mellan dina konton
            </div>
            <div
              style={{
                padding: "16px 20px",
                border: "1px solid var(--line)",
                borderRadius: 6,
                background: "rgba(15,21,37,0.7)",
                marginBottom: 22,
              }}
            >
              <p
                style={{
                  fontFamily: "var(--serif)",
                  fontSize: 13.5,
                  color: "var(--text-mid)",
                  marginTop: 0,
                }}
              >
                Pay yourself first · flytta från lönekontot till
                sparkontot eller ISK direkt när lönen kommer. Du kan
                inte ta ut mer än vad som finns på källkontot.
              </p>
              <button
                type="button"
                className="cta-btn"
                onClick={() => setTransferOpen(true)}
              >
                Ny överföring →
              </button>
              {transferOpen && (
                <TransferForm
                  accounts={accounts}
                  onCancel={() => setTransferOpen(false)}
                  onDone={() => {
                    setTransferOpen(false);
                    refresh();
                  }}
                />
              )}
            </div>

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
                {summary.transactions_count}{" "}
                {summary.transactions_count === 1
                  ? "transaktion"
                  : "transaktioner"}
              </div>
            </div>
          </aside>
        </div>
      </div>
    </div>
  );
}

import type { BankAccount } from "./api";

function TransferForm({
  accounts,
  onCancel,
  onDone,
}: {
  accounts: BankAccount[];
  onCancel: () => void;
  onDone: () => void;
}) {
  const checking = accounts.find((a) => a.type === "checking");
  const savings = accounts.find((a) => a.type === "savings");
  const [from, setFrom] = useState<number>(
    checking?.id || accounts[0]?.id || 0,
  );
  const [to, setTo] = useState<number>(
    savings?.id || accounts[1]?.id || accounts[0]?.id || 0,
  );
  const [amount, setAmount] = useState<string>("500");
  const [descr, setDescr] = useState<string>("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const amt = parseFloat(amount);
    if (!amt || amt <= 0) {
      setErr("Beloppet måste vara > 0");
      return;
    }
    if (from === to) {
      setErr("Från- och till-konto måste vara olika");
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      await v2Api.bankenTransfer({
        from_account_id: from,
        to_account_id: to,
        amount: amt,
        description: descr || undefined,
      });
      onDone();
    } catch (e) {
      setErr(String((e as Error)?.message || e));
    } finally {
      setBusy(false);
    }
  }

  const fieldStyle: React.CSSProperties = {
    background: "rgba(255,255,255,0.04)",
    border: "1px solid var(--line-strong)",
    color: "#fff",
    padding: "8px 10px",
    borderRadius: 6,
    fontFamily: "var(--mono)",
    fontSize: 12,
    width: "100%",
  };
  const labelStyle: React.CSSProperties = {
    fontFamily: "var(--mono)",
    fontSize: 9.5,
    letterSpacing: "1.2px",
    textTransform: "uppercase",
    color: "var(--text-mid)",
    display: "block",
    marginBottom: 4,
  };

  return (
    <form
      onSubmit={submit}
      style={{
        marginTop: 16,
        padding: "16px 18px",
        border: "1px solid var(--line-strong)",
        borderRadius: 6,
        background: "rgba(0,0,0,0.25)",
        display: "grid",
        gap: 12,
      }}
    >
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: 10,
        }}
      >
        <div>
          <label style={labelStyle}>Från konto</label>
          <select
            value={from}
            onChange={(e) => setFrom(parseInt(e.target.value, 10))}
            style={fieldStyle}
          >
            {accounts.map((a) => (
              <option key={a.id} value={a.id}>
                {a.name} · {SEK(a.total_value)} kr
              </option>
            ))}
          </select>
        </div>
        <div>
          <label style={labelStyle}>Till konto</label>
          <select
            value={to}
            onChange={(e) => setTo(parseInt(e.target.value, 10))}
            style={fieldStyle}
          >
            {accounts.map((a) => (
              <option key={a.id} value={a.id}>
                {a.name} · {SEK(a.total_value)} kr
              </option>
            ))}
          </select>
        </div>
      </div>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "120px 1fr",
          gap: 10,
        }}
      >
        <div>
          <label style={labelStyle}>Belopp (kr)</label>
          <input
            type="number"
            min="1"
            step="1"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            style={fieldStyle}
          />
        </div>
        <div>
          <label style={labelStyle}>Beskrivning (valfritt)</label>
          <input
            type="text"
            placeholder="t.ex. 'Buffert maj'"
            value={descr}
            onChange={(e) => setDescr(e.target.value)}
            style={fieldStyle}
          />
        </div>
      </div>
      {err && (
        <div
          style={{
            color: "#fca5a5",
            fontFamily: "var(--mono)",
            fontSize: 11,
          }}
        >
          {err}
        </div>
      )}
      <div style={{ display: "flex", gap: 10 }}>
        <button type="submit" className="cta-btn" disabled={busy}>
          {busy ? "Flyttar…" : "Flytta pengarna"}
        </button>
        <button
          type="button"
          className="cta-btn ghost"
          onClick={onCancel}
          disabled={busy}
        >
          Avbryt
        </button>
      </div>
    </form>
  );
}
