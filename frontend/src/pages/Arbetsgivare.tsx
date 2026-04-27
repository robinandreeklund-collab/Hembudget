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
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertCircle,
  Building2,
  CheckCircle2,
  Download,
  Eye,
  FileText,
  Loader2,
  Minus,
  TrendingDown,
  TrendingUp,
  Upload,
  X,
} from "lucide-react";
import React, { useEffect, useRef, useState } from "react";
import { api, formatSEK, getApiBase, getToken } from "@/api/client";
import { Card } from "@/components/Card";
import { NoStudentSelected } from "@/components/NoStudentSelected";
import { useAuth } from "@/hooks/useAuth";


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

const TABS: { id: Tab; label: string }[] = [
  { id: "oversikt", label: "Översikt" },
  { id: "lonespec", label: "Lönespec" },
  { id: "avtal", label: "Kollektivavtal" },
  { id: "lonesamtal", label: "Lönesamtal" },
  { id: "fragor", label: "Frågor" },
  { id: "events", label: "Eventlogg" },
];


export default function Arbetsgivare() {
  const [tab, setTab] = useState<Tab>("oversikt");
  const { role, asStudent } = useAuth();
  const teacherWithoutStudent = role === "teacher" && !asStudent;

  const statusQ = useQuery({
    queryKey: ["employer-status", asStudent ?? "self"],
    queryFn: () => api<EmployerStatusOut>("/employer/status"),
    // Kör inte queryn för lärare som inte har valt en elev — annars
    // får vi ett 400-fel från backend som inte är meningsfullt.
    enabled: !teacherWithoutStudent,
  });

  // Lärare som öppnar /arbetsgivare utan att ha valt en elev (t.ex.
  // direkt från sidebar-länken eller en bokmärkt URL) får en vänlig
  // "välj elev"-vy istället för en rå HTTP 400 från backend.
  if (teacherWithoutStudent) {
    return <NoStudentSelected pageName="Arbetsgivare" />;
  }

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
      {tab === "lonespec" && <SalarySlipsTab />}
      {tab === "avtal" && (
        statusQ.isLoading ? (
          <Card><div className="text-sm text-slate-600">Laddar…</div></Card>
        ) : statusQ.data ? (
          <AgreementTab status={statusQ.data} />
        ) : null
      )}
      {tab === "lonesamtal" && <NegotiationTab />}
      {tab === "fragor" && <QuestionsTab />}
      {tab === "events" && <EventLogTab />}
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


interface QuestionOptionOut {
  index: number;
  text: string;
}


interface QuestionOut {
  id: number;
  code: string;
  scenario_md: string;
  options: QuestionOptionOut[];
  difficulty: number;
  tags: string[] | null;
}


interface QuestionAnswerOut {
  delta_applied: number;
  chosen_explanation: string;
  correct_path_md: string;
  new_score: number;
  new_trend: "rising" | "falling" | "stable";
}


function QuestionsTab() {
  const qc = useQueryClient();
  const nextQ = useQuery({
    queryKey: ["employer-question-next"],
    queryFn: () => api<QuestionOut | null>("/employer/questions/next"),
  });
  const [answer, setAnswer] = useState<QuestionAnswerOut | null>(null);

  const answerMut = useMutation({
    mutationFn: (params: { question_id: number; chosen_index: number }) =>
      api<QuestionAnswerOut>("/employer/questions/answer", {
        method: "POST",
        body: JSON.stringify(params),
      }),
    onSuccess: (data) => {
      setAnswer(data);
      // Status + events ska reflektera den nya scoren
      qc.invalidateQueries({ queryKey: ["employer-status"] });
      qc.invalidateQueries({ queryKey: ["employer-events"] });
    },
  });

  function chooseAndAnswer(qid: number, idx: number) {
    if (answer) return;
    answerMut.mutate({ question_id: qid, chosen_index: idx });
  }

  function nextQuestion() {
    setAnswer(null);
    qc.invalidateQueries({ queryKey: ["employer-question-next"] });
  }

  if (nextQ.isLoading) {
    return <Card><div className="text-sm text-slate-600">Laddar fråga…</div></Card>;
  }
  if (nextQ.error) {
    return (
      <Card>
        <div className="text-sm text-rose-700">
          Kunde inte hämta fråga: {String(nextQ.error)}
        </div>
      </Card>
    );
  }

  const q = nextQ.data;

  if (!q) {
    return (
      <Card title="Inga fler frågor just nu">
        <div className="text-sm text-slate-700 leading-relaxed">
          Du har svarat på alla frågor som arbetsgivaren skickat ut. Nya
          situationer dyker upp över tid — kom tillbaka senare.
        </div>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      <Card title={`Fråga från ${labelDifficulty(q.difficulty)}`}>
        <div className="text-xs text-slate-500 mb-2">
          {q.tags && q.tags.length > 0 && (
            <span>
              {q.tags.map((t) => (
                <span
                  key={t}
                  className="inline-block bg-slate-100 text-slate-700 rounded px-1.5 py-0.5 mr-1"
                >
                  {t}
                </span>
              ))}
            </span>
          )}
        </div>
        <div className="text-base text-slate-900 leading-relaxed mb-4">
          <MarkdownLite text={q.scenario_md} />
        </div>
        <div className="space-y-2">
          {q.options.map((opt) => {
            const disabled = !!answer || answerMut.isPending;
            return (
              <button
                key={opt.index}
                onClick={() => chooseAndAnswer(q.id, opt.index)}
                disabled={disabled}
                className={`block w-full text-left rounded-md border px-3 py-2 text-sm transition ${
                  disabled
                    ? "border-slate-200 bg-slate-50 text-slate-500"
                    : "border-slate-300 bg-white hover:border-brand-400 hover:bg-brand-50"
                }`}
              >
                <span className="text-slate-500 mr-2">
                  {String.fromCharCode(65 + opt.index)}.
                </span>
                {opt.text}
              </button>
            );
          })}
        </div>
      </Card>

      {answer && (
        <Card>
          <div className="flex items-center justify-between mb-2">
            <div
              className={`text-base font-semibold ${
                answer.delta_applied > 0
                  ? "text-emerald-700"
                  : answer.delta_applied < 0
                    ? "text-rose-700"
                    : "text-slate-700"
              }`}
            >
              {answer.delta_applied > 0 ? "+" : ""}
              {answer.delta_applied} poäng
            </div>
            <div className="text-xs text-slate-500">
              Ny score: {answer.new_score}
            </div>
          </div>
          <div className="text-sm text-slate-800 mb-3 leading-relaxed">
            {answer.chosen_explanation}
          </div>
          <div className="border-t border-slate-200 pt-3">
            <div className="text-[10px] uppercase tracking-wide text-slate-500">
              Pedagogisk reflektion
            </div>
            <div className="text-sm text-slate-700 mt-1 leading-relaxed">
              <MarkdownLite text={answer.correct_path_md} />
            </div>
          </div>
          <div className="mt-4">
            <button
              onClick={nextQuestion}
              className="px-3 py-1.5 rounded bg-brand-600 text-white text-sm hover:bg-brand-700"
            >
              Nästa fråga →
            </button>
          </div>
        </Card>
      )}

      {answerMut.error && (
        <Card>
          <div className="text-sm text-rose-700">
            {String(answerMut.error)}
          </div>
        </Card>
      )}
    </div>
  );
}


function labelDifficulty(d: number): string {
  if (d <= 1) return "din arbetsgivare (lätt)";
  if (d <= 2) return "din arbetsgivare";
  if (d <= 3) return "din arbetsgivare (lite svårare)";
  return "din arbetsgivare (svår)";
}


interface EventOut {
  id: number;
  ts: string;
  kind: string;
  delta_score: number;
  reason_md: string;
  meta: Record<string, unknown> | null;
}


function EventLogTab() {
  const eventsQ = useQuery({
    queryKey: ["employer-events"],
    queryFn: () => api<{ events: EventOut[]; total: number }>(
      "/employer/events?limit=50",
    ),
  });

  if (eventsQ.isLoading) {
    return <Card><div className="text-sm text-slate-600">Laddar…</div></Card>;
  }
  if (eventsQ.error) {
    return (
      <Card>
        <div className="text-sm text-rose-700">
          Kunde inte hämta eventlogg: {String(eventsQ.error)}
        </div>
      </Card>
    );
  }
  const events = eventsQ.data?.events ?? [];

  if (events.length === 0) {
    return (
      <Card>
        <div className="text-sm text-slate-700">
          Inga händelser ännu. Din satisfaction startar på 70 — den
          rör sig när du svarar på frågor från arbetsgivaren, sjuk-
          anmäler dig, eller när läraren registrerar något manuellt.
        </div>
      </Card>
    );
  }

  return (
    <Card title={`Eventlogg (${events.length} händelser)`}>
      <div className="text-xs text-slate-500 mb-3">
        Varje rad förklarar varför din satisfaction-score rörde sig.
        Senaste först.
      </div>
      <div className="space-y-2">
        {events.map((e) => (
          <EventRow key={e.id} event={e} />
        ))}
      </div>
    </Card>
  );
}


function EventRow({ event }: { event: EventOut }) {
  const positive = event.delta_score > 0;
  const negative = event.delta_score < 0;
  const tone = positive
    ? "border-emerald-300 bg-emerald-50/40"
    : negative
      ? "border-rose-300 bg-rose-50/40"
      : "border-slate-200 bg-slate-50";
  const sign = positive ? "+" : "";
  const date = new Date(event.ts).toLocaleString("sv-SE", {
    dateStyle: "short",
    timeStyle: "short",
  });
  return (
    <div className={`border-l-4 rounded-r-md p-3 ${tone}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="text-xs text-slate-500">{date}</div>
        <div
          className={`text-sm font-semibold whitespace-nowrap ${
            positive ? "text-emerald-700" : negative ? "text-rose-700" : "text-slate-600"
          }`}
        >
          {sign}{event.delta_score} p
        </div>
      </div>
      <div className="text-[10px] uppercase tracking-wide text-slate-500 mt-1">
        {labelForKind(event.kind)}
      </div>
      <div className="text-sm text-slate-800 mt-1">
        <MarkdownLite text={event.reason_md} />
      </div>
    </div>
  );
}


function labelForKind(kind: string): string {
  switch (kind) {
    case "vab":
      return "VAB";
    case "sick":
      return "Sjukanmälan";
    case "question_answered":
      return "Svar på fråga";
    case "late":
      return "Försening";
    case "manual_teacher":
      return "Läraren";
    case "salary_negotiation_completed":
      return "Lönesamtal";
    default:
      return kind;
  }
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


// ---------- Lönesamtal (PR 4b) ----------

interface NegRoundOut {
  round_no: number;
  student_message: string;
  employer_response: string;
  proposed_pct: number | null;
  created_at: string;
}


interface NegotiationOut {
  id: number;
  student_id: number;
  profession: string;
  employer: string;
  starting_salary: number;
  avtal_norm_pct: number | null;
  avtal_code: string | null;
  status: "active" | "completed" | "abandoned";
  started_at: string;
  completed_at: string | null;
  final_salary: number | null;
  final_pct: number | null;
  teacher_summary_md: string | null;
  rounds: NegRoundOut[];
  max_rounds: number;
}


interface StartNegotiationOut {
  negotiation: NegotiationOut;
  briefing_md: string;
}


interface SendMessageOut {
  round_no: number;
  employer_response: string;
  proposed_pct: number | null;
  is_final_round: boolean;
  negotiation_status: string;
}


interface CompleteOut {
  final_pct: number | null;
  final_salary: number | null;
  avtal_norm_pct: number | null;
  pending_effective_from: string | null;
  summary_md: string;
}


function NegotiationTab() {
  const qc = useQueryClient();
  const [draft, setDraft] = useState("");
  const [completion, setCompletion] = useState<CompleteOut | null>(null);

  const startMut = useMutation({
    mutationFn: () => api<StartNegotiationOut>(
      "/employer/negotiation/start",
      { method: "POST" },
    ),
    onSuccess: () => {
      // Rensa lokala UI-rester när nytt samtal triggas
      setCompletion(null);
      setDraft("");
    },
  });

  // Försöker hämta startus + samtal automatiskt vid mount
  useEffect(() => {
    if (!startMut.data && !startMut.isPending) {
      startMut.mutate();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const negotiation = startMut.data?.negotiation;
  const briefing = startMut.data?.briefing_md ?? "";

  const sendMut = useMutation({
    mutationFn: (params: { id: number; message: string }) =>
      api<SendMessageOut>(
        `/employer/negotiation/${params.id}/message`,
        {
          method: "POST",
          body: JSON.stringify({ message: params.message }),
        },
      ),
    onSuccess: () => {
      setDraft("");
      // Refetch hela samtalet via start (samma session returneras)
      startMut.mutate();
    },
  });

  const completeMut = useMutation({
    mutationFn: (params: { id: number; accept_offer: boolean }) =>
      api<CompleteOut>(
        `/employer/negotiation/${params.id}/complete`,
        {
          method: "POST",
          body: JSON.stringify({ accept_offer: params.accept_offer }),
        },
      ),
    onSuccess: (data) => {
      setCompletion(data);
      // Översikten + status visar nu pending_salary
      qc.invalidateQueries({ queryKey: ["employer-status"] });
      qc.invalidateQueries({ queryKey: ["employer-events"] });
    },
  });

  function send() {
    if (!negotiation || draft.trim().length < 10) return;
    sendMut.mutate({ id: negotiation.id, message: draft });
  }

  if (startMut.isPending) {
    return <Card><div className="text-sm text-slate-600">Förbereder samtal…</div></Card>;
  }
  if (startMut.error) {
    return (
      <Card>
        <div className="text-sm text-rose-700">
          Kunde inte starta lönesamtal: {String(startMut.error)}
        </div>
      </Card>
    );
  }
  if (!negotiation) return null;

  // Slut-state — visa summary
  if (completion || negotiation.status !== "active") {
    return (
      <NegotiationSummary
        negotiation={negotiation}
        completion={completion}
        onStartNew={() => startMut.mutate()}
      />
    );
  }

  const roundsLeft = negotiation.max_rounds - negotiation.rounds.length;
  const lastBidPct =
    [...negotiation.rounds]
      .reverse()
      .find((r) => r.proposed_pct !== null)?.proposed_pct ?? null;
  const inputDisabled = sendMut.isPending || roundsLeft <= 0;
  const canAccept = lastBidPct !== null;

  return (
    <div className="space-y-4">
      {/* Briefing endast om inga ronder ännu */}
      {negotiation.rounds.length === 0 && (
        <Card>
          <MarkdownLite text={briefing} />
        </Card>
      )}

      {/* Status-rad */}
      <div className="flex items-center justify-between text-sm border rounded-md p-2 bg-slate-50">
        <div>
          <strong>Rond:</strong> {negotiation.rounds.length} av{" "}
          {negotiation.max_rounds}
          {lastBidPct !== null && (
            <>
              {" · "}
              <strong>Senaste bud:</strong> {lastBidPct.toFixed(1)} %
            </>
          )}
          {negotiation.avtal_norm_pct !== null && (
            <>
              {" · "}
              <strong>Avtals-norm:</strong>{" "}
              {negotiation.avtal_norm_pct.toFixed(1)} %
            </>
          )}
        </div>
        {canAccept && (
          <button
            onClick={() =>
              completeMut.mutate({
                id: negotiation.id,
                accept_offer: true,
              })
            }
            disabled={completeMut.isPending}
            className="text-xs bg-emerald-600 text-white rounded px-3 py-1 hover:bg-emerald-700 disabled:opacity-50"
          >
            Acceptera senaste bud ({lastBidPct?.toFixed(1)} %)
          </button>
        )}
      </div>

      {/* Tråden */}
      <div className="space-y-3">
        {negotiation.rounds.map((r) => (
          <div key={r.round_no} className="space-y-2">
            <div className="bg-slate-50 border-l-4 border-slate-300 rounded-r p-3">
              <div className="text-[10px] uppercase text-slate-500 mb-1">
                Du · rond {r.round_no}
              </div>
              <div className="text-sm whitespace-pre-wrap text-slate-800">
                {r.student_message}
              </div>
            </div>
            <div className="bg-brand-50 border-l-4 border-brand-400 rounded-r p-3">
              <div className="text-[10px] uppercase text-brand-700 mb-1">
                Maria (HR) · rond {r.round_no}
                {r.proposed_pct !== null && (
                  <span className="ml-2">
                    bud: <strong>{r.proposed_pct.toFixed(1)} %</strong>
                  </span>
                )}
              </div>
              <div className="text-sm whitespace-pre-wrap text-slate-800">
                {r.employer_response}
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Inmatningsruta */}
      {roundsLeft > 0 ? (
        <Card>
          <div className="text-xs text-slate-500 mb-1">
            Skriv ditt argument ({roundsLeft} ronder kvar)
          </div>
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            disabled={inputDisabled}
            rows={4}
            placeholder="T.ex. 'Jag tog över ansvar X i juni och har levererat Y. Marknadsdata visar Z för min roll. Jag siktar på 4 %.'"
            className="w-full border rounded p-2 text-sm disabled:opacity-50"
          />
          <div className="flex items-center justify-between mt-2">
            <div className="text-[10px] text-slate-500">
              Tips: hänvisa till avtals-normen och dina prestationer.
              Hot om uppsägning utan plan funkar inte — chefen håller
              sitt bud.
            </div>
            <button
              onClick={send}
              disabled={inputDisabled || draft.trim().length < 10}
              className="bg-brand-600 text-white rounded px-4 py-1.5 text-sm hover:bg-brand-700 disabled:opacity-50"
            >
              {sendMut.isPending ? "Skickar…" : "Skicka argument"}
            </button>
          </div>
          {sendMut.error && (
            <div className="text-xs text-rose-700 mt-2">
              {String(sendMut.error)}
            </div>
          )}
        </Card>
      ) : (
        <Card>
          <div className="text-sm text-slate-700 mb-2">
            Du har använt alla {negotiation.max_rounds} ronder.
            {canAccept ? " Acceptera senaste bud eller avbryt." : " Du kan avbryta."}
          </div>
          <div className="flex gap-2">
            {canAccept && (
              <button
                onClick={() =>
                  completeMut.mutate({
                    id: negotiation.id,
                    accept_offer: true,
                  })
                }
                disabled={completeMut.isPending}
                className="bg-emerald-600 text-white rounded px-4 py-1.5 text-sm hover:bg-emerald-700 disabled:opacity-50"
              >
                Acceptera ({lastBidPct?.toFixed(1)} %)
              </button>
            )}
            <button
              onClick={() =>
                completeMut.mutate({
                  id: negotiation.id,
                  accept_offer: false,
                })
              }
              disabled={completeMut.isPending}
              className="border border-slate-300 text-slate-700 rounded px-4 py-1.5 text-sm hover:bg-slate-50 disabled:opacity-50"
            >
              Avbryt utan höjning
            </button>
          </div>
        </Card>
      )}
    </div>
  );
}


function NegotiationSummary({
  negotiation,
  completion,
  onStartNew,
}: {
  negotiation: NegotiationOut;
  completion: CompleteOut | null;
  onStartNew: () => void;
}) {
  const finalPct = completion?.final_pct ?? negotiation.final_pct;
  const finalSalary = completion?.final_salary ?? negotiation.final_salary;
  const avtalNorm = completion?.avtal_norm_pct ?? negotiation.avtal_norm_pct;
  const effectiveFrom =
    completion?.pending_effective_from ?? null;

  const delta =
    finalPct !== null && avtalNorm !== null
      ? finalPct - avtalNorm
      : null;

  let assessTone = "border-slate-200 bg-slate-50";
  let assessText = "";
  if (delta !== null) {
    if (delta > 0.5) {
      assessTone = "border-emerald-300 bg-emerald-50";
      assessText = `Du landade ${delta.toFixed(1)} pp över avtals-norm — bra förhandling.`;
    } else if (delta < -0.5) {
      assessTone = "border-rose-300 bg-rose-50";
      assessText = `Du landade ${Math.abs(delta).toFixed(1)} pp under avtals-norm. Pedagogisk anledning att fundera över argumenten.`;
    } else {
      assessTone = "border-slate-200 bg-slate-50";
      assessText = "Du landade i nivå med avtals-normen.";
    }
  }

  return (
    <div className="space-y-4">
      <Card title="Lönesamtal avslutat">
        <div className={`border-l-4 rounded-md p-3 mb-3 ${assessTone}`}>
          <div className="text-xs uppercase tracking-wide text-slate-500">
            Resultat
          </div>
          {finalPct !== null && finalSalary !== null ? (
            <>
              <div className="text-2xl serif mt-1">
                {finalPct.toFixed(1)} % höjning
              </div>
              <div className="text-sm text-slate-700 mt-0.5">
                {formatSEK(negotiation.starting_salary)} →{" "}
                <strong>{formatSEK(finalSalary)}</strong>
                {effectiveFrom && (
                  <> · gäller från {effectiveFrom}</>
                )}
              </div>
              {assessText && (
                <div className="text-sm text-slate-700 mt-2">
                  {assessText}
                </div>
              )}
            </>
          ) : (
            <div className="text-sm text-slate-700 mt-1">
              Du valde att inte acceptera något bud — lönen är oförändrad.
            </div>
          )}
        </div>

        {/* Pedagogisk reflektion */}
        {completion?.summary_md ? (
          <MarkdownLite text={completion.summary_md} />
        ) : negotiation.teacher_summary_md ? (
          <MarkdownLite text={negotiation.teacher_summary_md} />
        ) : null}

        <div className="mt-4 flex gap-2">
          <button
            onClick={onStartNew}
            className="border border-slate-300 rounded px-3 py-1.5 text-sm hover:bg-slate-50"
          >
            Återgå till samtalet ovan
          </button>
        </div>
      </Card>

      {/* Transkript */}
      <Card title="Transkript">
        <div className="space-y-3">
          {negotiation.rounds.map((r) => (
            <div key={r.round_no} className="space-y-1">
              <div className="text-[10px] uppercase text-slate-500">
                Rond {r.round_no}
              </div>
              <div className="text-sm bg-slate-50 border-l-2 border-slate-300 pl-2 py-1">
                <strong>Du:</strong> {r.student_message}
              </div>
              <div className="text-sm bg-brand-50 border-l-2 border-brand-400 pl-2 py-1">
                <strong>Maria:</strong> {r.employer_response}
                {r.proposed_pct !== null && (
                  <span className="ml-2 text-xs text-brand-700">
                    (bud: {r.proposed_pct.toFixed(1)} %)
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}


// ---------- Lönespec-fliken (PR 4a) ----------

interface BatchArtifact {
  id: number;
  kind: string;
  title: string;
  filename: string;
  imported_at: string | null;
  meta: Record<string, unknown> | null;
}


interface BatchOut {
  id: number;
  year_month: string;
  artifact_count: number;
  imported_count: number;
  artifacts: BatchArtifact[];
}


function SalarySlipsTab() {
  const batchesQ = useQuery({
    queryKey: ["student-batches", "arbetsgivare"],
    queryFn: () => api<BatchOut[]>(
      "/student/batches?visible_in=arbetsgivare",
    ),
  });
  const qc = useQueryClient();
  const [previewArt, setPreviewArt] = useState<{
    batchId: number;
    art: BatchArtifact;
  } | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const lastBlobRef = useRef<string | null>(null);
  const [importing, setImporting] = useState<number | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    return () => {
      if (lastBlobRef.current) URL.revokeObjectURL(lastBlobRef.current);
    };
  }, []);

  // Plocka alla lönespec-artefakter, senaste batch först
  const slips: { batchId: number; year_month: string; art: BatchArtifact }[] = [];
  for (const b of batchesQ.data ?? []) {
    for (const a of b.artifacts ?? []) {
      if (a.kind === "lonespec") {
        slips.push({ batchId: b.id, year_month: b.year_month, art: a });
      }
    }
  }

  async function openPreview(batchId: number, art: BatchArtifact) {
    setPreviewArt({ batchId, art });
    setPreviewLoading(true);
    setErr(null);
    try {
      const url =
        `${getApiBase()}/student/batches/${batchId}/artifacts/${art.id}/download`;
      const tok = getToken();
      const res = await fetch(url, {
        headers: tok ? { Authorization: `Bearer ${tok}` } : undefined,
      });
      if (!res.ok) throw new Error(`Hämtning misslyckades (${res.status})`);
      const blob = await res.blob();
      const blobUrl = URL.createObjectURL(blob);
      if (lastBlobRef.current) URL.revokeObjectURL(lastBlobRef.current);
      lastBlobRef.current = blobUrl;
      setPreviewUrl(blobUrl);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
      setPreviewArt(null);
    } finally {
      setPreviewLoading(false);
    }
  }

  function closePreview() {
    setPreviewArt(null);
    setPreviewUrl(null);
    if (lastBlobRef.current) {
      URL.revokeObjectURL(lastBlobRef.current);
      lastBlobRef.current = null;
    }
  }

  async function downloadArt(batchId: number, art: BatchArtifact) {
    const url =
      `${getApiBase()}/student/batches/${batchId}/artifacts/${art.id}/download`;
    const tok = getToken();
    const res = await fetch(url, {
      headers: tok ? { Authorization: `Bearer ${tok}` } : undefined,
    });
    if (!res.ok) {
      setErr(`Nedladdning misslyckades (${res.status})`);
      return;
    }
    const blob = await res.blob();
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = art.filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
  }

  async function importArt(batchId: number, art: BatchArtifact) {
    setImporting(art.id);
    setErr(null);
    try {
      await api(
        `/student/batches/${batchId}/artifacts/${art.id}/import`,
        { method: "POST" },
      );
      qc.invalidateQueries({ queryKey: ["student-batches"] });
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setImporting(null);
    }
  }

  if (batchesQ.isLoading) {
    return <Card><div className="text-sm text-slate-600">Laddar lönespecar…</div></Card>;
  }
  if (slips.length === 0) {
    return (
      <Card title="Inga lönespecar än">
        <div className="text-sm text-slate-700 leading-relaxed">
          Lönespecar kommer från din arbetsgivare en gång per månad.
          När läraren genererar månadens material syns dom här direkt
          — du kan förhandsgranska, ladda ner och importera till
          bokföringen.
        </div>
      </Card>
    );
  }

  return (
    <Card title={`Lönespecar (${slips.length})`}>
      <div className="text-xs text-slate-500 mb-3">
        Förhandsgranska för att läsa lönespecen. Importera så hamnar
        siffrorna automatiskt i din bokföring (lön + skatt + pension).
      </div>
      {err && (
        <div className="text-sm text-rose-700 mb-2 border-l-2 border-rose-400 pl-2">
          {err}
        </div>
      )}
      <ul className="divide-y divide-slate-200">
        {slips.map(({ batchId, year_month, art }) => {
          const isPreviewing =
            previewArt?.art.id === art.id && previewArt.batchId === batchId;
          return (
            <li
              key={`${batchId}-${art.id}`}
              className={`py-2 flex items-center gap-3 ${
                isPreviewing ? "bg-brand-50 -mx-2 px-2 rounded" : ""
              }`}
            >
              <FileText className="w-4 h-4 text-slate-400 flex-shrink-0" />
              <button
                onClick={() => openPreview(batchId, art)}
                className="flex-1 text-left min-w-0 hover:text-brand-700"
              >
                <div className="font-medium text-sm truncate">
                  {year_month} — {art.title}
                </div>
                <div className="text-xs text-slate-500 truncate">
                  {art.filename}
                </div>
              </button>
              {art.imported_at ? (
                <span className="text-xs text-emerald-700 hidden sm:inline-flex items-center gap-1 mr-2">
                  <CheckCircle2 className="w-3.5 h-3.5" /> Importerad
                </span>
              ) : null}
              <button
                onClick={() => openPreview(batchId, art)}
                title="Förhandsgranska"
                className={`p-1.5 rounded ${
                  isPreviewing
                    ? "bg-brand-100 text-brand-700"
                    : "hover:bg-slate-100 text-slate-600"
                }`}
              >
                <Eye className="w-4 h-4" />
              </button>
              <button
                onClick={() => downloadArt(batchId, art)}
                title="Ladda ner PDF"
                className="p-1.5 hover:bg-slate-100 rounded text-slate-600"
              >
                <Download className="w-4 h-4" />
              </button>
              <button
                onClick={() => importArt(batchId, art)}
                disabled={importing !== null}
                title="Importera lön till bokföringen"
                className={`p-1.5 rounded text-emerald-600 ${
                  art.imported_at ? "hover:bg-emerald-50" : "hover:bg-emerald-100"
                } disabled:opacity-50`}
              >
                {importing === art.id ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Upload className="w-4 h-4" />
                )}
              </button>
            </li>
          );
        })}
      </ul>

      {/* Preview-overlay */}
      {previewArt && (
        <div className="fixed inset-0 z-50 flex flex-col bg-white">
          <div className="flex items-center justify-between p-3 border-b">
            <div className="min-w-0">
              <div className="font-medium text-sm truncate">
                {previewArt.art.title}
              </div>
              <div className="text-xs text-slate-500 truncate">
                {previewArt.art.filename}
              </div>
            </div>
            <div className="flex items-center gap-1">
              <button
                onClick={() =>
                  downloadArt(previewArt.batchId, previewArt.art)
                }
                title="Ladda ner"
                className="p-1.5 hover:bg-slate-100 rounded text-slate-600"
              >
                <Download className="w-4 h-4" />
              </button>
              <button
                onClick={closePreview}
                className="p-1.5 hover:bg-slate-100 rounded text-slate-600"
                aria-label="Stäng"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          </div>
          <div className="flex-1 bg-slate-100">
            {previewLoading ? (
              <div className="h-full flex items-center justify-center text-slate-500 text-sm">
                <Loader2 className="w-4 h-4 animate-spin mr-2" />
                Laddar…
              </div>
            ) : previewUrl ? (
              <iframe
                title={previewArt.art.filename}
                src={previewUrl}
                className="w-full h-full"
              />
            ) : null}
          </div>
        </div>
      )}
    </Card>
  );
}


