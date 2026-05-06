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
import { TimeCapacityBar, useTimeCapacity } from "./TimeCapacityWidget";
import { api } from "@/api/client";
import "./biz.css";


/** Hub-shell: V2Topbar + dark backdrop · samma wrapper som BizActorShell
 * fast utan actor-head (eftersom hubben har egen char-card-design).
 *
 * OBS: body[data-mode] sätts av V2Topbar.toggleMode (samt initial
 * useCompanyMode-mount). Vi sätter den INTE här, eftersom BizHub är
 * permanent mountad inuti CompanyModeWrapper (även när panelet är
 * display:none) — om vi tvingade "business" i en useEffect skulle
 * privat-läget gå sönder så fort eleven besökt /v2/hub en gång. */
function BizHubShell({ children }: { children: ReactNode }) {
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

      {/* === 1.5 TIDS-KAPACITET · alltid synlig på hubben === */}
      <CapacityBanner />

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
          <Link to="/v2/allabolag" className="biz-compass-node">
            <div className="biz-compass-node-eye">Aktör · klass</div>
            <div className="biz-compass-node-name">Allabolag</div>
            <div className="biz-compass-node-val">
              Se hur du står dig <em>mot klassen</em>
            </div>
          </Link>
          <Link to="/v2/foretag/klass-pool" className="biz-compass-node">
            <div className="biz-compass-node-eye">Aktör · klass</div>
            <div className="biz-compass-node-name">Klass-pool</div>
            <div className="biz-compass-node-val">
              Tävla med klasskompisar om <em>samma kund</em>
            </div>
          </Link>
          <Link to="/v2/foretag/jobbannonser" className="biz-compass-node">
            <div className="biz-compass-node-eye">Aktör · klass</div>
            <div className="biz-compass-node-name">Anställ klasskompis</div>
            <div className="biz-compass-node-val">
              Posta jobb · <em>klass-företag-tagg</em>
            </div>
          </Link>
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
          <Link to="/v2/foretag/arsredovisning" className="biz-compass-node">
            <div className="biz-compass-node-eye">Verktyg · biz</div>
            <div className="biz-compass-node-name">Årsredovisning</div>
            <div className="biz-compass-node-val">
              AI Bolagsverket granskar
            </div>
          </Link>
          <Link to="/v2/foretag/tillvaxt" className="biz-compass-node">
            <div className="biz-compass-node-eye">Verktyg · biz</div>
            <div className="biz-compass-node-name">Tillväxt</div>
            <div className="biz-compass-node-val">
              Lokaler · utrustning · lån · MCP
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
          {/* Beslut är ihopslaget i Tillväxt-vyn */}
        </div>

        {/* === 5. PEDAGOGIK · "Hur biz & privat hänger ihop" === */}
        <BizPrivateInfoBox company={company} />
      </div>

      {/* Tidigare fanns en "Stega vecka"-knapp här. Borttagen — biz-
       * motorn driver sig själv via auto_tick_if_due (1 biz-vecka per
       * real-timme, lazy-ticked vid endpoint-läsning). Inga manuella
       * steg. */}
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
 * CompanyOnboarding · 3-stegsflöde för att starta bolag
 *   1. Välj bransch (10 kort med stad-tillgänglighet)
 *   2. Välj form (enskild firma / AB) + namn
 *   3. Bekräfta + skapa
 * ====================================================================== */
function CompanyOnboarding({ onCreated }: { onCreated: (c: Company) => void }) {
  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [industries, setIndustries] = useState<import("./api").Industry[]>([]);
  const [selectedIndustry, setSelectedIndustry] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [form, setForm] = useState<"enskild_firma" | "ab">("enskild_firma");
  const [vatReg, setVatReg] = useState(true);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [showCapitalDialog, setShowCapitalDialog] = useState(false);
  const [capitalDialogReason, setCapitalDialogReason] = useState<string | null>(null);

  useEffect(() => {
    bizApi
      .listIndustries()
      .then(setIndustries)
      .catch(() => undefined);
  }, []);

  async function tryCreate(funding: "cash" | "private_loan" | "business_loan_pg") {
    if (!name.trim() || !selectedIndustry) return;
    setBusy(true);
    setErr(null);
    try {
      const c = await bizApi.createCompany({
        name: name.trim(),
        form,
        industry_key: selectedIndustry,
        vat_registered: vatReg,
        vat_period: "kvartal",
        share_capital: form === "ab" ? 25000 : null,
        funding_method: funding,
      });
      onCreated(c);
    } catch (e) {
      const msg = String((e as Error).message || e);
      // 402 = privatkonto saknar pengar / saknar buffert → visa dialog
      if (msg.includes("HTTP 402")) {
        // Plocka ut backend-detaljen (efter "HTTP 402: ... — <detail>")
        const m = msg.match(/—\s*(.+)$/);
        setCapitalDialogReason(m ? m[1] : msg);
        setShowCapitalDialog(true);
        setBusy(false);
        return;
      }
      setErr(msg);
    } finally {
      setBusy(false);
    }
  }

  const create = () => tryCreate("cash");

  // Lyssna på showCapitalDialog och rendera den nedan
  const selected = industries.find((i) => i.key === selectedIndustry);

  if (showCapitalDialog) {
    return (
      <BizHubShell>
        <StartupCapitalDialog
          reason={capitalDialogReason}
          onPick={(funding) => {
            setShowCapitalDialog(false);
            tryCreate(funding);
          }}
          onCancel={() => setShowCapitalDialog(false)}
        />
      </BizHubShell>
    );
  }

  return (
    <BizHubShell>
      <div className="biz-eye">Företagsläge · STARTA BOLAG</div>
      <h1 className="biz-h1" style={{ marginTop: 14 }}>
        Driv ditt eget <em>bolag</em>.
      </h1>
      <p
        style={{
          color: "rgba(255,255,255,0.55)",
          fontSize: "1rem",
          marginBottom: 28,
          marginTop: 12,
          fontFamily: "Source Serif 4, Georgia, serif",
        }}
      >
        Steg {step} av 3 · {step === 1 ? "Välj bransch"
          : step === 2 ? "Bolagsform & namn"
          : "Bekräfta"}
      </p>

      {step === 1 && (
        <>
          <p
            style={{
              fontFamily: "Source Serif 4, Georgia, serif",
              color: "rgba(255,255,255,0.85)",
              fontSize: 14.5,
              lineHeight: 1.55,
              marginBottom: 22,
            }}
          >
            Välj en av de 10 fasta branscherna. Branschen styr pris-baseline,
            kund-mix, säsong och pipeline-täthet i din stad. Vissa branscher
            kräver minst medelstor stad — markeras med 🔒 om din karaktär
            bor i för liten ort.
          </p>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))",
              gap: 12,
              marginBottom: 24,
            }}
          >
            {industries.map((ind) => {
              const isSel = selectedIndustry === ind.key;
              const blocked = !ind.available_in_my_city;
              return (
                <button
                  type="button"
                  key={ind.key}
                  onClick={() => {
                    if (blocked) return;
                    setSelectedIndustry(ind.key);
                  }}
                  disabled={blocked}
                  className="biz-card"
                  style={{
                    textAlign: "left",
                    cursor: blocked ? "not-allowed" : "pointer",
                    borderTopColor: isSel ? "#6366f1" : "#818cf8",
                    background: isSel
                      ? "rgba(99,102,241,0.18)"
                      : "rgba(15,21,37,0.7)",
                    opacity: blocked ? 0.4 : 1,
                    padding: 18,
                  }}
                >
                  <div
                    style={{
                      display: "flex",
                      alignItems: "baseline",
                      gap: 8,
                      flexWrap: "wrap",
                    }}
                  >
                    <span
                      style={{
                        fontFamily: "Source Serif 4, Georgia, serif",
                        fontSize: 17,
                        fontWeight: 700,
                        color: "#fff",
                      }}
                    >
                      {ind.label} {blocked && "🔒"}
                    </span>
                    <span
                      style={{
                        fontFamily: "JetBrains Mono, monospace",
                        fontSize: 9,
                        color: "rgba(255,255,255,0.4)",
                        letterSpacing: 1.2,
                      }}
                    >
                      SNI {ind.sni_code}
                    </span>
                  </div>
                  <p
                    style={{
                      fontFamily: "Source Serif 4, Georgia, serif",
                      fontSize: 13,
                      color: "rgba(255,255,255,0.7)",
                      lineHeight: 1.45,
                      margin: "8px 0 12px",
                    }}
                  >
                    {ind.short_description}
                  </p>
                  <div
                    style={{
                      display: "grid",
                      gridTemplateColumns: "1fr 1fr",
                      gap: 6,
                      fontFamily: "JetBrains Mono, monospace",
                      fontSize: 9.5,
                      color: "rgba(255,255,255,0.6)",
                    }}
                  >
                    <span>
                      Pris: {ind.hourly_rate_min}–{ind.hourly_rate_max} kr/h
                    </span>
                    <span>Marginal ~{ind.margin_baseline_pct} %</span>
                    <span>
                      {ind.requires_lokal
                        ? `Lokal ${ind.monthly_lokal_cost_baseline} kr/m`
                        : "Hemmabas"}
                    </span>
                    <span>
                      Utrustning {ind.equipment_cost_init.toLocaleString("sv-SE")} kr
                    </span>
                  </div>
                  {blocked && (
                    <div
                      style={{
                        marginTop: 8,
                        fontFamily: "JetBrains Mono, monospace",
                        fontSize: 9,
                        color: "#fbbf24",
                        letterSpacing: 0.6,
                      }}
                    >
                      Kräver minst medelstor stad
                    </div>
                  )}
                </button>
              );
            })}
          </div>
          <button
            onClick={() => setStep(2)}
            disabled={!selectedIndustry}
            className="biz-btn solid"
            style={{ padding: "12px 24px" }}
          >
            Nästa · bolagsform →
          </button>
        </>
      )}

      {step === 2 && selected && (
        <>
          <div className="biz-card" style={{ marginBottom: 22 }}>
            <div className="biz-card-eye">Vald bransch</div>
            <div className="biz-card-h">{selected.label}</div>
            <p
              style={{
                fontFamily: "Source Serif 4, Georgia, serif",
                color: "rgba(255,255,255,0.75)",
                fontSize: 13.5,
                marginTop: 8,
              }}
            >
              {selected.learning_focus}
            </p>
          </div>

          <label className="biz-field">
            <span className="biz-field-label">Bolagsnamn:</span>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={`ex: ${selected.label} ${form === "ab" ? "AB" : ""}`}
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
              <option value="ab">
                Aktiebolag (kräver 25 000 kr aktiekapital)
              </option>
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

          <div style={{ display: "flex", gap: 10, marginTop: 20 }}>
            <button
              onClick={() => setStep(1)}
              className="biz-btn"
            >
              ← Byt bransch
            </button>
            <button
              onClick={() => setStep(3)}
              disabled={!name.trim()}
              className="biz-btn solid"
            >
              Nästa · bekräfta →
            </button>
          </div>
        </>
      )}

      {step === 3 && selected && (
        <>
          <div className="biz-card" style={{ marginBottom: 16 }}>
            <div className="biz-card-eye">Bekräfta</div>
            <div className="biz-card-h">{name.trim()}</div>
            <ul
              style={{
                marginTop: 16,
                padding: 0,
                listStyle: "none",
                fontFamily: "Source Serif 4, Georgia, serif",
                fontSize: 14,
                color: "rgba(255,255,255,0.85)",
                lineHeight: 1.7,
              }}
            >
              <li>
                <strong style={{ color: "#c7d2fe" }}>Bransch:</strong>{" "}
                {selected.label} (SNI {selected.sni_code})
              </li>
              <li>
                <strong style={{ color: "#c7d2fe" }}>Bolagsform:</strong>{" "}
                {form === "ab" ? "Aktiebolag" : "Enskild firma"}
              </li>
              <li>
                <strong style={{ color: "#c7d2fe" }}>Stad:</strong>{" "}
                ärvs från karaktären (kan ej ändras)
              </li>
              <li>
                <strong style={{ color: "#c7d2fe" }}>Moms:</strong>{" "}
                {vatReg ? "registrerad" : "ej registrerad"}
              </li>
              {form === "ab" && (
                <li>
                  <strong style={{ color: "#c7d2fe" }}>Aktiekapital:</strong>{" "}
                  25 000 kr (skjuts in vid create)
                </li>
              )}
              <li>
                <strong style={{ color: "#c7d2fe" }}>Utrustning init:</strong>{" "}
                {selected.equipment_cost_init.toLocaleString("sv-SE")} kr
              </li>
            </ul>
          </div>

          {err && <div className="biz-error">{err}</div>}

          <div style={{ display: "flex", gap: 10, marginTop: 16 }}>
            <button onClick={() => setStep(2)} className="biz-btn">
              ← Tillbaka
            </button>
            <button
              onClick={create}
              disabled={busy}
              className="biz-btn solid"
              style={{ padding: "14px 28px", fontSize: "1rem" }}
            >
              {busy ? "Skapar…" : "Starta bolaget ✓"}
            </button>
          </div>
        </>
      )}
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


function StartupCapitalDialog({
  reason,
  onPick,
  onCancel,
}: {
  reason?: string | null;
  onPick: (funding: "private_loan" | "business_loan_pg") => void;
  onCancel: () => void;
}) {
  // Skilj på två fall: helt utan pengar vs. har pengar men ingen buffert kvar
  const isBufferCase = !!(reason && reason.includes("trygghets-bufferten"));
  const eye = isBufferCase ? "⚠ FÖR LITEN BUFFERT" : "⚠ AKTIEKAPITAL SAKNAS";
  return (
    <div style={{
      maxWidth: 720,
      margin: "40px auto",
      padding: "32px 28px",
      background: "linear-gradient(135deg, rgba(251,191,36,0.06), rgba(15,21,37,0.6))",
      border: "1px solid rgba(251,191,36,0.30)",
      borderRadius: 12,
    }}>
      <div style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 11, color: "#fbbf24", letterSpacing: 1.6, fontWeight: 700 }}>
        {eye}
      </div>
      <h1 style={{ fontFamily: "Source Serif 4, Georgia, serif", fontSize: 26, color: "#fff", fontWeight: 700, margin: "8px 0 16px" }}>
        {isBufferCase ? (
          <>Du har precis ihop pengarna · <em style={{ color: "#fbbf24" }}>men ingen buffert</em>.</>
        ) : (
          <>Du saknar 25 000 kr <em style={{ color: "#fbbf24" }}>i aktiekapital</em>.</>
        )}
      </h1>
      {reason && (
        <div style={{
          padding: "12px 14px",
          marginBottom: 14,
          background: "rgba(220,76,43,0.06)",
          borderLeft: "2px solid #fda594",
          borderRadius: 4,
          fontFamily: "Source Serif 4, Georgia, serif",
          fontSize: 13.5,
          color: "rgba(255,255,255,0.85)",
          lineHeight: 1.55,
        }}>
          {reason}
        </div>
      )}
      <p style={{ color: "rgba(255,255,255,0.78)", fontFamily: "Source Serif 4, Georgia, serif", fontSize: 15, lineHeight: 1.6 }}>
        {isBufferCase
          ? "Att tömma kassan på första dagen är en klassisk nybörjar-fälla. Mat, hyra och Spotify dras dagarna efter och tar dig minus innan första kunden hunnit betala. Bättre att lämna bufferten orörd och låna istället:"
          : "För att starta aktiebolag krävs minst 25 000 kr som du satsar i bolaget. Det är pengar som tillhör bolaget — du får inte ut dem som lön. Två vägar att lösa det:"}
      </p>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14, marginTop: 22 }}>
        {/* Privat startup-lån */}
        <div style={{
          padding: 18,
          background: "rgba(99,102,241,0.06)",
          border: "1px solid rgba(99,102,241,0.30)",
          borderRadius: 10,
        }}>
          <div style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 9.5, fontWeight: 700, letterSpacing: 1.4, color: "#c7d2fe" }}>
            ALTERNATIV A
          </div>
          <h3 style={{ fontFamily: "Source Serif 4, Georgia, serif", fontSize: 18, color: "#fff", margin: "8px 0", fontWeight: 700 }}>
            Privat startup-lån
          </h3>
          <p style={{ color: "rgba(255,255,255,0.8)", fontFamily: "Source Serif 4, Georgia, serif", fontSize: 13, lineHeight: 1.55, margin: "8px 0" }}>
            Du tar lån i ditt eget namn. Pengarna går in på privatkontot, sedan
            in i bolaget som aktiekapital.
          </p>
          <ul style={{ color: "rgba(255,255,255,0.75)", fontFamily: "Source Serif 4, Georgia, serif", fontSize: 13, lineHeight: 1.6, paddingLeft: 18, margin: "10px 0" }}>
            <li>25 000 kr · 6 % ränta · 5 år</li>
            <li>≈ 483 kr/mån från privatkontot</li>
            <li>Total kostnad: ~28 990 kr</li>
            <li>⚠ Påverkar din privata Trygghet-axel</li>
          </ul>
          <button onClick={() => onPick("private_loan")} style={{
            marginTop: 10, width: "100%",
            background: "rgba(99,102,241,0.25)", border: "1px solid rgba(99,102,241,0.5)",
            color: "#c7d2fe", padding: "10px 18px", borderRadius: 6,
            fontFamily: "JetBrains Mono, monospace", fontSize: 11, fontWeight: 700,
            letterSpacing: 1.2, textTransform: "uppercase", cursor: "pointer",
          }}>
            Ta privat lån →
          </button>
        </div>

        {/* Företagslån med personlig borgen */}
        <div style={{
          padding: 18,
          background: "rgba(251,191,36,0.06)",
          border: "1px solid rgba(251,191,36,0.30)",
          borderRadius: 10,
        }}>
          <div style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 9.5, fontWeight: 700, letterSpacing: 1.4, color: "#fbbf24" }}>
            ALTERNATIV B
          </div>
          <h3 style={{ fontFamily: "Source Serif 4, Georgia, serif", fontSize: 18, color: "#fff", margin: "8px 0", fontWeight: 700 }}>
            Företagslån · personlig borgen
          </h3>
          <p style={{ color: "rgba(255,255,255,0.8)", fontFamily: "Source Serif 4, Georgia, serif", fontSize: 13, lineHeight: 1.55, margin: "8px 0" }}>
            Bolaget tar lånet · pengarna stannar i bolagets kassa.
            Du går i personlig borgen om bolaget går i konkurs.
          </p>
          <ul style={{ color: "rgba(255,255,255,0.75)", fontFamily: "Source Serif 4, Georgia, serif", fontSize: 13, lineHeight: 1.6, paddingLeft: 18, margin: "10px 0" }}>
            <li>25 000 kr · 7 % ränta · 5 år</li>
            <li>≈ 495 kr/mån från bolagets kassa</li>
            <li>Lägre privat-skuldsättning</li>
            <li>⚠ Personlig borgen = du betalar om bolaget faller</li>
          </ul>
          <button onClick={() => onPick("business_loan_pg")} style={{
            marginTop: 10, width: "100%",
            background: "#fbbf24", border: "none",
            color: "#422006", padding: "10px 18px", borderRadius: 6,
            fontFamily: "JetBrains Mono, monospace", fontSize: 11, fontWeight: 700,
            letterSpacing: 1.2, textTransform: "uppercase", cursor: "pointer",
          }}>
            Ta företagslån →
          </button>
        </div>
      </div>

      <div style={{ marginTop: 22, padding: "14px 16px", background: "rgba(0,0,0,0.2)", borderLeft: "2px solid #6ee7b7", borderRadius: 4 }}>
        <div style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 9.5, color: "#6ee7b7", letterSpacing: 1.2, fontWeight: 700 }}>TIPS</div>
        <p style={{ color: "rgba(255,255,255,0.8)", fontFamily: "Source Serif 4, Georgia, serif", fontSize: 13, lineHeight: 1.55, margin: "6px 0 0" }}>
          Eller välj <em>enskild firma</em> i stället. Den kräver inget aktiekapital alls
          — men du har personligt ansvar för alla skulder och kan inte ta in nya delägare.
        </p>
      </div>

      <div style={{ marginTop: 18, display: "flex", justifyContent: "flex-end" }}>
        <button onClick={onCancel} style={{
          background: "transparent", border: "1px solid rgba(255,255,255,0.20)",
          color: "rgba(255,255,255,0.7)", padding: "10px 18px", borderRadius: 6,
          fontFamily: "JetBrains Mono, monospace", fontSize: 11, fontWeight: 700,
          letterSpacing: 1.2, textTransform: "uppercase", cursor: "pointer",
        }}>
          Avbryt · välj annan form
        </button>
      </div>
    </div>
  );
}


function CapacityBanner() {
  const { data, error, refresh } = useTimeCapacity();
  if (error || !data) return null;

  async function quit() {
    if (!confirm(
      "Säga upp privat-jobbet? Du går från lön + 40h privat-jobb "
      + "till heltidsentreprenör.\n\n"
      + "Påföljd: privat Trygghet -15.\n"
      + "Bonus: +44 h/v för bolaget."
    )) return;
    try {
      await api("/v2/foretag/capacity/quit-private-job", { method: "POST" });
      refresh();
      alert("Du är nu heltidsentreprenör. Lycka till!");
    } catch (e) { alert((e as Error).message); }
  }

  return (
    <div style={{ marginTop: 18, marginBottom: 18 }}>
      <TimeCapacityBar data={data} onQuit={quit} />
    </div>
  );
}
