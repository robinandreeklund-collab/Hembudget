/**
 * V2 Lånegivaren · matchar /proposals/vol-7/elev.html#p-lan EXAKT.
 *
 * Layout (samma som prototypen):
 *   1. .actor-back tillbaka-länk → /v2/hub
 *   2. .actor-head · "Aktör 04 · Lånegivaren"-pill (warm) +
 *      h1 "Dina lån, din kreditprofil" + actor-meta (Total skuld /
 *      Skuldkvot / Kreditprofil)
 *   3. .acct-grid (4 kort) · 1 aktiv + 3 möjliga (bolån, privatlån, billån)
 *   4. .act-grid (1.4fr 1fr):
 *      MAIN:
 *        - .section-eye + .tx-list · CSN amorteringsplan (4 senaste mån)
 *        - .section-eye + .biz-table · kreditprövning (5 rader)
 *        - .cta-card · uppdrag bolån
 *      ASIDE:
 *        - 4 .side-card (ränteavdrag · snabbamortering · befrielse · sms-varning)
 *   5. .peda · pedagogik
 */
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  v2Api,
  type BankData,
  type LoanData,
  type V2LoanApplyResponse,
  type V2LoanKind,
} from "./api";
import { V2Banner } from "./V2Banner";
import "./lan.css";

// Realistiska intervall per lånetyp — speglar backend-_LOAN_KIND_SPECS
type LoanKindSpec = {
  key: V2LoanKind;
  label: string;
  blurb: string;
  minAmount: number;
  maxAmount: number;
  minTerm: number;
  maxTerm: number;
  defaultAmount: number;
  defaultTerm: number;
  warning?: string;
};

const LOAN_KIND_SPECS: LoanKindSpec[] = [
  {
    key: "privatlan",
    label: "Privatlån",
    blurb: "För renovering, resa, möbler. Pengarna går in på lönekontot.",
    minAmount: 10_000,
    maxAmount: 500_000,
    minTerm: 12,
    maxTerm: 144,
    defaultAmount: 100_000,
    defaultTerm: 60,
  },
  {
    key: "billan",
    label: "Billån",
    blurb: "Bunden till bilköpet. Pengarna går till säljaren.",
    minAmount: 50_000,
    maxAmount: 500_000,
    minTerm: 36,
    maxTerm: 84,
    defaultAmount: 200_000,
    defaultTerm: 60,
  },
  {
    key: "bolan",
    label: "Bolån",
    blurb: "För bostadsköp. Lägst ränta — men kräver kontantinsats 15 %.",
    minAmount: 200_000,
    maxAmount: 5_000_000,
    minTerm: 120,
    maxTerm: 600,
    defaultAmount: 2_000_000,
    defaultTerm: 360,
  },
  {
    key: "smslan",
    label: "SMS-lån",
    blurb: "Snabbutbetalning utan kreditprövning. EXTREMT hög ränta.",
    minAmount: 1_000,
    maxAmount: 30_000,
    minTerm: 1,
    maxTerm: 12,
    defaultAmount: 5_000,
    defaultTerm: 6,
    warning:
      "Effektiv årsränta 30–60 %. Du betalar tillbaka mycket mer än du lånar.",
  },
];

const SEK = (n: number) =>
  new Intl.NumberFormat("sv-SE", { maximumFractionDigits: 0 }).format(n);

export function LanV2() {
  const [data, setData] = useState<LoanData | null>(null);
  const [bank, setBank] = useState<BankData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  // KALP-räknare state
  const [kalpAmount, setKalpAmount] = useState<string>("2400000");
  const [kalpTerm, setKalpTerm] = useState<string>("300");
  const [kalpResult, setKalpResult] = useState<
    import("./api").V2KALPResponse | null
  >(null);
  const [kalpRunning, setKalpRunning] = useState(false);
  const [kalpError, setKalpError] = useState<string | null>(null);

  // Extra-amortering state
  const [extraLoanId, setExtraLoanId] = useState<number | null>(null);
  const [extraAmount, setExtraAmount] = useState<string>("1000");
  const [extraAccountId, setExtraAccountId] = useState<number | null>(null);
  const [extraBusy, setExtraBusy] = useState(false);
  const [extraMsg, setExtraMsg] = useState<string | null>(null);

  // Ansök om nytt lån-state
  const [applyKind, setApplyKind] = useState<V2LoanKind | null>(null);
  const [applyAmount, setApplyAmount] = useState<string>("");
  const [applyTerm, setApplyTerm] = useState<string>("");
  const [applyPurpose, setApplyPurpose] = useState<string>("");
  const [applyAccountId, setApplyAccountId] = useState<number | null>(null);
  const [applyOffer, setApplyOffer] =
    useState<V2LoanApplyResponse | null>(null);
  const [applyBusy, setApplyBusy] = useState(false);
  const [applyError, setApplyError] = useState<string | null>(null);

  function openApply(kind: V2LoanKind) {
    const spec = LOAN_KIND_SPECS.find((s) => s.key === kind)!;
    setApplyKind(kind);
    setApplyAmount(String(spec.defaultAmount));
    setApplyTerm(String(spec.defaultTerm));
    setApplyPurpose("");
    setApplyOffer(null);
    setApplyError(null);
    const checking = bank?.accounts.find((a) => a.type === "checking");
    setApplyAccountId(checking?.id || bank?.accounts[0]?.id || null);
  }

  function closeApply() {
    setApplyKind(null);
    setApplyOffer(null);
    setApplyError(null);
  }

  async function runApplyCheck() {
    if (!applyKind) return;
    const amt = parseFloat(
      applyAmount.replace(/\s/g, "").replace(",", "."),
    );
    const term = parseInt(applyTerm, 10);
    if (isNaN(amt) || amt <= 0) {
      setApplyError("Ange giltigt lånebelopp");
      return;
    }
    if (isNaN(term) || term <= 0) {
      setApplyError("Ange löptid (mån)");
      return;
    }
    setApplyError(null);
    setApplyBusy(true);
    try {
      const res = await v2Api.loanApply({
        loan_kind: applyKind,
        amount: amt,
        term_months: term,
        purpose: applyPurpose || undefined,
        debit_account_id: applyAccountId || undefined,
        accept_offer: false,
      });
      setApplyOffer(res);
    } catch (e) {
      setApplyError(String((e as Error)?.message || e));
    } finally {
      setApplyBusy(false);
    }
  }

  async function acceptApplyOffer() {
    if (!applyKind || !applyOffer || !applyOffer.approved) return;
    const amt = parseFloat(
      applyAmount.replace(/\s/g, "").replace(",", "."),
    );
    const term = parseInt(applyTerm, 10);
    setApplyBusy(true);
    setApplyError(null);
    try {
      const res = await v2Api.loanApply({
        loan_kind: applyKind,
        amount: amt,
        term_months: term,
        purpose: applyPurpose || undefined,
        debit_account_id: applyAccountId || undefined,
        accept_offer: true,
      });
      setApplyOffer(res);
      // Refetcha lan-data så nya lånet syns
      refresh();
    } catch (e) {
      setApplyError(String((e as Error)?.message || e));
    } finally {
      setApplyBusy(false);
    }
  }

  function refresh() {
    v2Api
      .lan()
      .then(setData)
      .catch((e) => setError(String((e as Error)?.message || e)));
    v2Api.bank(0).then(setBank).catch(() => null);
  }

  async function executeExtraAmort() {
    if (!extraLoanId || !extraAccountId) return;
    const amt = parseFloat(extraAmount.replace(/\s/g, "").replace(",", "."));
    if (!amt || amt <= 0) {
      setExtraMsg("Ange ett positivt belopp");
      return;
    }
    setExtraBusy(true);
    setExtraMsg(null);
    try {
      const r = await v2Api.loanExtraAmortering(extraLoanId, {
        amount: amt,
        debit_account_id: extraAccountId,
      });
      setExtraMsg(
        `✓ Amorterade ${r.amount} kr extra. Kvarstående principal ` +
        `≈ ${Math.round(r.new_principal_estimate)} kr.`,
      );
      setExtraLoanId(null);
      refresh();
    } catch (e) {
      setExtraMsg(`Fel: ${String((e as Error)?.message || e)}`);
    } finally {
      setExtraBusy(false);
    }
  }

  async function runKalp() {
    const amt = parseFloat(kalpAmount.replace(/\s/g, "").replace(",", "."));
    const term = parseInt(kalpTerm, 10);
    if (isNaN(amt) || amt <= 0) {
      setKalpError("Ange giltigt lånebelopp (kr)");
      return;
    }
    if (isNaN(term) || term < 12) {
      setKalpError("Ange löptid i månader (minst 12)");
      return;
    }
    setKalpError(null);
    setKalpRunning(true);
    try {
      const res = await v2Api.kalp(amt, term);
      setKalpResult(res);
      // Refetcha /v2/lan så KALP-raden i credit_factors uppdateras
      const fresh = await v2Api.lan();
      setData(fresh);
    } catch (e) {
      setKalpError(String((e as Error)?.message || e));
    } finally {
      setKalpRunning(false);
    }
  }

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (error) {
    return (
      <div className="v2-lan-root">
        <V2Banner status={{ role: "student", is_super_admin: false }} />
        <div className="bank-loading">
          <div>
            <div style={{ color: "#fca5a5", marginBottom: 8 }}>
              Kunde inte ladda lån-data
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
        <div className="bank-loading">Laddar lån-data…</div>
      </div>
    );
  }

  const {
    cards,
    schedule,
    credit_factors,
    total_debt,
    debt_ratio,
    credit_class,
  } = data;

  return (
    <div className="v2-lan-root">
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
            <span className="pill warm">Aktör 04 · Lånegivaren</span>
            <h1 className="actor-name" style={{ marginTop: 14 }}>
              Dina <em>lån</em>, din kreditprofil.
            </h1>
            <p className="actor-sub">
              CSN · ev. bolån · privatlån · billån · kreditprövning av dig
              själv som låntagare
            </p>
          </div>
          <div className="actor-meta">
            Total skuld: <strong>{SEK(total_debt)} kr</strong>
            <br />
            Skuldkvot: <strong>{debt_ratio.toFixed(2)}×</strong> årsinkomst
            <br />
            Kreditprofil: <strong>{credit_class}</strong>
          </div>
        </header>

        {/* LÅNETYPER · aktiva lån (möjliga produkter visas i Fas 2 när
            LoanProduct-modellen finns) */}
        {cards.length === 0 ? (
          <div
            style={{
              padding: "32px 24px",
              border: "1px solid var(--line)",
              borderRadius: 6,
              fontFamily: "var(--serif)",
              color: "var(--text-mid)",
              marginBottom: 22,
            }}
          >
            Inga aktiva lån registrerade. När du får ett CSN-lån, bolån
            eller annat lån från Lånegivaren visas det här som ett kort
            med saldo + amortering.
          </div>
        ) : (
        <div className="acct-grid">
          {cards.map((c, idx) => (
            <div
              key={c.id ?? `card-${idx}`}
              className={`acct${c.is_active ? " active" : ""}${
                c.is_warning ? " warning" : ""
              }`}
            >
              <div>
                <div className="acct-eye">{c.eyebrow}</div>
                <div className="acct-name">{c.name}</div>
                <div className="acct-num">{c.detail}</div>
              </div>
              <div>
                <div
                  className="acct-bal"
                  style={
                    c.balance == null
                      ? { color: "var(--text-dim)" }
                      : undefined
                  }
                >
                  {c.balance != null ? (
                    c.is_active ? (
                      <em>{SEK(c.balance)}</em>
                    ) : (
                      SEK(c.balance)
                    )
                  ) : (
                    "— ej"
                  )}
                  {c.balance != null && " kr"}
                </div>
                {c.monthly_text && (
                  <div className="acct-bal-meta">{c.monthly_text}</div>
                )}
                {c.is_active && c.id != null && (
                  <button
                    type="button"
                    className="cta-btn ghost"
                    onClick={() => {
                      setExtraLoanId(c.id);
                      setExtraMsg(null);
                      // Default till lönekonto
                      const checking =
                        bank?.accounts.find((a) => a.type === "checking");
                      setExtraAccountId(
                        checking?.id || bank?.accounts[0]?.id || null,
                      );
                    }}
                    style={{
                      marginTop: 10,
                      padding: "6px 12px",
                      fontSize: 9.5,
                    }}
                  >
                    + Extra-amortering
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
        )}

        {/* INLINE EXTRA-AMORTERING-FORMULÄR */}
        {extraLoanId != null && bank && (
          <div
            style={{
              marginTop: 18,
              padding: "16px 20px",
              border: "1px solid var(--accent)",
              borderRadius: 6,
              background: "rgba(220,76,43,0.04)",
            }}
          >
            <div
              style={{
                fontFamily: "var(--mono)",
                fontSize: 9.5,
                letterSpacing: "1.2px",
                textTransform: "uppercase",
                color: "var(--accent)",
                marginBottom: 10,
              }}
            >
              ● Extra-amortering på {
                cards.find((c) => c.id === extraLoanId)?.name || "lånet"
              }
            </div>
            <p
              style={{
                fontFamily: "var(--serif)",
                fontSize: 13.5,
                color: "var(--text-mid)",
                marginTop: 0,
              }}
            >
              Att amortera extra ger en{" "}
              <em style={{ color: "var(--warm)" }}>
                garanterad avkastning
              </em>{" "}
              lika hög som lånets ränta. Beloppet dras från det konto du
              väljer.
            </p>
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "1fr 1fr 120px 120px",
                gap: 10,
                alignItems: "end",
              }}
            >
              <div>
                <label
                  style={{
                    display: "block",
                    fontFamily: "var(--mono)",
                    fontSize: 9,
                    letterSpacing: "1.2px",
                    textTransform: "uppercase",
                    color: "var(--text-mid)",
                    marginBottom: 4,
                  }}
                >
                  Från konto
                </label>
                <select
                  value={extraAccountId || ""}
                  onChange={(e) =>
                    setExtraAccountId(parseInt(e.target.value, 10))
                  }
                  style={{
                    background: "rgba(255,255,255,0.04)",
                    border: "1px solid var(--line-strong)",
                    color: "#fff",
                    padding: "8px 10px",
                    borderRadius: 6,
                    fontFamily: "var(--mono)",
                    fontSize: 12,
                    width: "100%",
                  }}
                >
                  {bank.accounts.map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.name} · {SEK(a.total_value)} kr
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label
                  style={{
                    display: "block",
                    fontFamily: "var(--mono)",
                    fontSize: 9,
                    letterSpacing: "1.2px",
                    textTransform: "uppercase",
                    color: "var(--text-mid)",
                    marginBottom: 4,
                  }}
                >
                  Belopp (kr)
                </label>
                <input
                  type="number"
                  min="1"
                  step="100"
                  value={extraAmount}
                  onChange={(e) => setExtraAmount(e.target.value)}
                  style={{
                    background: "rgba(255,255,255,0.04)",
                    border: "1px solid var(--line-strong)",
                    color: "#fff",
                    padding: "8px 10px",
                    borderRadius: 6,
                    fontFamily: "var(--mono)",
                    fontSize: 12,
                    width: "100%",
                  }}
                />
              </div>
              <button
                type="button"
                className="cta-btn"
                onClick={executeExtraAmort}
                disabled={extraBusy}
              >
                {extraBusy ? "Amorterar…" : "Amortera"}
              </button>
              <button
                type="button"
                className="cta-btn ghost"
                onClick={() => {
                  setExtraLoanId(null);
                  setExtraMsg(null);
                }}
                disabled={extraBusy}
              >
                Avbryt
              </button>
            </div>
            {extraMsg && (
              <div
                style={{
                  marginTop: 10,
                  padding: "8px 14px",
                  background: extraMsg.startsWith("Fel")
                    ? "rgba(252,165,165,0.06)"
                    : "rgba(110,231,183,0.06)",
                  border: extraMsg.startsWith("Fel")
                    ? "1px solid rgba(252,165,165,0.4)"
                    : "1px solid rgba(110,231,183,0.4)",
                  borderRadius: 6,
                  fontFamily: "var(--mono)",
                  fontSize: 11,
                  color: extraMsg.startsWith("Fel") ? "#fca5a5" : "#6ee7b7",
                }}
              >
                {extraMsg}
              </div>
            )}
          </div>
        )}

        {/* === ANSÖK OM NYTT LÅN === */}
        <div className="section-eye" style={{ marginTop: 32 }}>
          Ansök om nytt lån
        </div>
        <p
          style={{
            fontFamily: "var(--serif)",
            fontSize: 13.5,
            color: "var(--text-mid)",
            marginTop: 4,
            marginBottom: 16,
          }}
        >
          Du kan ansöka om fyra olika lånetyper. Banken bedömer din
          kreditprofil (UC) och din betalningsförmåga (KALP). Lånetagning
          påverkar din wellbeing — för bra eller sämre.
        </p>
        <div className="acct-grid">
          {LOAN_KIND_SPECS.map((spec) => (
            <div
              key={spec.key}
              className={`acct${
                spec.key === "smslan" ? " warning" : ""
              }`}
            >
              <div>
                <div className="acct-eye">
                  {spec.key === "smslan" ? "Varning" : "Ansök"}
                </div>
                <div className="acct-name">{spec.label}</div>
                <div className="acct-num" style={{ fontSize: 11.5 }}>
                  {spec.blurb}
                </div>
                <div
                  className="acct-num"
                  style={{ marginTop: 6, color: "var(--text-dim)" }}
                >
                  {SEK(spec.minAmount)}–{SEK(spec.maxAmount)} kr ·
                  {" "}{spec.minTerm}–{spec.maxTerm} mån
                </div>
              </div>
              <div>
                <button
                  type="button"
                  className="cta-btn"
                  onClick={() => openApply(spec.key)}
                  style={{ marginTop: 10, padding: "8px 14px" }}
                >
                  Ansök →
                </button>
              </div>
            </div>
          ))}
        </div>

        {/* INLINE APPLY-FORMULÄR */}
        {applyKind && (
          <div
            style={{
              marginTop: 18,
              padding: "16px 20px",
              border: `1px solid ${
                applyKind === "smslan" ? "#dc2626" : "var(--accent)"
              }`,
              borderRadius: 6,
              background:
                applyKind === "smslan"
                  ? "rgba(220,38,38,0.04)"
                  : "rgba(220,76,43,0.04)",
            }}
          >
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                marginBottom: 10,
              }}
            >
              <div
                style={{
                  fontFamily: "var(--mono)",
                  fontSize: 9.5,
                  letterSpacing: "1.2px",
                  textTransform: "uppercase",
                  color:
                    applyKind === "smslan" ? "#dc2626" : "var(--accent)",
                }}
              >
                ● Ansökan ·{" "}
                {LOAN_KIND_SPECS.find((s) => s.key === applyKind)?.label}
              </div>
              <button
                type="button"
                className="cta-btn ghost"
                onClick={closeApply}
                style={{ padding: "4px 10px", fontSize: 9.5 }}
              >
                Stäng
              </button>
            </div>

            {LOAN_KIND_SPECS.find((s) => s.key === applyKind)?.warning && (
              <div
                style={{
                  fontFamily: "var(--serif)",
                  fontSize: 12.5,
                  color: "#dc2626",
                  marginBottom: 12,
                  padding: "8px 12px",
                  background: "rgba(220,38,38,0.08)",
                  borderRadius: 4,
                }}
              >
                ⚠{" "}
                {
                  LOAN_KIND_SPECS.find((s) => s.key === applyKind)
                    ?.warning
                }
              </div>
            )}

            <div
              style={{
                display: "grid",
                gridTemplateColumns: "1fr 1fr 1fr",
                gap: 10,
                alignItems: "end",
              }}
            >
              <div>
                <label
                  style={{
                    display: "block",
                    fontFamily: "var(--mono)",
                    fontSize: 9,
                    letterSpacing: "1.2px",
                    textTransform: "uppercase",
                    color: "var(--text-mid)",
                    marginBottom: 4,
                  }}
                >
                  Belopp (kr)
                </label>
                <input
                  type="text"
                  value={applyAmount}
                  onChange={(e) => setApplyAmount(e.target.value)}
                  className="kalp-input"
                />
              </div>
              <div>
                <label
                  style={{
                    display: "block",
                    fontFamily: "var(--mono)",
                    fontSize: 9,
                    letterSpacing: "1.2px",
                    textTransform: "uppercase",
                    color: "var(--text-mid)",
                    marginBottom: 4,
                  }}
                >
                  Löptid (mån)
                </label>
                <input
                  type="text"
                  value={applyTerm}
                  onChange={(e) => setApplyTerm(e.target.value)}
                  className="kalp-input"
                />
              </div>
              <div>
                <label
                  style={{
                    display: "block",
                    fontFamily: "var(--mono)",
                    fontSize: 9,
                    letterSpacing: "1.2px",
                    textTransform: "uppercase",
                    color: "var(--text-mid)",
                    marginBottom: 4,
                  }}
                >
                  Konto för utbetalning
                </label>
                <select
                  value={applyAccountId || ""}
                  onChange={(e) =>
                    setApplyAccountId(parseInt(e.target.value, 10) || null)
                  }
                  className="kalp-input"
                >
                  {bank?.accounts.map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.name}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div style={{ marginTop: 10 }}>
              <label
                style={{
                  display: "block",
                  fontFamily: "var(--mono)",
                  fontSize: 9,
                  letterSpacing: "1.2px",
                  textTransform: "uppercase",
                  color: "var(--text-mid)",
                  marginBottom: 4,
                }}
              >
                Syfte (frivilligt)
              </label>
              <input
                type="text"
                value={applyPurpose}
                onChange={(e) => setApplyPurpose(e.target.value)}
                placeholder="t.ex. ny bil, renovering, semester"
                className="kalp-input"
                style={{ width: "100%" }}
              />
            </div>

            <div
              style={{
                marginTop: 14,
                display: "flex",
                gap: 10,
              }}
            >
              {!applyOffer && (
                <button
                  type="button"
                  className="cta-btn"
                  onClick={runApplyCheck}
                  disabled={applyBusy}
                  style={{ padding: "10px 16px" }}
                >
                  {applyBusy ? "Prövar..." : "Pröva utan att binda mig"}
                </button>
              )}
              {applyOffer && applyOffer.approved && !applyOffer.loan_id && (
                <button
                  type="button"
                  className="cta-btn"
                  onClick={acceptApplyOffer}
                  disabled={applyBusy}
                  style={{ padding: "10px 16px" }}
                >
                  {applyBusy
                    ? "Genomför..."
                    : `Godkänn — ta lånet (${SEK(applyOffer.offered_monthly_payment || 0)} kr/mån)`}
                </button>
              )}
              {applyOffer && (
                <button
                  type="button"
                  className="cta-btn ghost"
                  onClick={() => {
                    setApplyOffer(null);
                  }}
                  style={{ padding: "10px 16px" }}
                >
                  Räkna om
                </button>
              )}
            </div>

            {applyError && (
              <div
                style={{
                  marginTop: 10,
                  padding: "8px 12px",
                  background: "rgba(220,38,38,0.08)",
                  borderRadius: 4,
                  color: "#fca5a5",
                  fontFamily: "var(--mono)",
                  fontSize: 11,
                }}
              >
                {applyError}
              </div>
            )}

            {applyOffer && (
              <div
                style={{
                  marginTop: 14,
                  padding: "12px 14px",
                  background: applyOffer.loan_id
                    ? "rgba(34,197,94,0.08)"
                    : applyOffer.approved
                      ? "rgba(34,197,94,0.05)"
                      : "rgba(220,38,38,0.05)",
                  borderRadius: 4,
                  fontFamily: "var(--serif)",
                  fontSize: 13,
                }}
              >
                {applyOffer.loan_id ? (
                  <>
                    <div
                      style={{
                        color: "#6ee7b7",
                        fontWeight: 600,
                        marginBottom: 6,
                      }}
                    >
                      ✓ Lånet är genomfört · saldo finns på ditt konto
                    </div>
                    <div style={{ color: "var(--text-mid)" }}>
                      {applyOffer.lender} · {SEK(applyOffer.offered_monthly_payment || 0)} kr/mån
                      {" "}· ränta {((applyOffer.offered_rate || 0) * 100).toFixed(2)} %
                    </div>
                  </>
                ) : applyOffer.approved ? (
                  <>
                    <div
                      style={{
                        color: "#6ee7b7",
                        fontWeight: 600,
                        marginBottom: 6,
                      }}
                    >
                      ✓ Godkänd av {applyOffer.lender}
                    </div>
                    <div style={{ color: "var(--text-mid)" }}>
                      <strong>Score:</strong> {applyOffer.score} (grad{" "}
                      {applyOffer.grade}) ·{" "}
                      <strong>Ränta:</strong>{" "}
                      {((applyOffer.offered_rate || 0) * 100).toFixed(2)} %
                      {" "}· <strong>Per mån:</strong>{" "}
                      {SEK(applyOffer.offered_monthly_payment || 0)} kr
                      {" "}· <strong>Totalt återbetalas:</strong>{" "}
                      {SEK(applyOffer.offered_total_repay || 0)} kr
                    </div>
                    <div
                      style={{
                        color: "var(--text-dim)",
                        fontSize: 12,
                        marginTop: 6,
                      }}
                    >
                      KALP{" "}
                      {applyOffer.kalp_passed
                        ? `passerad (+${SEK(applyOffer.kalp_left_after_all)} kr/mån kvar efter allt)`
                        : `EJ passerad (saknar ${SEK(Math.abs(applyOffer.kalp_left_after_all))} kr/mån)`}
                    </div>
                  </>
                ) : (
                  <>
                    <div
                      style={{
                        color: "#fca5a5",
                        fontWeight: 600,
                        marginBottom: 6,
                      }}
                    >
                      ✗ Avslag
                    </div>
                    <div style={{ color: "var(--text-mid)" }}>
                      {applyOffer.decline_reason}
                    </div>
                    {applyOffer.score > 0 && (
                      <div
                        style={{
                          color: "var(--text-dim)",
                          fontSize: 12,
                          marginTop: 6,
                        }}
                      >
                        Score: {applyOffer.score} (grad {applyOffer.grade})
                      </div>
                    )}
                  </>
                )}
                {applyOffer.warnings.length > 0 && (
                  <div style={{ marginTop: 10 }}>
                    {applyOffer.warnings.map((w, i) => (
                      <div
                        key={i}
                        style={{
                          color: "#fca5a5",
                          fontSize: 12,
                          marginTop: 4,
                        }}
                      >
                        ⚠ {w}
                      </div>
                    ))}
                  </div>
                )}
                {applyOffer.wellbeing_impact.length > 0 && (
                  <div
                    style={{
                      marginTop: 10,
                      fontSize: 12,
                      color: "var(--text-dim)",
                    }}
                  >
                    Wellbeing-påverkan:{" "}
                    {applyOffer.wellbeing_impact
                      .map(
                        (w) =>
                          `${w.axis} ${w.delta > 0 ? "+" : ""}${w.delta}`,
                      )
                      .join(" · ")}
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        <div className="act-grid">
          <div>
            {/* AMORTERINGSPLAN · senaste 4 mån */}
            <div className="section-eye">CSN · amorteringsplan</div>
            {schedule.length === 0 ? (
              <div
                style={{
                  padding: 20,
                  border: "1px solid var(--line)",
                  borderRadius: 6,
                  fontFamily: "var(--serif)",
                  color: "var(--text-mid)",
                }}
              >
                Inga betalningar registrerade än. När amorteringar dras visas
                de här som månadshändelser.
              </div>
            ) : (
              <div className="tx-list">
                {schedule.map((row, idx) => (
                  <div className="tx-row" key={`${row.month}-${idx}`}>
                    <span className="tx-date">{row.label}</span>
                    <div>
                      <div className="tx-name">
                        Annuitet · {SEK(row.monthly_amount)} kr
                      </div>
                      <div className="tx-name-sub">{row.description}</div>
                    </div>
                    <span className="tx-meta">
                      {row.capital_part != null
                        ? `${SEK(row.capital_part)} kap`
                        : ""}
                    </span>
                    <span className="tx-meta">
                      {row.interest_part != null
                        ? `${SEK(row.interest_part)} ränta`
                        : ""}
                    </span>
                    <span
                      className="tx-meta"
                      style={{
                        color:
                          row.status === "betald"
                            ? "var(--text-mid)"
                            : "var(--warm)",
                      }}
                    >
                      {row.status}
                    </span>
                  </div>
                ))}
              </div>
            )}

            {/* KREDITPRÖVNING · visas bara om vi har riktig data */}
            {credit_factors.length > 0 && (
              <>
            <div className="section-eye" style={{ marginTop: 24 }}>
              Kreditprövning · av dig själv som låntagare
            </div>
            <div className="biz-table">
              <div className="biz-table-row head">
                <span>Faktor</span>
                <span>Ditt värde</span>
                <span>Bedömning</span>
              </div>
              {credit_factors.map((f, idx) => (
                <div className="biz-table-row" key={idx}>
                  <div>
                    <div className="biz-factor-name">{f.factor}</div>
                    <div className="biz-factor-detail">{f.detail}</div>
                  </div>
                  <span className={`biz-factor-value ${f.severity}`}>
                    {f.value}
                  </span>
                  <span
                    className={`biz-factor-assess${
                      f.severity === "good" ? " good" : ""
                    }`}
                  >
                    {f.assessment}
                  </span>
                </div>
              ))}
            </div>
              </>
            )}

            {/* KALP-RÄKNARE · eleven simulerar lånebelopp */}
            <div className="section-eye" style={{ marginTop: 24 }}>
              KALP-räknare · stresstest 7 %
            </div>
            <div
              style={{
                background: "rgba(15, 21, 37, 0.7)",
                border: "1px solid var(--line)",
                borderRadius: 6,
                padding: "20px 24px",
                marginBottom: 16,
              }}
            >
              <div
                style={{
                  fontFamily: "var(--serif)",
                  fontSize: 14,
                  color: "var(--text-mid)",
                  marginBottom: 14,
                }}
              >
                Räkna om du klarar månadskostnaden vid 7 % stresstest
                (Finansinspektionens riktvärde) givet din inkomst, hyra
                och Konsumentverkets levnadsschablon.
              </div>
              <div
                style={{
                  display: "flex",
                  gap: 12,
                  flexWrap: "wrap",
                  alignItems: "end",
                  marginBottom: 14,
                }}
              >
                <label
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    gap: 4,
                    flex: "1 1 180px",
                  }}
                >
                  <span
                    style={{
                      fontFamily: "var(--mono)",
                      fontSize: 9.5,
                      color: "var(--text-mid)",
                      letterSpacing: "1.2px",
                      textTransform: "uppercase",
                    }}
                  >
                    Lånebelopp (kr)
                  </span>
                  <input
                    type="number"
                    value={kalpAmount}
                    onChange={(e) => setKalpAmount(e.target.value)}
                    style={{
                      background: "rgba(255, 255, 255, 0.04)",
                      border: "1px solid var(--line-strong)",
                      color: "#fff",
                      padding: "8px 12px",
                      borderRadius: 4,
                      fontFamily: "var(--mono)",
                      fontSize: 14,
                    }}
                  />
                </label>
                <label
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    gap: 4,
                    flex: "0 0 140px",
                  }}
                >
                  <span
                    style={{
                      fontFamily: "var(--mono)",
                      fontSize: 9.5,
                      color: "var(--text-mid)",
                      letterSpacing: "1.2px",
                      textTransform: "uppercase",
                    }}
                  >
                    Löptid (mån)
                  </span>
                  <input
                    type="number"
                    value={kalpTerm}
                    onChange={(e) => setKalpTerm(e.target.value)}
                    style={{
                      background: "rgba(255, 255, 255, 0.04)",
                      border: "1px solid var(--line-strong)",
                      color: "#fff",
                      padding: "8px 12px",
                      borderRadius: 4,
                      fontFamily: "var(--mono)",
                      fontSize: 14,
                    }}
                  />
                </label>
                <button
                  type="button"
                  className="cta-btn"
                  disabled={kalpRunning}
                  onClick={runKalp}
                  style={{ marginTop: 0 }}
                >
                  {kalpRunning ? "Räknar…" : "Räkna KALP"}
                </button>
              </div>
              {kalpError && (
                <div
                  style={{
                    fontFamily: "var(--mono)",
                    fontSize: 11,
                    color: "#fca5a5",
                    marginBottom: 8,
                  }}
                >
                  {kalpError}
                </div>
              )}
              {kalpResult && (
                <div
                  style={{
                    background: kalpResult.passed
                      ? "rgba(110, 231, 183, 0.06)"
                      : "rgba(220, 76, 43, 0.06)",
                    border: `1px solid ${
                      kalpResult.passed
                        ? "rgba(110, 231, 183, 0.3)"
                        : "rgba(220, 76, 43, 0.3)"
                    }`,
                    borderRadius: 6,
                    padding: 14,
                    fontFamily: "var(--serif)",
                    fontSize: 14,
                    lineHeight: 1.5,
                  }}
                >
                  <div
                    style={{
                      fontFamily: "var(--mono)",
                      fontSize: 10,
                      letterSpacing: "1.2px",
                      textTransform: "uppercase",
                      color: kalpResult.passed ? "#6ee7b7" : "#fda594",
                      marginBottom: 6,
                    }}
                  >
                    {kalpResult.passed
                      ? "● Passerad — du klarar stresstestet"
                      : "● Underkänd — månadskostnaden är för hög"}
                  </div>
                  <div>
                    Inkomst <strong>{SEK(kalpResult.monthly_income_net)} kr</strong> ·
                    hyra <strong>{SEK(kalpResult.monthly_housing)}</strong> ·
                    levnadsschablon{" "}
                    <strong>
                      {SEK(kalpResult.monthly_consumer_schablon)}
                    </strong>{" "}
                    · befintlig skuld{" "}
                    <strong>
                      {SEK(kalpResult.monthly_existing_debt_payments)}
                    </strong>
                    .
                  </div>
                  <div style={{ marginTop: 6 }}>
                    Lånekostnad vid stress 7 %:{" "}
                    <strong>
                      {SEK(kalpResult.monthly_loan_payment_at_stress)} kr/mån
                    </strong>
                  </div>
                  <div style={{ marginTop: 6 }}>
                    Kvar att leva på:{" "}
                    <strong
                      style={{
                        color: kalpResult.passed ? "#6ee7b7" : "#fda594",
                      }}
                    >
                      {SEK(kalpResult.monthly_left_after_all)} kr/mån
                    </strong>
                  </div>
                </div>
              )}
            </div>

            {/* PEDAGOGIK */}
            <div className="peda">
              <div className="peda-eye">Pedagogik · vad du lär dig här</div>
              <div className="peda-h">
                Inte alla lån är <em>lika</em>.
              </div>
              <p className="peda-prose">
                CSN-räntan är cirka 1/4 av bolåneräntan och 1/10 av
                blanco-låneräntan. Bolån är dyrare men finansierar tillgång
                (bostad). Privatlån är dyrast och oftast onödigt. Sms-lån är
                finansiell rovdrift. Lär dig skilja på{" "}
                <code>billig skuld</code> (CSN, bolån mot bostad),{" "}
                <code>medel</code> (billån mot bil), och{" "}
                <code>dyr skuld</code> (kreditkort, blanco, sms-lån).
              </p>
              <ul className="peda-bullets">
                <li className="peda-bullet">
                  <strong>Annuitet</strong>Samma månadsbelopp hela tiden —
                  ränta minskar, amortering ökar.
                </li>
                <li className="peda-bullet">
                  <strong>Rak amortering</strong>Samma kapital varje gång —
                  månadskostnad sjunker.
                </li>
                <li className="peda-bullet">
                  <strong>Effektiv ränta</strong>Inkluderar avgifter. Den
                  enda räntan att jämföra med.
                </li>
                <li className="peda-bullet">
                  <strong>UC-score</strong>Kreditupplysning. A–E. För många
                  påbörjade ansökningar = sänker.
                </li>
              </ul>
              <div className="peda-concepts">
                <span className="peda-concept">Annuitet</span>
                <span className="peda-concept">Effektiv ränta</span>
                <span className="peda-concept">Skuldkvot</span>
                <span className="peda-concept">Belåningsgrad</span>
                <span className="peda-concept">UC-score</span>
                <span className="peda-concept">Kronofogden</span>
                <span className="peda-concept">Räntegolv</span>
              </div>
              <div className="peda-tip">
                Lånekalkylatorn (verktyg 06) låter dig simulera "vad händer
                om jag amorterar 500 extra/mån i 5 år?" För CSN: lite. För
                bolån vid 4 %: mycket. Räkna alltid innan du beslutar.
              </div>
            </div>
          </div>

          <aside>
            <div className="side-card">
              <div className="side-card-eye">Ränteavdrag</div>
              <div className="side-card-h">
                30 % <em>av räntan</em>
              </div>
              <div className="side-card-meta">
                Räntor på CSN och bolån ger 30 % skatteavdrag (under 100k).
                Syns i din deklaration.
              </div>
              <a
                className="side-card-link"
                onClick={(e) => {
                  e.preventDefault();
                  navigate("/v2/skatten");
                }}
                href="#"
              >
                Se deklarationen ↗
              </a>
            </div>
            <div className="side-card">
              <div className="side-card-eye">Snabbamortering</div>
              <div className="side-card-h">
                Beror på <em>räntan</em>
              </div>
              <div className="side-card-meta">
                Att amortera extra på ett lån ger en "garanterad avkastning"
                lika hög som räntan. Jämför mot vad du kan tjäna i ISK-fond
                (~7 % real avk. historiskt) innan du beslutar.
              </div>
            </div>
            <div className="side-card">
              <div className="side-card-eye">Befrielse vid arbetslöshet</div>
              <div className="side-card-h">Möjlig</div>
              <div className="side-card-meta">
                CSN ger amorteringsbefrielse vid arbetslöshet, sjukdom,
                föräldraledighet. Pausa istället för missa.
              </div>
            </div>
            <div className="side-card warning">
              <div className="side-card-eye">Varning · sms-lån</div>
              <div className="side-card-h">
                <em>20–40 %</em> ränta
              </div>
              <div className="side-card-meta">
                Många unga vuxna fastnar i sms-lån för impulsköp. Effektiv
                ränta + ev. UC-anmärkning ger livslång ekonomisk skuldfälla.
                Aldrig.
              </div>
            </div>
          </aside>
        </div>
      </div>
    </div>
  );
}
