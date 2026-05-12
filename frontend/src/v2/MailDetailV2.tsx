/**
 * Postlådan · brevdetalj — elev-vy.
 *
 * Speglar prototypen /proposals/vol-7/elev.html · p-cc + p-lonespec.
 * Layout väljs automatiskt baserat på mail.mail_type:
 * - invoice + sender_kind=cred → CC-faktura med tx-lista
 * - salary_slip → Lönespec med spec-tabell + arbetsgivaravgifter
 * - andra typer → standard mail-body
 *
 * Markerar mailet som "viewed" vid första öppning. Eleven kan klicka
 * på enskild tx → /v2/tx/{id}.
 */
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  v2Api,
  type V2InvoiceData,
  type V2MailDetailData,
} from "./api";
import { V2Banner } from "./V2Banner";
import { BankIdSignModal } from "./BankIdSignModal";
import "./lan.css";
import "./faktura-shell.css";

const SEK = (n: number) =>
  new Intl.NumberFormat("sv-SE", { maximumFractionDigits: 0 }).format(n);

const SHORT_DATE = (iso: string | null): string => {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleDateString("sv-SE", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
};

// TIME_DATE-helper togs bort när sender_meta-raden ersattes med
// strukturerad faktura-meta (Org.nr + adress).

// === Avsändar-meta-uppslag · ger fakturalook med riktig org-nr + adress ===
// Mappar sender_short / sender substring till officiella detaljer som
// visas i fakturalookens header. Pedagogiskt: eleven ser hur en riktig
// faktura ser ut med organisationsnummer, adress och kontaktuppgifter.
type SenderMeta = {
  fullName: string;
  orgNumber: string;
  address: string[];
  website?: string;
};
const SENDER_META: Record<string, SenderMeta> = {
  // Hyresvärdar (sender innehåller "Bostäder")
  "Bostäder": {
    fullName: "Bostadsförvaltning AB",
    orgNumber: "556421-7892",
    address: ["Hyrestorget 4", "112 30 Stockholm"],
    website: "www.bostader.se",
  },
  // Försäkringsbolag
  Folksam: {
    fullName: "Folksam ömsesidig sakförsäkring",
    orgNumber: "502006-1619",
    address: ["106 60 Stockholm"],
    website: "www.folksam.se",
  },
  Trygg: {
    fullName: "Trygg-Hansa Försäkring AB",
    orgNumber: "516406-0763",
    address: ["106 26 Stockholm"],
    website: "www.trygghansa.se",
  },
  // Telekom
  Telia: {
    fullName: "Telia Sverige AB",
    orgNumber: "556430-0142",
    address: ["169 94 Solna"],
    website: "www.telia.se",
  },
  Bahnhof: {
    fullName: "Bahnhof AB",
    orgNumber: "556519-9493",
    address: ["Box 7702", "103 95 Stockholm"],
    website: "www.bahnhof.se",
  },
  // Energi
  Tibber: {
    fullName: "Tibber AB",
    orgNumber: "559107-0570",
    address: ["Kungsbron 1", "111 22 Stockholm"],
    website: "www.tibber.com",
  },
  // Kollektivtrafik
  Västtrafik: {
    fullName: "Västtrafik AB",
    orgNumber: "556558-5012",
    address: ["Box 405", "401 26 Göteborg"],
    website: "www.vasttrafik.se",
  },
  Lokaltrafik: {
    fullName: "Regionens kollektivtrafik",
    orgNumber: "232100-0016",
    address: ["Stora Torget 1"],
    website: "www.lokaltrafik.se",
  },
  // Banker
  SEB: {
    fullName: "Skandinaviska Enskilda Banken AB",
    orgNumber: "502032-9081",
    address: ["106 40 Stockholm"],
    website: "www.seb.se",
  },
  Nordea: {
    fullName: "Nordea Bank Abp",
    orgNumber: "516406-0120",
    address: ["105 71 Stockholm"],
    website: "www.nordea.se",
  },
  Avanza: {
    fullName: "Avanza Bank AB",
    orgNumber: "556573-5668",
    address: ["Box 1399", "111 93 Stockholm"],
    website: "www.avanza.se",
  },
  // Myndigheter
  Skatteverket: {
    fullName: "Skatteverket",
    orgNumber: "202100-5448",
    address: ["171 94 Solna"],
    website: "www.skatteverket.se",
  },
  Försäkringskassan: {
    fullName: "Försäkringskassan",
    orgNumber: "202100-5521",
    address: ["103 51 Stockholm"],
    website: "www.forsakringskassan.se",
  },
  Pensionsmyndigheten: {
    fullName: "Pensionsmyndigheten",
    orgNumber: "202100-6255",
    address: ["106 87 Stockholm"],
    website: "www.pensionsmyndigheten.se",
  },
  CSN: {
    fullName: "Centrala studiestödsnämnden",
    orgNumber: "202100-1819",
    address: ["851 82 Sundsvall"],
    website: "www.csn.se",
  },
  // Arbetsgivare
  Arbetsgivaren: {
    fullName: "Arbetsgivaren AB",
    orgNumber: "556xxx-xxxx",
    address: [],
  },
};

function lookupSender(sender: string): SenderMeta {
  // Prova exakt match först, sen substring
  if (SENDER_META[sender]) return SENDER_META[sender];
  for (const key of Object.keys(SENDER_META)) {
    if (sender.includes(key)) {
      // För "Linköping Bostäder" → använd "Bostäder"-template men byt namn
      if (key === "Bostäder") {
        return {
          ...SENDER_META[key],
          fullName: sender + " AB",
        };
      }
      return SENDER_META[key];
    }
  }
  // Fallback för okänd avsändare — generera plausibel meta
  return {
    fullName: sender,
    orgNumber: "—",
    address: [],
  };
}

// Faktura-typ-badge utifrån mail_type + sender_kind
function fakturaBadge(
  mail_type: string,
  sender_kind: string,
): { label: string; color: string } {
  if (mail_type === "salary_slip") return { label: "LÖNESPEC", color: "#3b82f6" };
  if (mail_type === "reminder") return { label: "PÅMINNELSE", color: "#dc2626" };
  if (mail_type === "authority") return { label: "MYNDIGHETSPOST", color: "#16a34a" };
  if (mail_type === "info") return { label: "INFORMATION", color: "#64748b" };
  // invoice — variera baserat på sender_kind
  if (sender_kind === "cred") return { label: "KREDITKORTSFAKTURA", color: "#6366f1" };
  return { label: "FAKTURA", color: "#dc4c2b" };
}

export function MailDetailV2() {
  const { mailId } = useParams<{ mailId: string }>();
  const id = mailId ? parseInt(mailId, 10) : 0;
  const [data, setData] = useState<V2MailDetailData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);
  const [exportMsg, setExportMsg] = useState<string | null>(null);
  // Fas 4 · BankID-signering state för lån. MÅSTE deklareras före
  // alla conditional early-returns annars bryter vi Rules of Hooks
  // (React kastar och hela vyn blir vitskärm).
  const [bankIdSession, setBankIdSession] = useState<{
    token: string;
    qr_url: string;
    expires_at: string;
  } | null>(null);
  const [, setBankIdBusy] = useState(false);
  const [bankIdError, setBankIdError] = useState<string | null>(null);
  const [bankIdConfirmed, setBankIdConfirmed] = useState(false);
  // IDs av lån-erbjudanden som FORTFARANDE är pending (godkända men
  // ej accepterade). Vi visar "Acceptera lånet"-knappen bara om
  // brevets _loan_application_id-marker finns i denna mängd. Om
  // eleven redan accepterat via /v2/lan eller via tidigare brev-
  // klick gömmer vi knappen för att undvika dubbla accepter.
  const [pendingLoanIds, setPendingLoanIds] = useState<Set<number>>(
    new Set(),
  );
  const navigate = useNavigate();

  function refreshPendingLoanIds() {
    v2Api.creditPendingOffers()
      .then((d) =>
        setPendingLoanIds(new Set(d.offers.map((o) => o.application_id))),
      )
      .catch(() => null);
  }

  useEffect(() => {
    if (!id) return;
    v2Api
      .mailDetail(id)
      .then(setData)
      .catch((e) => setError(String((e as Error)?.message || e)));
    refreshPendingLoanIds();
  }, [id]);

  async function exportToBank() {
    if (!data) return;
    setExporting(true);
    setExportMsg(null);
    try {
      await v2Api.postladanExport(id, {});
      setExportMsg("✓ Exporterad till banken — gå till BankID för att signera");
      // Refresh detail vy så status uppdateras
      const refreshed = await v2Api.mailDetail(id);
      setData(refreshed);
    } catch (e) {
      setExportMsg(`Fel: ${String((e as Error)?.message || e)}`);
    } finally {
      setExporting(false);
    }
  }

  async function setStatus(
    status: "paid" | "expired" | "viewed" | "handled",
  ) {
    if (!data) return;
    setExporting(true);
    setExportMsg(null);
    try {
      await v2Api.updateMailStatus(id, status);
      const refreshed = await v2Api.mailDetail(id);
      setData(refreshed);
      const labels = {
        paid: "✓ Markerat som betalt",
        expired: "⊘ Markerat som ignorerat (utgången)",
        viewed: "✓ Markerat som granskad",
        handled: "✓ Markerat som hanterat",
      };
      setExportMsg(labels[status]);
    } catch (e) {
      setExportMsg(`Fel: ${String((e as Error)?.message || e)}`);
    } finally {
      setExporting(false);
    }
  }

  if (error && !data) {
    return (
      <div className="v2-lan-root">
        <V2Banner status={{ role: "student", is_super_admin: false }} />
        <div className="bank-loading">
          <div>
            <div style={{ color: "#fca5a5", marginBottom: 8 }}>
              Kunde inte ladda brev
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
        <div className="bank-loading">Laddar brev…</div>
      </div>
    );
  }

  const m = data.mail;
  const isCcInvoice = data.cc_invoice != null;
  const isSalarySlip = data.salary_slip != null;
  const isStructuredInvoice = data.invoice != null;

  // Anställningserbjudande · body innehåller "_employment_id=N"-marker
  // som vi skickar med vid accept/decline. Marker döljs visuellt.
  const employmentIdMatch = m.body?.match(/_employment_id=(\d+)/);
  const employmentOfferId = employmentIdMatch
    ? parseInt(employmentIdMatch[1], 10)
    : null;
  // Lånegodkännande · body innehåller "_loan_application_id=N"-marker.
  const loanIdMatch = m.body?.match(/_loan_application_id=(\d+)/);
  const loanApplicationId = loanIdMatch
    ? parseInt(loanIdMatch[1], 10)
    : null;
  const bodyClean = m.body
    ? m.body
        .replace(/_employment_id=\d+\n?/g, "")
        .replace(/_loan_application_id=\d+\n?/g, "")
        .trim()
    : "";

  async function respondToLoanOffer(accept: boolean) {
    if (loanApplicationId == null) return;
    if (!accept) {
      if (!confirm("Tacka nej till lånet?")) return;
      setExporting(true);
      setExportMsg(null);
      try {
        await v2Api.creditDecline(loanApplicationId);
        await v2Api.updateMailStatus(id, "handled");
        const refreshed = await v2Api.mailDetail(id);
        setData(refreshed);
        setExportMsg("Du tackade nej till lånet.");
      } catch (e) {
        setExportMsg(`Fel: ${String((e as Error)?.message || e)}`);
      } finally {
        setExporting(false);
      }
      return;
    }
    // Accept-flow · initiera BankID-session, visa QR-kod, polla
    // tills mobilen bekräftar (matchar /v2/bank-id-flödet).
    setBankIdBusy(true);
    setBankIdError(null);
    setBankIdConfirmed(false);
    try {
      const s = await v2Api.bankSessionInit(
        `private_loan_sign_${loanApplicationId}`,
      );
      setBankIdSession({
        token: s.token,
        qr_url: s.qr_url,
        expires_at: s.expires_at,
      });
    } catch (e) {
      const msg = String((e as Error)?.message || e);
      if (msg.includes("PIN saknas") || msg.includes("set-pin")) {
        setExportMsg(
          "BankID saknar PIN. Sätt först din bank-PIN under /v2/bank-id.",
        );
      } else {
        setExportMsg(`Fel vid BankID-init: ${msg}`);
      }
    } finally {
      setBankIdBusy(false);
    }
  }

  // Polla session-status så fort vi har en aktiv session. Avbryts
  // när modalen stängs eller sessionen bekräftas.
  useEffect(() => {
    if (!bankIdSession || bankIdConfirmed) return;
    const token = bankIdSession.token;
    let cancelled = false;
    const interval = setInterval(async () => {
      try {
        const status = await v2Api.bankSessionStatus(token);
        if (cancelled) return;
        if (status.confirmed_at) {
          setBankIdConfirmed(true);
          clearInterval(interval);
          // Auto-fortsätt med accept så fort signering bekräftats
          if (loanApplicationId == null) return;
          try {
            const res = await v2Api.creditAcceptFromMail(
              loanApplicationId, token,
            );
            await v2Api.updateMailStatus(id, "handled");
            const refreshed = await v2Api.mailDetail(id);
            setData(refreshed);
            refreshPendingLoanIds();
            setBankIdSession(null);
            setExportMsg(
              `✓ Lån signerat & accepterat · ${Math.round(res.deposited_amount).toLocaleString("sv-SE")} kr insatt. ${res.pedagogical_note}`,
            );
          } catch (e) {
            setBankIdError(
              `Lånet kunde inte slutföras: ${String((e as Error)?.message || e)}`,
            );
          }
        }
      } catch {
        // Tyst — session kan ha löpt ut, polla igen
      }
    }, 1500);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [bankIdSession, bankIdConfirmed, loanApplicationId, id]);

  async function respondToOffer(accept: boolean) {
    if (employmentOfferId == null) return;
    let reason: string | undefined;
    if (!accept) {
      const r = prompt(
        "Skäl till att tacka nej (frivilligt — visas för företagaren)",
        "",
      );
      if (r === null) return;
      reason = r.trim() || undefined;
    } else {
      if (
        !confirm(
          "Acceptera anställning?\n\n"
            + "· Din nuvarande anställning sägs upp automatiskt med 30 dgr varsel (LAS).\n"
            + "· Din profil byter arbetsgivare direkt och första lönespec utbetalas den 25:e.\n\n"
            + "Är du säker?",
        )
      ) {
        return;
      }
    }
    setExporting(true);
    setExportMsg(null);
    try {
      if (accept) {
        await v2Api.employmentAccept(employmentOfferId);
      } else {
        await v2Api.employmentDecline(employmentOfferId, reason);
      }
      await v2Api.updateMailStatus(id, "handled");
      const refreshed = await v2Api.mailDetail(id);
      setData(refreshed);
      setExportMsg(
        accept ? "✓ Anställning accepterad — välkommen!" : "Du tackade nej.",
      );
    } catch (e) {
      setExportMsg(`Fel: ${String((e as Error)?.message || e)}`);
    } finally {
      setExporting(false);
    }
  }

  // Avsändar-icon-färg per kind
  const senderColors: Record<string, string> = {
    cred: "linear-gradient(135deg, #6366f1 0%, #818cf8 100%)",
    work: "linear-gradient(135deg, #1e3a8a 0%, #3b82f6 100%)",
    skv: "linear-gradient(135deg, #166534 0%, #16a34a 100%)",
    bank: "linear-gradient(135deg, #be185d 0%, #ec4899 100%)",
    ins: "linear-gradient(135deg, #b45309 0%, #f59e0b 100%)",
    util: "linear-gradient(135deg, #0e7490 0%, #06b6d4 100%)",
    pen: "linear-gradient(135deg, #b45309 0%, #ea580c 100%)",
    land: "linear-gradient(135deg, #166534 0%, #22c55e 100%)",
    other: "linear-gradient(135deg, #475569 0%, #64748b 100%)",
  };
  const senderBg = senderColors[m.sender_kind] || senderColors.other;

  // Faktura-meta för shellen
  const senderMeta = lookupSender(m.sender);
  const badge = fakturaBadge(m.mail_type, m.sender_kind);
  const fakturaNumber = data.invoice?.invoice_number
    || (m.ocr_reference ? `#${m.ocr_reference.slice(0, 10)}` : null);

  return (
    <div className="v2-lan-root">
      <V2Banner status={{ role: "student", is_super_admin: false }} />

      <div className="shell">
        <Link className="actor-back" to="/v2/postladan">
          Tillbaka till postlådan
        </Link>

        <article className="faktura-shell">
          {/* === FAKTURA HEADER · avsändare + badge + meta === */}
          <header className="fs-head">
            <div className="fs-head-left">
              <div
                className="fs-sender-logo"
                style={{ background: senderBg }}
              >
                {m.sender_short || m.sender.slice(0, 3).toUpperCase()}
              </div>
              <div className="fs-sender-block">
                <div className="fs-sender-name">{senderMeta.fullName}</div>
                <div className="fs-sender-meta">
                  Org.nr {senderMeta.orgNumber}
                  {senderMeta.address.map((line, i) => (
                    <span key={i}> · {line}</span>
                  ))}
                  {senderMeta.website && <span> · {senderMeta.website}</span>}
                </div>
              </div>
            </div>
            <div className="fs-head-right">
              <span
                className="fs-badge"
                style={{
                  borderColor: badge.color,
                  color: badge.color,
                }}
              >
                {badge.label}
              </span>
            </div>
          </header>

          {/* === META-RAD · kund + datum + fakturanr + förfaller === */}
          <div className="fs-meta-grid">
            <div className="fs-meta-cell">
              <div className="fs-meta-eye">Mottagare</div>
              <div className="fs-meta-val fs-meta-val-name">
                {(data as { recipient_name?: string }).recipient_name || "Privatperson"}
              </div>
            </div>
            <div className="fs-meta-cell">
              <div className="fs-meta-eye">
                {m.mail_type === "salary_slip" ? "Utbetald" : "Fakturadatum"}
              </div>
              <div className="fs-meta-val">
                {SHORT_DATE(m.received_at)}
              </div>
            </div>
            {fakturaNumber && (
              <div className="fs-meta-cell">
                <div className="fs-meta-eye">
                  {m.mail_type === "salary_slip" ? "Lönespec" : "Fakturanr"}
                </div>
                <div className="fs-meta-val fs-meta-val-mono">
                  {fakturaNumber}
                </div>
              </div>
            )}
            {m.due_date && m.mail_type !== "salary_slip" && (
              <div className="fs-meta-cell fs-meta-cell-emphasis">
                <div className="fs-meta-eye">Förfaller</div>
                <div className="fs-meta-val fs-meta-val-due">
                  {SHORT_DATE(m.due_date)}
                </div>
              </div>
            )}
          </div>

          {/* === SUBJECT (stor) === */}
          <div className="fs-subject">
            <h1 className="fs-subject-h">{m.subject}</h1>
            {m.body_meta && (
              <div className="fs-subject-meta">{m.body_meta}</div>
            )}
          </div>

          {/* Body */}
          <div style={{ padding: "24px 28px" }}>
            {isCcInvoice && data.cc_invoice && (
              <CcInvoiceLayout cc={data.cc_invoice} />
            )}
            {isSalarySlip && data.salary_slip && (
              <SalarySlipLayout sal={data.salary_slip} />
            )}
            {!isCcInvoice && !isSalarySlip && isStructuredInvoice
              && data.invoice && (
              <InvoiceLayout inv={data.invoice} />
            )}
            {!isCcInvoice && !isSalarySlip && !isStructuredInvoice
              && bodyClean && (
              <div
                style={{
                  fontFamily: "var(--serif)",
                  fontSize: 14.5,
                  lineHeight: 1.6,
                  whiteSpace: "pre-wrap",
                  color: "var(--text)",
                }}
              >
                {bodyClean}
              </div>
            )}

            {exportMsg && (
              <div
                style={{
                  marginTop: 18,
                  padding: "10px 16px",
                  border: exportMsg.startsWith("Fel")
                    ? "1px solid rgba(252,165,165,0.4)"
                    : "1px solid rgba(110,231,183,0.4)",
                  background: exportMsg.startsWith("Fel")
                    ? "rgba(252,165,165,0.06)"
                    : "rgba(110,231,183,0.06)",
                  borderRadius: 6,
                  fontFamily: "var(--mono)",
                  fontSize: 11,
                  color: exportMsg.startsWith("Fel") ? "#fca5a5" : "#6ee7b7",
                }}
              >
                {exportMsg}
              </div>
            )}

            {/* === BETALNINGSBLOCK · pedagogiskt fakturalik ruta === */}
            {(m.bankgiro || m.ocr_reference) && m.mail_type !== "salary_slip"
              && m.mail_type !== "info" && (
              <div className="fs-pay-block">
                <div className="fs-pay-eye">● Betalning</div>
                <div className="fs-pay-grid">
                  {m.bankgiro && (
                    <div>
                      <div className="fs-pay-cell-eye">Bankgiro</div>
                      <div className="fs-pay-cell-val">{m.bankgiro}</div>
                    </div>
                  )}
                  {m.ocr_reference && (
                    <div>
                      <div className="fs-pay-cell-eye">OCR / referens</div>
                      <div className="fs-pay-cell-val fs-pay-cell-mono">
                        {m.ocr_reference}
                      </div>
                    </div>
                  )}
                  {m.due_date && (
                    <div>
                      <div className="fs-pay-cell-eye">Förfaller</div>
                      <div className="fs-pay-cell-val fs-pay-cell-due">
                        {SHORT_DATE(m.due_date)}
                      </div>
                    </div>
                  )}
                  {m.amount != null && (
                    <div>
                      <div className="fs-pay-cell-eye">Att betala</div>
                      <div className="fs-pay-cell-val fs-pay-cell-amount">
                        {m.amount > 0 ? "+ " : ""}
                        {SEK(Math.abs(m.amount))} kr
                      </div>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Actions */}
            <div
              style={{
                display: "flex",
                gap: 10,
                flexWrap: "wrap",
                marginTop: 28,
                paddingTop: 22,
                borderTop: "1px solid var(--line)",
              }}
            >
              {/* Anställningserbjudande · accept / decline · bara om
                  status fortfarande unhandled OCH employment_id finns. */}
              {employmentOfferId != null && m.status === "unhandled" && (
                <>
                  <button
                    type="button"
                    className="cta-btn"
                    disabled={exporting}
                    onClick={() => respondToOffer(true)}
                    style={{ border: 0, cursor: "pointer" }}
                  >
                    ✓ Acceptera anställning
                  </button>
                  <button
                    type="button"
                    className="cta-btn ghost"
                    disabled={exporting}
                    onClick={() => respondToOffer(false)}
                    style={{ border: 0, cursor: "pointer" }}
                  >
                    ✗ Tacka nej
                  </button>
                </>
              )}
              {/* Lånegodkännande · accept / decline · samma mönster
                  som employment, bara om status fortfarande unhandled
                  OCH _loan_application_id finns i body OCH application
                  fortfarande är pending (har inte redan accepterats
                  via /v2/lan-vyn). */}
              {loanApplicationId != null
                && m.status === "unhandled"
                && pendingLoanIds.has(loanApplicationId) && (
                <>
                  <button
                    type="button"
                    className="cta-btn"
                    disabled={exporting}
                    onClick={() => respondToLoanOffer(true)}
                    style={{ border: 0, cursor: "pointer" }}
                  >
                    ✓ Acceptera lånet
                  </button>
                  <button
                    type="button"
                    className="cta-btn ghost"
                    disabled={exporting}
                    onClick={() => respondToLoanOffer(false)}
                    style={{ border: 0, cursor: "pointer" }}
                  >
                    ✗ Tacka nej till lånet
                  </button>
                </>
              )}
              {/* Faktura kan exporteras till banken (skapar UpcomingTransaction) */}
              {(m.mail_type === "invoice" || m.mail_type === "reminder") &&
                m.amount !== null && (
                  <button
                    type="button"
                    className="cta-btn"
                    disabled={exporting || m.upcoming_id !== null}
                    onClick={exportToBank}
                    style={{ border: 0, cursor: "pointer" }}
                  >
                    {exporting
                      ? "Exporterar…"
                      : m.upcoming_id !== null
                      ? "✓ Exporterad till banken"
                      : "Exportera till banken (signera) →"}
                  </button>
                )}
              {m.upcoming_id !== null && (
                <button
                  type="button"
                  className="cta-btn"
                  onClick={() => navigate("/v2/banken")}
                  style={{ border: 0, cursor: "pointer" }}
                >
                  Gå till banken & signera →
                </button>
              )}
              {/* Försök igen · för failed autogiro-dragningar (SKV-5) */}
              {m.status === "failed" && (
                <button
                  type="button"
                  className="cta-btn primary"
                  disabled={exporting}
                  onClick={async () => {
                    try {
                      const res = await v2Api.retryPayment(m.id);
                      alert(res.message);
                      if (res.status === "paid") {
                        // Reload current page
                        window.location.reload();
                      }
                    } catch (e) {
                      alert(
                        "Kunde inte försöka igen: "
                        + String((e as Error)?.message || e),
                      );
                    }
                  }}
                  style={{ cursor: "pointer" }}
                >
                  Försök igen →
                </button>
              )}
              {/* Markera som betald manuellt (utan att gå via BankID) */}
              {(m.mail_type === "invoice" || m.mail_type === "reminder") &&
                m.status !== "paid" &&
                m.status !== "expired" &&
                m.status !== "failed" && (
                  <button
                    type="button"
                    className="cta-btn ghost"
                    disabled={exporting}
                    onClick={() => setStatus("paid")}
                    style={{ border: 0, cursor: "pointer" }}
                  >
                    Markera som betald →
                  </button>
                )}
              {/* Markera som hanterat — för info/authority/reminder/
                  salary_slip där det inte finns en "betal"-action.
                  Försvinner från postlådan + dashboard som
                  "senaste händelse". */}
              {(m.mail_type === "info"
                || m.mail_type === "authority"
                || m.mail_type === "salary_slip"
                || (m.mail_type === "reminder" && (m.amount ?? 0) >= 0))
                && m.status !== "handled"
                && m.status !== "paid"
                && m.status !== "exported" && (
                  <button
                    type="button"
                    className="cta-btn ghost"
                    disabled={exporting}
                    onClick={() => setStatus("handled")}
                    style={{ border: 0, cursor: "pointer" }}
                  >
                    Markera som hanterat ✓
                  </button>
                )}
              {/* Ignorera = sätt expired (eleven har valt att inte hantera) */}
              {m.status === "unhandled" && (
                <button
                  type="button"
                  className="cta-btn ghost"
                  disabled={exporting}
                  onClick={() => {
                    if (
                      m.mail_type === "invoice" &&
                      !confirm(
                        "Ignorera fakturan? Den blir 'utgången' och påverkar pentagonen negativt (säkerhet & ekonomi)." +
                        " Använd hellre 'Markera betald' eller 'Exportera till banken' om du faktiskt hanterar den.",
                      )
                    ) return;
                    setStatus("expired");
                  }}
                  style={{ border: 0, cursor: "pointer" }}
                >
                  Ignorera (markera utgången)
                </button>
              )}
              {isSalarySlip && (
                <Link
                  to="/v2/arbetsgivaren"
                  className="cta-btn"
                  style={{ textDecoration: "none" }}
                >
                  Se hos arbetsgivaren →
                </Link>
              )}
              {isSalarySlip && (
                <Link
                  to="/v2/maria"
                  className="cta-btn ghost"
                  style={{ textDecoration: "none" }}
                >
                  Använd i Maria-samtalet →
                </Link>
              )}
              {/* Ladda ner som riktig PDF · bara för fakturor med
                  invoice_data (inte CC-fakturor eller lönespec som
                  har egna layouter). */}
              {isStructuredInvoice && (
                <button
                  type="button"
                  className="cta-btn ghost"
                  style={{ border: 0, cursor: "pointer" }}
                  onClick={async () => {
                    try {
                      const blob = await v2Api.mailPdf(id);
                      const url = URL.createObjectURL(blob);
                      window.open(url, "_blank");
                      // Frigör blob-URL efter 60 sek
                      setTimeout(() => URL.revokeObjectURL(url), 60000);
                    } catch (e) {
                      setExportMsg(`Fel: ${String((e as Error)?.message || e)}`);
                    }
                  }}
                >
                  ⬇ Ladda ner som PDF
                </button>
              )}
              <Link
                to="/v2/postladan"
                className="cta-btn ghost"
                style={{ textDecoration: "none" }}
              >
                Tillbaka till postlådan
              </Link>
            </div>
          </div>
        </article>

        {/* Pedagogik */}
        {isCcInvoice && <CcPedaBlock />}
        {isSalarySlip && <SalaryPedaBlock />}

        {/* BankID-modal · QR-kod-flöde (Fas 4 · v2) · matchar
            /v2/bank-id-flödet. Eleven scannar QR med mobilen, går
            till /bank/sign?token=…, anger PIN. Web pollar var 1.5s
            och fortsätter accept automatiskt vid bekräftelse. */}
        {bankIdSession && (
          <BankIdSignModal
            session={bankIdSession}
            confirmed={bankIdConfirmed}
            error={bankIdError}
            onClose={() => {
              setBankIdSession(null);
              setBankIdError(null);
              setBankIdConfirmed(false);
            }}
          />
        )}

      </div>
    </div>
  );
}

/**
 * Strukturerad fakturarendering · för game_engine-fakturor
 * (el, mobil, bredband, hyra, BRF-avgift, bolån, drift, försäkring,
 * lokaltrafik). Visar header med fakturanummer + period, tabell med
 * rader (label, qty, unit, price, amount), moms-sektion, totalsumma
 * och payment-info. Analog SalarySlipLayout.
 */
function InvoiceLayout({ inv }: { inv: V2InvoiceData }) {
  const periodLabel =
    inv.period_start && inv.period_end
      ? `${SHORT_DATE(inv.period_start)} – ${SHORT_DATE(inv.period_end)}`
      : "—";
  const extra = inv.extra || {};
  const momsNote = (extra.moms_note as string) || null;
  const tip = (extra.tip as string) || null;
  const policyNotes = (extra.policy_notes as string) || null;

  return (
    <>
      {/* HEADER · fakturanummer + period */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr 1fr",
          gap: 10,
          marginBottom: 22,
        }}
      >
        <StatCard
          eye="Fakturanummer"
          value={inv.invoice_number}
          sub={`Period ${periodLabel}`}
        />
        <StatCard
          eye="Att betala"
          value={`${SEK(inv.total)} kr`}
          sub={
            inv.moms > 0
              ? `inkl moms ${Math.round(inv.moms_rate)} %`
              : "momsfritt"
          }
          warm
        />
        <StatCard
          eye="OCR-referens"
          value={inv.ocr || "—"}
          sub={inv.bankgiro ? `BG ${inv.bankgiro}` : "—"}
        />
      </div>

      {/* SPECIFIKATION · rader */}
      <div className="section-eye" style={{ marginBottom: 14 }}>
        Specifikation · {inv.rows.length} {inv.rows.length === 1 ? "rad" : "rader"}
      </div>
      <div
        style={{
          background: "rgba(255,255,255,0.02)",
          border: "1px solid var(--line)",
          borderRadius: 6,
          padding: "16px 22px",
          marginBottom: 22,
        }}
      >
        <table
          style={{
            width: "100%",
            borderCollapse: "collapse",
            fontFamily: "var(--mono)",
            fontSize: 12,
          }}
        >
          <tbody>
            {inv.rows.map((r, i) => {
              const showQty = r.qty != null;
              return (
                <tr
                  key={i}
                  style={{
                    borderTop: "1px solid rgba(255,255,255,0.04)",
                  }}
                >
                  <td
                    style={{
                      padding: "10px 0",
                      color: "var(--text)",
                      fontFamily: "var(--mono)",
                      fontSize: 12,
                    }}
                  >
                    {r.label}
                    {showQty && (
                      <div
                        style={{
                          fontSize: 10,
                          color: "var(--text-dim)",
                          marginTop: 2,
                        }}
                      >
                        {r.qty} {r.unit || ""}
                        {r.unit_price != null
                          && ` × ${r.unit_price.toFixed(2)} kr`}
                      </div>
                    )}
                  </td>
                  <td
                    style={{
                      padding: "10px 0",
                      textAlign: "right",
                      color: "#fff",
                      fontFamily: "var(--mono)",
                      fontSize: 12,
                    }}
                  >
                    {SEK(r.amount)} kr
                  </td>
                </tr>
              );
            })}

            {/* SUBTOTAL */}
            <tr
              style={{
                borderTop: "1px solid var(--line-strong)",
              }}
            >
              <td
                style={{
                  padding: "10px 0",
                  color: "var(--text-mid)",
                  fontFamily: "var(--mono)",
                  fontSize: 11,
                  textTransform: "uppercase",
                  letterSpacing: "0.6px",
                }}
              >
                Subtotal (exkl moms)
              </td>
              <td
                style={{
                  padding: "10px 0",
                  textAlign: "right",
                  color: "var(--text-mid)",
                  fontFamily: "var(--mono)",
                  fontSize: 12,
                }}
              >
                {SEK(inv.subtotal)} kr
              </td>
            </tr>

            {/* MOMS */}
            {inv.moms > 0 && (
              <tr>
                <td
                  style={{
                    padding: "6px 0",
                    color: "var(--text-mid)",
                    fontFamily: "var(--mono)",
                    fontSize: 11,
                  }}
                >
                  Moms {Math.round(inv.moms_rate)} %
                </td>
                <td
                  style={{
                    padding: "6px 0",
                    textAlign: "right",
                    color: "var(--text-mid)",
                    fontFamily: "var(--mono)",
                    fontSize: 12,
                  }}
                >
                  {SEK(inv.moms)} kr
                </td>
              </tr>
            )}

            {/* TOTAL */}
            <tr style={{ borderTop: "1px solid var(--warm)" }}>
              <td
                style={{
                  padding: "12px 0",
                  color: "var(--warm)",
                  fontFamily: "var(--serif)",
                  fontSize: 14,
                  fontWeight: 700,
                }}
              >
                TOTALT ATT BETALA
              </td>
              <td
                style={{
                  padding: "12px 0",
                  textAlign: "right",
                  color: "var(--warm)",
                  fontFamily: "var(--serif)",
                  fontSize: 16,
                  fontWeight: 700,
                  fontStyle: "italic",
                }}
              >
                {SEK(inv.total)} kr
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      {/* MOMS-INFO + tip + försäkringsvillkor */}
      {(momsNote || tip || policyNotes) && (
        <div
          style={{
            padding: "12px 16px",
            background: "rgba(99,102,241,0.06)",
            border: "1px solid rgba(99,102,241,0.2)",
            borderRadius: 6,
            marginBottom: 18,
            fontFamily: "var(--serif)",
            fontSize: 12.5,
            color: "var(--text-mid)",
            lineHeight: 1.5,
          }}
        >
          {momsNote && (
            <div>
              <strong style={{ color: "#a5b4fc" }}>Moms-info: </strong>
              {momsNote}
            </div>
          )}
          {tip && (
            <div style={{ marginTop: momsNote ? 6 : 0 }}>
              <strong style={{ color: "#a5b4fc" }}>Tips: </strong>
              {tip}
            </div>
          )}
          {policyNotes && (
            <div style={{ marginTop: 6 }}>
              <strong style={{ color: "#a5b4fc" }}>
                Försäkringsvillkor:{" "}
              </strong>
              {policyNotes}
            </div>
          )}
        </div>
      )}

      {/* BETALNINGSINFO */}
      <div
        style={{
          padding: "12px 16px",
          border: "1px solid var(--line)",
          borderRadius: 6,
          fontFamily: "var(--mono)",
          fontSize: 11,
          color: "var(--text-mid)",
          letterSpacing: "0.4px",
        }}
      >
        Betala via banken senast på förfallodagen. Vid försening:
        påminnelseavgift 60-95 kr + ränta enl. räntelagen.
      </div>
    </>
  );
}

function CcInvoiceLayout({ cc }: { cc: NonNullable<V2MailDetailData["cc_invoice"]> }) {
  const diff =
    cc.diff_pct_vs_prev != null
      ? `${cc.diff_pct_vs_prev >= 0 ? "+" : ""}${cc.diff_pct_vs_prev.toFixed(1)} %`
      : null;
  return (
    <>
      {/* CC-summary 3 stat-cards */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(3, 1fr)",
          gap: 10,
          marginBottom: 22,
        }}
      >
        <StatCard
          eye="Total fakturasumma"
          value={`${SEK(cc.total_amount)} kr`}
          sub={`${cc.tx_count} köp under perioden`}
        />
        <StatCard
          eye="Att klassa själv"
          value={`${cc.unclassified_count} / ${cc.tx_count}`}
          sub={`${cc.auto_classified_count} auto-klassade`}
          warm={cc.unclassified_count > 0}
        />
        <StatCard
          eye={`Snitt köp · profil ${cc.profile_label}`}
          value={`${SEK(cc.avg_amount)} kr`}
          sub={`Konsumentverket: ${SEK(cc.consumer_avg)} kr · slösa-profil: ${SEK(cc.profile_avg)} kr`}
        />
      </div>

      <div
        className="section-eye"
        style={{ marginBottom: 14 }}
      >
        Transaktioner · sorterat efter datum ({cc.tx_count})
      </div>

      {cc.transactions.length === 0 ? (
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
          Inga transaktioner hittade i perioden{" "}
          {SHORT_DATE(cc.period_start)} – {SHORT_DATE(cc.period_end)}.
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          {cc.transactions.map((t) => (
            <Link
              to={`/v2/tx/${t.id}`}
              key={t.id}
              style={{
                display: "grid",
                gridTemplateColumns: "100px 1fr 100px 90px 60px",
                gap: 10,
                padding: "10px 14px",
                background: t.is_classified
                  ? "rgba(15,21,37,0.5)"
                  : "rgba(220,76,43,0.06)",
                border: "1px solid var(--line)",
                borderLeftWidth: 3,
                borderLeftColor: t.is_classified
                  ? "var(--line-strong)"
                  : "var(--accent)",
                borderRadius: 4,
                textDecoration: "none",
                color: "inherit",
                cursor: "pointer",
                alignItems: "center",
              }}
            >
              <span
                style={{
                  fontFamily: "var(--mono)",
                  fontSize: 11,
                  color: "var(--text-mid)",
                }}
              >
                {SHORT_DATE(t.date)}
              </span>
              <div>
                <div
                  style={{
                    fontFamily: "var(--serif)",
                    fontSize: 13.5,
                  }}
                >
                  {t.raw_description}
                </div>
                <div
                  style={{
                    fontFamily: "var(--mono)",
                    fontSize: 9.5,
                    color: "var(--text-dim)",
                  }}
                >
                  {t.normalized_merchant || "—"}
                  {t.user_verified ? " · manuell" : t.is_classified ? " · auto" : " · oklassad"}
                </div>
              </div>
              <span
                style={{
                  fontFamily: "var(--mono)",
                  fontSize: 11,
                  color: t.is_classified
                    ? "var(--text-mid)"
                    : "var(--accent)",
                  fontWeight: t.is_classified ? "normal" : 700,
                  letterSpacing: "0.6px",
                  textTransform: "uppercase",
                }}
              >
                {t.category_name || "Klassa"}
              </span>
              <span
                style={{
                  fontFamily: "var(--serif)",
                  fontSize: 13,
                  textAlign: "right",
                }}
              >
                {t.amount > 0 ? "+ " : "− "}
                {SEK(Math.abs(t.amount))} kr
              </span>
              <span
                style={{
                  fontFamily: "var(--mono)",
                  fontSize: 9,
                  color: t.is_classified
                    ? "var(--text-dim)"
                    : "var(--warm)",
                  textAlign: "right",
                }}
              >
                {t.is_classified ? "se →" : "klassa →"}
              </span>
            </Link>
          ))}
        </div>
      )}

      {cc.prev_month_amount != null && (
        <div
          style={{
            marginTop: 22,
            padding: "16px 20px",
            background: "rgba(99,102,241,0.06)",
            border: "1px solid rgba(99,102,241,0.2)",
            borderRadius: 6,
          }}
        >
          <div
            style={{
              fontFamily: "var(--mono)",
              fontSize: 10,
              fontWeight: 700,
              letterSpacing: "1.4px",
              textTransform: "uppercase",
              color: "#a5b4fc",
              marginBottom: 8,
            }}
          >
            ● Hur fakturan utvecklats
          </div>
          <p
            style={{
              fontFamily: "var(--serif)",
              fontSize: 14,
              lineHeight: 1.5,
              color: "var(--text)",
              margin: 0,
            }}
          >
            Föregående period: <strong>{SEK(cc.prev_month_amount)} kr</strong>.
            Den här perioden:{" "}
            <strong style={{ color: "var(--warm)" }}>
              {SEK(cc.total_amount)} kr
            </strong>
            . Skillnad: <strong>{diff || "—"}</strong>
            {diff && cc.diff_pct_vs_prev != null && cc.diff_pct_vs_prev > 5
              ? " — en signal Echo plockar upp."
              : ""}
          </p>
        </div>
      )}
    </>
  );
}

function SalarySlipLayout({ sal }: { sal: NonNullable<V2MailDetailData["salary_slip"]> }) {
  return (
    <>
      {/* Lönespec-summary */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(3, 1fr)",
          gap: 10,
          marginBottom: 22,
        }}
      >
        <StatCard
          eye="Bruttolön"
          value={`${SEK(sal.gross_salary)} kr`}
          sub={
            sal.ob_total > 0
              ? `${SEK(sal.gross_salary - sal.ob_total)} grund + ${SEK(sal.ob_total)} OB`
              : "ingen OB-tillägg"
          }
        />
        <StatCard
          eye="Skatt"
          value={`− ${SEK(sal.tax)} kr`}
          sub="tabellskatt + ev. jobbskatteavdrag"
        />
        <StatCard
          eye="Netto till banken"
          value={`${SEK(sal.net_salary)} kr`}
          sub={`brutto-effektivitet ${Math.round((sal.net_salary / sal.gross_salary) * 100)} %`}
          warm
        />
      </div>

      <div
        className="section-eye"
        style={{ marginBottom: 14 }}
      >
        Specifikation
      </div>
      <div
        style={{
          background: "rgba(255,255,255,0.02)",
          border: "1px solid var(--line)",
          borderRadius: 6,
          padding: "18px 22px",
          marginBottom: 22,
        }}
      >
        <SpecTable rows={sal.net_lines} />
      </div>

      <div
        className="section-eye"
        style={{ marginTop: 24, marginBottom: 14 }}
      >
        Arbetsgivaravgifter (visas men dras inte från eleven)
      </div>
      <div
        style={{
          background: "rgba(255,255,255,0.02)",
          border: "1px solid var(--line)",
          borderRadius: 6,
          padding: "18px 22px",
          marginBottom: 22,
        }}
      >
        <SpecTable rows={sal.employer_lines} />
        <p
          style={{
            marginTop: 14,
            fontFamily: "var(--serif)",
            fontSize: 13.5,
            lineHeight: 1.5,
            color: "var(--text-mid)",
          }}
        >
          Det här är pedagogiskt viktigt:{" "}
          <em style={{ color: "var(--warm)" }}>
            arbetsgivaren betalar {SEK(sal.total_employer_cost)} kr/mån för
            dig
          </em>{" "}
          — du ser {SEK(sal.net_salary)} kr på kontot. Skillnaden{" "}
          {SEK(sal.total_employer_cost - sal.net_salary)} kr går till
          samhälle (skatt &amp; socialavgifter) och din egen pension.
        </p>
      </div>
    </>
  );
}

function SpecTable({
  rows,
}: {
  rows: { label: string; amount: number; is_total: boolean }[];
}) {
  return (
    <table
      style={{
        width: "100%",
        borderCollapse: "collapse",
        fontFamily: "var(--mono)",
        fontSize: 12,
      }}
    >
      <tbody>
        {rows.map((r, i) => (
          <tr
            key={i}
            style={{
              borderTop: r.is_total
                ? "1px solid var(--warm)"
                : "1px solid rgba(255,255,255,0.04)",
            }}
          >
            <td
              style={{
                padding: "10px 0",
                color: r.is_total ? "var(--warm)" : "var(--text)",
                fontWeight: r.is_total ? 700 : 400,
                fontFamily: r.is_total
                  ? "var(--serif)"
                  : "var(--mono)",
                fontSize: r.is_total ? 14 : 12,
              }}
            >
              {r.label}
            </td>
            <td
              style={{
                padding: "10px 0",
                textAlign: "right",
                color: r.is_total ? "var(--warm)" : "#fff",
                fontWeight: r.is_total ? 700 : 400,
                fontFamily: r.is_total
                  ? "var(--serif)"
                  : "var(--mono)",
                fontSize: r.is_total ? 16 : 12,
                fontStyle: r.is_total ? "italic" : "normal",
              }}
            >
              {r.amount >= 0 ? "" : "− "}
              {SEK(Math.abs(r.amount))} kr
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function StatCard({
  eye, value, sub, warm,
}: {
  eye: string;
  value: string;
  sub: string;
  warm?: boolean;
}) {
  return (
    <div
      style={{
        padding: "16px 20px",
        border: "1px solid var(--line)",
        borderRadius: 6,
      }}
    >
      <div
        style={{
          fontFamily: "var(--mono)",
          fontSize: 9.5,
          letterSpacing: "1.2px",
          textTransform: "uppercase",
          color: "var(--text-dim)",
        }}
      >
        {eye}
      </div>
      <div
        style={{
          fontFamily: "var(--serif)",
          fontSize: 22,
          fontWeight: 700,
          marginTop: 4,
          color: warm ? "var(--warm)" : "#fff",
          fontStyle: warm ? "italic" : "normal",
        }}
      >
        {value}
      </div>
      <div
        style={{
          fontFamily: "var(--mono)",
          fontSize: 10,
          color: "var(--text-mid)",
          marginTop: 4,
        }}
      >
        {sub}
      </div>
    </div>
  );
}

function CcPedaBlock() {
  return (
    <div className="peda" style={{ marginTop: 22 }}>
      <div className="peda-eye">Pedagogik · vad du lär dig här</div>
      <div className="peda-h">
        Kreditkort är <em>förra månadens beslut</em>.
      </div>
      <p className="peda-prose">
        Det är här verkligheten slår tillbaka. Du köpte pizza på Max efter
        laxsim, och 11 dagar senare landar fakturan i postlådan
        tillsammans med 46 andra köp. Kreditkortet är{" "}
        <strong>förra månadens beslut samlade på ett papper</strong>.
        Räntan blir hög om du delbetalar (
        <em>ca 14–18 % årlig effektiv ränta</em>) — det är en av de
        dyraste skuldformerna en ung vuxen kan hamna i.
      </p>
      <ul className="peda-bullets">
        <li>
          <strong>Kreditgräns</strong>Maxbelopp banken låter dig handla
          för. 5 000–50 000 vanligt.
        </li>
        <li>
          <strong>Faktureringsdag</strong>Ofta 25–28:e. Du har 25–30 dgr
          på dig att betala.
        </li>
        <li>
          <strong>Delbetalning</strong>Bekvämt nu, dyrt totalt. Räkna
          räntan innan du klickar.
        </li>
        <li>
          <strong>Räntefri kredit</strong>Köp idag, betala fakturan i sin
          helhet i tid → 0 % ränta.
        </li>
      </ul>
      <div className="peda-concepts">
        <span className="peda-concept">Effektiv ränta</span>
        <span className="peda-concept">Krediteringstid</span>
        <span className="peda-concept">Konsumentkrediter</span>
        <span className="peda-concept">Klassificering</span>
        <span className="peda-concept">Skuldfälla</span>
      </div>
      <div className="peda-tip">
        Klassa de oklassade transaktionerna nu — det är där du faktiskt
        ser ditt eget mönster. Vanor blir synliga när de samlas.
      </div>
    </div>
  );
}

function SalaryPedaBlock() {
  return (
    <div className="peda" style={{ marginTop: 22 }}>
      <div className="peda-eye">Pedagogik · vad du lär dig här</div>
      <div className="peda-h">
        Lönespec är <em>kvittot</em> på en månads samhällskontrakt.
      </div>
      <p className="peda-prose">
        Bruttolönen sätts av <code>kollektivavtal</code> +{" "}
        <code>OB</code>. Skatten dras enligt <code>tabell</code> +{" "}
        <code>jobbskatteavdrag</code>. ITP1 (4,5 %) är pension som{" "}
        <em>arbetsgivaren</em> betalar — du ser den men dras inte. Den
        totala kostnaden för arbetsgivaren är ~ 39 % över din bruttolön
        (sociala avgifter 31,42 %, ITP, friskvård). Det är därför
        arbetsgivare ofta är försiktiga med att höja — varje krona blir
        1,39 kr för dem.
      </p>
      <ul className="peda-bullets">
        <li>
          <strong>Skattetabell</strong>Hänger på kommun + ev.
          kyrkoavgift. Stockholm = lägst.
        </li>
        <li>
          <strong>Jobbskatteavdrag</strong>Sänker skatten ~1 800–2 200
          kr/mån för låg-mellan-inkomst.
        </li>
        <li>
          <strong>OB-tillägg</strong>Beskattas som vanlig lön. Räknas
          pensionsgrundande.
        </li>
        <li>
          <strong>Skatteklass</strong>Tabell 30–37. Beror på födelseår.
        </li>
      </ul>
      <div className="peda-concepts">
        <span className="peda-concept">Bruttolön</span>
        <span className="peda-concept">Nettolön</span>
        <span className="peda-concept">Tabellskatt</span>
        <span className="peda-concept">Sociala avgifter</span>
        <span className="peda-concept">Pensionsgrundande inkomst</span>
      </div>
      <div className="peda-tip">
        Räkna själv: brutto · ta 32 % schablonskatt · jämför med specens
        skatt. Skillnaden är jobbskatteavdraget. Det är så du{" "}
        <em>känner</em> hur skattesystemet är progressivt.
      </div>
    </div>
  );
}
