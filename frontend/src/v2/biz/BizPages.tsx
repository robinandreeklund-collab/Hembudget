/**
 * Företagsläget · 5 detalj-vyer (Bug #7-utbyggnad).
 *
 * BizBokforing  · /v2/foretag/bokforing
 * BizFakturor   · /v2/foretag/fakturor (inkl. kunder)
 * BizLon        · /v2/foretag/lon (lön till mig själv, AB)
 * BizMoms       · /v2/foretag/moms (kvartalsdeklaration)
 * BizBolagsskatt · /v2/foretag/bolagsskatt (årsprognos)
 * BizInstallningar · /v2/foretag/installningar
 */
import { useEffect, useState, type ReactNode } from "react";
import {
  bizApi,
  type Company,
  type CompanyCustomer,
  type CompanyInvoice,
  type CompanyOwnerSalary,
  type CompanyTransaction,
  type CorporateTax,
  type VatPeriod,
} from "./api";
import { BizActorShell } from "./BizActorShell";
import "./biz.css";


const SEK = (n: number) =>
  new Intl.NumberFormat("sv-SE", { maximumFractionDigits: 0 }).format(n);

const TODAY = () => new Date().toISOString().slice(0, 10);


// === Shared compact-shell wrapper med actor-shell-defaults ===
// (för sub-pages som inte har en dedikerad actor-vy med custom title/meta)

function BizShell({ title, eye, children }: {
  title: string; eye: string; children: ReactNode;
}) {
  return (
    <BizActorShell
      pillLabel={eye}
      title={title}
    >
      {children}
    </BizActorShell>
  );
}


// === BIZ BOKFORING (intäkter & utgifter) ===

export function BizBokforing() {
  const [txs, setTxs] = useState<CompanyTransaction[]>([]);
  const [showAdd, setShowAdd] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const refresh = () => {
    bizApi.listTransactions(200).then(setTxs).catch((e) => setErr(String(e)));
  };
  useEffect(() => { refresh(); }, []);

  const incomeSum = txs.filter((t) => t.kind === "income")
    .reduce((acc, t) => acc + t.amount_excl_vat, 0);
  const expenseSum = txs.filter((t) => t.kind === "expense" || t.kind === "salary")
    .reduce((acc, t) => acc + t.amount_excl_vat, 0);
  const result = incomeSum - expenseSum;
  const margin = incomeSum > 0 ? Math.round((result / incomeSum) * 100) : 0;

  // Pedagogiskt: t-konto-mappning från transaction-kategori till BAS-kontoplan
  function basAccounts(t: CompanyTransaction): string {
    if (t.kind === "income") return "1510 D / 3000 + 2611 K";
    if (t.kind === "salary") return "7210 D / 1930 + 2710 K";
    if (t.kind === "vat_payment") return "2650 D / 1930 K";
    if (t.kind === "tax_payment") return "2510 D / 1930 K";
    // expense
    const cat = (t.category || "").toLowerCase();
    if (cat.includes("hyra") || cat.includes("lokal")) return "5010 D / 1930 K";
    if (cat.includes("telefon") || cat.includes("internet")) return "6212 D / 1930 K";
    if (cat.includes("kontor") || cat.includes("material")) return "6110 D / 1930 K";
    if (cat.includes("dator") || cat.includes("möbler") || cat.includes("inventari"))
      return "1220 D + 2641 D / 1930 K";
    return "5610 D + 2641 D / 1930 K";
  }

  return (
    <BizActorShell
      pillLabel="Verktyg · biz · Bokföring"
      title={
        <>
          Verifikat <em>just nu</em>.
        </>
      }
      subtitle={
        txs.length === 0
          ? "Inga verifikat ännu — börja med att lägga till en transaktion"
          : `Dubbel bokföring · BAS 2024 förenklad (~30 konton) · ${txs.length} verifikat`
      }
      meta={
        <>
          Verifikat totalt: <strong>{txs.length}</strong>
          <br />
          Intäkter: <strong>{SEK(incomeSum)} kr</strong>
          <br />
          Senaste:{" "}
          <strong>
            {txs[0] ? `A${txs[0].id} · ${txs[0].occurred_on}` : "—"}
          </strong>
        </>
      }
    >
      {err && <ErrorBanner msg={err} />}

      <div className="cc-summary" style={{ gridTemplateColumns: "repeat(3, 1fr)" }}>
        <div className="cc-stat">
          <div className="cc-stat-eye">Intäkter</div>
          <div className="cc-stat-num">
            <em style={{ color: "#6ee7b7" }}>{SEK(incomeSum)}</em> kr
          </div>
          <div className="cc-stat-sub">3000 Försäljning ex moms</div>
        </div>
        <div className="cc-stat">
          <div className="cc-stat-eye">Kostnader</div>
          <div className="cc-stat-num">−{SEK(expenseSum)} kr</div>
          <div className="cc-stat-sub">5610 · 1220 · 6991 · …</div>
        </div>
        <div className="cc-stat">
          <div className="cc-stat-eye">Resultat</div>
          <div
            className="cc-stat-num warm"
            style={{ color: result >= 0 ? "#6ee7b7" : "#fda594" }}
          >
            <em>
              {result >= 0 ? "+ " : "− "}
              {SEK(Math.abs(result))}
            </em>{" "}
            kr
          </div>
          <div className="cc-stat-sub">marginal {margin} %</div>
        </div>
      </div>

      <div className="section-eye" style={{ color: "#c7d2fe" }}>
        Senaste verifikat (T-konton)
      </div>
      {txs.length === 0 ? (
        <div className="biz-empty">
          Inga transaktioner än. Lägg till intäkter/utgifter med
          knappen nedan.
        </div>
      ) : (
        <div className="biz-table-grid">
          <div
            className="biz-table-grid-row head"
            style={{
              gridTemplateColumns: "60px 80px 1.4fr 1.2fr 100px 80px 32px",
            }}
          >
            <span>Ver</span>
            <span>Datum</span>
            <span>Berör</span>
            <span>Konton (D / K)</span>
            <span>Belopp</span>
            <span>Status</span>
            <span></span>
          </div>
          {txs.slice(0, 30).map((t) => (
            <div
              key={t.id}
              className="biz-table-grid-row"
              style={{
                gridTemplateColumns: "60px 80px 1.4fr 1.2fr 100px 80px 32px",
              }}
            >
              <span
                style={{
                  fontFamily: "JetBrains Mono, monospace",
                  fontSize: 10,
                }}
              >
                A{t.id}
              </span>
              <span
                style={{
                  fontFamily: "JetBrains Mono, monospace",
                  fontSize: 10,
                  color: "rgba(255,255,255,0.55)",
                }}
              >
                {t.occurred_on}
              </span>
              <div>
                <div
                  style={{
                    fontSize: 13,
                    color: "#fff",
                    fontFamily: "Source Serif 4, Georgia, serif",
                  }}
                >
                  {t.description || t.category}
                </div>
                <div
                  style={{
                    fontFamily: "JetBrains Mono, monospace",
                    fontSize: 9,
                    color: "rgba(255,255,255,0.4)",
                    marginTop: 2,
                  }}
                >
                  {t.kind === "income" ? "Intäkt"
                    : t.kind === "expense" ? "Utgift"
                    : t.kind === "salary" ? "Lön"
                    : t.kind === "vat_payment" ? "Moms in"
                    : "Skatt"}
                  {t.category ? ` · ${t.category}` : ""}
                </div>
              </div>
              <span
                style={{
                  fontFamily: "JetBrains Mono, monospace",
                  fontSize: 10,
                  color: "rgba(255,255,255,0.55)",
                }}
              >
                {basAccounts(t)}
              </span>
              <span
                style={{
                  fontFamily: "Source Serif 4, Georgia, serif",
                  fontStyle: "italic",
                  color: t.kind === "income" ? "#6ee7b7" : "#fff",
                  fontWeight: 700,
                }}
              >
                {SEK(t.amount_excl_vat + (t.vat_amount || 0))}
              </span>
              <span className="biz-status paid">Klar</span>
              <button
                onClick={async () => {
                  if (!confirm("Radera verifikat A" + t.id + "?")) return;
                  await bizApi.deleteTransaction(t.id);
                  refresh();
                }}
                className="biz-btn"
                style={{
                  padding: "2px 6px",
                  fontSize: 10,
                  color: "#fda594",
                  borderColor: "rgba(248,113,113,0.3)",
                }}
                title="Radera"
              >
                ✕
              </button>
            </div>
          ))}
        </div>
      )}

      <article className="biz-cta-card">
        <div className="biz-cta-eye">Bokför nytt</div>
        <div className="biz-cta-h">
          Lägg till en <em>transaktion</em>.
        </div>
        <p className="biz-cta-prose">
          Välj kategori (intäkt, utgift, lön, skatte/moms-betalning) och
          summa exkl moms. Systemet räknar moms automatiskt och föreslår
          BAS-konton enligt kategorin.
        </p>
        <button
          onClick={() => setShowAdd(true)}
          className="biz-btn solid"
          style={{ marginTop: 4 }}
        >
          + Ny transaktion
        </button>
      </article>

      <div className="peda">
        <div className="peda-eye">Pedagogik · vad du lär dig här</div>
        <div className="peda-h">
          Bokföring är <em>språk</em>, inte aritmetik.
        </div>
        <p className="peda-prose">
          Varje affärshändelse skrivs i två konton (debet + kredit) som
          balanserar. Faktura skickad: <strong>1510 Kundfordran D · 3000
          Försäljning K · 2611 Moms ut K</strong>. Pengarna kommer in:{" "}
          <strong>1930 Bank D · 1510 Kundfordran K</strong>. Du <em>ser</em>{" "}
          alla händelser samlade — det är där du faktiskt förstår var
          pengarna går.
        </p>
        <ul className="peda-bullets">
          <li>
            <strong>Debet / kredit</strong>Inte +/−. Konto-typ avgör.
            Tillgång ↑ = D. Skuld ↑ = K.
          </li>
          <li>
            <strong>BAS-kontoplan</strong>Standard i Sverige · ~ 30 konton
            räcker för en ung firma.
          </li>
          <li>
            <strong>T-konto</strong>Ett konto har två sidor. Saldo = D − K
            (eller K − D).
          </li>
          <li>
            <strong>Resultat</strong>Intäkter − kostnader. Visas i
            resultaträkning.
          </li>
        </ul>
        <div className="peda-concepts">
          <span className="peda-concept">Debet</span>
          <span className="peda-concept">Kredit</span>
          <span className="peda-concept">T-konto</span>
          <span className="peda-concept">Verifikat</span>
          <span className="peda-concept">Balansräkning</span>
          <span className="peda-concept">Resultaträkning</span>
        </div>
        <div className="peda-tip">
          Lärare bedömer din portfolio inte för enskilda kontoval — utan
          helheten. Att du klassar konsekvent över tid är värt mer än att
          alltid hitta exakt rätt BAS-konto.
        </div>
      </div>

      {showAdd && (
        <AddTransactionModal
          onClose={() => setShowAdd(false)}
          onAdded={() => { setShowAdd(false); refresh(); }}
        />
      )}
    </BizActorShell>
  );
}

function AddTransactionModal({ onClose, onAdded }: { onClose: () => void; onAdded: () => void }) {
  const [occurred, setOccurred] = useState(TODAY());
  const [kind, setKind] = useState("income");
  const [category, setCategory] = useState("Försäljning");
  const [description, setDescription] = useState("");
  const [amount, setAmount] = useState(0);
  const [vatRate, setVatRate] = useState(0.25);
  const [busy, setBusy] = useState(false);

  return (
    <Modal onClose={onClose} title="Ny transaktion">
      <Field label="Datum">
        <input type="date" value={occurred} onChange={(e) => setOccurred(e.target.value)} style={input()} />
      </Field>
      <Field label="Typ">
        <select value={kind} onChange={(e) => setKind(e.target.value)} style={input()}>
          <option value="income">Intäkt</option>
          <option value="expense">Utgift</option>
        </select>
      </Field>
      <Field label="Kategori">
        <input value={category} onChange={(e) => setCategory(e.target.value)} style={input()} placeholder="ex: Tjänster, Material, Hyra" />
      </Field>
      <Field label="Beskrivning">
        <input value={description} onChange={(e) => setDescription(e.target.value)} style={input()} />
      </Field>
      <Field label="Belopp exkl. moms">
        <input type="number" value={amount} onChange={(e) => setAmount(parseFloat(e.target.value) || 0)} style={input()} />
      </Field>
      <Field label="Momssats">
        <select value={vatRate} onChange={(e) => setVatRate(parseFloat(e.target.value))} style={input()}>
          <option value="0.25">25 % (standard)</option>
          <option value="0.12">12 % (livsmedel/restaurang)</option>
          <option value="0.06">6 % (kultur/transport)</option>
          <option value="0">0 % (utlandsförsäljning)</option>
        </select>
      </Field>
      <div style={{ color: "rgba(255,255,255,0.6)", fontSize: "0.85rem", marginTop: 10 }}>
        Moms: {SEK(amount * vatRate)} kr · Totalt inkl moms: <strong>{SEK(amount * (1 + vatRate))} kr</strong>
      </div>
      <button
        disabled={busy || !description || amount <= 0}
        onClick={async () => {
          setBusy(true);
          try {
            await bizApi.addTransaction({
              occurred_on: occurred, kind, category, description,
              amount_excl_vat: amount, vat_rate: vatRate,
            });
            onAdded();
          } finally { setBusy(false); }
        }}
        style={{ ...btnPrimary(), marginTop: 18 }}
      >
        {busy ? "Sparar…" : "Spara"}
      </button>
    </Modal>
  );
}


// === BIZ FAKTUROR (kunder + invoices) ===

export function BizFakturor() {
  const [invoices, setInvoices] = useState<CompanyInvoice[]>([]);
  const [customers, setCustomers] = useState<CompanyCustomer[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [showAddInv, setShowAddInv] = useState(false);
  const [showAddCust, setShowAddCust] = useState(false);

  const refresh = () => {
    bizApi.listInvoices().then(setInvoices).catch((e) => setErr(String(e)));
    bizApi.listCustomers().then(setCustomers).catch(() => undefined);
  };
  useEffect(() => { refresh(); }, []);

  const today = TODAY();
  const totalNet = invoices.reduce((acc, i) => acc + i.amount_excl_vat, 0);
  const totalIncl = invoices.reduce((acc, i) => acc + i.total_incl_vat, 0);
  const sent = invoices.filter((i) => i.status === "sent").length;
  const paid = invoices.filter((i) => i.status === "paid").length;
  const drafts = invoices.filter((i) => i.status === "draft").length;
  const overdue = invoices.filter(
    (i) => i.status === "sent" && i.due_on < today,
  );
  const dueToday = invoices.filter(
    (i) => i.status === "sent" && i.due_on === today,
  );
  const outstanding = invoices
    .filter((i) => i.status === "sent")
    .reduce((acc, i) => acc + i.total_incl_vat, 0);
  const paidTotal = invoices
    .filter((i) => i.status === "paid")
    .reduce((acc, i) => acc + i.total_incl_vat, 0);

  return (
    <BizActorShell
      pillLabel="Aktör · biz · Kundfakturor"
      title={
        <>
          Fakturera <em>kunden</em>.
        </>
      }
      subtitle={
        invoices.length === 0
          ? "Skapa din första kund och faktura"
          : `${sent} utskickade · ${paid} betalda${
              dueToday.length > 0 ? ` · ${dueToday.length} förfaller idag` : ""
            }${drafts > 0 ? ` · ${drafts} utkast` : ""}`
      }
      meta={
        <>
          {dueToday.length > 0 ? (
            <>
              Förfaller idag:{" "}
              <strong style={{ color: "#dc4c2b" }}>
                {dueToday.length} st
              </strong>
              <br />
            </>
          ) : (
            <>
              Förfaller idag: <strong>0</strong>
              <br />
            </>
          )}
          Total utestående: <strong>{SEK(outstanding)} kr</strong>
          <br />
          Inbetalt: <strong>{SEK(paidTotal)} kr</strong>
        </>
      }
    >
      {err && <ErrorBanner msg={err} />}

      <div className="cc-summary">
        <div className="cc-stat">
          <div className="cc-stat-eye">Fakturerat hittills</div>
          <div className="cc-stat-num">
            <em>{SEK(totalNet)}</em> kr
          </div>
          <div className="cc-stat-sub">{invoices.length} fakturor</div>
        </div>
        <div className="cc-stat">
          <div className="cc-stat-eye">Inbetalt</div>
          <div className="cc-stat-num" style={{ color: "#6ee7b7" }}>
            {SEK(paidTotal)} kr
          </div>
          <div className="cc-stat-sub">
            {paid} av {invoices.length} fakturor
          </div>
        </div>
        <div className="cc-stat">
          <div className="cc-stat-eye">Utestående</div>
          <div className="cc-stat-num" style={{ color: "#fbbf24" }}>
            {SEK(outstanding)} kr
          </div>
          <div className="cc-stat-sub">{sent} öppna</div>
        </div>
        <div className="cc-stat">
          <div className="cc-stat-eye">Försenade</div>
          <div className="cc-stat-num warm">
            <em>{overdue.length}</em>
          </div>
          <div className="cc-stat-sub">
            {overdue.length === 0
              ? "ingen försening"
              : `total ${SEK(overdue.reduce((a, i) => a + i.total_incl_vat, 0))} kr`}
          </div>
        </div>
      </div>

      {customers.length === 0 && (
        <div
          style={{
            padding: 14,
            background: "rgba(251,191,36,0.1)",
            border: "1px solid rgba(251,191,36,0.3)",
            borderRadius: 8,
            marginBottom: 14,
            color: "#fbbf24",
            fontFamily: "Source Serif 4, Georgia, serif",
          }}
        >
          Skapa minst en kund innan du kan fakturera.
        </div>
      )}

      <div
        className="section-eye"
        style={{ color: "#c7d2fe", marginTop: 8 }}
      >
        Alla fakturor
      </div>
      {invoices.length === 0 ? (
        <div className="biz-empty">
          Inga fakturor än. Skapa din första nedan.
        </div>
      ) : (
        <div className="biz-table-grid">
          <div
            className="biz-table-grid-row head"
            style={{
              gridTemplateColumns:
                "60px 80px 1.6fr 100px 110px 100px 80px",
            }}
          >
            <span>#</span>
            <span>Datum</span>
            <span>Kund / specifikation</span>
            <span>Belopp</span>
            <span>Förfaller</span>
            <span>Status</span>
            <span></span>
          </div>
          {invoices.map((inv) => {
            const isOverdue = inv.status === "sent" && inv.due_on < today;
            const isDueToday = inv.status === "sent" && inv.due_on === today;
            return (
              <div
                key={inv.id}
                className={`biz-table-grid-row${isOverdue || isDueToday ? " alert" : ""}`}
                style={{
                  gridTemplateColumns:
                    "60px 80px 1.6fr 100px 110px 100px 80px",
                }}
              >
                <span
                  style={{
                    fontFamily: "JetBrains Mono, monospace",
                    fontSize: 10,
                    color: isOverdue || isDueToday
                      ? "#dc4c2b"
                      : "rgba(255,255,255,0.4)",
                  }}
                >
                  {inv.invoice_number || "—"}
                </span>
                <span
                  style={{
                    fontFamily: "JetBrains Mono, monospace",
                    fontSize: 10,
                    color: "rgba(255,255,255,0.55)",
                  }}
                >
                  {inv.status === "draft"
                    ? "— · utkast"
                    : inv.issued_on}
                </span>
                <div>
                  <div
                    style={{
                      fontFamily: "Source Serif 4, Georgia, serif",
                      fontSize: 14,
                      color: inv.status === "draft"
                        ? "rgba(255,255,255,0.55)"
                        : "#fff",
                      fontWeight: 700,
                    }}
                  >
                    {inv.customer_name}
                    {inv.status === "draft" && (
                      <em
                        style={{
                          color: "rgba(255,255,255,0.4)",
                          fontSize: 11,
                          fontStyle: "italic",
                          marginLeft: 6,
                        }}
                      >
                        (utkast — ej utskickad)
                      </em>
                    )}
                  </div>
                  <div
                    style={{
                      fontFamily: "JetBrains Mono, monospace",
                      fontSize: 9,
                      color: "rgba(255,255,255,0.4)",
                      marginTop: 2,
                    }}
                  >
                    {inv.description}
                    {inv.amount_excl_vat > 0 && (
                      <>
                        {" · "}
                        {SEK(inv.amount_excl_vat)} ex moms
                        {inv.vat_amount > 0 && (
                          <> · {SEK(inv.vat_amount)} moms</>
                        )}
                      </>
                    )}
                  </div>
                </div>
                <span
                  style={{
                    fontFamily: "Source Serif 4, Georgia, serif",
                    fontStyle: "italic",
                    color: inv.status === "paid"
                      ? "#6ee7b7"
                      : inv.status === "draft"
                      ? "rgba(255,255,255,0.4)"
                      : isOverdue
                      ? "#dc4c2b"
                      : "#fbbf24",
                    fontWeight: 700,
                  }}
                >
                  {inv.total_incl_vat > 0
                    ? `${SEK(inv.total_incl_vat)} kr`
                    : "— kr"}
                </span>
                <span
                  style={{
                    fontFamily: "JetBrains Mono, monospace",
                    fontSize: 10,
                    color: isDueToday
                      ? "#dc4c2b"
                      : isOverdue
                      ? "#dc4c2b"
                      : inv.status === "paid"
                      ? "rgba(255,255,255,0.55)"
                      : "rgba(255,255,255,0.55)",
                    fontWeight: isDueToday ? 700 : 400,
                  }}
                >
                  {inv.status === "paid"
                    ? `betald ${inv.paid_on || ""}`
                    : inv.status === "draft"
                    ? "—"
                    : isDueToday
                    ? "förfaller IDAG"
                    : isOverdue
                    ? `${inv.due_on} (sen)`
                    : `förfaller ${inv.due_on}`}
                </span>
                <span
                  className={`biz-status ${
                    inv.status === "paid" ? "paid"
                      : inv.status === "sent" ? (isOverdue ? "overdue" : "sent")
                      : "draft"
                  }`}
                >
                  {inv.status === "paid"
                    ? "Betald"
                    : inv.status === "sent"
                    ? isOverdue ? "Sen" : "Skickad"
                    : "Utkast"}
                </span>
                {inv.status === "sent" && (
                  <button
                    onClick={async () => {
                      await bizApi.markInvoicePaid(inv.id);
                      refresh();
                    }}
                    className="biz-btn"
                    style={{ padding: "4px 8px", fontSize: 10 }}
                  >
                    Betald ✓
                  </button>
                )}
                {inv.status !== "sent" && <span></span>}
              </div>
            );
          })}
        </div>
      )}

      {/* CTA-card · skapa ny faktura / ny kund */}
      <article className="biz-cta-card">
        <div className="biz-cta-eye">Skapa nytt</div>
        <div className="biz-cta-h">
          {customers.length === 0
            ? <>Lägg till första <em>kunden</em>.</>
            : <>Fakturera nästa <em>kund</em>.</>}
        </div>
        <p className="biz-cta-prose">
          Fakturan får automatiskt fakturanummer + OCR + förfallodatum 30
          dgr framåt. PDF skapas automatiskt och kan postlådas till kunden.
        </p>
        <div style={{ display: "flex", gap: 8, marginTop: 14 }}>
          <button
            onClick={() => setShowAddInv(true)}
            className="biz-btn solid"
            disabled={customers.length === 0}
          >
            + Ny faktura
          </button>
          <button
            onClick={() => setShowAddCust(true)}
            className="biz-btn"
          >
            + Ny kund
          </button>
        </div>
      </article>

      {/* Pedagogik */}
      <div className="peda">
        <div className="peda-eye">Pedagogik · vad du lär dig här</div>
        <div className="peda-h">
          Faktura är ett <em>juridiskt dokument</em>.
        </div>
        <p className="peda-prose">
          Det är inte ett mejl med belopp. Den måste innehålla{" "}
          <strong>fakturanummer</strong>, <strong>fakturadatum</strong>,{" "}
          <strong>förfallodatum</strong>, <strong>F-skatt-uppgift</strong>,{" "}
          <strong>OCR-nummer</strong>, specifikation av tjänsten, ev.{" "}
          <strong>moms 25 %</strong> (på tjänster). Saknas något kan kunden
          bestrida. Allt registreras hos Skatteverket via{" "}
          <em>kontrolluppgift</em> nästa år.
        </p>
        <ul className="peda-bullets">
          <li>
            <strong>Moms in vs ut</strong>Du tar ut 25 % på faktura,
            redovisar månadsvis. Skillnaden = nettomoms.
          </li>
          <li>
            <strong>Påminnelse</strong>Efter 14 dagar skicka påminnelse + 60
            kr avgift. Efter 30 dgr → inkasso.
          </li>
          <li>
            <strong>Dröjsmålsränta</strong>Referensränta + 8 % på obetalt
            belopp. Du har rätt — men måste fakturera den.
          </li>
          <li>
            <strong>Bokföringspost</strong>Faktura skickad → kundfordran ↑,
            ej intäkt än. Betald → bank ↑, fordran ↓.
          </li>
        </ul>
        <div className="peda-concepts">
          <span className="peda-concept">Kundfordran</span>
          <span className="peda-concept">Moms-redovisning</span>
          <span className="peda-concept">F-skatt</span>
          <span className="peda-concept">OCR-nummer</span>
          <span className="peda-concept">Periodisering</span>
          <span className="peda-concept">Inkasso</span>
        </div>
        <div className="peda-tip">
          När en kund betalar — bokningen sker automatiskt: kundfordran ↓,
          företagskonto ↑. Pentagon-axeln "Likviditet" tippar upp samtidigt.
          Total fakturerat exkl moms är{" "}
          <em>{SEK(totalNet)} kr</em>; inkl moms{" "}
          <em>{SEK(totalIncl)} kr</em>.
        </div>
      </div>

      {showAddInv && (
        <AddInvoiceModal
          customers={customers}
          onClose={() => setShowAddInv(false)}
          onAdded={() => { setShowAddInv(false); refresh(); }}
        />
      )}
      {showAddCust && (
        <AddCustomerModal
          onClose={() => setShowAddCust(false)}
          onAdded={() => { setShowAddCust(false); refresh(); }}
        />
      )}
    </BizActorShell>
  );
}

function AddCustomerModal({ onClose, onAdded }: { onClose: () => void; onAdded: () => void }) {
  const [name, setName] = useState("");
  const [orgNr, setOrgNr] = useState("");
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);

  return (
    <Modal onClose={onClose} title="Ny kund">
      <Field label="Namn">
        <input value={name} onChange={(e) => setName(e.target.value)} style={input()} placeholder="Företag eller person" />
      </Field>
      <Field label="Org-nr (om företag)">
        <input value={orgNr} onChange={(e) => setOrgNr(e.target.value)} style={input()} placeholder="556677-8899" />
      </Field>
      <Field label="E-post">
        <input value={email} onChange={(e) => setEmail(e.target.value)} style={input()} type="email" />
      </Field>
      <button
        disabled={busy || !name.trim()}
        onClick={async () => {
          setBusy(true);
          try {
            await bizApi.addCustomer({
              name: name.trim(),
              org_number: orgNr.trim() || undefined,
              email: email.trim() || undefined,
              is_private: !orgNr.trim(),
            });
            onAdded();
          } finally { setBusy(false); }
        }}
        style={{ ...btnPrimary(), marginTop: 18 }}
      >
        {busy ? "Sparar…" : "Spara kund"}
      </button>
    </Modal>
  );
}

function AddInvoiceModal({
  customers, onClose, onAdded,
}: { customers: CompanyCustomer[]; onClose: () => void; onAdded: () => void }) {
  const [custId, setCustId] = useState(customers[0]?.id || 0);
  const [issued, setIssued] = useState(TODAY());
  const [due, setDue] = useState(() => {
    const d = new Date(); d.setDate(d.getDate() + 30);
    return d.toISOString().slice(0, 10);
  });
  const [description, setDescription] = useState("");
  const [amount, setAmount] = useState(0);
  const [vatRate, setVatRate] = useState(0.25);
  const [busy, setBusy] = useState(false);

  return (
    <Modal onClose={onClose} title="Ny faktura">
      <Field label="Kund">
        <select value={custId} onChange={(e) => setCustId(parseInt(e.target.value))} style={input()}>
          {customers.map((c) => (
            <option key={c.id} value={c.id}>{c.name}</option>
          ))}
        </select>
      </Field>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
        <Field label="Fakturadatum">
          <input type="date" value={issued} onChange={(e) => setIssued(e.target.value)} style={input()} />
        </Field>
        <Field label="Förfallodag">
          <input type="date" value={due} onChange={(e) => setDue(e.target.value)} style={input()} />
        </Field>
      </div>
      <Field label="Beskrivning">
        <input value={description} onChange={(e) => setDescription(e.target.value)} style={input()} />
      </Field>
      <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: 12 }}>
        <Field label="Belopp exkl. moms">
          <input type="number" value={amount} onChange={(e) => setAmount(parseFloat(e.target.value) || 0)} style={input()} />
        </Field>
        <Field label="Momssats">
          <select value={vatRate} onChange={(e) => setVatRate(parseFloat(e.target.value))} style={input()}>
            <option value="0.25">25 %</option>
            <option value="0.12">12 %</option>
            <option value="0.06">6 %</option>
            <option value="0">0 %</option>
          </select>
        </Field>
      </div>
      <div style={{ color: "rgba(255,255,255,0.6)", fontSize: "0.85rem", marginTop: 10 }}>
        Moms: {SEK(amount * vatRate)} kr · Totalt: <strong>{SEK(amount * (1 + vatRate))} kr</strong>
      </div>
      <button
        disabled={busy || !description || amount <= 0 || !custId}
        onClick={async () => {
          setBusy(true);
          try {
            await bizApi.addInvoice({
              customer_id: custId,
              issued_on: issued, due_on: due,
              description, amount_excl_vat: amount, vat_rate: vatRate,
            });
            onAdded();
          } finally { setBusy(false); }
        }}
        style={{ ...btnPrimary(), marginTop: 18 }}
      >
        {busy ? "Sparar…" : "Skicka faktura"}
      </button>
    </Modal>
  );
}


// === BIZ LON (lön till mig själv, AB) ===

export function BizLon() {
  const [salaries, setSalaries] = useState<CompanyOwnerSalary[]>([]);
  const [showAdd, setShowAdd] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const refresh = () => {
    bizApi.listOwnerSalaries().then(setSalaries).catch((e) => setErr(String(e)));
  };
  useEffect(() => { refresh(); }, []);

  const totalGross = salaries.reduce((acc, s) => acc + s.gross_salary, 0);
  const totalCost = salaries.reduce((acc, s) => acc + s.total_cost_to_company, 0);

  return (
    <BizShell eye="Bolag · 03" title="Lön till mig själv">
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 18 }}>
        <Card label="Total lön (brutto)" value={`${SEK(totalGross)} kr`} color="#c7d2fe" />
        <Card label="Total kostnad bolaget" value={`${SEK(totalCost)} kr`} color="#fbbf24" />
      </div>

      <button onClick={() => setShowAdd(true)} style={btnPrimary()}>
        + Ta ut lön
      </button>

      {showAdd && (
        <PayOwnerSalaryModal
          onClose={() => setShowAdd(false)}
          onPaid={() => { setShowAdd(false); refresh(); }}
        />
      )}

      {err && <ErrorBanner msg={err} />}

      <h2 style={{ color: "white", fontSize: "1.1rem", marginTop: 18, marginBottom: 8 }}>Lönehistorik</h2>
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        {salaries.length === 0 ? (
          <Empty msg="Inga uttag än." />
        ) : (
          salaries.map((s) => (
            <article key={s.id} style={txRow()}>
              <div style={{ minWidth: 90, color: "rgba(255,255,255,0.5)", fontFamily: "JetBrains Mono, monospace", fontSize: "0.8rem" }}>
                {s.paid_on}
              </div>
              <div style={{ flex: 1 }}>
                <strong style={{ color: "white" }}>{SEK(s.gross_salary)} kr brutto</strong>
                <div style={{ color: "rgba(255,255,255,0.5)", fontSize: "0.78rem" }}>
                  Arb.giv.avg {SEK(s.employer_fee_amount)} · Skatt {SEK(s.prel_tax_amount)} · Du fick {SEK(s.net_to_owner)}
                </div>
              </div>
              <div style={{ textAlign: "right", fontFamily: "JetBrains Mono, monospace" }}>
                <strong style={{ color: "#fda594" }}>−{SEK(s.total_cost_to_company)} kr</strong>
                <div style={{ color: "rgba(255,255,255,0.4)", fontSize: "0.75rem" }}>bolagets kostnad</div>
              </div>
            </article>
          ))
        )}
      </div>
    </BizShell>
  );
}

function PayOwnerSalaryModal({ onClose, onPaid }: { onClose: () => void; onPaid: () => void }) {
  const [paidOn, setPaidOn] = useState(TODAY());
  const [gross, setGross] = useState(30000);
  const [isYoung, setIsYoung] = useState(false);
  const [preview, setPreview] = useState<{ employer_fee_amount: number; prel_tax_amount: number; net_to_owner: number; total_cost_to_company: number } | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (gross > 0) {
      bizApi.previewOwnerSalary(gross, isYoung).then(setPreview).catch(() => setPreview(null));
    }
  }, [gross, isYoung]);

  return (
    <Modal onClose={onClose} title="Ta ut lön">
      <Field label="Utbetalningsdatum">
        <input type="date" value={paidOn} onChange={(e) => setPaidOn(e.target.value)} style={input()} />
      </Field>
      <Field label="Bruttolön">
        <input type="number" value={gross} onChange={(e) => setGross(parseInt(e.target.value) || 0)} style={input()} />
      </Field>
      <label style={{ display: "flex", alignItems: "center", gap: 8, color: "rgba(255,255,255,0.7)", marginTop: 12 }}>
        <input type="checkbox" checked={isYoung} onChange={(e) => setIsYoung(e.target.checked)} />
        <span>Jag är 18-24 år (lägre arbetsgivaravgift 19.49 %)</span>
      </label>

      {preview && (
        <div style={{ marginTop: 18, padding: 14, background: "rgba(99,102,241,0.08)", border: "1px solid rgba(99,102,241,0.25)", borderRadius: 8 }}>
          <div style={{ color: "rgba(255,255,255,0.85)", fontSize: "0.9rem" }}>
            Du får ut: <strong style={{ color: "#34d399" }}>{SEK(preview.net_to_owner)} kr netto</strong><br />
            Bolaget betalar: <strong style={{ color: "#fda594" }}>{SEK(preview.total_cost_to_company)} kr</strong> (lön + arb.giv.avg)<br />
            <span style={{ color: "rgba(255,255,255,0.5)", fontSize: "0.8rem" }}>
              Arbetsgivaravgift {SEK(preview.employer_fee_amount)} · Preliminärskatt {SEK(preview.prel_tax_amount)}
            </span>
          </div>
        </div>
      )}

      <button
        disabled={busy || gross <= 0}
        onClick={async () => {
          setBusy(true);
          try {
            await bizApi.payOwnerSalary({ paid_on: paidOn, gross_salary: gross, is_young: isYoung });
            onPaid();
          } finally { setBusy(false); }
        }}
        style={{ ...btnPrimary(), marginTop: 18 }}
      >
        {busy ? "Bokför…" : "Bokför lön"}
      </button>
    </Modal>
  );
}


// === BIZ MOMS ===

export function BizMoms() {
  const [periods, setPeriods] = useState<VatPeriod[]>([]);
  const [previewStart, setPreviewStart] = useState("2026-01-01");
  const [previewEnd, setPreviewEnd] = useState("2026-03-31");
  const [preview, setPreview] = useState<{ output_vat: number; input_vat: number; net_vat: number; n_transactions: number } | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const refresh = () => {
    bizApi.listVatPeriods().then(setPeriods).catch((e) => setErr(String(e)));
  };
  useEffect(() => { refresh(); }, []);

  const runPreview = () => {
    bizApi.previewVat(previewStart, previewEnd).then(setPreview).catch((e) => setErr(String(e)));
  };

  const fileNow = async () => {
    setBusy(true);
    try {
      const period_label = `${previewStart.slice(0, 7)}_to_${previewEnd.slice(0, 7)}`;
      const due = new Date(previewEnd);
      due.setDate(due.getDate() + 42); // 42 dagar efter periodens slut
      await bizApi.fileVat({
        period_label, start_date: previewStart, end_date: previewEnd,
        due_date: due.toISOString().slice(0, 10),
      });
      setPreview(null);
      refresh();
    } catch (e) { setErr(String((e as Error).message || e)); }
    finally { setBusy(false); }
  };

  // Hitta nästa öppna period (= "att betala")
  const nextOpen = periods.find((p) => p.status === "open");
  const nextDue = nextOpen?.due_date || null;
  const nextOutVat = nextOpen?.output_vat || preview?.output_vat || 0;
  const nextInVat = nextOpen?.input_vat || preview?.input_vat || 0;
  const nextNetVat = nextOpen?.net_vat
    ?? preview?.net_vat
    ?? 0;

  return (
    <BizActorShell
      pillLabel="Aktör · biz · Skatteverket"
      title={
        <>
          {nextDue ? (
            <>Moms <em>{nextDue}</em> · F-skatt löpande.</>
          ) : (
            <>Moms &amp; F-skatt — <em>aktuellt läge</em>.</>
          )}
        </>
      }
      subtitle={
        nextOpen
          ? `Period ${nextOpen.start_date.slice(0, 7)} → ${nextOpen.end_date.slice(0, 7)} · F-skatt månadsvis baserat på prognos`
          : "Inga öppna momsperioder · använd förhandsvisning nedan"
      }
      meta={
        <>
          Moms ut: <strong>{SEK(nextOutVat)} kr</strong>
          <br />
          Moms in: <strong>−{SEK(nextInVat)} kr</strong>
          <br />
          {nextDue ? (
            <>
              Att betala {nextDue}:{" "}
              <strong style={{ color: "#fbbf24" }}>
                {SEK(Math.max(0, nextNetVat))} kr
              </strong>
            </>
          ) : (
            <>
              Senaste period: <strong>{periods.length} st inlämnade</strong>
            </>
          )}
        </>
      }
    >
      {err && <ErrorBanner msg={err} />}

      <div className="cc-summary" style={{ gridTemplateColumns: "repeat(3, 1fr)" }}>
        <div className="cc-stat">
          <div className="cc-stat-eye">Utgående moms (period)</div>
          <div className="cc-stat-num">
            <em>{SEK(nextOutVat)}</em> kr
          </div>
          <div className="cc-stat-sub">25 % på din försäljning</div>
        </div>
        <div className="cc-stat">
          <div className="cc-stat-eye">Ingående moms (period)</div>
          <div className="cc-stat-num">−{SEK(nextInVat)} kr</div>
          <div className="cc-stat-sub">25 % på leverantörsfakturor</div>
        </div>
        <div className="cc-stat">
          <div className="cc-stat-eye">
            {nextNetVat >= 0 ? "Att betala" : "Att få tillbaka"}
          </div>
          <div
            className="cc-stat-num warm"
            style={{ color: nextNetVat >= 0 ? "#fbbf24" : "#6ee7b7" }}
          >
            <em>{SEK(Math.abs(nextNetVat))}</em> kr
          </div>
          <div className="cc-stat-sub">utgående minus ingående</div>
        </div>
      </div>

      {/* Förhandsvisa period · CTA-card */}
      <article className="biz-cta-card">
        <div className="biz-cta-eye">Förhandsvisa period</div>
        <div className="biz-cta-h">
          Räkna fram ny moms-period.
        </div>
        <p className="biz-cta-prose">
          Välj start- och slutdatum för perioden — vi summerar utgående
          (försäljning) och ingående (inköp) moms från bokföringen och
          visar nettot. Du kan sedan lämna in deklarationen.
        </p>
        <div
          style={{
            display: "flex",
            gap: 10,
            marginTop: 12,
            flexWrap: "wrap",
            alignItems: "center",
          }}
        >
          <input
            type="date"
            value={previewStart}
            onChange={(e) => setPreviewStart(e.target.value)}
            style={input()}
          />
          <span style={{ color: "rgba(255,255,255,0.55)" }}>→</span>
          <input
            type="date"
            value={previewEnd}
            onChange={(e) => setPreviewEnd(e.target.value)}
            style={input()}
          />
          <button onClick={runPreview} className="biz-btn">
            Räkna ut
          </button>
        </div>
        {preview && (
          <div
            style={{
              marginTop: 14,
              padding: 12,
              background: "rgba(255,255,255,0.04)",
              borderRadius: 8,
              fontFamily: "Source Serif 4, Georgia, serif",
            }}
          >
            <div style={{ color: "rgba(255,255,255,0.85)" }}>
              Utgående moms (försäljning):{" "}
              <strong>{SEK(preview.output_vat)} kr</strong>
              <br />
              Ingående moms (inköp):{" "}
              <strong>{SEK(preview.input_vat)} kr</strong>
              <br />
              <strong
                style={{
                  color: preview.net_vat >= 0 ? "#fbbf24" : "#6ee7b7",
                  fontSize: "1.1rem",
                }}
              >
                Netto att{" "}
                {preview.net_vat >= 0 ? "betala in" : "få tillbaka"}:{" "}
                {SEK(Math.abs(preview.net_vat))} kr
              </strong>
              <span
                style={{
                  color: "rgba(255,255,255,0.55)",
                  marginLeft: 8,
                  fontSize: "0.85rem",
                }}
              >
                ({preview.n_transactions} txns)
              </span>
            </div>
            <button
              onClick={fileNow}
              disabled={busy}
              className="biz-btn solid"
              style={{ marginTop: 14 }}
            >
              {busy ? "Lämnar in…" : "Lämna in deklaration"}
            </button>
          </div>
        )}
      </article>

      <div className="section-eye" style={{ color: "#fbbf24", marginTop: 22 }}>
        Inlämnade deklarationer
      </div>
      {periods.length === 0 ? (
        <div className="biz-empty">
          Inga deklarationer inlämnade än. Använd förhandsvisning ovan när
          du är redo.
        </div>
      ) : (
        <div className="biz-table-grid">
          <div
            className="biz-table-grid-row head"
            style={{
              gridTemplateColumns: "120px 1.5fr 110px 110px 100px",
            }}
          >
            <span>Period</span>
            <span>Datumspann</span>
            <span>Netto</span>
            <span>Förfaller</span>
            <span>Status</span>
          </div>
          {periods.map((p) => (
            <div
              key={p.id}
              className="biz-table-grid-row"
              style={{
                gridTemplateColumns: "120px 1.5fr 110px 110px 100px",
              }}
            >
              <span
                style={{
                  fontFamily: "JetBrains Mono, monospace",
                  fontSize: 10,
                }}
              >
                {p.period_label}
              </span>
              <div>
                <div
                  style={{
                    fontFamily: "Source Serif 4, Georgia, serif",
                    fontSize: 13.5,
                    color: "#fff",
                  }}
                >
                  {p.start_date} → {p.end_date}
                </div>
                <div
                  style={{
                    fontFamily: "JetBrains Mono, monospace",
                    fontSize: 9,
                    color: "rgba(255,255,255,0.4)",
                  }}
                >
                  Ut {SEK(p.output_vat)} · In {SEK(p.input_vat)}
                  {p.filed_on && ` · inlämnad ${p.filed_on}`}
                </div>
              </div>
              <span
                style={{
                  fontFamily: "Source Serif 4, Georgia, serif",
                  fontStyle: "italic",
                  color: p.net_vat >= 0 ? "#fbbf24" : "#6ee7b7",
                  fontWeight: 700,
                }}
              >
                {p.net_vat >= 0 ? "−" : "+"}
                {SEK(Math.abs(p.net_vat))} kr
              </span>
              <span
                style={{
                  fontFamily: "JetBrains Mono, monospace",
                  fontSize: 10,
                  color: "rgba(255,255,255,0.55)",
                }}
              >
                {p.due_date}
              </span>
              <span
                className={`biz-status ${
                  p.status === "paid"
                    ? "paid"
                    : p.status === "filed"
                    ? "sent"
                    : "open"
                }`}
              >
                {p.status === "paid"
                  ? "Betald"
                  : p.status === "filed"
                  ? "Inlämnad"
                  : "Öppen"}
              </span>
            </div>
          ))}
        </div>
      )}

      <div className="peda">
        <div className="peda-eye">Pedagogik · vad du lär dig här</div>
        <div className="peda-h">
          Företag betalar skatt <em>i förskott</em>.
        </div>
        <p className="peda-prose">
          Som privatperson dras skatten av arbetsgivaren <em>innan</em>{" "}
          lönen kommer. Som företagare måste du själv beräkna och betala
          in <strong>F-skatt</strong> månadsvis baserat på din egen
          prognos. Är prognosen för låg → kvarskatt + kostnadsränta. För
          hög → överbetald, får tillbaka. Lärar-frågan: <em>hur räknar du
          på något som inte hänt än?</em>
        </p>
        <ul className="peda-bullets">
          <li>
            <strong>F-skatt</strong>Förenklad förskotts-skatt på prognos.
            Justeras vid årsbokslut.
          </li>
          <li>
            <strong>Moms-redovisning</strong>Månads / kvartal / år beroende
            på omsättning.
          </li>
          <li>
            <strong>Egenavgifter</strong>Sociala avgifter du själv betalar
            (~28,97 % på överskott).
          </li>
          <li>
            <strong>Bokslut</strong>Sista april följande år. Resultat
            överförs till privat-deklaration.
          </li>
        </ul>
        <div className="peda-concepts">
          <span className="peda-concept">F-skatt</span>
          <span className="peda-concept">A-skatt</span>
          <span className="peda-concept">Moms-period</span>
          <span className="peda-concept">Egenavgifter</span>
          <span className="peda-concept">Bokslut</span>
          <span className="peda-concept">Periodisering</span>
        </div>
        <div className="peda-tip">
          När du klickar "Byt till privat" — kvar i ditt privata
          Skatteverket finns rad: "Inkomst av näringsverksamhet". Företagets
          resultat överförs hit varje år och beskattas som privat inkomst
          (efter egenavgifter). Det är så enskild firma fungerar.
        </div>
      </div>
    </BizActorShell>
  );
}


// === BIZ BOLAGSSKATT ===

export function BizBolagsskatt() {
  const [year, setYear] = useState(new Date().getFullYear());
  const [data, setData] = useState<CorporateTax | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    bizApi.corporateTax(year).then(setData).catch((e) => setErr(String((e as Error).message || e)));
  }, [year]);

  return (
    <BizShell eye="Bolag · 05" title="Bolagsskatt">
      <div style={{ marginBottom: 18 }}>
        <label style={{ color: "rgba(255,255,255,0.7)", marginRight: 10 }}>År:</label>
        <input type="number" value={year} min={2020} max={2030} onChange={(e) => setYear(parseInt(e.target.value) || year)} style={{ ...input(), width: 100 }} />
      </div>

      {err && <ErrorBanner msg={err} />}

      {data && (
        <>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12, marginBottom: 18 }}>
            <Card label="Intäkter" value={`${SEK(data.income_total)} kr`} color="#34d399" />
            <Card label="Utgifter" value={`${SEK(data.expense_total)} kr`} color="#fda594" />
            <Card
              label="Resultat före skatt"
              value={`${data.profit_before_tax >= 0 ? "+" : ""}${SEK(data.profit_before_tax)} kr`}
              color={data.profit_before_tax >= 0 ? "#6ee7b7" : "#fda594"}
            />
          </div>

          <article style={{ padding: 24, background: "linear-gradient(135deg, rgba(99,102,241,0.08), rgba(168,85,247,0.05))", border: "1px solid rgba(99,102,241,0.3)", borderRadius: 14 }}>
            <div style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 10, color: "#818cf8", letterSpacing: 1.4, fontWeight: 700 }}>
              ÅRSDEKLARATION K10 · {year}
            </div>
            <h2 style={{ color: "white", fontSize: "1.5rem", margin: "10px 0" }}>
              Estimerad bolagsskatt: <span style={{ color: "#fda594" }}>{SEK(data.estimated_tax)} kr</span>
            </h2>
            <p style={{ color: "rgba(255,255,255,0.7)", marginTop: 6 }}>
              Bolagsskatten i Sverige är <strong>{(data.corporate_tax_rate * 100).toFixed(1)} %</strong> av
              skattepliktigt resultat. Resultat efter skatt: <strong style={{ color: "#34d399" }}>{SEK(data.profit_after_tax)} kr</strong>.
            </p>
            <div style={{ marginTop: 14, color: "rgba(255,255,255,0.5)", fontSize: "0.85rem" }}>
              Baserat på {data.n_transactions} transaktioner. Lön ingår i utgifter.
            </div>
          </article>
        </>
      )}
    </BizShell>
  );
}


// === BIZ INSTÄLLNINGAR ===

export function BizInstallningar() {
  const [company, setCompany] = useState<Company | null>(null);
  const [name, setName] = useState("");
  const [orgNr, setOrgNr] = useState("");
  const [vatReg, setVatReg] = useState(false);
  const [vatPeriod, setVatPeriod] = useState("kvartal");
  const [sni, setSni] = useState("");
  const [industry, setIndustry] = useState("");
  const [shareCap, setShareCap] = useState<number>(25000);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => {
    bizApi.getCompany().then((c) => {
      setCompany(c);
      if (c) {
        setName(c.name);
        setOrgNr(c.org_number || "");
        setVatReg(c.vat_registered);
        setVatPeriod(c.vat_period);
        setSni(c.sni_code || "");
        setIndustry(c.industry_label || "");
        setShareCap(c.share_capital || 25000);
      }
    });
  }, []);

  if (!company) {
    return (
      <BizShell eye="Bolag · 06" title="Inställningar">
        <Empty msg="Inget bolag att redigera. Skapa ett från översikten först." />
      </BizShell>
    );
  }

  return (
    <BizShell eye="Bolag · 06" title="Inställningar">
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
        <Field label="Bolagsnamn">
          <input value={name} onChange={(e) => setName(e.target.value)} style={input()} />
        </Field>
        <Field label="Org-nr">
          <input value={orgNr} onChange={(e) => setOrgNr(e.target.value)} style={input()} placeholder="556677-8899" />
        </Field>
        <Field label="SNI-kod (SCB)">
          <input value={sni} onChange={(e) => setSni(e.target.value)} style={input()} placeholder="62010" />
        </Field>
        <Field label="Bransch">
          <input value={industry} onChange={(e) => setIndustry(e.target.value)} style={input()} placeholder="Konsulttjänster IT" />
        </Field>
        {company.form === "ab" && (
          <Field label="Aktiekapital">
            <input type="number" value={shareCap} onChange={(e) => setShareCap(parseInt(e.target.value) || 25000)} style={input()} />
          </Field>
        )}
        <Field label="Momsperiod">
          <select value={vatPeriod} onChange={(e) => setVatPeriod(e.target.value)} style={input()}>
            <option value="kvartal">Kvartal</option>
            <option value="ar">År (omsättning &lt; 1 mkr)</option>
            <option value="manad">Månad (omsättning &gt; 40 mkr)</option>
          </select>
        </Field>
      </div>

      <label style={{ display: "flex", alignItems: "center", gap: 8, color: "rgba(255,255,255,0.7)", marginTop: 14 }}>
        <input type="checkbox" checked={vatReg} onChange={(e) => setVatReg(e.target.checked)} />
        <span>Momsregistrerad</span>
      </label>

      {msg && <div style={{ marginTop: 14, padding: 10, background: "rgba(110,231,183,0.1)", color: "#6ee7b7", borderRadius: 6 }}>{msg}</div>}

      <div style={{ display: "flex", gap: 10, marginTop: 18 }}>
        <button
          onClick={async () => {
            setBusy(true); setMsg(null);
            try {
              await bizApi.patchCompany(company.id, {
                name, form: company.form,
                org_number: orgNr || null,
                sni_code: sni || null,
                industry_label: industry || null,
                share_capital: company.form === "ab" ? shareCap : null,
                vat_registered: vatReg,
                vat_period: vatPeriod,
              } as any);
              setMsg("Sparat ✓");
            } catch (e) { setMsg(`Fel: ${String((e as Error).message || e)}`); }
            finally { setBusy(false); }
          }}
          style={btnPrimary()}
          disabled={busy}
        >
          {busy ? "Sparar…" : "Spara"}
        </button>
        <button
          onClick={async () => {
            if (!confirm("Stänga bolaget? Det går inte att ångra (men data sparas).")) return;
            await bizApi.closeCompany(company.id);
            window.location.href = "/v2/hub";
          }}
          style={{ ...btnSecondary(), color: "#fda594" }}
        >
          Stäng bolaget
        </button>
      </div>
    </BizShell>
  );
}


// === Shared widgets ===

function Card({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div style={{ padding: 14, background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.08)", borderRadius: 10 }}>
      <div style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 9, color: "rgba(255,255,255,0.5)", letterSpacing: 1.3, fontWeight: 700, textTransform: "uppercase" }}>
        {label}
      </div>
      <div style={{ color, fontSize: "1.3rem", fontWeight: 700, marginTop: 4 }}>{value}</div>
    </div>
  );
}

function Empty({ msg }: { msg: string }) {
  return (
    <div style={{ padding: "40px 20px", textAlign: "center", color: "rgba(255,255,255,0.5)", border: "1px solid rgba(255,255,255,0.08)", borderRadius: 8 }}>
      {msg}
    </div>
  );
}

function ErrorBanner({ msg }: { msg: string }) {
  return (
    <div style={{ padding: 12, background: "rgba(220,76,43,0.12)", border: "1px solid rgba(220,76,43,0.3)", color: "#fda594", borderRadius: 8, marginTop: 14 }}>
      {msg}
    </div>
  );
}

function Modal({ children, onClose, title }: { children: React.ReactNode; onClose: () => void; title: string }) {
  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", zIndex: 9300, display: "grid", placeItems: "center", padding: 20 }} onClick={onClose}>
      <div onClick={(e) => e.stopPropagation()} style={{ background: "rgba(15,21,37,0.98)", border: "1px solid rgba(255,255,255,0.18)", borderRadius: 14, padding: 26, maxWidth: 580, width: "100%", maxHeight: "85vh", overflowY: "auto" }}>
        <h2 style={{ color: "white", fontSize: "1.2rem", margin: "0 0 14px" }}>{title}</h2>
        {children}
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label style={{ display: "block", marginTop: 10 }}>
      <span style={{ display: "block", color: "rgba(255,255,255,0.7)", fontSize: "0.85rem", marginBottom: 4 }}>{label}</span>
      {children}
    </label>
  );
}

function input(): React.CSSProperties {
  return {
    background: "rgba(255,255,255,0.05)",
    border: "1px solid rgba(255,255,255,0.18)",
    color: "white",
    padding: "8px 12px",
    borderRadius: 6,
    width: "100%",
    fontFamily: "inherit",
  };
}

function txRow(): React.CSSProperties {
  return {
    display: "flex",
    gap: 14,
    alignItems: "center",
    padding: 12,
    background: "rgba(255,255,255,0.03)",
    border: "1px solid rgba(255,255,255,0.08)",
    borderRadius: 8,
  };
}

function btnPrimary(): React.CSSProperties {
  return {
    background: "#818cf8",
    color: "#1a1a1a",
    border: "none",
    padding: "10px 18px",
    borderRadius: 6,
    cursor: "pointer",
    fontWeight: 700,
  };
}

function btnSecondary(): React.CSSProperties {
  return {
    background: "transparent",
    border: "1px solid rgba(255,255,255,0.2)",
    color: "rgba(255,255,255,0.85)",
    padding: "8px 14px",
    borderRadius: 6,
    cursor: "pointer",
    textDecoration: "none",
    fontSize: "0.85rem",
  };
}

