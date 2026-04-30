/**
 * V2 Postlådan · matchar /proposals/vol-7/elev.html#p-mail EXAKT.
 *
 * Layout (samma som prototypen):
 *   1. .actor-back tillbaka-länk → /v2/hub
 *   2. .mail-head · "Meta-aktör · Postlådan · N brev"-pill +
 *      actor-name + actor-meta
 *   3. .mail-stat-row · 4 nyckeltal
 *   4. .mail-tabs · Allt / Ohanterade / Fakturor / Lönespecar /
 *      Myndighet / Övrigt (med count-badge)
 *   5. .mail-list · alla brev som rader (dot+ikon+from+subject+
 *      amount+due+status). Klick markerar som "viewed".
 *   6. .peda · pedagogik-block
 *
 * All data live från /v2/postladan.
 */
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  v2Api,
  type MailData,
  type V2MailItem,
  type V2MailType,
  type V2MailStatus,
} from "./api";
import { V2Banner } from "./V2Banner";
import "./postladan.css";

const SEK = (n: number) =>
  new Intl.NumberFormat("sv-SE", { maximumFractionDigits: 0 }).format(n);

const SHORT_DATE = (iso: string | null): string => {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleDateString("sv-SE", { day: "numeric", month: "short" });
};

const STATUS_LABEL: Record<V2MailStatus, string> = {
  unhandled: "Ohanterad",
  viewed: "Granskad",
  exported: "Exporterad",
  paid: "Betald",
  expired: "Utgången",
};

type TabKey =
  | "all"
  | "unhandled"
  | "invoice"
  | "salary_slip"
  | "authority"
  | "other";

const TAB_TO_FILTER: Record<
  TabKey,
  V2MailType | "unhandled" | "other" | undefined
> = {
  all: undefined,
  unhandled: "unhandled",
  invoice: "invoice",
  salary_slip: "salary_slip",
  authority: "authority",
  other: "other",
};

const MAIL_TYPE_LABEL: Record<V2MailType, string> = {
  invoice: "faktura",
  salary_slip: "lönespec",
  authority: "myndighetspost",
  reminder: "påminnelse",
  info: "info-brev",
};

function deriveSenderMeta(m: V2MailItem): string {
  // Använd explicit sender_meta om läraren har satt det.
  if (m.sender_meta) return m.sender_meta;
  // Annars härled från typ + ev. nummer.
  const parts: string[] = [MAIL_TYPE_LABEL[m.mail_type]];
  if (m.bankgiro) parts.push(`BG ${m.bankgiro}`);
  else if (m.ocr_reference) parts.push(`OCR ${m.ocr_reference}`);
  if (m.is_recurring) parts.push("återkommande");
  return parts.join(" · ");
}

export function PostladanV2() {
  const [data, setData] = useState<MailData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<TabKey>("all");
  const navigate = useNavigate();

  function load(currentTab: TabKey) {
    v2Api
      .postladan(TAB_TO_FILTER[currentTab])
      .then(setData)
      .catch((e) => setError(String((e as Error)?.message || e)));
  }

  useEffect(() => {
    load(tab);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab]);

  async function openMail(item: V2MailItem) {
    if (item.status === "unhandled") {
      try {
        await v2Api.updateMailStatus(item.id, "viewed");
        load(tab);
      } catch {
        /* fail-soft — user kan ändå se brevet */
      }
    }
  }

  if (error) {
    return (
      <div className="v2-postladan-root">
        <V2Banner status={{ role: "student", is_super_admin: false }} />
        <div className="bank-loading">
          <div>
            <div style={{ color: "#fca5a5", marginBottom: 8 }}>
              Kunde inte ladda postlådan
            </div>
            <pre style={{ fontSize: 11 }}>{error}</pre>
          </div>
        </div>
      </div>
    );
  }
  if (!data) {
    return (
      <div className="v2-postladan-root">
        <V2Banner status={{ role: "student", is_super_admin: false }} />
        <div className="bank-loading">Laddar postlådan…</div>
      </div>
    );
  }

  const { summary, items } = data;
  // "Övrigt" = allt utöver invoice/salary_slip/authority/info (typiskt
  // reminder). Räknat på backend som other_count + info-tabben är
  // separat: prototypens "Övrigt" mappar till info_count + reminder.
  const ovrigtCount = summary.info_count + summary.other_count;

  function fmtDateTime(iso: string | null): string {
    if (!iso) return "—";
    const d = new Date(iso);
    return d.toLocaleString("sv-SE", {
      day: "numeric",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
    });
  }
  function fmtDate(iso: string | null): string {
    if (!iso) return "—";
    const d = new Date(iso);
    return d.toLocaleDateString("sv-SE", { day: "numeric", month: "short" });
  }
  const spendLabel =
    summary.spend_profile === "sparsam"
      ? "sparsam"
      : summary.spend_profile === "slosa"
      ? "slösaktig"
      : "balanserad";

  return (
    <div className="v2-postladan-root">
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

        <header className="mail-head">
          <div>
            <span className="pill">
              Meta-aktör · Postlådan · {summary.total_count} brev
            </span>
            <h1 className="actor-name" style={{ marginTop: 14 }}>
              Postlådan — <em>där allt landar</em>.
            </h1>
            <p className="actor-sub">
              Brev, fakturor, lönespecar, myndighetspost · pendling med banken
              &amp; bokföringen
            </p>
          </div>
          <div className="actor-meta">
            Spenderprofil <strong>{spendLabel}</strong>
            <br />
            Senaste utskick{" "}
            <strong>{fmtDateTime(summary.last_received_at)}</strong>
            <br />
            Nästa väntat {fmtDate(summary.next_due_date)}
          </div>
        </header>

        {/* STAT-ROW · matchar prototypen */}
        <div className="mail-stat-row">
          <div className="mail-stat">
            <div className="mail-stat-eye">Ohanterade</div>
            <div className="mail-stat-num">
              <em>{summary.unhandled_count}</em>/{summary.total_count}
            </div>
            <div className="mail-stat-sub">kräver åtgärd</div>
          </div>
          <div className="mail-stat">
            <div className="mail-stat-eye">Att betala denna v</div>
            <div className="mail-stat-num warm">
              <em>{SEK(summary.to_pay_amount)}</em> kr
            </div>
            <div className="mail-stat-sub">
              {summary.invoice_count} fakturor
            </div>
          </div>
          <div className="mail-stat">
            <div className="mail-stat-eye">Inkommande denna v</div>
            <div className="mail-stat-num green">
              <em>+ {SEK(summary.incoming_amount)}</em> kr
            </div>
            <div className="mail-stat-sub">
              {summary.salary_slip_count} lönespec
            </div>
          </div>
          <div className="mail-stat">
            <div className="mail-stat-eye">Påminnelse-risk</div>
            <div className="mail-stat-num">{summary.overdue_count}</div>
            <div className="mail-stat-sub">
              {summary.overdue_count === 0 ? "inga försenade" : "försenade"}
            </div>
          </div>
        </div>

        {/* TABS */}
        <div className="mail-tabs">
          <a
            className={`mail-tab${tab === "all" ? " active" : ""}`}
            onClick={(e) => {
              e.preventDefault();
              setTab("all");
            }}
            href="#"
          >
            Allt <span className="count">{summary.total_count}</span>
          </a>
          <a
            className={`mail-tab${tab === "unhandled" ? " active" : ""}`}
            onClick={(e) => {
              e.preventDefault();
              setTab("unhandled");
            }}
            href="#"
          >
            Ohanterade{" "}
            <span className="count">{summary.unhandled_count}</span>
          </a>
          <a
            className={`mail-tab${tab === "invoice" ? " active" : ""}`}
            onClick={(e) => {
              e.preventDefault();
              setTab("invoice");
            }}
            href="#"
          >
            Fakturor <span className="count">{summary.invoice_count}</span>
          </a>
          <a
            className={`mail-tab${tab === "salary_slip" ? " active" : ""}`}
            onClick={(e) => {
              e.preventDefault();
              setTab("salary_slip");
            }}
            href="#"
          >
            Lönespecar{" "}
            <span className="count">{summary.salary_slip_count}</span>
          </a>
          <a
            className={`mail-tab${tab === "authority" ? " active" : ""}`}
            onClick={(e) => {
              e.preventDefault();
              setTab("authority");
            }}
            href="#"
          >
            Myndighet{" "}
            <span className="count">{summary.authority_count}</span>
          </a>
          <a
            className={`mail-tab${tab === "other" ? " active" : ""}`}
            onClick={(e) => {
              e.preventDefault();
              setTab("other");
            }}
            href="#"
          >
            Övrigt <span className="count">{ovrigtCount}</span>
          </a>
        </div>

        {/* LIST */}
        {items.length === 0 ? (
          <div
            style={{
              padding: "32px 28px",
              border: "1px solid var(--line)",
              borderRadius: 6,
              fontFamily: "var(--serif)",
              color: "var(--text-mid)",
              marginBottom: 22,
            }}
          >
            {summary.total_count === 0
              ? "Postlådan är tom. Lärare seedar mail via lärar-vyn så börjar friktionen."
              : "Inga brev i denna kategori."}
          </div>
        ) : (
          <div className="mail-list">
            {items.map((m) => {
              const today = new Date();
              today.setHours(0, 0, 0, 0);
              const due = m.due_date ? new Date(m.due_date) : null;
              const days = due
                ? Math.round(
                    (due.getTime() - today.getTime()) / (1000 * 60 * 60 * 24),
                  )
                : null;
              const urgent =
                days !== null &&
                days <= 5 &&
                m.status === "unhandled" &&
                m.mail_type === "invoice";
              const dueClass = urgent
                ? " urgent"
                : m.amount === null
                ? " muted"
                : "";

              const isInfo = m.amount === null;
              const isIncome = m.amount !== null && m.amount > 0;
              const amountText =
                m.amount === null
                  ? "—"
                  : isIncome
                  ? `+ ${SEK(m.amount)}`
                  : `${SEK(m.amount)}`;

              const dueText =
                m.status === "paid"
                  ? "betald"
                  : m.status === "exported"
                  ? `betalas ${SHORT_DATE(m.due_date)}`
                  : m.due_date
                  ? `förfaller ${SHORT_DATE(m.due_date)}`
                  : "info-brev";

              return (
                <a
                  key={m.id}
                  className={`mail-item${
                    m.status === "unhandled" ? " unread" : ""
                  }`}
                  onClick={(e) => {
                    e.preventDefault();
                    void openMail(m);
                  }}
                  href="#"
                >
                  <span className="mail-dot" />
                  <div className={`mail-icon ${m.sender_kind}`}>
                    {m.sender_short || m.sender.slice(0, 3).toUpperCase()}
                  </div>
                  <div>
                    <div className="mail-from">{m.sender}</div>
                    <div className="mail-from-meta">
                      {deriveSenderMeta(m)}
                    </div>
                  </div>
                  <div>
                    <div className="mail-subject">{m.subject}</div>
                    {m.body_meta && (
                      <div
                        className="mail-from-meta"
                        style={{ marginTop: 3 }}
                      >
                        {m.body_meta}
                      </div>
                    )}
                  </div>
                  <div className={`mail-amount${isIncome ? " in" : ""}`}>
                    {!isInfo && (isIncome || urgent) ? (
                      <em>{amountText}</em>
                    ) : (
                      amountText
                    )}{" "}
                    {!isInfo && "kr"}
                  </div>
                  <div className={`mail-due${dueClass}`}>
                    {urgent && days !== null && days >= 0
                      ? `${dueText} (om ${days} d)`
                      : dueText}
                  </div>
                  <span className={`mail-status ${m.status}`}>
                    {STATUS_LABEL[m.status]}
                  </span>
                </a>
              );
            })}
          </div>
        )}

        {/* PEDAGOGIK */}
        <div className="peda">
          <div className="peda-eye">Pedagogik · vad du lär dig här</div>
          <div className="peda-h">
            Postlådan är där <em>livet</em> kommer in.
          </div>
          <p className="peda-prose">
            Hyran landar inte i banken — den landar i postlådan, och du
            bestämmer om den ska exporteras till banken som dragning. Skatten
            kommer som ett brev. Lönen är en specifikation innan den blir
            kontosaldo. <em>Friktion är inte bug, det är funktion.</em> Att
            tvingas öppna brevet och välja är där medvetenhet börjar.
          </p>
          <ul className="peda-bullets">
            <li className="peda-bullet">
              <strong>Faktura</strong>Beloppet du måste betala. OCR är
              nyckeln som matchar.
            </li>
            <li className="peda-bullet">
              <strong>Lönespec</strong>Bruttolön minus skatt + avdrag = netto
              till kontot.
            </li>
            <li className="peda-bullet">
              <strong>Myndighetspost</strong>Skatteverket, Pensionsmyndigheten —
              har deadlines, inte valbart.
            </li>
            <li className="peda-bullet">
              <strong>Autogiro</strong>När du litar på avsändaren — banken
              betalar utan ditt val.
            </li>
          </ul>
          <div className="peda-concepts">
            <span className="peda-concept">Friktion</span>
            <span className="peda-concept">OCR</span>
            <span className="peda-concept">Förfallodag</span>
            <span className="peda-concept">Cash flow</span>
            <span className="peda-concept">E-faktura</span>
          </div>
          <div className="peda-tip">
            {summary.unhandled_count > 0
              ? `Echo: "Du har ${summary.unhandled_count} ohanterade brev. Att skjuta upp blir ofta påminnelseavgifter — vad är priset på 'jag kollar imorgon'?"`
              : `Echo: "Du har inga ohanterade brev just nu. Reflektera: hur mycket är det värt att INTE ha en stack obetalda räkningar i bakgrunden?"`}
          </div>
        </div>
      </div>
    </div>
  );
}
