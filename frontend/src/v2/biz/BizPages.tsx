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
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { V2Banner } from "../V2Banner";
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


const SEK = (n: number) =>
  new Intl.NumberFormat("sv-SE", { maximumFractionDigits: 0 }).format(n);

const TODAY = () => new Date().toISOString().slice(0, 10);


// === Shared shell ===

function BizShell({ title, eye, children }: {
  title: string; eye: string; children: React.ReactNode;
}) {
  return (
    <div
      style={{
        minHeight: "100vh",
        background: "linear-gradient(180deg, #0a0e1a 0%, #0f1525 100%)",
      }}
    >
      <V2Banner status={{ role: "student", is_super_admin: false }} />
      <div style={{ maxWidth: 1100, margin: "0 auto", padding: "20px 28px 40px" }}>
        <Link
          to="/v2/hub"
          style={{
            color: "rgba(255,255,255,0.6)",
            textDecoration: "none",
            display: "inline-block",
            marginBottom: 18,
            fontFamily: "JetBrains Mono, monospace",
            fontSize: "0.8rem",
            letterSpacing: 1.1,
            textTransform: "uppercase",
          }}
        >
          ← Bolag · översikt
        </Link>
        <header style={{ marginBottom: 24 }}>
          <div
            style={{
              fontFamily: "JetBrains Mono, monospace",
              fontSize: 11,
              color: "#818cf8",
              letterSpacing: 1.4,
              fontWeight: 700,
            }}
          >
            {eye}
          </div>
          <h1 style={{ color: "white", fontSize: "1.8rem", margin: "6px 0 0" }}>
            {title}
          </h1>
        </header>
        {children}
      </div>
    </div>
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

  return (
    <BizShell eye="Bolag · 01" title="Bokföring">
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12, marginBottom: 18 }}>
        <Card label="Intäkter" value={`${SEK(incomeSum)} kr`} color="#34d399" />
        <Card label="Utgifter" value={`${SEK(expenseSum)} kr`} color="#fda594" />
        <Card
          label="Resultat"
          value={`${incomeSum - expenseSum >= 0 ? "+" : ""}${SEK(incomeSum - expenseSum)} kr`}
          color={incomeSum - expenseSum >= 0 ? "#6ee7b7" : "#fda594"}
        />
      </div>

      <button onClick={() => setShowAdd(true)} style={btnPrimary()}>
        + Ny transaktion
      </button>

      {showAdd && (
        <AddTransactionModal
          onClose={() => setShowAdd(false)}
          onAdded={() => { setShowAdd(false); refresh(); }}
        />
      )}

      {err && <ErrorBanner msg={err} />}

      <div style={{ marginTop: 18, display: "flex", flexDirection: "column", gap: 6 }}>
        {txs.length === 0 ? (
          <Empty msg="Inga transaktioner än. Lägg till intäkter/utgifter." />
        ) : (
          txs.map((t) => (
            <article key={t.id} style={txRow()}>
              <div style={{ minWidth: 90, color: "rgba(255,255,255,0.5)", fontFamily: "JetBrains Mono, monospace", fontSize: "0.8rem" }}>
                {t.occurred_on}
              </div>
              <div style={{ flex: 1 }}>
                <strong style={{ color: "white" }}>{t.description}</strong>
                <div style={{ color: "rgba(255,255,255,0.5)", fontSize: "0.78rem" }}>
                  {t.category} · {t.kind === "income" ? "Intäkt" : t.kind === "expense" ? "Utgift" : t.kind === "salary" ? "Lön" : "Skatt"}
                </div>
              </div>
              <div style={{ textAlign: "right", minWidth: 120 }}>
                <strong
                  style={{
                    color: t.kind === "income" ? "#34d399" : "#fda594",
                    fontFamily: "JetBrains Mono, monospace",
                  }}
                >
                  {t.kind === "income" ? "+" : "−"}{SEK(t.amount_excl_vat)} kr
                </strong>
                {t.vat_amount > 0 && (
                  <div style={{ color: "rgba(255,255,255,0.4)", fontSize: "0.75rem" }}>
                    moms {SEK(t.vat_amount)} kr
                  </div>
                )}
              </div>
              <button
                onClick={async () => {
                  if (!confirm("Radera transaktionen?")) return;
                  await bizApi.deleteTransaction(t.id);
                  refresh();
                }}
                style={{ ...btnSm(), color: "#fda594" }}
              >
                ✕
              </button>
            </article>
          ))
        )}
      </div>
    </BizShell>
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

  const total = invoices.reduce((acc, i) => acc + i.total_incl_vat, 0);
  const open = invoices.filter((i) => i.status === "sent").length;
  const paid = invoices.filter((i) => i.status === "paid").length;

  return (
    <BizShell eye="Bolag · 02" title="Kunder & fakturor">
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr", gap: 12, marginBottom: 18 }}>
        <Card label="Total fakturerat" value={`${SEK(total)} kr`} color="#c7d2fe" />
        <Card label="Öppna" value={`${open} st`} color="#fbbf24" />
        <Card label="Betalda" value={`${paid} st`} color="#34d399" />
        <Card label="Kunder" value={`${customers.length} st`} color="#a78bfa" />
      </div>

      <div style={{ display: "flex", gap: 10, marginBottom: 14 }}>
        <button onClick={() => setShowAddInv(true)} style={btnPrimary()} disabled={customers.length === 0}>
          + Ny faktura
        </button>
        <button onClick={() => setShowAddCust(true)} style={btnSecondary()}>
          + Ny kund
        </button>
      </div>

      {customers.length === 0 && (
        <div style={{ padding: 14, background: "rgba(251,191,36,0.1)", border: "1px solid rgba(251,191,36,0.3)", borderRadius: 8, marginBottom: 14, color: "#fbbf24" }}>
          Skapa minst en kund innan du kan fakturera.
        </div>
      )}

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

      {err && <ErrorBanner msg={err} />}

      <h2 style={{ color: "white", fontSize: "1.1rem", marginTop: 18, marginBottom: 8 }}>Fakturor</h2>
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        {invoices.length === 0 ? (
          <Empty msg="Inga fakturor än." />
        ) : (
          invoices.map((inv) => (
            <article key={inv.id} style={txRow()}>
              <div style={{ minWidth: 100, color: "rgba(255,255,255,0.6)", fontFamily: "JetBrains Mono, monospace", fontSize: "0.8rem" }}>
                {inv.invoice_number}
              </div>
              <div style={{ flex: 1 }}>
                <strong style={{ color: "white" }}>{inv.customer_name}</strong>
                <div style={{ color: "rgba(255,255,255,0.6)", fontSize: "0.85rem" }}>
                  {inv.description}
                </div>
                <div style={{ color: "rgba(255,255,255,0.4)", fontSize: "0.78rem" }}>
                  Skickad {inv.issued_on} · Förfaller {inv.due_on}
                  {inv.paid_on ? ` · Betald ${inv.paid_on}` : ""}
                </div>
              </div>
              <div style={{ textAlign: "right" }}>
                <strong style={{ color: "white", fontFamily: "JetBrains Mono, monospace" }}>
                  {SEK(inv.total_incl_vat)} kr
                </strong>
                <div>
                  <span
                    style={{
                      fontSize: "0.7rem",
                      padding: "2px 8px",
                      borderRadius: 100,
                      fontWeight: 700,
                      background:
                        inv.status === "paid"
                          ? "rgba(110,231,183,0.18)"
                          : inv.status === "sent"
                            ? "rgba(251,191,36,0.18)"
                            : "rgba(255,255,255,0.06)",
                      color:
                        inv.status === "paid"
                          ? "#6ee7b7"
                          : inv.status === "sent"
                            ? "#fbbf24"
                            : "rgba(255,255,255,0.5)",
                    }}
                  >
                    {inv.status.toUpperCase()}
                  </span>
                </div>
              </div>
              {inv.status === "sent" && (
                <button
                  onClick={async () => {
                    await bizApi.markInvoicePaid(inv.id);
                    refresh();
                  }}
                  style={{ ...btnSm(), color: "#34d399" }}
                >
                  Betald ✓
                </button>
              )}
            </article>
          ))
        )}
      </div>
    </BizShell>
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

  return (
    <BizShell eye="Bolag · 04" title="Momsdeklaration">
      {err && <ErrorBanner msg={err} />}

      <section style={{ marginBottom: 24, padding: 16, background: "rgba(99,102,241,0.06)", border: "1px solid rgba(99,102,241,0.25)", borderRadius: 10 }}>
        <strong style={{ color: "white" }}>Förhandsvisa period</strong>
        <div style={{ display: "flex", gap: 10, marginTop: 12, flexWrap: "wrap", alignItems: "center" }}>
          <input type="date" value={previewStart} onChange={(e) => setPreviewStart(e.target.value)} style={input()} />
          <span style={{ color: "rgba(255,255,255,0.5)" }}>→</span>
          <input type="date" value={previewEnd} onChange={(e) => setPreviewEnd(e.target.value)} style={input()} />
          <button onClick={runPreview} style={btnSecondary()}>Räkna ut</button>
        </div>
        {preview && (
          <div style={{ marginTop: 14, padding: 12, background: "rgba(255,255,255,0.04)", borderRadius: 8 }}>
            <div style={{ color: "rgba(255,255,255,0.85)" }}>
              Utgående moms (försäljning): <strong>{SEK(preview.output_vat)} kr</strong><br />
              Ingående moms (inköp): <strong>{SEK(preview.input_vat)} kr</strong><br />
              <strong style={{ color: preview.net_vat >= 0 ? "#fda594" : "#34d399", fontSize: "1.1rem" }}>
                Netto att {preview.net_vat >= 0 ? "betala in" : "få tillbaka"}: {SEK(Math.abs(preview.net_vat))} kr
              </strong>
              <span style={{ color: "rgba(255,255,255,0.5)", marginLeft: 8 }}>({preview.n_transactions} txns)</span>
            </div>
            <button onClick={fileNow} disabled={busy} style={{ ...btnPrimary(), marginTop: 14 }}>
              {busy ? "Lämnar in…" : "Lämna in deklaration"}
            </button>
          </div>
        )}
      </section>

      <h2 style={{ color: "white", fontSize: "1.1rem", marginBottom: 8 }}>Inlämnade deklarationer</h2>
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        {periods.length === 0 ? (
          <Empty msg="Inga deklarationer inlämnade än." />
        ) : (
          periods.map((p) => (
            <article key={p.id} style={txRow()}>
              <div style={{ minWidth: 130, color: "rgba(255,255,255,0.7)", fontFamily: "JetBrains Mono, monospace", fontSize: "0.85rem" }}>
                {p.period_label}
              </div>
              <div style={{ flex: 1 }}>
                <strong style={{ color: "white" }}>
                  {p.start_date} → {p.end_date}
                </strong>
                <div style={{ color: "rgba(255,255,255,0.5)", fontSize: "0.8rem" }}>
                  Förfaller {p.due_date}
                  {p.filed_on ? ` · Inlämnad ${p.filed_on}` : ""}
                </div>
              </div>
              <div style={{ textAlign: "right", fontFamily: "JetBrains Mono, monospace" }}>
                <strong style={{ color: p.net_vat >= 0 ? "#fda594" : "#34d399" }}>
                  {p.net_vat >= 0 ? "−" : "+"}{SEK(Math.abs(p.net_vat))} kr
                </strong>
                <div style={{ color: "rgba(255,255,255,0.4)", fontSize: "0.75rem" }}>
                  Ut {SEK(p.output_vat)} · In {SEK(p.input_vat)}
                </div>
              </div>
            </article>
          ))
        )}
      </div>
    </BizShell>
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

function btnSm(): React.CSSProperties {
  return {
    background: "transparent",
    border: "none",
    padding: "6px 10px",
    cursor: "pointer",
    fontSize: "0.85rem",
  };
}
