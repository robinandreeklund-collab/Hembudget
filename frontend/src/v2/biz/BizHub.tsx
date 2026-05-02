/**
 * Företagsläget · BizHub.
 *
 * Bug #7-utbyggnad · ersatt CompanyComingSoon. Visas när
 * useCompanyMode() = "business". Innehåller:
 *   - Översikt: bolaget, total intäkt/utgift, resultat
 *   - 6 paneler: Bolagsform, Bokföring, Lön, Kunder/fakturor, Moms, Bolagsskatt
 */
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { bizApi, type Company } from "./api";


const SEK = (n: number) =>
  new Intl.NumberFormat("sv-SE", { maximumFractionDigits: 0 }).format(n);


export function BizHub() {
  const [company, setCompany] = useState<Company | null>(null);
  const [loading, setLoading] = useState(true);
  const [stats, setStats] = useState<{
    income: number;
    expense: number;
    n_invoices_open: number;
    n_invoices_paid: number;
    next_vat_due?: string | null;
  }>({ income: 0, expense: 0, n_invoices_open: 0, n_invoices_paid: 0 });

  useEffect(() => {
    Promise.all([
      bizApi.getCompany(),
      bizApi.listTransactions(500),
      bizApi.listInvoices(),
      bizApi.listVatPeriods().catch(() => []),
    ])
      .then(([c, txs, invs, vps]) => {
        setCompany(c);
        const inc = txs.filter((t) => t.kind === "income")
          .reduce((acc, t) => acc + t.amount_excl_vat, 0);
        const exp = txs.filter((t) => t.kind === "expense" || t.kind === "salary")
          .reduce((acc, t) => acc + t.amount_excl_vat, 0);
        const open = invs.filter((i) => i.status === "sent").length;
        const paid = invs.filter((i) => i.status === "paid").length;
        const nextVat = vps.find((v) => v.status === "open")?.due_date || null;
        setStats({ income: inc, expense: exp, n_invoices_open: open, n_invoices_paid: paid, next_vat_due: nextVat });
      })
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div style={{ padding: 60, textAlign: "center", color: "#c7d2fe" }}>
        Laddar bolagets data…
      </div>
    );
  }

  if (!company) {
    return <CompanyOnboarding onCreated={(c) => setCompany(c)} />;
  }

  const profit = stats.income - stats.expense;

  return (
    <div style={{ padding: "20px 28px 40px" }}>
      {/* Bolagets header */}
      <header
        style={{
          padding: 24,
          marginBottom: 20,
          background:
            "linear-gradient(135deg, rgba(99,102,241,0.12), rgba(168,85,247,0.06))",
          border: "1px solid rgba(99,102,241,0.3)",
          borderRadius: 14,
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
          <div>
            <div
              style={{
                fontFamily: "JetBrains Mono, monospace",
                fontSize: 11,
                color: "#818cf8",
                letterSpacing: 1.4,
                fontWeight: 700,
              }}
            >
              {company.form === "ab"
                ? "Aktiebolag"
                : company.form === "enskild_firma"
                  ? "Enskild firma"
                  : "Handelsbolag"}
              {company.org_number ? ` · ${company.org_number}` : ""}
            </div>
            <h1 style={{ color: "white", fontSize: "1.8rem", margin: "6px 0 4px" }}>
              {company.name}
            </h1>
            <div style={{ color: "rgba(255,255,255,0.6)" }}>
              Startat {company.started_on}
              {company.share_capital
                ? ` · Aktiekapital ${SEK(company.share_capital)} kr`
                : ""}
              {company.vat_registered
                ? ` · Momsreg (${company.vat_period})`
                : " · Ej momsreg"}
            </div>
          </div>
          <Link to="/v2/foretag/installningar" style={btnSecondary()}>
            Inställningar
          </Link>
        </div>
      </header>

      {/* KPI-rad */}
      <div style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
        gap: 12,
        marginBottom: 24,
      }}>
        <Kpi label="Intäkter" value={`${SEK(stats.income)} kr`} color="#34d399" />
        <Kpi label="Utgifter" value={`${SEK(stats.expense)} kr`} color="#fda594" />
        <Kpi
          label="Resultat"
          value={`${profit >= 0 ? "+" : ""}${SEK(profit)} kr`}
          color={profit >= 0 ? "#6ee7b7" : "#fda594"}
        />
        <Kpi
          label="Öppna fakturor"
          value={`${stats.n_invoices_open} st`}
          color="#fbbf24"
        />
        {stats.next_vat_due && (
          <Kpi
            label="Nästa moms"
            value={stats.next_vat_due}
            color="#c7d2fe"
          />
        )}
      </div>

      {/* Aktör-grid */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
          gap: 14,
        }}
      >
        <BizActorCard
          eye="01"
          name="Bokföring"
          desc="Intäkter & utgifter med moms-belopp"
          to="/v2/foretag/bokforing"
        />
        <BizActorCard
          eye="02"
          name="Kunder & fakturor"
          desc="Skapa, skicka, markera betald"
          to="/v2/foretag/fakturor"
        />
        {company.form === "ab" && (
          <BizActorCard
            eye="03"
            name="Lön till mig själv"
            desc="Beräkna arbetsgivaravgift + skatt"
            to="/v2/foretag/lon"
          />
        )}
        {company.vat_registered && (
          <BizActorCard
            eye="04"
            name="Momsdeklaration"
            desc="Kvartalsvis till Skatteverket"
            to="/v2/foretag/moms"
          />
        )}
        {company.form === "ab" && (
          <BizActorCard
            eye="05"
            name="Bolagsskatt"
            desc="20.6 % på årets resultat"
            to="/v2/foretag/bolagsskatt"
          />
        )}
        <BizActorCard
          eye="06"
          name="Inställningar"
          desc="Bolagsnamn, moms, branschkod"
          to="/v2/foretag/installningar"
        />
      </div>
    </div>
  );
}


function Kpi({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div
      style={{
        padding: 14,
        background: "rgba(255,255,255,0.03)",
        border: "1px solid rgba(255,255,255,0.08)",
        borderRadius: 10,
      }}
    >
      <div
        style={{
          fontFamily: "JetBrains Mono, monospace",
          fontSize: 9,
          color: "rgba(255,255,255,0.5)",
          letterSpacing: 1.3,
          textTransform: "uppercase",
          fontWeight: 700,
        }}
      >
        {label}
      </div>
      <div style={{ color, fontSize: "1.3rem", fontWeight: 700, marginTop: 4 }}>
        {value}
      </div>
    </div>
  );
}


function BizActorCard({
  eye, name, desc, to,
}: { eye: string; name: string; desc: string; to: string }) {
  return (
    <Link
      to={to}
      style={{
        padding: 18,
        background: "rgba(255,255,255,0.03)",
        border: "1px solid rgba(99,102,241,0.2)",
        borderRadius: 12,
        textDecoration: "none",
        display: "block",
        transition: "all 0.2s",
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.background = "rgba(99,102,241,0.08)";
        e.currentTarget.style.borderColor = "rgba(99,102,241,0.45)";
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.background = "rgba(255,255,255,0.03)";
        e.currentTarget.style.borderColor = "rgba(99,102,241,0.2)";
      }}
    >
      <div
        style={{
          fontFamily: "JetBrains Mono, monospace",
          fontSize: 9,
          color: "#818cf8",
          letterSpacing: 1.3,
          fontWeight: 700,
        }}
      >
        Bolag · {eye}
      </div>
      <strong style={{ color: "white", fontSize: "1.05rem", marginTop: 6, display: "block" }}>
        {name}
      </strong>
      <div style={{ color: "rgba(255,255,255,0.6)", fontSize: "0.85rem", marginTop: 4 }}>
        {desc}
      </div>
    </Link>
  );
}


function CompanyOnboarding({ onCreated }: { onCreated: (c: Company) => void }) {
  const [name, setName] = useState("");
  const [form, setForm] = useState<"enskild_firma" | "ab">("enskild_firma");
  const [vatReg, setVatReg] = useState(true);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const create = async () => {
    if (!name.trim()) return;
    setBusy(true);
    setErr(null);
    try {
      const c = await bizApi.createCompany({
        name: name.trim(),
        form,
        vat_registered: vatReg,
        vat_period: "kvartal",
        share_capital: form === "ab" ? 25000 : null,
      });
      onCreated(c);
    } catch (e) {
      setErr(String((e as Error).message || e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      style={{
        padding: "60px 40px",
        maxWidth: 720,
        margin: "0 auto",
        background:
          "linear-gradient(135deg, rgba(99,102,241,0.05), rgba(168,85,247,0.05))",
        border: "1px solid rgba(99,102,241,0.25)",
        borderRadius: 16,
      }}
    >
      <div
        style={{
          fontFamily: "JetBrains Mono, monospace",
          fontSize: 11,
          color: "#818cf8",
          letterSpacing: 1.6,
          textTransform: "uppercase",
          fontWeight: 700,
        }}
      >
        Företagsläge · STARTA BOLAG
      </div>
      <h1
        style={{
          color: "white",
          fontSize: "2rem",
          margin: "16px 0",
          fontFamily: "Source Serif 4, Georgia, serif",
        }}
      >
        Driv ditt eget <em style={{ color: "#c7d2fe" }}>bolag</em>.
      </h1>
      <p style={{ color: "rgba(255,255,255,0.7)", fontSize: "1rem", marginBottom: 28 }}>
        Skapa en enskild firma eller aktiebolag. Du behåller din privatekonomi
        parallellt — växla mellan med toggle-knappen i topbar.
      </p>

      <label style={lbl()}>
        Bolagsnamn:
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="ex: Sara A. Konsult AB"
          style={inputStyle()}
        />
      </label>

      <label style={lbl()}>
        Bolagsform:
        <select
          value={form}
          onChange={(e) => setForm(e.target.value as typeof form)}
          style={inputStyle()}
        >
          <option value="enskild_firma">Enskild firma (lättast)</option>
          <option value="ab">Aktiebolag (kräver 25 000 kr aktiekapital)</option>
        </select>
      </label>

      <label
        style={{
          ...lbl(),
          display: "flex",
          alignItems: "center",
          gap: 10,
          flexDirection: "row",
        }}
      >
        <input
          type="checkbox"
          checked={vatReg}
          onChange={(e) => setVatReg(e.target.checked)}
        />
        <span>Momsregistrera (krävs vid omsättning &gt; 80 000 kr/år)</span>
      </label>

      {err && (
        <div
          style={{
            marginTop: 14,
            padding: 10,
            background: "rgba(220,76,43,0.15)",
            color: "#fda594",
            borderRadius: 6,
          }}
        >
          {err}
        </div>
      )}

      <button
        onClick={create}
        disabled={busy || !name.trim()}
        style={{
          marginTop: 20,
          padding: "14px 28px",
          background: "#818cf8",
          color: "#1a1a1a",
          border: "none",
          borderRadius: 8,
          cursor: busy || !name.trim() ? "not-allowed" : "pointer",
          fontWeight: 700,
          fontSize: "1rem",
        }}
      >
        {busy ? "Skapar…" : "Starta bolaget →"}
      </button>
    </div>
  );
}


function lbl(): React.CSSProperties {
  return {
    display: "block",
    color: "rgba(255,255,255,0.7)",
    fontSize: "0.9rem",
    marginTop: 16,
  };
}

function inputStyle(): React.CSSProperties {
  return {
    background: "rgba(255,255,255,0.05)",
    border: "1px solid rgba(255,255,255,0.18)",
    color: "white",
    padding: "10px 12px",
    borderRadius: 6,
    width: "100%",
    fontFamily: "inherit",
    marginTop: 6,
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
