import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import {
  CalendarPlus, Image as ImageIcon, Loader2, Sparkles, Trash2,
  TrendingDown, TrendingUp, Users,
} from "lucide-react";
import { api, formatSEK, getToken } from "@/api/client";
import { Card } from "@/components/Card";

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
  matched_transaction_id: number | null;
}

interface Forecast {
  month: string;
  upcoming_incomes: Array<{ id: number; name: string; amount: number; expected_date: string; owner: string | null }>;
  upcoming_bills: Array<{ id: number; name: string; amount: number; expected_date: string }>;
  totals: {
    expected_income: number;
    upcoming_bills: number;
    avg_fixed_expenses: number;
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
  const forecastQ = useQuery({
    queryKey: ["upcoming-forecast", month],
    queryFn: () => api<Forecast>(`/upcoming/forecast?month=${month}&split_ratio=0.5`),
  });

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["upcoming"] });
    qc.invalidateQueries({ queryKey: ["upcoming-forecast"] });
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
  const bills = items.filter((i) => i.kind === "bill");
  const incomes = items.filter((i) => i.kind === "income");

  return (
    <div className="p-6 space-y-5 max-w-5xl">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold flex items-center gap-2">
            <CalendarPlus className="w-6 h-6" />
            Kommande
          </h1>
          <div className="text-sm text-slate-500 mt-0.5">
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

      {forecastQ.data && (
        <Card title={`Månadsprognos — ${month}`}>
          <div className="grid grid-cols-4 gap-3">
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
            <Stat
              icon={<TrendingDown className="w-4 h-4 text-rose-600" />}
              label="Snitt fasta kostnader"
              value={formatSEK(forecastQ.data.totals.avg_fixed_expenses)}
              hint="Genomsnitt senaste 3 mån (exkl. transfers)"
            />
            <Stat
              icon={<Users className="w-4 h-4 text-brand-600" />}
              label="Kvar att dela"
              value={formatSEK(forecastQ.data.totals.available_to_split)}
              tone={forecastQ.data.totals.available_to_split >= 0 ? "good" : "bad"}
            />
          </div>
          <div className="mt-4 p-3 bg-brand-50 border border-brand-100 rounded text-sm">
            <strong>50/50-fördelning:</strong>{" "}
            <span className="font-semibold">
              {formatSEK(forecastQ.data.split.per_person_share)}
            </span>{" "}
            till var och en som privata pengar efter fasta kostnader och kommande fakturor.
            {Object.keys(forecastQ.data.income_by_owner).length > 0 && (
              <div className="text-xs text-slate-500 mt-1">
                Inkomst per person:{" "}
                {Object.entries(forecastQ.data.income_by_owner)
                  .map(([k, v]) => `${k} ${formatSEK(v)}`)
                  .join(" · ")}
              </div>
            )}
          </div>
        </Card>
      )}

      <Card title="Tolka fakturor automatiskt">
        <div className="text-sm text-slate-500 mb-3">
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
          <ImageIcon className="w-10 h-10 mx-auto text-slate-400 mb-2" />
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
              className="text-xs text-slate-500 hover:underline"
            >
              Rensa lista
            </button>
          </div>
        )}
      </Card>

      <Card title="Snabbinmatning via text">
        <div className="text-sm text-slate-500 mb-2">
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

      <div className="grid grid-cols-2 gap-4">
        <Card title={`Kommande fakturor (${bills.length})`}>
          <ItemList items={bills} onDelete={(id) => deleteMut.mutate(id)} />
        </Card>
        <Card title={`Kommande löner (${incomes.length})`}>
          <ItemList items={incomes} onDelete={(id) => deleteMut.mutate(id)} />
        </Card>
      </div>
    </div>
  );
}

function ItemList({
  items,
  onDelete,
}: {
  items: UpcomingItem[];
  onDelete: (id: number) => void;
}) {
  if (items.length === 0) {
    return <div className="text-sm text-slate-500">Inget registrerat ännu.</div>;
  }
  return (
    <div className="space-y-1">
      {items.map((i) => (
        <div key={i.id} className="flex items-center gap-3 border rounded p-2 text-sm">
          <div className="flex-1 min-w-0">
            <div className="font-medium truncate">{i.name}</div>
            <div className="text-xs text-slate-500">
              {i.expected_date}
              {i.owner ? ` · ${i.owner}` : ""}
              {i.recurring_monthly ? " · återkommande" : ""}
              {i.source !== "manual" ? ` · källa: ${i.source}` : ""}
              {i.matched_transaction_id ? " · ✓ bokförd" : ""}
            </div>
          </div>
          <div className="font-semibold shrink-0">{formatSEK(i.amount)}</div>
          <button
            onClick={() => onDelete(i.id)}
            className="text-slate-400 hover:text-rose-600 shrink-0"
          >
            <Trash2 className="w-4 h-4" />
          </button>
        </div>
      ))}
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
    <div className="bg-white border border-slate-200 rounded-xl p-3">
      <div className="flex items-center gap-1.5 text-xs uppercase text-slate-500">
        {icon}
        {label}
      </div>
      <div className={`text-xl font-semibold mt-1 ${color}`}>{value}</div>
      {hint && <div className="text-xs text-slate-400 mt-0.5">{hint}</div>}
    </div>
  );
}
