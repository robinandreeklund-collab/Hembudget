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
  type V2MailDetailData,
} from "./api";
import { V2Banner } from "./V2Banner";
import "./lan.css";

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

const TIME_DATE = (iso: string): string => {
  const d = new Date(iso);
  return d.toLocaleString("sv-SE", {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
};

export function MailDetailV2() {
  const { mailId } = useParams<{ mailId: string }>();
  const id = mailId ? parseInt(mailId, 10) : 0;
  const [data, setData] = useState<V2MailDetailData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);
  const [exportMsg, setExportMsg] = useState<string | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    if (!id) return;
    v2Api
      .mailDetail(id)
      .then(setData)
      .catch((e) => setError(String((e as Error)?.message || e)));
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

  async function setStatus(status: "paid" | "expired" | "viewed") {
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

  return (
    <div className="v2-lan-root">
      <V2Banner status={{ role: "student", is_super_admin: false }} />

      <div className="shell">
        <Link className="actor-back" to="/v2/postladan">
          Tillbaka till postlådan
        </Link>

        <article
          style={{
            background: "rgba(15,21,37,0.7)",
            border: "1px solid var(--line)",
            borderRadius: 8,
          }}
        >
          {/* Header */}
          <header
            style={{
              padding: "24px 28px",
              borderBottom: "1px solid var(--line)",
              display: "flex",
              justifyContent: "space-between",
              gap: 18,
              flexWrap: "wrap",
            }}
          >
            <div style={{ minWidth: 260, flex: "1 1 60%" }}>
              <div
                style={{
                  display: "flex",
                  gap: 14,
                  alignItems: "center",
                  marginBottom: 12,
                }}
              >
                <div
                  style={{
                    width: 44,
                    height: 44,
                    borderRadius: 8,
                    background: senderBg,
                    display: "grid",
                    placeItems: "center",
                    fontFamily: "var(--mono)",
                    fontSize: 11,
                    fontWeight: 700,
                    color: "#fff",
                    flexShrink: 0,
                  }}
                >
                  {m.sender_short || m.sender.slice(0, 3).toUpperCase()}
                </div>
                <div>
                  <div
                    style={{
                      fontFamily: "var(--serif)",
                      fontSize: 16,
                      fontWeight: 700,
                    }}
                  >
                    {m.sender}
                  </div>
                  <div
                    style={{
                      fontFamily: "var(--mono)",
                      fontSize: 10,
                      color: "var(--text-mid)",
                    }}
                  >
                    {m.sender_meta || `${m.mail_type} · ${TIME_DATE(m.received_at)}`}
                  </div>
                </div>
              </div>
              <div
                style={{
                  fontFamily: "var(--serif)",
                  fontSize: 22,
                  fontWeight: 700,
                  letterSpacing: "-0.4px",
                }}
              >
                {m.subject}
              </div>
              {m.body_meta && (
                <div
                  style={{
                    fontFamily: "var(--mono)",
                    fontSize: 11,
                    color: "var(--text-mid)",
                    marginTop: 6,
                  }}
                >
                  {m.body_meta}
                </div>
              )}
            </div>
            <div
              style={{
                fontFamily: "var(--mono)",
                fontSize: 11,
                color: "var(--text-mid)",
                lineHeight: 1.7,
                textAlign: "right",
                minWidth: 200,
              }}
            >
              {m.due_date && (
                <>
                  Förfaller <strong>{SHORT_DATE(m.due_date)}</strong>
                  <br />
                </>
              )}
              {m.amount != null && (
                <>
                  Belopp:{" "}
                  <strong>
                    {m.amount > 0 ? "+ " : "− "}
                    {SEK(Math.abs(m.amount))} kr
                  </strong>
                  <br />
                </>
              )}
              {m.ocr_reference && (
                <>
                  OCR <strong>{m.ocr_reference}</strong>
                </>
              )}
            </div>
          </header>

          {/* Body */}
          <div style={{ padding: "24px 28px" }}>
            {isCcInvoice && data.cc_invoice && (
              <CcInvoiceLayout cc={data.cc_invoice} />
            )}
            {isSalarySlip && data.salary_slip && (
              <SalarySlipLayout sal={data.salary_slip} />
            )}
            {!isCcInvoice && !isSalarySlip && m.body && (
              <div
                style={{
                  fontFamily: "var(--serif)",
                  fontSize: 14.5,
                  lineHeight: 1.6,
                  whiteSpace: "pre-wrap",
                  color: "var(--text)",
                }}
              >
                {m.body}
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
              {/* Markera som betald manuellt (utan att gå via BankID) */}
              {(m.mail_type === "invoice" || m.mail_type === "reminder") &&
                m.status !== "paid" &&
                m.status !== "expired" && (
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

      </div>
    </div>
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
