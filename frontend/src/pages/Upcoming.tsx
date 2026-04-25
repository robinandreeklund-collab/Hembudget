import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import {
  CalendarPlus, ChevronDown, ChevronRight, Image as ImageIcon,
  Loader2, Sparkles, Trash2, Unlink,
  TrendingDown, TrendingUp, Users,
} from "lucide-react";
import { api, formatSEK, getToken } from "@/api/client";
import { Card } from "@/components/Card";
import type { Account, Category } from "@/types/models";

interface UpcomingLine {
  id: number;
  description: string;
  amount: number;
  category_id: number | null;
  sort_order: number;
}

interface UpcomingItem {
  id: number;
  kind: "bill" | "income";
  name: string;
  amount: number;
  expected_date: string;
  owner: string | null;
  category_id: number | null;
  recurring_monthly: boolean;
  source: string;
  source_image_path: string | null;
  notes: string | null;
  invoice_number: string | null;
  invoice_date: string | null;
  ocr_reference: string | null;
  bankgiro: string | null;
  plusgiro: string | null;
  iban: string | null;
  debit_account_id: number | null;
  debit_date: string | null;
  autogiro: boolean;
  matched_transaction_id: number | null;
  lines: UpcomingLine[];
  payment_tx_ids?: number[];
  payment_transactions?: Array<{
    id: number;
    date: string;
    amount: number;
    description: string;
    account_id: number;
    account_name: string | null;
  }>;
  paid_amount?: number;
  payment_status?: "unpaid" | "partial" | "paid" | "overpaid";
}

interface Forecast {
  month: string;
  salary_cycle_start_day?: number;
  period_start?: string;
  period_end?: string;
  upcoming_incomes: Array<{ id: number; name: string; amount: number; expected_date: string; owner: string | null }>;
  upcoming_bills: Array<{ id: number; name: string; amount: number; expected_date: string }>;
  totals: {
    expected_income: number;
    upcoming_bills: number;
    loan_scheduled?: number;
    avg_fixed_expenses: number;
    after_known_bills?: number;
    available_to_split: number;
  };
  split: {
    ratio: number;
    per_person_share: number;
    per_person_other: number;
  };
  income_by_owner: Record<string, number>;
}

function currentMonth(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

function apiBase(): string {
  let explicit = (import.meta as ImportMeta).env.VITE_API_BASE;
  if (explicit) {
    if (!/^https?:\/\//i.test(explicit)) explicit = `https://${explicit}`;
    return explicit.replace(/\/$/, "");
  }
  const port = localStorage.getItem("hembudget_api_port") || "8765";
  return `http://127.0.0.1:${port}`;
}

interface ParseState {
  file: File;
  status: "uploading" | "done" | "error";
  message?: string;
  item?: UpcomingItem;
}

export default function Upcoming() {
  const qc = useQueryClient();
  const [month, setMonth] = useState(currentMonth());
  const [parseJobs, setParseJobs] = useState<ParseState[]>([]);
  const [textInput, setTextInput] = useState("");
  const [textKind, setTextKind] = useState<"bill" | "income">("bill");
  const dragRef = useRef<HTMLDivElement>(null);
  const [isDragging, setIsDragging] = useState(false);

  const listQ = useQuery({
    queryKey: ["upcoming"],
    queryFn: () => api<UpcomingItem[]>("/upcoming/?only_future=false"),
  });
  const accountsQ = useQuery({
    queryKey: ["accounts"],
    queryFn: () => api<Account[]>("/accounts"),
  });
  const categoriesQ = useQuery({
    queryKey: ["categories"],
    queryFn: () => api<Category[]>("/categories"),
  });
  const setLinesMut = useMutation({
    mutationFn: (p: { id: number; lines: Array<Omit<UpcomingLine, "id">> }) =>
      api<UpcomingLine[]>(`/upcoming/${p.id}/lines`, {
        method: "PUT",
        body: JSON.stringify(p.lines),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["upcoming"] }),
  });
  const updateMut = useMutation({
    mutationFn: (p: { id: number; data: Partial<UpcomingItem> }) =>
      api(`/upcoming/${p.id}`, { method: "PATCH", body: JSON.stringify(p.data) }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["upcoming"] });
      qc.invalidateQueries({ queryKey: ["upcoming-forecast"] });
    },
  });
  const forecastQ = useQuery({
    queryKey: ["upcoming-forecast", month],
    queryFn: () => api<Forecast>(`/upcoming/forecast?month=${month}&split_ratio=0.5`),
  });

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["upcoming"] });
    qc.invalidateQueries({ queryKey: ["upcoming-forecast"] });
    qc.invalidateQueries({ queryKey: ["transactions"] });
    qc.invalidateQueries({ queryKey: ["budget"] });
    qc.invalidateQueries({ queryKey: ["balances"] });
    qc.invalidateQueries({ queryKey: ["accounts"] });
  };

  const textMut = useMutation({
    mutationFn: async () => {
      const form = new FormData();
      form.append("text", textInput);
      form.append("kind", textKind);
      const token = getToken();
      const res = await fetch(`${apiBase()}/upcoming/parse-text`, {
        method: "POST",
        body: form,
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) throw new Error(await res.text());
      return res.json();
    },
    onSuccess: () => {
      setTextInput("");
      invalidate();
    },
  });

  const deleteMut = useMutation({
    mutationFn: (id: number) => api(`/upcoming/${id}`, { method: "DELETE" }),
    onSuccess: invalidate,
  });

  async function uploadInvoices(files: FileList | File[]) {
    const arr = Array.from(files);
    const initial: ParseState[] = arr.map((f) => ({ file: f, status: "uploading" }));
    setParseJobs((prev) => [...prev, ...initial]);

    const token = getToken();
    for (let i = 0; i < arr.length; i++) {
      const f = arr[i];
      const form = new FormData();
      form.append("file", f);
      form.append("kind", "bill");
      try {
        const res = await fetch(`${apiBase()}/upcoming/parse-invoice-image`, {
          method: "POST",
          body: form,
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        });
        if (!res.ok) {
          const text = await res.text();
          setParseJobs((prev) =>
            prev.map((j) => (j.file === f ? { ...j, status: "error", message: text } : j)),
          );
          continue;
        }
        const item: UpcomingItem = await res.json();
        setParseJobs((prev) =>
          prev.map((j) => (j.file === f ? { ...j, status: "done", item } : j)),
        );
      } catch (e) {
        setParseJobs((prev) =>
          prev.map((j) =>
            j.file === f ? { ...j, status: "error", message: String(e) } : j,
          ),
        );
      }
    }
    invalidate();
  }

  function onDrop(e: React.DragEvent) {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files.length) uploadInvoices(e.dataTransfer.files);
  }

  const items = listQ.data ?? [];
  // "Öppen" = INTE fullt betald (payment_status !== "paid"). Delbetalda
  // fakturor (t.ex. Amex 27 000 kr där 2 000 kr är inbetalt) ska fortsätta
  // ligga i Kommande med resterande belopp tills hela summan är klar —
  // matched_transaction_id är bara "primär match" och blir satt redan vid
  // första delbetalningen, så det dugger INTE som paid-indikator.
  const isFullyPaid = (i: UpcomingItem) => i.payment_status === "paid";
  const openBills = items.filter((i) => i.kind === "bill" && !isFullyPaid(i));
  const paidBills = items.filter((i) => i.kind === "bill" && isFullyPaid(i));
  const openIncomes = items.filter((i) => i.kind === "income" && !isFullyPaid(i));
  const paidIncomes = items.filter((i) => i.kind === "income" && isFullyPaid(i));

  return (
    <div className="p-3 md:p-6 space-y-4 md:space-y-5 max-w-5xl">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold flex items-center gap-2">
            <CalendarPlus className="w-6 h-6" />
            Kommande
          </h1>
          <div className="text-sm text-slate-700 mt-0.5">
            Planera kommande fakturor och löner — se hur mycket som blir kvar att dela.
          </div>
        </div>
        <input
          type="month"
          value={month}
          onChange={(e) => setMonth(e.target.value)}
          className="border rounded-lg px-3 py-1.5"
        />
      </div>

      <SalaryCycleSetting month={month} />

      {forecastQ.data && (
        <Card
          title={
            forecastQ.data.salary_cycle_start_day &&
            forecastQ.data.salary_cycle_start_day > 1
              ? `Månadsprognos — ${month} (${forecastQ.data.period_start?.slice(5)} – ${forecastQ.data.period_end?.slice(5)})`
              : `Månadsprognos — ${month}`
          }
        >
          <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
            <Stat
              icon={<TrendingUp className="w-4 h-4 text-emerald-600" />}
              label="Kommande lön"
              value={formatSEK(forecastQ.data.totals.expected_income)}
            />
            <Stat
              icon={<TrendingDown className="w-4 h-4 text-amber-600" />}
              label="Kommande fakturor"
              value={formatSEK(forecastQ.data.totals.upcoming_bills)}
            />
            {(forecastQ.data.totals.loan_scheduled ?? 0) > 0 && (
              <Stat
                icon={<TrendingDown className="w-4 h-4 text-amber-700" />}
                label="Lån (ränta + amort.)"
                value={formatSEK(forecastQ.data.totals.loan_scheduled ?? 0)}
                hint="Från låneschemat för månaden"
              />
            )}
            <Stat
              icon={<Users className="w-4 h-4 text-emerald-700" />}
              label="Kvar efter kända"
              value={formatSEK(
                forecastQ.data.totals.after_known_bills ??
                (forecastQ.data.totals.expected_income -
                  forecastQ.data.totals.upcoming_bills),
              )}
              hint="Lön − fakturor − lån (ignorerar variabla utgifter)"
              tone={
                (forecastQ.data.totals.after_known_bills ??
                  (forecastQ.data.totals.expected_income -
                    forecastQ.data.totals.upcoming_bills)) >= 0
                  ? "good"
                  : "bad"
              }
            />
            <Stat
              icon={<TrendingDown className="w-4 h-4 text-rose-600" />}
              label="Snitt variabla utg."
              value={formatSEK(forecastQ.data.totals.avg_fixed_expenses)}
              hint="3-mån-snitt: mat, transport, nöje (exkl. fakturor + lån)"
            />
          </div>
          <div className="mt-4 p-3 bg-brand-50 border border-brand-100 rounded text-sm">
            <strong>Så här räknas det:</strong>{" "}
            <span className="font-mono text-xs">
              {formatSEK(forecastQ.data.totals.expected_income)} lön
              − {formatSEK(forecastQ.data.totals.upcoming_bills)} fakturor
              {(forecastQ.data.totals.loan_scheduled ?? 0) > 0 && (
                <> − {formatSEK(forecastQ.data.totals.loan_scheduled ?? 0)} lån</>
              )}
              {" "}= {formatSEK(forecastQ.data.totals.after_known_bills ?? 0)}{" "}
              kvar efter kända
            </span>
            <div className="text-xs font-mono mt-1">
              − {formatSEK(forecastQ.data.totals.avg_fixed_expenses)} snitt variabla
              = <strong className={
                forecastQ.data.totals.available_to_split >= 0
                  ? "text-emerald-700"
                  : "text-rose-600"
              }>
                {formatSEK(forecastQ.data.totals.available_to_split)}
              </strong> prognostiserat överskott
            </div>
            <div className="mt-2">
              <strong>50/50-fördelning av överskott:</strong>{" "}
              <span className="font-semibold">
                {formatSEK(forecastQ.data.split.per_person_share)}
              </span>{" "}
              till var och en.
            </div>
            {Object.keys(forecastQ.data.income_by_owner).length > 0 && (
              <div className="text-xs text-slate-700 mt-1">
                Inkomst per person:{" "}
                {Object.entries(forecastQ.data.income_by_owner)
                  .map(([k, v]) => `${k} ${formatSEK(v)}`)
                  .join(" · ")}
              </div>
            )}
          </div>
        </Card>
      )}

      <CreditCardInvoiceCard onDone={invalidate} />

      <Card title="Tolka fakturor automatiskt">
        <div className="text-sm text-slate-700 mb-3">
          Dra och släpp fakturabilder. Systemet skickar varje bild till din lokala
          LM Studio-modell som extraherar betalningsmottagare, belopp och förfallodag
          helt automatiskt.{" "}
          <strong>
            Byt till en vision-kapabel modell i LM Studio först (t.ex. Qwen2.5-VL, Llava, Pixtral)
          </strong>
          .
        </div>

        <div
          ref={dragRef}
          onDragOver={(e) => {
            e.preventDefault();
            setIsDragging(true);
          }}
          onDragLeave={() => setIsDragging(false)}
          onDrop={onDrop}
          className={`border-2 border-dashed rounded-lg p-8 text-center transition ${
            isDragging
              ? "border-brand-500 bg-brand-50"
              : "border-slate-300 bg-slate-50"
          }`}
        >
          <ImageIcon className="w-10 h-10 mx-auto text-slate-600 mb-2" />
          <div className="text-sm text-slate-600">
            Dra fakturabilder hit, eller{" "}
            <label className="text-brand-600 cursor-pointer underline">
              välj filer
              <input
                type="file"
                multiple
                accept="image/*,.pdf"
                className="hidden"
                onChange={(e) => e.target.files && uploadInvoices(e.target.files)}
              />
            </label>
          </div>
        </div>

        {parseJobs.length > 0 && (
          <div className="mt-3 space-y-2">
            {parseJobs.map((job, i) => (
              <div
                key={i}
                className="flex items-center gap-3 p-2 border rounded bg-white text-sm"
              >
                {job.status === "uploading" && (
                  <Loader2 className="w-4 h-4 animate-spin text-brand-600" />
                )}
                {job.status === "done" && (
                  <Sparkles className="w-4 h-4 text-emerald-600" />
                )}
                {job.status === "error" && (
                  <div className="w-4 h-4 rounded-full bg-rose-500" />
                )}
                <div className="flex-1 truncate">{job.file.name}</div>
                {job.item && (
                  <div className="text-slate-600 text-xs">
                    <strong>{job.item.name}</strong> — {formatSEK(job.item.amount)}, förfall {job.item.expected_date}
                  </div>
                )}
                {job.status === "error" && (
                  <div className="text-rose-600 text-xs truncate max-w-md">{job.message}</div>
                )}
              </div>
            ))}
            <button
              onClick={() => setParseJobs([])}
              className="text-xs text-slate-700 hover:underline"
            >
              Rensa lista
            </button>
          </div>
        )}
      </Card>

      <Card title="Snabbinmatning via text">
        <div className="text-sm text-slate-700 mb-2">
          Skriv fritt, LM Studio tolkar: <em>"Vattenfall 1 420 kr förfaller 30 april"</em> eller
          <em> "Lön Robin 42 000 kr den 25:e"</em>. Bra för räkningar utan bild.
        </div>
        <div className="flex gap-2">
          <select
            value={textKind}
            onChange={(e) => setTextKind(e.target.value as "bill" | "income")}
            className="border rounded px-2 py-1.5"
          >
            <option value="bill">Faktura</option>
            <option value="income">Lön/Inkomst</option>
          </select>
          <input
            value={textInput}
            onChange={(e) => setTextInput(e.target.value)}
            placeholder="T.ex. SBAB bolåneränta 8 500 kr förfaller 25 april"
            className="flex-1 border rounded px-3 py-1.5"
          />
          <button
            onClick={() => textInput && textMut.mutate()}
            disabled={!textInput || textMut.isPending}
            className="bg-brand-600 text-white px-4 py-1.5 rounded disabled:opacity-40"
          >
            {textMut.isPending ? "Tolkar…" : "Lägg till"}
          </button>
        </div>
      </Card>

      <Card title={`Kommande fakturor (${openBills.length})`}>
        <ItemList
          items={openBills}
          accounts={accountsQ.data ?? []}
          categories={categoriesQ.data ?? []}
          onDelete={(id) => deleteMut.mutate(id)}
          onUpdate={(id, data) => updateMut.mutate({ id, data })}
          onSetLines={(id, lines) => setLinesMut.mutate({ id, lines })}
          grouped
          defaultExpandedMonths={2}
        />
      </Card>
      {paidBills.length > 0 && (
        <Card title={`Betalda fakturor (${paidBills.length})`}>
          <div className="text-xs text-slate-700 mb-2">
            Fakturor som auto-matchats mot en befintlig bankrad — visas här
            för historik. Tas inte med i cashflow-prognosen. Klicka på en
            månad för att se detaljer.
          </div>
          <ItemList
            items={paidBills}
            accounts={accountsQ.data ?? []}
            categories={categoriesQ.data ?? []}
            onDelete={(id) => deleteMut.mutate(id)}
            onUpdate={(id, data) => updateMut.mutate({ id, data })}
            onSetLines={(id, lines) => setLinesMut.mutate({ id, lines })}
            grouped
          />
        </Card>
      )}
      {(openIncomes.length > 0 || paidIncomes.length > 0) && (
        <Card title="Lön har flyttat">
          <div className="text-sm text-slate-700">
            Lönerelaterade rader visas nu på en egen sida —{" "}
            <a href="/salaries" className="text-brand-600 underline">
              gå till Lön
            </a>
            {" "}för KPI:er, breakdown per person, kommande och historik.
          </div>
        </Card>
      )}
    </div>
  );
}

const SV_MONTH_NAMES = [
  "januari", "februari", "mars", "april", "maj", "juni",
  "juli", "augusti", "september", "oktober", "november", "december",
];

function formatMonthLabel(ym: string): string {
  const [y, m] = ym.split("-").map(Number);
  if (!y || !m) return ym;
  return `${SV_MONTH_NAMES[m - 1]} ${y}`;
}

function ItemList({
  items,
  accounts,
  categories,
  onDelete,
  onUpdate,
  onSetLines,
  grouped = false,
  defaultExpandedMonths = 0,
}: {
  items: UpcomingItem[];
  accounts: Account[];
  categories: Category[];
  onDelete: (id: number) => void;
  onUpdate: (id: number, data: Partial<UpcomingItem>) => void;
  onSetLines: (id: number, lines: Array<Omit<UpcomingLine, "id">>) => void;
  /** Gruppera på expected_date-månad med kollapsbara sektioner */
  grouped?: boolean;
  /** Antal senaste månader som är expanderade från start (0 = alla kollapsade) */
  defaultExpandedMonths?: number;
}) {
  if (items.length === 0) {
    return <div className="text-sm text-slate-700">Inget registrerat ännu.</div>;
  }
  if (!grouped) {
    return (
      <div className="space-y-2">
        {items.map((i) => (
          <UpcomingRow
            key={i.id}
            item={i}
            accounts={accounts}
            categories={categories}
            onDelete={onDelete}
            onUpdate={onUpdate}
            onSetLines={onSetLines}
          />
        ))}
      </div>
    );
  }

  // Gruppera per YYYY-MM
  const byMonth: Record<string, UpcomingItem[]> = {};
  for (const i of items) {
    const ym = i.expected_date.slice(0, 7);
    (byMonth[ym] = byMonth[ym] || []).push(i);
  }
  // Sortera nyast först så senaste månaden syns överst
  const months = Object.keys(byMonth).sort().reverse();
  // Bara aktuell (pågående) månad ska vara öppen by default. Framtida
  // månader (maj, juni…) kollapsade så vyn inte blir överlastad med
  // återkommande prenumerationer flera månader framåt. Om aktuell
  // månad saknas i listan (t.ex. alla rader ligger i maj), öppna den
  // närmaste framtida månaden istället.
  const todayYm = new Date().toISOString().slice(0, 7);
  const defaultOpen: string[] = [];
  if (months.includes(todayYm)) {
    defaultOpen.push(todayYm);
  } else if (defaultExpandedMonths > 0) {
    // Fallback: första N månader (gammal beteende) om aktuell månad saknas
    defaultOpen.push(...months.slice(0, defaultExpandedMonths));
  }
  const initiallyOpen = new Set(defaultOpen);

  return (
    <div className="space-y-2">
      {months.map((ym) => (
        <MonthSection
          key={ym}
          month={ym}
          items={byMonth[ym]}
          accounts={accounts}
          categories={categories}
          onDelete={onDelete}
          onUpdate={onUpdate}
          onSetLines={onSetLines}
          initiallyOpen={initiallyOpen.has(ym)}
        />
      ))}
    </div>
  );
}

function MonthSection({
  month,
  items,
  accounts,
  categories,
  onDelete,
  onUpdate,
  onSetLines,
  initiallyOpen,
}: {
  month: string;
  items: UpcomingItem[];
  accounts: Account[];
  categories: Category[];
  onDelete: (id: number) => void;
  onUpdate: (id: number, data: Partial<UpcomingItem>) => void;
  onSetLines: (id: number, lines: Array<Omit<UpcomingLine, "id">>) => void;
  initiallyOpen: boolean;
}) {
  const [open, setOpen] = useState(initiallyOpen);
  // "Matchad" = fullt betald (payment_status === "paid"). Delbetalda
  // räknas som omatchade eftersom det finns något kvar att göra. Detta
  // matchar backend /upcoming/forecast-logiken så siffrorna stämmer
  // mellan månads-prognos-kortet och denna lista.
  const matched = items.filter((i) => i.payment_status === "paid").length;
  const unmatched = items.length - matched;
  // Månads-total = ÅTERSTÅENDE belopp för ej-fullt-betalda, inte gross.
  // Så här räknar också /upcoming/forecast bills_total — en Amex-faktura
  // på 27 000 kr där 2 000 kr redan är inbetalt visas som 25 000 kr.
  // OBS: amount + paid_amount kommer som string från Pydantic/Decimal,
  // så Number()-cast innan subtraktion.
  const total = items.reduce((s, i) => {
    if (i.payment_status === "paid") return s;
    const remaining = Math.abs(Number(i.amount)) - Math.abs(Number(i.paid_amount ?? 0));
    return s + Math.max(0, remaining);
  }, 0);
  const allMatched = matched > 0 && unmatched === 0;

  return (
    <div className="border rounded-lg overflow-hidden">
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center gap-3 px-3 py-2 hover:bg-slate-50 text-left"
      >
        {open ? (
          <ChevronDown className="w-4 h-4 text-slate-600 shrink-0" />
        ) : (
          <ChevronRight className="w-4 h-4 text-slate-600 shrink-0" />
        )}
        <div className="flex-1 min-w-0">
          <div className="font-medium capitalize">{formatMonthLabel(month)}</div>
          <div className="text-xs text-slate-700 flex flex-wrap gap-x-2">
            <span>{items.length} st</span>
            {matched > 0 && (
              <span className="text-emerald-600">· {matched} matchade</span>
            )}
            {unmatched > 0 && (
              <span className="text-amber-700">· {unmatched} omatchade</span>
            )}
            {allMatched && <span className="text-emerald-600">· ✓ allt OK</span>}
          </div>
        </div>
        <div className="text-right shrink-0">
          <div className="font-semibold">{formatSEK(total)}</div>
        </div>
      </button>
      {open && (
        <div className="border-t p-2 space-y-2 bg-slate-50/40">
          {items.map((i) => (
            <UpcomingRow
              key={i.id}
              item={i}
              accounts={accounts}
              categories={categories}
              onDelete={onDelete}
              onUpdate={onUpdate}
              onSetLines={onSetLines}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function UpcomingRow({
  item: i,
  accounts,
  categories,
  onDelete,
  onUpdate,
  onSetLines,
}: {
  item: UpcomingItem;
  accounts: Account[];
  categories: Category[];
  onDelete: (id: number) => void;
  onUpdate: (id: number, data: Partial<UpcomingItem>) => void;
  onSetLines: (id: number, lines: Array<Omit<UpcomingLine, "id">>) => void;
}) {
  // Auto-expandera raden om den är överbetald — då är det troligtvis
  // en fel-matchning och användaren vill se listan direkt för att
  // kunna ångra den.
  const [open, setOpen] = useState(i.payment_status === "overpaid");
  const debitAccount = accounts.find((a) => a.id === i.debit_account_id);
  const hasDetails =
    i.invoice_number || i.ocr_reference || i.bankgiro || i.plusgiro || i.iban ||
    i.invoice_date || i.notes;

  const isIncome = i.kind === "income";
  const L = isIncome
    ? {
        dateLabel: "Utbetalningsdatum",
        secondDateLabel: "Insätts",
        secondDateField: "Insättningsdag",
        accountLabel: "Insättningskonto",
        nameLabel: "Avsändare / arbetsgivare",
        summaryDate: "Utbetalas",
        summaryAccount: "till",
      }
    : {
        dateLabel: "Förfallodag",
        secondDateLabel: "Dras",
        secondDateField: "Debiteringsdag",
        accountLabel: "Debiteringskonto",
        nameLabel: "Mottagare / namn",
        summaryDate: "Förfall",
        summaryAccount: "från",
      };

  return (
    <div className="border rounded text-sm">
      <div className="flex items-center gap-3 p-2">
        <button
          onClick={() => setOpen((o) => !o)}
          className="text-slate-600 hover:text-slate-700"
        >
          {open ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
        </button>
        <div className="flex-1 min-w-0">
          <div className="font-medium truncate">{i.name}</div>
          <div className="text-xs text-slate-700 flex flex-wrap gap-x-2">
            <span>{L.summaryDate} {i.expected_date}</span>
            {i.debit_date && i.debit_date !== i.expected_date && (
              <span>· {L.secondDateLabel} {i.debit_date}</span>
            )}
            {debitAccount && <span>· {L.summaryAccount} {debitAccount.name}</span>}
            {!isIncome && i.autogiro && <span className="text-amber-700">· autogiro</span>}
            {i.owner && <span>· {i.owner}</span>}
            {i.recurring_monthly && <span>· återkommande</span>}
            {i.source !== "manual" && <span>· {i.source}</span>}
            {i.payment_status === "paid" && (
              <span className="text-emerald-600">
                · ✓ fullt betald
                {(i.payment_tx_ids?.length ?? 0) > 1 &&
                  ` (${i.payment_tx_ids?.length} delbetalningar)`}
              </span>
            )}
            {i.payment_status === "partial" && (
              <span className="text-amber-700">
                · ⚠ delbetalt {formatSEK(i.paid_amount ?? 0)} av{" "}
                {formatSEK(i.amount)} (kvar{" "}
                {formatSEK(i.amount - (i.paid_amount ?? 0))})
              </span>
            )}
            {i.payment_status === "overpaid" && (
              <span className="text-rose-600 font-medium">
                · ⚠ överbetald: {formatSEK(i.paid_amount ?? 0)} av{" "}
                {formatSEK(i.amount)} (+
                {formatSEK((i.paid_amount ?? 0) - i.amount)} för mycket) —
                expandera för att ångra fel-matchning
              </span>
            )}
            {i.matched_transaction_id && i.payment_status !== "paid" &&
              i.payment_status !== "partial" && i.payment_status !== "overpaid" && (
              <span className="text-emerald-600">
                · ✓ matchad mot transaktion #{i.matched_transaction_id}
              </span>
            )}
            {(!i.payment_status || i.payment_status === "unpaid" ||
              i.payment_status === "partial") && (
              <FindBankTxButton item={i} />
            )}
            {(!i.payment_status || i.payment_status === "unpaid") &&
              !i.matched_transaction_id && (
              <MaterializeDropdown item={i} accounts={accounts} />
            )}
            {i.source_image_path && (
              <button
                onClick={() => {
                  const token = getToken();
                  fetch(`${apiBase()}/upcoming/${i.id}/source`, {
                    headers: token ? { Authorization: `Bearer ${token}` } : {},
                  })
                    .then((r) => {
                      if (!r.ok) throw new Error("Filen saknas");
                      return r.blob();
                    })
                    .then((b) => window.open(URL.createObjectURL(b), "_blank"))
                    .catch((e) => alert(String(e.message ?? e)));
                }}
                className="nav-link"
                title="Öppna original-fakturan i ny flik"
              >
                · 📎 se faktura
              </button>
            )}
          </div>
        </div>
        <div
          className={`font-semibold shrink-0 ${
            isIncome ? "text-emerald-600" : "text-rose-600"
          }`}
        >
          {/* Tecken följer kind, inte tecknet i datan — bills är alltid
              utgift, income alltid inkomst. Vissa bills från auto:
              subscription lagrades förr negativt och skulle annars
              visas med fel tecken. */}
          {isIncome ? "+" : "−"}{formatSEK(Math.abs(Number(i.amount)))}
        </div>
        <button
          onClick={() => onDelete(i.id)}
          className="text-slate-600 hover:text-rose-600 shrink-0"
          title="Ta bort"
        >
          <Trash2 className="w-4 h-4" />
        </button>
      </div>

      {open && (
        <div className="border-t bg-slate-50 p-3 space-y-3">
          {(i.payment_transactions?.length ?? 0) > 0 && (
            <MatchedPaymentsList item={i} />
          )}
          <div className="grid grid-cols-2 gap-3 text-xs">
            <EditField
              label={L.dateLabel}
              value={i.expected_date}
              type="date"
              onChange={(v) => onUpdate(i.id, { expected_date: v })}
            />
            <EditField
              label={L.secondDateField}
              value={i.debit_date ?? i.expected_date}
              type="date"
              onChange={(v) => onUpdate(i.id, { debit_date: v })}
            />
            <div>
              <div className="text-slate-700 mb-0.5">{L.accountLabel}</div>
              <select
                value={i.debit_account_id ?? ""}
                onChange={(e) =>
                  onUpdate(i.id, { debit_account_id: e.target.value ? Number(e.target.value) : null })
                }
                className="border rounded px-2 py-1 w-full"
              >
                <option value="">— välj —</option>
                {accounts
                  .filter((a) => a.type === "checking" || a.type === "shared")
                  .map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.name} ({a.type})
                    </option>
                  ))}
              </select>
            </div>
            {!isIncome ? (
              <div className="flex items-end">
                <label className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={i.autogiro}
                    onChange={(e) => onUpdate(i.id, { autogiro: e.target.checked })}
                  />
                  <span className="text-slate-600">Autogiro (dras automatiskt)</span>
                </label>
              </div>
            ) : (
              <EditField
                label="Mottagare (du)"
                value={i.owner ?? ""}
                onChange={(v) => onUpdate(i.id, { owner: v || null as unknown as UpcomingItem["owner"] })}
              />
            )}
            <EditField
              label="Belopp (kr)"
              value={String(i.amount)}
              type="number"
              onChange={(v) => onUpdate(i.id, { amount: Number(v) as unknown as UpcomingItem["amount"] })}
            />
            <EditField
              label={L.nameLabel}
              value={i.name}
              onChange={(v) => onUpdate(i.id, { name: v })}
            />
            <div>
              <div className="text-xs text-slate-700 mb-1">Kategori</div>
              <select
                value={i.category_id ?? ""}
                onChange={(e) =>
                  onUpdate(i.id, {
                    category_id: e.target.value ? Number(e.target.value) : null,
                  } as Partial<UpcomingItem>)
                }
                className="border rounded px-2 py-1 w-full text-sm"
              >
                <option value="">— ingen kategori —</option>
                {categories.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
              {i.lines.length > 0 && (
                <div className="text-xs text-slate-600 mt-1">
                  Denna faktura har {i.lines.length} split-rader som har egna
                  kategorier. Dessa används före fakturans kategori i rapporter.
                </div>
              )}
            </div>
          </div>

          {hasDetails && (
            <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs border-t pt-2">
              {i.invoice_number && <Detail label="Fakturanummer" value={i.invoice_number} />}
              {i.invoice_date && <Detail label="Fakturadatum" value={i.invoice_date} />}
              {i.ocr_reference && <Detail label="OCR/Referens" value={i.ocr_reference} mono />}
              {i.bankgiro && <Detail label="Bankgiro" value={i.bankgiro} mono />}
              {i.plusgiro && <Detail label="Plusgiro" value={i.plusgiro} mono />}
              {i.iban && <Detail label="IBAN" value={i.iban} mono />}
              {i.notes && (
                <div className="col-span-2">
                  <Detail label="Anteckningar" value={i.notes} />
                </div>
              )}
            </div>
          )}

          <LinesEditor
            upcomingId={i.id}
            totalAmount={i.amount}
            initialLines={i.lines ?? []}
            categories={categories}
            onSave={onSetLines}
          />
        </div>
      )}
    </div>
  );
}

function LinesEditor({
  upcomingId,
  totalAmount,
  initialLines,
  categories,
  onSave,
}: {
  upcomingId: number;
  totalAmount: number;
  initialLines: UpcomingLine[];
  categories: Category[];
  onSave: (id: number, lines: Array<Omit<UpcomingLine, "id">>) => void;
}) {
  const [open, setOpen] = useState(initialLines.length > 0);
  const [draft, setDraft] = useState<Array<Omit<UpcomingLine, "id">>>(
    initialLines.map((l) => ({
      description: l.description,
      amount: l.amount,
      category_id: l.category_id,
      sort_order: l.sort_order,
    })),
  );

  const sum = draft.reduce((acc, l) => acc + (Number(l.amount) || 0), 0);
  const diff = Math.round((totalAmount - sum) * 100) / 100;
  const isValid = Math.abs(diff) <= 1;

  function addRow() {
    setDraft((d) => [
      ...d,
      { description: "", amount: 0, category_id: null, sort_order: d.length },
    ]);
  }

  function removeRow(idx: number) {
    setDraft((d) => d.filter((_, i) => i !== idx));
  }

  function update(idx: number, patch: Partial<Omit<UpcomingLine, "id">>) {
    setDraft((d) => d.map((l, i) => (i === idx ? { ...l, ...patch } : l)));
  }

  return (
    <div className="border-t pt-2">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="text-xs text-slate-600 hover:text-ink inline-flex items-center gap-1"
      >
        {open ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
        Fakturarader ({draft.length})
        {draft.length > 0 && (
          <span className={isValid ? "text-emerald-600" : "text-amber-600"}>
            · summa {formatSEK(sum)}
            {!isValid && ` (diff ${formatSEK(diff)})`}
          </span>
        )}
      </button>
      {open && (
        <div className="mt-2 space-y-1.5">
          {draft.length === 0 && (
            <div className="text-xs text-slate-700">
              Dela upp fakturan per kategori — t.ex. energifaktura i el, vatten
              och bredband. Summan ska stämma med fakturasumman (±1 kr).
            </div>
          )}
          {draft.map((line, idx) => (
            <div key={idx} className="flex gap-1.5 items-center text-xs">
              <input
                type="text"
                placeholder="Beskrivning"
                value={line.description}
                onChange={(e) => update(idx, { description: e.target.value })}
                className="flex-1 border rounded px-2 py-1"
              />
              <input
                type="number"
                placeholder="Belopp"
                value={line.amount || ""}
                onChange={(e) =>
                  update(idx, { amount: Number(e.target.value) })
                }
                className="w-24 border rounded px-2 py-1 text-right"
              />
              <select
                value={line.category_id ?? ""}
                onChange={(e) =>
                  update(idx, {
                    category_id: e.target.value ? Number(e.target.value) : null,
                  })
                }
                className="border rounded px-2 py-1"
              >
                <option value="">Kategori…</option>
                {categories.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
              <button
                type="button"
                onClick={() => removeRow(idx)}
                className="text-rose-500 hover:text-rose-700"
                title="Ta bort rad"
              >
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            </div>
          ))}
          <div className="flex gap-2 items-center">
            <button
              type="button"
              onClick={addRow}
              className="text-xs nav-link"
            >
              + Lägg till rad
            </button>
            <button
              type="button"
              onClick={() => onSave(upcomingId, draft)}
              disabled={draft.length === 0}
              className="text-xs bg-brand-600 text-white px-3 py-1 rounded hover:bg-brand-700 disabled:opacity-50 ml-auto"
            >
              Spara rader
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function EditField({
  label,
  value,
  type = "text",
  onChange,
}: {
  label: string;
  value: string;
  type?: string;
  onChange: (v: string) => void;
}) {
  const [v, setV] = useState(value);
  return (
    <div>
      <div className="text-slate-700 mb-0.5">{label}</div>
      <input
        type={type}
        value={v}
        onChange={(e) => setV(e.target.value)}
        onBlur={() => v !== value && onChange(v)}
        className="border rounded px-2 py-1 w-full"
      />
    </div>
  );
}

function Detail({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div>
      <span className="text-slate-700">{label}: </span>
      <span className={mono ? "font-mono" : ""}>{value}</span>
    </div>
  );
}

function MatchedPaymentsList({ item }: { item: UpcomingItem }) {
  const qc = useQueryClient();
  const unmatchMut = useMutation({
    mutationFn: (txId: number) =>
      api(`/transactions/${txId}/unmatch-upcoming`, { method: "POST" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["upcoming"] });
      qc.invalidateQueries({ queryKey: ["forecast"] });
      qc.invalidateQueries({ queryKey: ["transactions"] });
      qc.invalidateQueries({ queryKey: ["ledger"] });
    },
  });
  const payments = item.payment_transactions ?? [];
  const isOverpaid = item.payment_status === "overpaid";
  return (
    <div className={
      "rounded border p-2 " +
      (isOverpaid
        ? "border-rose-300 bg-rose-50"
        : "border-slate-200 bg-white")
    }>
      <div className="text-xs font-medium text-slate-700 mb-1.5">
        {isOverpaid ? (
          <span className="text-rose-700">
            ⚠ Överbetald — troligen fel-matchning. Ångra nedan för att
            frigöra transaktionen:
          </span>
        ) : (
          <>Matchade betalningar ({payments.length} st)</>
        )}
      </div>
      <div className="space-y-1">
        {payments.map((p) => (
          <div
            key={p.id}
            className="flex items-center gap-2 text-xs bg-white rounded border px-2 py-1"
          >
            <span className="text-slate-700 w-20 shrink-0">{p.date}</span>
            <span
              className={
                "w-24 text-right shrink-0 font-medium " +
                (p.amount < 0 ? "text-rose-600" : "text-emerald-700")
              }
            >
              {formatSEK(p.amount)}
            </span>
            <span className="flex-1 min-w-0 truncate" title={p.description}>
              {p.description}
            </span>
            <span className="text-slate-600 w-32 shrink-0 truncate">
              {p.account_name ?? `#${p.account_id}`}
            </span>
            <button
              onClick={() => {
                if (confirm(
                  `Ångra matchningen av "${p.description}" (${formatSEK(p.amount)}) mot "${item.name}"?\n\nTransaktionen finns kvar — den bara slutar räknas som en betalning av denna faktura/lön.`,
                )) {
                  unmatchMut.mutate(p.id);
                }
              }}
              disabled={unmatchMut.isPending}
              className="text-rose-600 hover:text-rose-800 disabled:opacity-50 shrink-0"
              title="Ångra denna matchning — transaktionen frigörs"
            >
              <Unlink className="w-3.5 h-3.5" />
            </button>
          </div>
        ))}
      </div>
      {unmatchMut.error && (
        <div className="text-xs text-rose-600 mt-1">
          {(unmatchMut.error as Error).message}
        </div>
      )}
    </div>
  );
}

function Stat({
  icon,
  label,
  value,
  hint,
  tone,
}: {
  icon?: React.ReactNode;
  label: string;
  value: string;
  hint?: string;
  tone?: "good" | "bad";
}) {
  const color = tone === "good" ? "text-emerald-600" : tone === "bad" ? "text-rose-600" : "";
  return (
    <div className="bg-white border-[1.5px] border-rule p-3">
      <div className="flex items-center gap-1.5 text-xs uppercase text-slate-700">
        {icon}
        {label}
      </div>
      <div className={`text-xl font-semibold mt-1 ${color}`}>{value}</div>
      {hint && <div className="text-xs text-slate-600 mt-0.5">{hint}</div>}
    </div>
  );
}

interface CCResult {
  upcoming_id: number;
  card_account_name: string;
  transactions_created: number;
  transactions_skipped_duplicates: number;
  transfers_marked: number;
  transfers_paired: number;
  invoice_total: number;
  due_date: string;
  payer_account_id: number | null;
  opening_balance_extracted: number | null;
  closing_balance_extracted: number | null;
  opening_balance_set_on_account?: number | null;
  opening_balance_date?: string | null;
  parser?: string;   // "pdf:amex" | "pdf:seb_kort" | undefined (vision)
}

interface PdfDiagnostic {
  file: File;
  message: string;
  textSample: string;
  textLength: number;
}

function CreditCardInvoiceCard({ onDone }: { onDone: () => void }) {
  const [jobs, setJobs] = useState<
    { file: File; status: "uploading" | "done" | "error"; message?: string }[]
  >([]);
  const [result, setResult] = useState<CCResult | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [pdfDiagnostic, setPdfDiagnostic] = useState<PdfDiagnostic | null>(null);

  async function tryPdfParser(
    file: File,
    force: "amex" | "seb_kort" | null,
  ): Promise<
    | { ok: true; data: CCResult }
    | { ok: false; status: number; detail: unknown }
  > {
    const token = getToken();
    const pdfForm = new FormData();
    pdfForm.append("file", file);
    const url = force
      ? `${apiBase()}/upcoming/parse-credit-card-pdf?force=${force}`
      : `${apiBase()}/upcoming/parse-credit-card-pdf`;
    const res = await fetch(url, {
      method: "POST",
      body: pdfForm,
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (res.ok) return { ok: true, data: (await res.json()) as CCResult };
    let detail: unknown;
    try {
      detail = await res.json();
    } catch {
      detail = await res.text();
    }
    return { ok: false, status: res.status, detail };
  }

  async function visionFallback(files: File[]) {
    const token = getToken();
    const form = new FormData();
    for (const f of files) form.append("files", f);
    try {
      const res = await fetch(
        `${apiBase()}/upcoming/parse-credit-card-invoice`,
        {
          method: "POST",
          body: form,
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        },
      );
      if (!res.ok) {
        const text = await res.text();
        setJobs(files.map((f) => ({ file: f, status: "error", message: text })));
        return;
      }
      const data = (await res.json()) as CCResult;
      setJobs(files.map((f) => ({ file: f, status: "done", message: "vision" })));
      setResult(data);
      onDone();
    } catch (e) {
      setJobs(
        files.map((f) => ({ file: f, status: "error", message: String(e) })),
      );
    }
  }

  async function upload(files: FileList | File[]) {
    const arr = Array.from(files);
    if (arr.length === 0) return;
    setJobs(arr.map((f) => ({ file: f, status: "uploading" })));
    setResult(null);
    setPdfDiagnostic(null);

    // Steg 1: om exakt en PDF, prova deterministisk parser
    if (arr.length === 1 && /\.pdf$/i.test(arr[0].name)) {
      const result = await tryPdfParser(arr[0], null);
      if (result.ok) {
        setJobs([{ file: arr[0], status: "done", message: result.data.parser }]);
        setResult(result.data);
        onDone();
        return;
      }
      if (result.status === 415) {
        // Auto-detektering misslyckades → visa diagnostik + knappar för
        // att tvinga parser eller falla tillbaka på vision
        interface ApiDetail {
          message?: string;
          extracted_text_sample?: string;
          text_length?: number;
        }
        const detail = result.detail as {
          message?: string;
          detail?: ApiDetail;
        };
        // FastAPI wrappar custom detail i { detail: ... }; om strukturen
        // kom platt (ingen wrap), använd det rakt av.
        const info: ApiDetail = detail.detail ?? (detail as ApiDetail);
        setPdfDiagnostic({
          file: arr[0],
          message:
            info.message ??
            detail.message ??
            "PDF-parsern kunde inte avgöra utgivare",
          textSample: info.extracted_text_sample ?? "",
          textLength: info.text_length ?? 0,
        });
        setJobs([
          {
            file: arr[0],
            status: "error",
            message: "okänt PDF-format",
          },
        ]);
        return;
      }
      // Annat fel — visa som generellt fel
      setJobs([
        {
          file: arr[0],
          status: "error",
          message:
            typeof result.detail === "string"
              ? result.detail
              : JSON.stringify(result.detail),
        },
      ]);
      return;
    }

    // Steg 2: vision-fallback för bilder / flera filer
    await visionFallback(arr);
  }

  async function retryWithForce(force: "amex" | "seb_kort") {
    if (!pdfDiagnostic) return;
    setJobs([{ file: pdfDiagnostic.file, status: "uploading" }]);
    const result = await tryPdfParser(pdfDiagnostic.file, force);
    if (result.ok) {
      setJobs([
        { file: pdfDiagnostic.file, status: "done", message: result.data.parser },
      ]);
      setResult(result.data);
      setPdfDiagnostic(null);
      onDone();
    } else {
      setJobs([
        {
          file: pdfDiagnostic.file,
          status: "error",
          message:
            typeof result.detail === "string"
              ? result.detail
              : JSON.stringify(result.detail),
        },
      ]);
    }
  }

  return (
    <Card title="Läs in kreditkortsfaktura (PDF/bild)">
      <div className="text-sm text-slate-700 mb-3">
        Dra in en eller flera Amex- eller SEB Kort-fakturor. Systemet läser BÅDE:
        <ul className="list-disc pl-5 mt-1 space-y-0.5">
          <li>Fakturasumma + förfallodag → hamnar under Kommande fakturor</li>
          <li>Alla enskilda köp → läggs in som transaktioner på kortkontot
            (skapas automatiskt om det inte finns), kategoriseras av regelmotorn</li>
        </ul>
        <div className="mt-2 text-xs text-emerald-700">
          <strong>PDF-fakturor (Amex, SEB Kort):</strong> parse:as deterministiskt
          direkt från textlagret — ingen LLM, snabbt och exakt. Bilder och okända
          PDF-format faller tillbaka på vision AI (Qwen2.5-VL, Pixtral).
        </div>
      </div>

      <div
        onDragOver={(e) => {
          e.preventDefault();
          setIsDragging(true);
        }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setIsDragging(false);
          if (e.dataTransfer.files.length) upload(e.dataTransfer.files);
        }}
        className={`border-2 border-dashed rounded-lg p-8 text-center transition ${
          isDragging ? "border-brand-500 bg-brand-50" : "border-slate-300 bg-slate-50"
        }`}
      >
        <ImageIcon className="w-10 h-10 mx-auto text-slate-600 mb-2" />
        <div className="text-sm text-slate-600">
          Dra kreditkortsfaktura hit, eller{" "}
          <label className="text-brand-600 cursor-pointer underline">
            välj filer
            <input
              type="file"
              multiple
              accept="image/*,.pdf"
              className="hidden"
              onChange={(e) => e.target.files && upload(e.target.files)}
            />
          </label>
        </div>
      </div>

      {jobs.length > 0 && (
        <div className="mt-3 space-y-1">
          {jobs.map((j, i) => (
            <div key={i} className="flex items-center gap-3 p-2 border rounded bg-white text-sm">
              {j.status === "uploading" && <Loader2 className="w-4 h-4 animate-spin text-brand-600" />}
              {j.status === "done" && <Sparkles className="w-4 h-4 text-emerald-600" />}
              {j.status === "error" && <div className="w-4 h-4 rounded-full bg-rose-500" />}
              <div className="flex-1 truncate">{j.file.name}</div>
              {j.status === "done" && j.message && (
                <div className="text-emerald-600 text-xs font-mono">{j.message}</div>
              )}
              {j.status === "error" && j.message && (
                <div className="text-rose-600 text-xs truncate max-w-md">{j.message}</div>
              )}
            </div>
          ))}
        </div>
      )}

      {pdfDiagnostic && (
        <div className="mt-3 p-3 rounded bg-amber-50 border border-amber-200 text-sm">
          <div className="font-semibold text-amber-900 mb-1">
            PDF-parsern kunde inte avgöra utgivare
          </div>
          <div className="text-amber-800 mb-2">
            {pdfDiagnostic.message}
          </div>
          <div className="flex flex-wrap gap-2 mb-3">
            <button
              onClick={() => retryWithForce("amex")}
              className="text-xs bg-brand-600 text-white px-3 py-1.5 rounded hover:bg-brand-700"
            >
              Tvinga Amex-parsern
            </button>
            <button
              onClick={() => retryWithForce("seb_kort")}
              className="text-xs bg-brand-600 text-white px-3 py-1.5 rounded hover:bg-brand-700"
            >
              Tvinga SEB Kort-parsern
            </button>
            <button
              onClick={() => {
                setPdfDiagnostic(null);
                void visionFallback([pdfDiagnostic.file]);
              }}
              className="text-xs bg-slate-200 text-slate-700 px-3 py-1.5 rounded hover:bg-slate-300"
            >
              Kör vision AI istället
            </button>
          </div>
          <details>
            <summary className="text-xs text-amber-700 cursor-pointer">
              Visa extraherad text ({pdfDiagnostic.textLength} tecken)
            </summary>
            <pre className="mt-2 text-xs font-mono bg-white border border-amber-200 rounded p-2 max-h-60 overflow-auto whitespace-pre-wrap">
              {pdfDiagnostic.textSample || "(ingen text extraherad)"}
            </pre>
            <div className="text-xs text-amber-700 mt-1">
              Skicka de första ~800 tecknen ovan till utvecklaren så
              finjusteras regex-mönstren.
            </div>
          </details>
        </div>
      )}

      {result && (
        <div className="mt-3 p-3 rounded bg-emerald-50 border border-emerald-200 text-sm">
          <div className="font-semibold mb-1 flex items-center gap-2">
            {result.card_account_name}
            {result.parser && (
              <span className="text-xs bg-emerald-200 text-emerald-900 px-1.5 py-0.5 rounded font-mono">
                {result.parser}
              </span>
            )}
          </div>
          <div>
            Fakturasumma <strong>{formatSEK(result.invoice_total)}</strong> förfaller{" "}
            <strong>{result.due_date}</strong>
          </div>
          <div>
            <strong>{result.transactions_created}</strong> nya köp lades till
            {result.transactions_skipped_duplicates > 0 &&
              ` (${result.transactions_skipped_duplicates} dubletter hoppades över)`}
            .
          </div>
          {result.transfers_marked > 0 && (
            <div>{result.transfers_marked} autogiro-dragningar markerade som överföring.</div>
          )}
          {result.opening_balance_extracted !== null && (
            <div>
              Ingående saldo {formatSEK(result.opening_balance_extracted)} ·
              Utgående {formatSEK(result.closing_balance_extracted ?? result.invoice_total)}
              {result.opening_balance_set_on_account !== null && (
                <span className="text-emerald-700">
                  {" "}· Kortkontots saldo auto-satt till{" "}
                  {formatSEK(result.opening_balance_set_on_account)}{" "}
                  från {result.opening_balance_date}
                </span>
              )}
            </div>
          )}
        </div>
      )}
    </Card>
  );
}

function MaterializeDropdown({
  item,
  accounts,
}: {
  item: UpcomingItem;
  accounts: Account[];
}) {
  const qc = useQueryClient();
  const [pick, setPick] = useState<string>("");
  const mut = useMutation({
    mutationFn: (accountId: number) =>
      api(`/upcoming/${item.id}/materialize-to-account`, {
        method: "POST",
        body: JSON.stringify({ account_id: accountId }),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["upcoming"] });
      qc.invalidateQueries({ queryKey: ["transactions"] });
      qc.invalidateQueries({ queryKey: ["balances"] });
      qc.invalidateQueries({ queryKey: ["ytd-income"] });
      qc.invalidateQueries({ queryKey: ["ledger"] });
    },
  });

  // Sortera: ägar-matchade konton först, inkognito och valt-owner högst
  const sorted = [...accounts].sort((a, b) => {
    const ownerMatch = (acc: Account) =>
      item.owner && acc.incognito ? -2 : acc.incognito ? -1 : 0;
    return ownerMatch(a) - ownerMatch(b);
  });

  return (
    <span className="inline-flex items-center gap-1">
      <span className="text-slate-400">·</span>
      <select
        value={pick}
        onChange={(e) => {
          const v = Number(e.target.value);
          if (v) mut.mutate(v);
          setPick("");
        }}
        disabled={mut.isPending}
        className="text-xs border rounded px-1 py-0.5 bg-white"
        title="Skapa motsvarande transaktion på valt konto (t.ex. hennes inkognito-konto) och koppla ihop"
      >
        <option value="">
          {mut.isPending ? "Kopplar…" : "Koppla till konto…"}
        </option>
        {sorted.map((a) => (
          <option key={a.id} value={a.id}>
            {a.name} {a.incognito ? "(inkognito)" : ""}
          </option>
        ))}
      </select>
    </span>
  );
}

interface BankTxCandidate {
  transaction_id: number;
  date: string;
  amount: number;
  description: string;
  account_id: number;
  account_name: string | null;
  is_transfer: boolean;
  amount_diff: number;
  date_diff_days: number;
  exact_match: boolean;
}

function FindBankTxButton({ item }: { item: UpcomingItem }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <span className="text-slate-400">·</span>
      <button
        onClick={() => setOpen(true)}
        className="nav-link text-xs"
        title="Leta efter en befintlig bankrad och koppla (stödjer delbetalningar)"
      >
        hitta bankrad
      </button>
      {open && (
        <FindBankTxModal item={item} onClose={() => setOpen(false)} />
      )}
    </>
  );
}

function FindBankTxModal({
  item,
  onClose,
}: {
  item: UpcomingItem;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const [selected, setSelected] = useState<Set<number>>(new Set());
  // Default: upcoming.amount så ALLA delbetalningar syns (en del på 445 kr
  // av en 13 445 kr faktura har Δ=13 000 kr, vilket är inom full
  // upcoming-beloppet). Användaren kan strama åt om listan blir för lång.
  const [amtTol, setAmtTol] = useState(Math.ceil(Number(item.amount)));
  const [dateTol, setDateTol] = useState(14);

  const candsQ = useQuery({
    queryKey: ["find-bank-tx", item.id, amtTol, dateTol],
    queryFn: () =>
      api<{
        upcoming_name: string;
        expected_tx_amount: number;
        target_date: string;
        candidates: BankTxCandidate[];
      }>(
        `/upcoming/${item.id}/find-bank-tx?amount_tolerance=${amtTol}&date_tolerance_days=${dateTol}`,
      ),
  });

  const matchMut = useMutation({
    mutationFn: async (txIds: number[]) => {
      // Sekventiellt så vi inte skapar race conditions
      for (const id of txIds) {
        await api(`/transactions/${id}/match-upcoming`, {
          method: "POST",
          body: JSON.stringify({ upcoming_id: item.id }),
        });
      }
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["upcoming"] });
      qc.invalidateQueries({ queryKey: ["transactions"] });
      qc.invalidateQueries({ queryKey: ["ledger"] });
      qc.invalidateQueries({ queryKey: ["budget"] });
      onClose();
    },
  });

  const cands = candsQ.data?.candidates ?? [];
  const selectedAmount = cands
    .filter((c) => selected.has(c.transaction_id))
    .reduce((s, c) => s + c.amount, 0);
  const expectedAmount = candsQ.data?.expected_tx_amount ?? 0;
  const selectionDiff = Math.abs(selectedAmount - expectedAmount);

  return (
    <div
      className="fixed inset-0 z-40 bg-slate-900/50 flex items-start justify-center p-4 overflow-y-auto"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-lg shadow-xl w-full max-w-3xl mt-10"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between p-4 border-b">
          <div>
            <h2 className="text-lg font-semibold">Hitta bankrad att koppla</h2>
            <div className="text-sm text-slate-700 mt-1">
              <strong>{item.name}</strong> · {formatSEK(item.amount)} ·
              förfall {item.expected_date}
            </div>
            <div className="text-xs text-slate-600 mt-0.5">
              Välj EN rad om fakturan betalats i ett svep, eller FLERA för
              delbetalningar som summerar till{" "}
              <strong>{formatSEK(expectedAmount)}</strong>.
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1 text-slate-600 hover:text-slate-900"
          >
            <span className="text-lg">×</span>
          </button>
        </div>

        <div className="p-4 space-y-3">
          <div className="flex gap-3 text-xs items-center">
            <label>
              Beloppstolerans ±
              <input
                type="number"
                value={amtTol}
                onChange={(e) => setAmtTol(Number(e.target.value))}
                className="border rounded px-1 py-0.5 w-16 ml-1"
              />{" "}
              kr
            </label>
            <label>
              Datumtolerans ±
              <input
                type="number"
                value={dateTol}
                onChange={(e) => setDateTol(Number(e.target.value))}
                className="border rounded px-1 py-0.5 w-16 ml-1"
              />{" "}
              dagar
            </label>
            <div className="ml-auto text-xs">
              {cands.length} kandidater hittade
            </div>
          </div>

          {candsQ.isLoading ? (
            <div className="text-sm text-slate-700">Söker…</div>
          ) : cands.length === 0 ? (
            <div className="text-sm text-slate-700 py-4 text-center">
              Inga kandidater — prova öka toleransen.
            </div>
          ) : (
            <div className="space-y-1 max-h-96 overflow-y-auto">
              {cands.map((c) => {
                const isSel = selected.has(c.transaction_id);
                return (
                  <label
                    key={c.transaction_id}
                    className={`flex items-center gap-2 border rounded p-2 text-sm cursor-pointer hover:bg-slate-50 ${
                      isSel ? "bg-brand-50 border-brand-300" : ""
                    } ${c.exact_match ? "ring-1 ring-emerald-300" : ""}`}
                  >
                    <input
                      type="checkbox"
                      checked={isSel}
                      onChange={(e) => {
                        setSelected((prev) => {
                          const next = new Set(prev);
                          if (e.target.checked) next.add(c.transaction_id);
                          else next.delete(c.transaction_id);
                          return next;
                        });
                      }}
                    />
                    <div className="flex-1 min-w-0">
                      <div className="font-medium truncate">
                        {c.description}
                      </div>
                      <div className="text-xs text-slate-700 flex flex-wrap gap-x-2">
                        <span>{c.date}</span>
                        <span>· {c.account_name ?? `#${c.account_id}`}</span>
                        <span>
                          · Δ{" "}
                          <span
                            className={
                              c.amount_diff < 1
                                ? "text-emerald-700"
                                : c.amount_diff < 10
                                ? ""
                                : "text-amber-700"
                            }
                          >
                            {c.amount_diff.toFixed(0)} kr
                          </span>
                        </span>
                        <span>· {c.date_diff_days}d från förfallodag</span>
                        {c.is_transfer && (
                          <span className="text-blue-600">· överföring</span>
                        )}
                        {c.exact_match && (
                          <span className="text-emerald-600 font-medium">
                            · exakt
                          </span>
                        )}
                      </div>
                    </div>
                    <div
                      className={`font-semibold shrink-0 ${
                        c.amount < 0 ? "text-rose-600" : "text-emerald-600"
                      }`}
                    >
                      {formatSEK(c.amount)}
                    </div>
                  </label>
                );
              })}
            </div>
          )}

          {selected.size > 0 && (
            <div className="bg-brand-50 border border-brand-200 rounded p-3 text-sm">
              <div>
                Valt:{" "}
                <strong>{selected.size} rad(er)</strong> · summa{" "}
                <strong>{formatSEK(selectedAmount)}</strong>
                {" · "}
                förväntat{" "}
                <strong>{formatSEK(expectedAmount)}</strong>
                {selectionDiff < 2 ? (
                  <span className="text-emerald-700 ml-2">✓ matchar</span>
                ) : (
                  <span className="text-amber-700 ml-2">
                    Δ {formatSEK(selectionDiff)}
                  </span>
                )}
              </div>
            </div>
          )}

          <div className="flex justify-end gap-2">
            <button
              onClick={onClose}
              className="text-sm text-slate-700 hover:text-slate-900 px-3 py-1.5"
            >
              Avbryt
            </button>
            <button
              onClick={() => matchMut.mutate(Array.from(selected))}
              disabled={selected.size === 0 || matchMut.isPending}
              className="bg-brand-600 text-white text-sm px-4 py-1.5 rounded disabled:opacity-50"
            >
              {matchMut.isPending
                ? "Kopplar…"
                : selected.size === 1
                ? "Matcha mot vald rad"
                : `Matcha mot ${selected.size} rader`}
            </button>
          </div>
          {matchMut.isError && (
            <div className="text-xs text-rose-600">
              {(matchMut.error as Error).message}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function SalaryCycleSetting({ month: _ }: { month: string }) {
  const qc = useQueryClient();
  const settingQ = useQuery({
    queryKey: ["setting", "salary_cycle_start_day"],
    queryFn: async () => {
      try {
        const r = await api<{ value: number | null }>(
          "/settings/salary_cycle_start_day",
        );
        return r.value ?? 1;
      } catch {
        return 1;
      }
    },
  });
  const setMut = useMutation({
    mutationFn: (value: number) =>
      api(`/settings/salary_cycle_start_day`, {
        method: "PUT",
        body: JSON.stringify({ value }),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["setting", "salary_cycle_start_day"] });
      qc.invalidateQueries({ queryKey: ["forecast"] });
    },
  });

  const cycleDay = settingQ.data ?? 1;
  return (
    <div className="border rounded-lg bg-indigo-50/40 p-3 text-sm flex items-center gap-3">
      <div className="flex-1">
        <div className="font-medium text-slate-800">
          Lönecykel för budget
          {cycleDay > 1 && (
            <span className="ml-2 text-xs bg-indigo-100 text-indigo-800 px-2 py-0.5 rounded">
              Aktiv: dag {cycleDay}
            </span>
          )}
        </div>
        <div className="text-xs text-slate-700 mt-0.5">
          {cycleDay === 1 ? (
            <>
              Just nu räknar prognosen på kalendermånader (1:a till 30:e).
              Om din lön kommer en annan dag (t.ex. 25:e) och fakturor i
              början av nästa månad täcks av föregående månads lön — sätt
              lönecykel-dagen så flyttar prognosen gränsen.
            </>
          ) : (
            <>
              Budget-månaden går från dag {cycleDay} till dag {cycleDay} i
              nästa månad. Fakturor i början av nästa kalendermånad
              räknas till föregående månads budget eftersom de täcks av
              lönen som kommer den {cycleDay}:e.
            </>
          )}
        </div>
      </div>
      <label className="flex items-center gap-1.5 text-xs">
        Lön kommer dag
        <input
          type="number"
          min={1}
          max={28}
          value={cycleDay}
          onChange={(e) => {
            const v = Math.max(1, Math.min(28, Number(e.target.value) || 1));
            setMut.mutate(v);
          }}
          className="border rounded px-2 py-1 w-16 text-right"
          disabled={setMut.isPending}
        />
      </label>
    </div>
  );
}
