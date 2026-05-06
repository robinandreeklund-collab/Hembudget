/**
 * BizHub · företagsläges-hub som matchar proposals/vol-7 p-biz-hub
 * (rad 5307-5485 i prototypen).
 *
 * Layout (alltid i denna ordning):
 *   1. hub-head: rubrik + biz-char-card med snabb-pills
 *   2. pentagon-stage med biz-pent-now/biz-pent-prev + 5 axlar
 *   3. biz-event-card · senaste händelse (senaste oöppnade fakturan
 *      eller senaste nya offertförfrågan)
 *   4. compass · 7 företags-aktörer som klickbara noder
 *   5. peda-block "Hur biz & privat hänger ihop" — ordagrant från prototyp
 */
import { useEffect, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { V2Topbar } from "../V2Topbar";
import {
  bizApi,
  type BizAxis,
  type BizPentagon,
  type Company,
  type CompanyInvoice,
} from "./api";
import { BizPentagon as BizPentagonChart } from "./BizPentagon";
import { BizPentagonFlipCard } from "./BizPentagonFlipCard";
import "./biz.css";


/** Hub-shell: V2Topbar + dark backdrop · samma wrapper som BizActorShell
 * fast utan actor-head (eftersom hubben har egen char-card-design). */
function BizHubShell({ children }: { children: ReactNode }) {
  useEffect(() => {
    const prev = document.body.getAttribute("data-mode");
    document.body.setAttribute("data-mode", "business");
    return () => {
      document.body.setAttribute("data-mode", prev || "private");
    };
  }, []);
  return (
    <div className="v2-biz-root">
      <V2Topbar status={{ role: "student", is_super_admin: false }} />
      <div className="biz-shell">{children}</div>
    </div>
  );
}


const SEK = (n: number) =>
  new Intl.NumberFormat("sv-SE", { maximumFractionDigits: 0 }).format(n);


type HubStats = {
  income: number;
  expense: number;
  n_invoices_open: number;
  n_invoices_paid: number;
  n_invoices_overdue: number;
  next_vat_due: string | null;
  unbookkept_count: number;
};


export function BizHub() {
  // body[data-mode="business"] sätts av BizHubShell · ingen useEffect här.
  const [company, setCompany] = useState<Company | null>(null);
  const [pentagon, setPentagon] = useState<BizPentagon | null>(null);
  const [allowed, setAllowed] = useState<boolean | null>(null);
  const [loading, setLoading] = useState(true);
  const [stats, setStats] = useState<HubStats>({
    income: 0,
    expense: 0,
    n_invoices_open: 0,
    n_invoices_paid: 0,
    n_invoices_overdue: 0,
    next_vat_due: null,
    unbookkept_count: 0,
  });
  const [latestInvoice, setLatestInvoice] = useState<CompanyInvoice | null>(null);
  const [activeAxis, setActiveAxis] = useState<BizAxis | null>(null);

  useEffect(() => {
    bizApi
      .modeStatus()
      .then((s) => setAllowed(s.enabled))
      .catch(() => setAllowed(false));
  }, []);

  useEffect(() => {
    if (allowed !== true) return;
    Promise.all([
      bizApi.getCompany(),
      bizApi.listTransactions(500),
      bizApi.listInvoices(),
      bizApi.listVatPeriods().catch(() => []),
    ])
      .then(([c, txs, invs, vps]) => {
        setCompany(c);
        const inc = txs
          .filter((t) => t.kind === "income")
          .reduce((acc, t) => acc + t.amount_excl_vat, 0);
        const exp = txs
          .filter((t) => t.kind === "expense" || t.kind === "salary")
          .reduce((acc, t) => acc + t.amount_excl_vat, 0);
        const open = invs.filter((i) => i.status === "sent").length;
        const paid = invs.filter((i) => i.status === "paid").length;
        const today = new Date().toISOString().slice(0, 10);
        const overdue = invs.filter(
          (i) => i.status === "sent" && i.due_on < today,
        ).length;
        const nextVat = vps.find((v) => v.status === "open")?.due_date || null;

        // Pedagogiskt "ofört" = utgifter utan kategori (förenklat:
        // räkna icke-income-tx som ej angetts category-tag)
        const unbookkept = txs.filter(
          (t) =>
            t.kind !== "income"
            && (!t.category || t.category === "" || t.category === "övrigt"),
        ).length;

        setStats({
          income: inc,
          expense: exp,
          n_invoices_open: open,
          n_invoices_paid: paid,
          n_invoices_overdue: overdue,
          next_vat_due: nextVat,
          unbookkept_count: unbookkept,
        });

        // Senaste oöppnade/nyaste faktura för biz-event-card
        const sent = invs
          .filter((i) => i.status === "sent")
          .sort((a, b) => b.issued_on.localeCompare(a.issued_on));
        setLatestInvoice(sent[0] || invs[0] || null);

        if (c) {
          bizApi.pentagon().then(setPentagon).catch(() => undefined);
        }
      })
      .finally(() => setLoading(false));
  }, [allowed]);

  if (allowed === false) return <BusinessNotAllowed />;
  if (loading) {
    return (
      <BizHubShell>
        <div className="biz-empty">Laddar bolagets data…</div>
      </BizHubShell>
    );
  }
  if (!company) return <CompanyOnboarding onCreated={(c) => setCompany(c)} />;

  return (
    <BizHubShell>
      {/* === 1. HUB-HEAD: rubrik + biz-char-card === */}
      <div className="biz-hub-head">
        <div>
          <span className="biz-pill">
            Företaget · {company.industry_label || "enskild firma"}
            {pentagon ? ` · vinst ${pentagon.metrics.margin_4w_pct.toFixed(0)}%` : ""}
          </span>
          <h1 className="biz-h1" style={{ marginTop: 14 }}>
            {company.name} — <em>vecka i drift</em>.
          </h1>
          <p className="biz-lead">
            {pentagon && pentagon.metrics.income_4w > 0 ? (
              <>
                Omsättning <em>{SEK(pentagon.metrics.income_4w)} kr</em> rullande 4 v.{" "}
                {stats.n_invoices_overdue > 0 && (
                  <>
                    <em>{stats.n_invoices_overdue} kundfaktura</em>
                    {stats.n_invoices_overdue > 1 ? "or" : ""} förfaller idag.{" "}
                  </>
                )}
                {stats.n_invoices_open > 0 && stats.n_invoices_overdue === 0 && (
                  <>
                    <em>{stats.n_invoices_open} öppna fakturor</em> väntar på betalning.{" "}
                  </>
                )}
                Vinstmarginalen är{" "}
                <strong>{pentagon.metrics.margin_4w_pct.toFixed(0)}%</strong>.
              </>
            ) : (
              <>
                Bolaget är just startat — ingen omsättning än. Skapa din första
                offert eller registrera en kund för att komma igång.
              </>
            )}
          </p>
        </div>

        <BizCharCard company={company} pentagon={pentagon} stats={stats} />
      </div>

      {/* === 2. PENTAGON-STAGE · klickbara axlar → flip-kort === */}
      {pentagon && (
        <BizPentagonFlipCard
          activeAxis={activeAxis}
          onClose={() => setActiveAxis(null)}
          front={
            <BizPentagonChart
              data={pentagon}
              onAxisClick={(ax) => setActiveAxis(ax)}
            />
          }
        />
      )}

      {/* === 3. EVENT-CARD · senaste händelse === */}
      {latestInvoice && (
        <BizEventCard invoice={latestInvoice} />
      )}

      {/* === 4. KOMPASS · 7 företags-aktörer === */}
      <div className="compass">
        <div className="compass-eye">Företagets aktörer · sju rum att gå in i</div>
        <div className="compass-grid" style={{ marginBottom: 18 }}>
          <Link to="/v2/foretag/offerter" className="biz-compass-node">
            <div className="biz-compass-node-eye">Aktör · biz</div>
            <div className="biz-compass-node-name">Kunder & offerter</div>
            <div className="biz-compass-node-val">
              <em>{stats.n_invoices_paid}</em> aktiva
            </div>
          </Link>
          <Link
            to="/v2/foretag/fakturor"
            className={`biz-compass-node${stats.n_invoices_overdue > 0 ? " alert" : ""}`}
          >
            <div
              className="biz-compass-node-eye"
              style={
                stats.n_invoices_overdue > 0
                  ? { color: "#dc4c2b" }
                  : undefined
              }
            >
              Aktör · biz
            </div>
            <div className="biz-compass-node-name">Kundfakturor</div>
            <div className="biz-compass-node-val">
              {stats.n_invoices_overdue > 0
                ? <><em>{stats.n_invoices_overdue}</em> förfaller idag</>
                : `${stats.n_invoices_open} öppna`}
            </div>
          </Link>
          <Link to="/v2/foretag/leverantorer" className="biz-compass-node">
            <div className="biz-compass-node-eye">Aktör · biz</div>
            <div className="biz-compass-node-name">Leverantörer</div>
            <div className="biz-compass-node-val">
              {stats.expense > 0 ? `${SEK(stats.expense)} kr/4v` : "0 fakturor"}
            </div>
          </Link>
          <Link to="/v2/foretag/bokforing" className="biz-compass-node">
            <div className="biz-compass-node-eye">Verktyg · biz</div>
            <div className="biz-compass-node-name">Bokföring</div>
            <div className="biz-compass-node-val">
              {stats.unbookkept_count > 0
                ? `${stats.unbookkept_count} verifikat oförda`
                : "Allt fört"}
            </div>
          </Link>
          <Link
            to="/v2/foretag/moms"
            className={`biz-compass-node${stats.next_vat_due ? " warn" : ""}`}
          >
            <div
              className="biz-compass-node-eye"
              style={stats.next_vat_due ? { color: "#fbbf24" } : undefined}
            >
              Aktör · biz
            </div>
            <div className="biz-compass-node-name">Skatteverket biz</div>
            <div className="biz-compass-node-val">
              {stats.next_vat_due
                ? <>Moms <em>{stats.next_vat_due}</em></>
                : "Ingen skuld nu"}
            </div>
          </Link>
          <Link to="/v2/foretag/bank" className="biz-compass-node">
            <div className="biz-compass-node-eye">Aktör · biz</div>
            <div className="biz-compass-node-name">Banken (företag)</div>
            <div className="biz-compass-node-val">
              {pentagon ? `${SEK(pentagon.metrics.kassa)} kr` : "—"}
            </div>
          </Link>
          <Link to="/v2/foretag/beslut" className="biz-compass-node">
            <div className="biz-compass-node-eye">Verktyg · biz</div>
            <div className="biz-compass-node-name">Beslut</div>
            <div className="biz-compass-node-val">
              {company.form === "ab" ? "Anställa, försäkring" : "Friskvård, leasing"}
            </div>
          </Link>
        </div>

        {/* === 5. PEDAGOGIK · "Hur biz & privat hänger ihop" === */}
        <BizPrivateInfoBox company={company} />
      </div>

      {/* Spelmotor-knappen längst ner (lärar-funktion) */}
      <TickWeekButton />
    </BizHubShell>
  );
}


/* ======================================================================
 * BizCharCard · matchar prototyp rad 5321-5340
 * ====================================================================== */
function BizCharCard({
  company,
  pentagon,
  stats,
}: {
  company: Company;
  pentagon: BizPentagon | null;
  stats: HubStats;
}) {
  return (
    <article className="biz-char-card">
      <div className="biz-char-eye">
        Företag ·{" "}
        {company.form === "ab"
          ? "aktiebolag"
          : company.form === "handelsbolag"
          ? "handelsbolag"
          : "enskild firma"}
        {pentagon ? ` · v${weekOfYear(new Date())} i drift` : ""}
      </div>
      <div className="biz-char-name">
        {company.name.replace(/\s+(AB|HB|EF)\s*$/, "")}
        {company.form === "ab" && <em> AB</em>}
      </div>
      <div className="biz-char-meta">
        {company.form === "ab"
          ? "aktiebolag"
          : company.form === "handelsbolag"
          ? "handelsbolag"
          : "enskild firma"}
        <span className="biz-char-divider">·</span>
        {company.industry_label || "tjänster"}
        {company.org_number && (
          <>
            <span className="biz-char-divider">·</span>
            {company.org_number}
          </>
        )}
      </div>

      <div className="biz-char-section">Status nu</div>
      <p className="biz-char-prose">
        {pentagon && pentagon.metrics.income_4w > 0 ? (
          <>
            Omsättning <em>{SEK(pentagon.metrics.income_4w)} kr</em> rullande 4 v ·
            vinstmarginal{" "}
            <strong>{pentagon.metrics.margin_4w_pct.toFixed(0)}%</strong> · kassa{" "}
            <em>{SEK(pentagon.metrics.kassa)} kr</em>.
            {stats.n_invoices_open > 0 && (
              <>
                {" "}
                Du har <strong>{stats.n_invoices_open} öppna fakturor</strong> som
                väntar på betalning.
              </>
            )}
          </>
        ) : (
          <>
            Bolaget är inte i full drift än. Registrera dina första kunder och
            skapa offerter för att börja generera omsättning.
          </>
        )}
      </p>

      <div className="biz-char-pills">
        {stats.n_invoices_overdue > 0 && (
          <Link to="/v2/foretag/fakturor" className="biz-char-pill alert">
            {stats.n_invoices_overdue} faktura
            {stats.n_invoices_overdue > 1 ? "or" : ""} förfaller idag
          </Link>
        )}
        {stats.n_invoices_open > 0 && stats.n_invoices_overdue === 0 && (
          <Link to="/v2/foretag/fakturor" className="biz-char-pill">
            {stats.n_invoices_open} öppna fakturor
          </Link>
        )}
        <Link to="/v2/foretag/bokforing" className="biz-char-pill">
          Bokföring
        </Link>
        {company.vat_registered && stats.next_vat_due && (
          <Link to="/v2/foretag/moms" className="biz-char-pill">
            Moms {stats.next_vat_due}
          </Link>
        )}
        {company.form === "ab" && (
          <Link to="/v2/foretag/lon" className="biz-char-pill">
            Ta ut lön
          </Link>
        )}
      </div>
    </article>
  );
}


/* ======================================================================
 * BizEventCard · matchar prototyp rad 5400-5414 (senaste händelse)
 * ====================================================================== */
function BizEventCard({ invoice }: { invoice: CompanyInvoice }) {
  const today = new Date().toISOString().slice(0, 10);
  const overdue = invoice.status === "sent" && invoice.due_on < today;
  return (
    <article className="biz-event-card">
      <div className="biz-event-eye">
        Händelse · faktura {invoice.invoice_number} ·{" "}
        {overdue ? "FÖRFALLER IDAG" : invoice.status}
      </div>
      <h2 className="biz-event-headline">
        {invoice.customer_name} —{" "}
        <em>{overdue ? "förfaller" : "nästa steg"}</em>.
      </h2>
      <p className="biz-event-prose">
        {overdue ? (
          <>
            Fakturan på <strong>{SEK(invoice.amount_excl_vat)} kr</strong> till{" "}
            {invoice.customer_name} förföll{" "}
            <strong>{invoice.due_on}</strong>. Skicka påminnelse eller
            markera som betald om du fått pengarna.
          </>
        ) : invoice.status === "sent" ? (
          <>
            Faktura {invoice.invoice_number} skickad <strong>{invoice.issued_on}</strong> ·
            förfaller <strong>{invoice.due_on}</strong> · belopp{" "}
            <strong>{SEK(invoice.amount_excl_vat)} kr</strong> exkl. moms.
          </>
        ) : (
          <>
            Faktura <strong>{invoice.invoice_number}</strong> markerad som{" "}
            {invoice.status}.
          </>
        )}
      </p>
      <div className="biz-event-actions">
        <Link to={`/v2/foretag/fakturor`} className="biz-btn solid">
          Öppna faktura →
        </Link>
        <Link to="/v2/foretag/fakturor" className="biz-btn">
          Se alla
        </Link>
      </div>
    </article>
  );
}


/* ======================================================================
 * BizPrivateInfoBox · ordagrant copy från prototyp rad 5458-5484
 * ====================================================================== */
function BizPrivateInfoBox({ company }: { company: Company }) {
  return (
    <div className="peda">
      <div className="peda-eye">Hur biz & privat hänger ihop</div>
      <div className="peda-h">
        Allt är <em>du</em>. Två konton, ett liv.
      </div>
      <p className="peda-prose">
        Privat och företag är <strong>separata bokföringsenheter</strong> men
        samma person. När du tar ut <em>egen lön</em> från företagskontot till
        ditt privatkonto är det en överföring som syns i båda bokföringarna.
        Tjänar företaget bra → <em>privatkontot</em> får mer. Pentagon i
        privatläge påverkas av företagets resultat — det är samma person, samma
        stress, samma framgång.
      </p>
      <ul className="peda-bullets">
        <li>
          <strong>Egen lön</strong>
          {company.form === "ab"
            ? "Du betalar privatskatt + arb.giv.avg. 31,42 % från företaget"
            : "Du tar ut det du behöver, betalar privatskatt — inte arbetsgivaravgift."}
        </li>
        <li>
          <strong>Egen insättning</strong>Att skjuta in privata pengar i
          företaget. Räknas som lån/eget kapital.
        </li>
        <li>
          <strong>Skatt</strong>Privatskatt på överskott + moms 25 % på fakturor
          (utgående).
        </li>
        <li>
          <strong>F-skatt</strong>Du betalar in själv månadsvis baserat på
          prognos.
        </li>
      </ul>
      <div className="peda-concepts">
        <span className="peda-concept">Egen lön</span>
        <span className="peda-concept">Eget kapital</span>
        <span className="peda-concept">F-skatt</span>
        <span className="peda-concept">Moms in &amp; ut</span>
        <span className="peda-concept">Resultatöverföring</span>
        <span className="peda-concept">Periodisering</span>
      </div>
      <div className="peda-tip">
        När du klickar "Byt till privat" upptill — flippar appen tillbaka. Allt
        du gör i biz påverkar ditt privata över tid: bättre vinst → mer egen
        lön → bättre privat-pentagon.
      </div>
    </div>
  );
}


/* ======================================================================
 * Spelmotor · stega vecka (lärar-test-knapp)
 * ====================================================================== */
function TickWeekButton() {
  const [running, setRunning] = useState(false);
  const [last, setLast] = useState<{
    week_no: number;
    new_opps: number;
    accepted: number;
    rejected: number;
    paid: number;
    events: number;
    rep: number;
  } | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function tick() {
    setRunning(true);
    setErr(null);
    try {
      const r = await bizApi.tick();
      setLast({
        week_no: r.week_no,
        new_opps: r.new_opportunities,
        accepted: r.quotes_accepted,
        rejected: r.quotes_rejected,
        paid: r.invoices_paid_now,
        events: r.events_triggered,
        rep: r.reputation_after,
      });
    } catch (e) {
      setErr(String((e as Error).message || e));
    } finally {
      setRunning(false);
    }
  }

  return (
    <div
      style={{
        marginTop: 32,
        padding: 18,
        background:
          "linear-gradient(120deg, rgba(99,102,241,0.18), rgba(167,139,250,0.12))",
        border: "1px solid rgba(99, 102, 241, 0.3)",
        borderRadius: 12,
        display: "flex",
        alignItems: "center",
        gap: 16,
        flexWrap: "wrap",
      }}
    >
      <div style={{ flex: "1 1 240px" }}>
        <div className="biz-eye">Spelmotor · stega tiden</div>
        <div
          style={{
            fontFamily: "Source Serif 4, Georgia, serif",
            fontWeight: 700,
            fontSize: "1.1rem",
            marginTop: 4,
            color: "#fff",
          }}
        >
          Stega bolaget en vecka framåt
        </div>
        <div
          style={{
            color: "rgba(255,255,255,0.55)",
            fontSize: "0.85rem",
            marginTop: 4,
          }}
        >
          Genererar nya offertförfrågningar, kunder svarar på öppna offerter,
          gamla fakturor förfaller. Slump-events triggas i avancerat läge.
        </div>
      </div>
      <button
        onClick={tick}
        disabled={running}
        className="biz-btn solid"
        style={{ padding: "12px 24px", fontSize: "1rem" }}
      >
        {running ? "Stegar…" : "Stega vecka →"}
      </button>
      {err && (
        <div className="biz-error" style={{ flexBasis: "100%" }}>
          {err}
        </div>
      )}
      {last && (
        <div
          style={{
            flexBasis: "100%",
            marginTop: 8,
            padding: 12,
            borderRadius: 8,
            background: "rgba(15, 21, 37, 0.5)",
            fontSize: "0.85rem",
          }}
        >
          <div style={{ color: "#6ee7b7", fontWeight: 600 }}>
            Vecka {last.week_no} klar
          </div>
          <div style={{ color: "rgba(255,255,255,0.8)", marginTop: 4 }}>
            {last.new_opps} nya förfrågningar
            {last.accepted > 0 && ` · ${last.accepted} offerter accepterade`}
            {last.rejected > 0 && ` · ${last.rejected} avslagna`}
            {last.paid > 0 && ` · ${last.paid} fakturor betalda`}
            {last.events > 0 && ` · ${last.events} oväntat event`}
            {" · "}rykte {last.rep}/100
          </div>
        </div>
      )}
    </div>
  );
}


/* ======================================================================
 * BusinessNotAllowed · samma som tidigare
 * ====================================================================== */
function BusinessNotAllowed() {
  return (
    <BizHubShell>
      <div
        style={{
          padding: "60px 40px",
          maxWidth: 720,
          margin: "40px auto",
          background:
            "linear-gradient(135deg, rgba(251,191,36,0.06), rgba(15,21,37,0.5))",
          border: "1px solid rgba(251,191,36,0.3)",
          borderRadius: 16,
          textAlign: "center",
        }}
      >
        <div className="biz-eye" style={{ color: "#fbbf24" }}>
          Företagsläge · INTE AKTIVERAT
        </div>
        <h2
          style={{
            color: "white",
            fontSize: "1.8rem",
            margin: "16px 0",
            fontFamily: "Source Serif 4, Georgia, serif",
          }}
        >
          Be din lärare aktivera företagsläget.
        </h2>
        <p style={{ color: "rgba(255,255,255,0.7)" }}>
          Företagsläget aktiveras per elev av läraren. När det är på kan du
          driva enskild firma eller AB parallellt med din privatekonomi.
        </p>
        <Link
          to="/v2/hub"
          style={{
            display: "inline-block",
            marginTop: 18,
            padding: "10px 20px",
            background: "#fbbf24",
            color: "#1a1a1a",
            borderRadius: 6,
            textDecoration: "none",
            fontWeight: 700,
          }}
        >
          ← Tillbaka till privatekonomin
        </Link>
      </div>
    </BizHubShell>
  );
}


/* ======================================================================
 * CompanyOnboarding · oförändrat (skapa bolag)
 * ====================================================================== */
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
    <BizHubShell>
      <div
        style={{
          padding: "60px 40px",
          maxWidth: 720,
          margin: "0 auto",
          background:
            "linear-gradient(135deg, rgba(99,102,241,0.05), rgba(168,85,247,0.05))",
          border: "1px solid rgba(99, 102, 241, 0.25)",
          borderRadius: 16,
        }}
      >
        <div className="biz-eye">Företagsläge · STARTA BOLAG</div>
        <h1 className="biz-h1" style={{ marginTop: 14 }}>
          Driv ditt eget <em>bolag</em>.
        </h1>
        <p
          style={{
            color: "rgba(255,255,255,0.7)",
            fontSize: "1rem",
            marginBottom: 28,
            marginTop: 12,
          }}
        >
          Skapa en enskild firma eller aktiebolag. Du behåller din
          privatekonomi parallellt — växla mellan med toggle-knappen i topbar.
        </p>

        <label className="biz-field">
          <span className="biz-field-label">Bolagsnamn:</span>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="ex: Sara A. Konsult AB"
            className="biz-input"
          />
        </label>

        <label className="biz-field">
          <span className="biz-field-label">Bolagsform:</span>
          <select
            value={form}
            onChange={(e) => setForm(e.target.value as typeof form)}
            className="biz-select"
          >
            <option value="enskild_firma">Enskild firma (lättast)</option>
            <option value="ab">Aktiebolag (kräver 25 000 kr aktiekapital)</option>
          </select>
        </label>

        <label
          className="biz-field"
          style={{ display: "flex", alignItems: "center", gap: 10 }}
        >
          <input
            type="checkbox"
            checked={vatReg}
            onChange={(e) => setVatReg(e.target.checked)}
          />
          <span>Momsregistrera (krävs vid omsättning &gt; 80 000 kr/år)</span>
        </label>

        {err && <div className="biz-error">{err}</div>}

        <button
          onClick={create}
          disabled={busy || !name.trim()}
          className="biz-btn solid"
          style={{ marginTop: 20, padding: "14px 28px", fontSize: "1rem" }}
        >
          {busy ? "Skapar…" : "Starta bolaget →"}
        </button>
      </div>
    </BizHubShell>
  );
}


/** Hjälpare · ISO-vecka för ett datum (Sverige använder ISO-veckor) */
function weekOfYear(d: Date): number {
  const t = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
  t.setUTCDate(t.getUTCDate() + 4 - (t.getUTCDay() || 7));
  const yearStart = new Date(Date.UTC(t.getUTCFullYear(), 0, 1));
  return Math.ceil(((+t - +yearStart) / 86400000 + 1) / 7);
}
