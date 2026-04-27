/**
 * /arbetsgivare — central hub för arbetsgivar-dynamik (idé 1 i
 * dev_v1.md).
 *
 * Samlar lönespec, lönesamtal, kollektivavtal, satisfaction-score
 * och slumpade frågor på en plats. Banken hanterar bank-saker
 * (kontoutdrag etc); arbetsgivaren är där allt jobb-relaterat sker.
 *
 * F2a — skelett med flikar och "Kommer snart"-stubbar. Översikt,
 * Avtal, Eventlogg och Frågor fylls i F2b–F2e. Lönespec och
 * Lönesamtal hör till PR 4 (efter idé 2-backend).
 */
import { useQuery } from "@tanstack/react-query";
import {
  Building2,
  TrendingDown,
  TrendingUp,
  Minus,
  AlertCircle,
} from "lucide-react";
import React, { useState } from "react";
import { api, formatSEK } from "@/api/client";
import { Card } from "@/components/Card";


interface AgreementOut {
  code: string;
  name: string;
  union: string;
  employer_org: string;
  summary_md: string;
  source_url: string | null;
  verified: boolean;
  meta: Record<string, unknown>;
}


interface SatisfactionOut {
  score: number;
  trend: "rising" | "falling" | "stable";
  last_event_at: string | null;
}


interface EmployerStatusOut {
  student_id: number;
  profession: string;
  employer: string;
  gross_salary_monthly: number;
  pending_salary_monthly: number | null;
  pending_effective_from: string | null;
  pension_pct: number | null;
  satisfaction: SatisfactionOut;
  agreement: AgreementOut | null;
  has_agreement: boolean;
}


type Tab =
  | "oversikt"
  | "lonespec"
  | "avtal"
  | "lonesamtal"
  | "fragor"
  | "events";

const TABS: { id: Tab; label: string; comingSoon?: boolean }[] = [
  { id: "oversikt", label: "Översikt" },
  { id: "lonespec", label: "Lönespec", comingSoon: true },
  { id: "avtal", label: "Kollektivavtal" },
  { id: "lonesamtal", label: "Lönesamtal", comingSoon: true },
  { id: "fragor", label: "Frågor" },
  { id: "events", label: "Eventlogg" },
];


export default function Arbetsgivare() {
  const [tab, setTab] = useState<Tab>("oversikt");

  const statusQ = useQuery({
    queryKey: ["employer-status"],
    queryFn: () => api<EmployerStatusOut>("/employer/status"),
  });

  return (
    <div className="p-3 md:p-6 space-y-4 md:space-y-5">
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <h1 className="serif text-3xl leading-tight flex items-center gap-2">
            <Building2 className="w-7 h-7" />
            Arbetsgivare
          </h1>
          <div className="text-sm text-slate-700 mt-1">
            Här samlas allt som rör ditt jobb: lönespec, kollektivavtal,
            lönesamtal och din relation till arbetsgivaren. Banken sköter
            själva pengarna; det här är var du <em>jobbar</em>.
          </div>
        </div>
      </div>

      <div className="flex gap-2 border-b overflow-x-auto">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`px-3 py-2 text-sm border-b-2 whitespace-nowrap ${
              tab === t.id
                ? "border-brand-600 text-brand-700"
                : "border-transparent text-slate-600 hover:text-slate-900"
            }`}
          >
            {t.label}
            {t.comingSoon && (
              <span className="ml-1 text-[10px] text-slate-400 align-top">
                snart
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Stub-tabbar; fylls i F2b–F2e */}
      {tab === "oversikt" && (
        statusQ.isLoading ? (
          <Card><div className="text-sm text-slate-600">Laddar…</div></Card>
        ) : statusQ.error ? (
          <Card>
            <div className="text-sm text-rose-700">
              Kunde inte hämta status: {String(statusQ.error)}
            </div>
          </Card>
        ) : statusQ.data ? (
          <OverviewTab status={statusQ.data} />
        ) : null
      )}
      {tab === "lonespec" && (
        <ComingSoon
          what="Lönespec"
          note="Hör till PR 4 — kommer efter att lönesamtals-backenden är klar."
        />
      )}
      {tab === "avtal" && (
        statusQ.isLoading ? (
          <Card><div className="text-sm text-slate-600">Laddar…</div></Card>
        ) : statusQ.data ? (
          <AgreementTab status={statusQ.data} />
        ) : null
      )}
      {tab === "lonesamtal" && (
        <ComingSoon
          what="Lönesamtal"
          note="Hör till PR 4 — kommer efter att lönesamtals-backenden är klar."
        />
      )}
      {tab === "fragor" && <ComingSoon what="Frågor" />}
      {tab === "events" && <ComingSoon what="Eventlogg" />}
    </div>
  );
}


function OverviewTab({ status }: { status: EmployerStatusOut }) {
  const score = status.satisfaction.score;
  const trend = status.satisfaction.trend;
  const pendingDelta =
    status.pending_salary_monthly !== null
      ? status.pending_salary_monthly - status.gross_salary_monthly
      : null;
  const pension =
    status.pension_pct !== null
      ? Math.round((status.gross_salary_monthly * status.pension_pct) / 100)
      : null;

  return (
    <div className="space-y-4">
      {/* Översta raden: arbetsgivar-id-kort + satisfaction-mätare */}
      <div className="grid grid-cols-1 md:grid-cols-[2fr_1fr] gap-4">
        <Card>
          <div className="text-xs uppercase tracking-wide text-slate-500">
            Din arbetsgivare
          </div>
          <div className="text-2xl serif mt-1">{status.employer}</div>
          <div className="text-sm text-slate-700 mt-1">
            Du jobbar som <strong>{status.profession}</strong>.
          </div>

          <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mt-4">
            <Kpi
              label="Aktuell bruttolön"
              value={formatSEK(status.gross_salary_monthly)}
              hint="per månad"
            />
            <Kpi
              label="Tjänstepension"
              value={pension !== null ? formatSEK(pension) : "—"}
              hint={
                status.pension_pct !== null
                  ? `${status.pension_pct.toFixed(1)} % av brutto`
                  : "saknas"
              }
            />
            {status.pending_salary_monthly !== null && (
              <Kpi
                label="Ny lön (pågående)"
                value={formatSEK(status.pending_salary_monthly)}
                hint={
                  status.pending_effective_from
                    ? `gäller från ${status.pending_effective_from}`
                    : "kommer nästa lönespec"
                }
                tone={pendingDelta && pendingDelta > 0 ? "good" : undefined}
              />
            )}
          </div>
        </Card>

        <SatisfactionGauge score={score} trend={trend} />
      </div>

      {/* Avtals-banner */}
      {status.has_agreement && status.agreement ? (
        <AgreementBanner agreement={status.agreement} />
      ) : (
        <NoAgreementBanner />
      )}

      {/* Pedagogisk hint längst ner */}
      <div className="text-xs text-slate-500 leading-snug">
        Översikten visar nuläget. Detaljerade avtals-villkor finns i
        fliken <em>Kollektivavtal</em>; varför din satisfaction-score
        rör sig syns i <em>Eventlogg</em>; ditt nästa beslutstillfälle
        finns i <em>Frågor</em>.
      </div>
    </div>
  );
}


function Kpi({
  label, value, hint, tone,
}: {
  label: string;
  value: string;
  hint?: string;
  tone?: "good" | "bad";
}) {
  const color =
    tone === "good"
      ? "text-emerald-700"
      : tone === "bad"
        ? "text-rose-700"
        : "text-slate-900";
  return (
    <div className="bg-white border rounded p-3">
      <div className="text-[10px] uppercase tracking-wide text-slate-500">
        {label}
      </div>
      <div className={`text-lg font-semibold mt-0.5 ${color}`}>{value}</div>
      {hint && <div className="text-[11px] text-slate-500 mt-0.5">{hint}</div>}
    </div>
  );
}


function SatisfactionGauge({
  score, trend,
}: {
  score: number;
  trend: "rising" | "falling" | "stable";
}) {
  // Färg-tröskel: <25 = critical, <40 = low, <60 = neutral, ≥60 = good
  const color =
    score < 25
      ? "text-rose-700 bg-rose-50 border-rose-200"
      : score < 40
        ? "text-amber-700 bg-amber-50 border-amber-200"
        : score < 60
          ? "text-slate-700 bg-slate-50 border-slate-200"
          : "text-emerald-700 bg-emerald-50 border-emerald-200";
  const TrendIcon =
    trend === "rising" ? TrendingUp : trend === "falling" ? TrendingDown : Minus;
  const trendLabel =
    trend === "rising" ? "stiger" : trend === "falling" ? "sjunker" : "stabil";
  return (
    <div className={`border rounded-lg p-4 ${color}`}>
      <div className="text-xs uppercase tracking-wide opacity-80">
        Arbetsgivar-nöjdhet
      </div>
      <div className="flex items-baseline gap-2 mt-1">
        <span className="text-5xl serif font-semibold">{score}</span>
        <span className="text-sm opacity-80">/ 100</span>
      </div>
      <div className="flex items-center gap-1 text-xs mt-2 opacity-90">
        <TrendIcon className="w-3.5 h-3.5" />
        Trenden {trendLabel} (senaste 5 händelserna)
      </div>
    </div>
  );
}


function AgreementBanner({ agreement }: { agreement: AgreementOut }) {
  return (
    <div className="border-l-4 border-brand-400 bg-brand-50 rounded-md p-3">
      <div className="text-xs uppercase tracking-wide text-brand-700">
        Ditt kollektivavtal
      </div>
      <div className="text-base font-semibold text-slate-900 mt-0.5">
        {agreement.name}
      </div>
      <div className="text-sm text-slate-700">
        {agreement.union} <span className="text-slate-400">↔</span>{" "}
        {agreement.employer_org}
      </div>
      {!agreement.verified && (
        <div className="flex items-center gap-1 text-xs text-amber-700 mt-1">
          <AlertCircle className="w-3.5 h-3.5" />
          Sammanfattningen är preliminär — väntar på faktagranskning.
        </div>
      )}
    </div>
  );
}


function AgreementTab({ status }: { status: EmployerStatusOut }) {
  const ag = status.agreement;
  if (!ag) {
    // Småföretag-fallback har egen pedagogisk text. Vi kan rendera samma
    // banner från översikten + en kort lista över lagstadgade golv.
    return (
      <div className="space-y-3">
        <NoAgreementBanner />
        <Card title="Lagstadgade golv (utan avtal)">
          <ul className="text-sm text-slate-700 list-disc ml-5 space-y-1">
            <li>
              <strong>Semester:</strong> 25 dagar/år enligt semesterlagen
            </li>
            <li>
              <strong>Sjuklön:</strong> dag 1 karens, dag 2–14 80 % (sjuk-
              lönelagen). Dag 15+ Försäkringskassan.
            </li>
            <li>
              <strong>Övertid:</strong> rätt till ersättning enligt
              arbetstidslagen — nivå förhandlas individuellt.
            </li>
            <li>
              <strong>Tjänstepension:</strong> ingen — du behöver spara
              själv (ISK eller kapitalförsäkring) för att kompensera.
            </li>
          </ul>
        </Card>
      </div>
    );
  }
  return (
    <div className="space-y-3">
      <AgreementBanner agreement={ag} />
      <div className="grid grid-cols-1 md:grid-cols-[2fr_1fr] gap-4">
        <Card title="Avtalets innehåll">
          <MarkdownLite text={ag.summary_md} />
          {ag.source_url && (
            <div className="mt-3 text-xs">
              <a
                href={ag.source_url}
                target="_blank"
                rel="noreferrer"
                className="text-brand-700 hover:underline"
              >
                Läs det officiella avtalet →
              </a>
            </div>
          )}
        </Card>
        <Card title="Nyckeltal">
          <AgreementMetaTable meta={ag.meta} />
        </Card>
      </div>
    </div>
  );
}


/**
 * Mycket enkel markdown-renderare — bara rubriker, fet text och brödtext.
 * Vi vill inte dra in `marked` eller liknande för 5 användningsfall.
 * Avtals-summaries använder bara `## h2`, `**fet**` och radbrytningar.
 */
function MarkdownLite({ text }: { text: string }) {
  const lines = text.split("\n");
  const out: React.ReactNode[] = [];
  let buffer: string[] = [];
  function flushBuffer() {
    if (buffer.length === 0) return;
    const para = buffer.join(" ").trim();
    if (para) {
      out.push(
        <p key={out.length} className="text-sm text-slate-700 leading-relaxed">
          {renderInline(para)}
        </p>,
      );
    }
    buffer = [];
  }
  for (const line of lines) {
    if (line.startsWith("## ")) {
      flushBuffer();
      out.push(
        <h2 key={out.length} className="text-base font-semibold text-slate-900 mt-3">
          {line.slice(3)}
        </h2>,
      );
    } else if (line.trim() === "") {
      flushBuffer();
    } else {
      buffer.push(line);
    }
  }
  flushBuffer();
  return <div className="space-y-2">{out}</div>;
}


/** Bryter en sträng på `**...**` och returnerar React-noder. */
function renderInline(s: string): React.ReactNode[] {
  const parts: React.ReactNode[] = [];
  let last = 0;
  const re = /\*\*([^*]+)\*\*/g;
  let m: RegExpExecArray | null;
  let i = 0;
  while ((m = re.exec(s)) !== null) {
    if (m.index > last) parts.push(s.slice(last, m.index));
    parts.push(<strong key={i++}>{m[1]}</strong>);
    last = m.index + m[0].length;
  }
  if (last < s.length) parts.push(s.slice(last));
  return parts;
}


function AgreementMetaTable({ meta }: { meta: Record<string, unknown> }) {
  const rows: { label: string; value: string }[] = [];

  // Revisionsökning per år
  const rev = meta.revision_pct_year as Record<string, number> | undefined;
  if (rev && Object.keys(rev).length > 0) {
    const years = Object.keys(rev).sort();
    const formatted = years.map((y) => `${y}: ${rev[y]} %`).join(", ");
    rows.push({ label: "Revisionsökning", value: formatted });
  }
  if (typeof meta.revision_note === "string" && meta.revision_note) {
    rows.push({ label: "Revisions-typ", value: meta.revision_note });
  }

  // Semester
  if (typeof meta.vacation_days === "number") {
    let val = `${meta.vacation_days} dagar`;
    if (typeof meta.vacation_days_age_40 === "number") {
      val += ` (${meta.vacation_days_age_40} från 40 år`;
      if (typeof meta.vacation_days_age_50 === "number") {
        val += `, ${meta.vacation_days_age_50} från 50)`;
      } else {
        val += ")";
      }
    }
    rows.push({ label: "Semester", value: val });
  }

  // Övertid
  if (typeof meta.overtime_pct === "number") {
    let val = `${meta.overtime_pct} % vardagar`;
    if (typeof meta.overtime_pct_weekend === "number") {
      val += `, ${meta.overtime_pct_weekend} % helger`;
    } else if (typeof meta.overtime_pct_extra === "number") {
      val += `, ${meta.overtime_pct_extra} % efter två timmar`;
    }
    rows.push({ label: "Övertid", value: val });
  }

  // OB
  const obParts: string[] = [];
  if (typeof meta.ob_evening_pct === "number") {
    obParts.push(`kväll ${meta.ob_evening_pct} %`);
  }
  if (typeof meta.ob_night_pct === "number") {
    obParts.push(`natt ${meta.ob_night_pct} %`);
  }
  if (typeof meta.ob_weekend_pct === "number") {
    obParts.push(`helg ${meta.ob_weekend_pct} %`);
  }
  if (typeof meta.ob_saturday_pct === "number") {
    obParts.push(`lördag ${meta.ob_saturday_pct} %`);
  }
  if (typeof meta.ob_sunday_pct === "number") {
    obParts.push(`söndag ${meta.ob_sunday_pct} %`);
  }
  if (obParts.length > 0) {
    rows.push({ label: "OB-tillägg", value: obParts.join(", ") });
  }

  // Tjänstepension
  if (typeof meta.pension_system === "string" && meta.pension_system) {
    let val = meta.pension_system;
    if (typeof meta.pension_pct === "number") {
      val += ` — ${meta.pension_pct} %`;
      if (typeof meta.pension_pct_above_75ibb === "number") {
        val += ` (${meta.pension_pct_above_75ibb} % över 7,5 IBB)`;
      }
    }
    rows.push({ label: "Tjänstepension", value: val });
  } else if (meta.pension_system === null) {
    rows.push({
      label: "Tjänstepension",
      value: "saknas — viktig att kompensera privat",
    });
  }

  if (rows.length === 0) {
    return (
      <div className="text-sm text-slate-500">
        Avtalet har inga strukturerade nyckeltal ännu.
      </div>
    );
  }
  return (
    <table className="w-full text-sm">
      <tbody>
        {rows.map((r) => (
          <tr key={r.label} className="border-b border-slate-100 last:border-0">
            <td className="py-1.5 pr-3 text-slate-600 align-top whitespace-nowrap">
              {r.label}
            </td>
            <td className="py-1.5 text-slate-900">{r.value}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}


function NoAgreementBanner() {
  return (
    <div className="border-l-4 border-slate-300 bg-slate-50 rounded-md p-3">
      <div className="text-xs uppercase tracking-wide text-slate-600">
        Småföretag utan kollektivavtal
      </div>
      <div className="text-sm text-slate-700 mt-0.5 leading-relaxed">
        Din arbetsplats omfattas inte av ett kollektivavtal. Det betyder
        att lön, övertid och tjänstepension regleras direkt med chefen
        — inte av centrala förhandlingar. Konsekvensen syns tydligast i
        att <strong>tjänstepension saknas</strong> (förlorat värde
        över ett arbetsliv kan bli sexsiffrigt). Läs mer i fliken{" "}
        <em>Kollektivavtal</em>.
      </div>
    </div>
  );
}


function ComingSoon({ what, note }: { what: string; note?: string }) {
  return (
    <div className="bg-white border border-slate-200 rounded-md p-6">
      <div className="text-base font-semibold text-slate-900 mb-1">
        {what}
      </div>
      <div className="text-sm text-slate-600">
        Kommer i nästa commit. {note}
      </div>
    </div>
  );
}
