import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import {
  CalendarPlus, ChevronDown, ChevronRight, Image as ImageIcon,
  Loader2, Sparkles, Trash2,
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
  const bills = items.filter((i) => i.kind === "bill");
  const incomes = items.filter((i) => i.kind === "income");

  return (
    <div className="p-3 md:p-6 space-y-4 md:space-y-5 max-w-5xl">
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
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
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

      <CreditCardInvoiceCard onDone={invalidate} />

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

      <Card title={`Kommande fakturor (${bills.length})`}>
        <ItemList
          items={bills}
          accounts={accountsQ.data ?? []}
          categories={categoriesQ.data ?? []}
          onDelete={(id) => deleteMut.mutate(id)}
          onUpdate={(id, data) => updateMut.mutate({ id, data })}
          onSetLines={(id, lines) => setLinesMut.mutate({ id, lines })}
        />
      </Card>
      <Card title={`Kommande löner (${incomes.length})`}>
        <ItemList
          items={incomes}
          accounts={accountsQ.data ?? []}
          categories={categoriesQ.data ?? []}
          onDelete={(id) => deleteMut.mutate(id)}
          onUpdate={(id, data) => updateMut.mutate({ id, data })}
          onSetLines={(id, lines) => setLinesMut.mutate({ id, lines })}
        />
      </Card>
    </div>
  );
}

function ItemList({
  items,
  accounts,
  categories,
  onDelete,
  onUpdate,
  onSetLines,
}: {
  items: UpcomingItem[];
  accounts: Account[];
  categories: Category[];
  onDelete: (id: number) => void;
  onUpdate: (id: number, data: Partial<UpcomingItem>) => void;
  onSetLines: (id: number, lines: Array<Omit<UpcomingLine, "id">>) => void;
}) {
  if (items.length === 0) {
    return <div className="text-sm text-slate-500">Inget registrerat ännu.</div>;
  }
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
  const [open, setOpen] = useState(false);
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
          className="text-slate-400 hover:text-slate-700"
        >
          {open ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
        </button>
        <div className="flex-1 min-w-0">
          <div className="font-medium truncate">{i.name}</div>
          <div className="text-xs text-slate-500 flex flex-wrap gap-x-2">
            <span>{L.summaryDate} {i.expected_date}</span>
            {i.debit_date && i.debit_date !== i.expected_date && (
              <span>· {L.secondDateLabel} {i.debit_date}</span>
            )}
            {debitAccount && <span>· {L.summaryAccount} {debitAccount.name}</span>}
            {!isIncome && i.autogiro && <span className="text-amber-700">· autogiro</span>}
            {i.owner && <span>· {i.owner}</span>}
            {i.recurring_monthly && <span>· återkommande</span>}
            {i.source !== "manual" && <span>· {i.source}</span>}
            {i.matched_transaction_id && <span className="text-emerald-600">· ✓ bokförd</span>}
          </div>
        </div>
        <div
          className={`font-semibold shrink-0 ${
            isIncome ? "text-emerald-600" : ""
          }`}
        >
          {isIncome ? "+" : ""}{formatSEK(i.amount)}
        </div>
        <button
          onClick={() => onDelete(i.id)}
          className="text-slate-400 hover:text-rose-600 shrink-0"
          title="Ta bort"
        >
          <Trash2 className="w-4 h-4" />
        </button>
      </div>

      {open && (
        <div className="border-t bg-slate-50 p-3 space-y-3">
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
              <div className="text-slate-500 mb-0.5">{L.accountLabel}</div>
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
        className="text-xs text-slate-600 hover:text-brand-700 inline-flex items-center gap-1"
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
            <div className="text-xs text-slate-500">
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
              className="text-xs text-brand-600 hover:text-brand-700"
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
      <div className="text-slate-500 mb-0.5">{label}</div>
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
      <span className="text-slate-500">{label}: </span>
      <span className={mono ? "font-mono" : ""}>{value}</span>
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
  opening_balance_set_on_account: number | null;
  opening_balance_date: string | null;
}

function CreditCardInvoiceCard({ onDone }: { onDone: () => void }) {
  const [jobs, setJobs] = useState<
    { file: File; status: "uploading" | "done" | "error"; message?: string }[]
  >([]);
  const [result, setResult] = useState<CCResult | null>(null);
  const [isDragging, setIsDragging] = useState(false);

  async function upload(files: FileList | File[]) {
    const arr = Array.from(files);
    if (arr.length === 0) return;
    setJobs(arr.map((f) => ({ file: f, status: "uploading" })));
    setResult(null);

    const form = new FormData();
    for (const f of arr) form.append("files", f);
    const token = getToken();
    try {
      const res = await fetch(`${apiBase()}/upcoming/parse-credit-card-invoice`, {
        method: "POST",
        body: form,
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) {
        const text = await res.text();
        setJobs(arr.map((f) => ({ file: f, status: "error", message: text })));
        return;
      }
      const data = (await res.json()) as CCResult;
      setJobs(arr.map((f) => ({ file: f, status: "done" })));
      setResult(data);
      onDone();
    } catch (e) {
      setJobs(arr.map((f) => ({ file: f, status: "error", message: String(e) })));
    }
  }

  return (
    <Card title="Läs in kreditkortsfaktura (PDF/bild)">
      <div className="text-sm text-slate-500 mb-3">
        Dra in en eller flera Amex- eller SEB Kort-fakturor. AI läser BÅDE:
        <ul className="list-disc pl-5 mt-1 space-y-0.5">
          <li>Fakturasumma + förfallodag → hamnar under Kommande fakturor</li>
          <li>Alla enskilda köp → läggs in som transaktioner på kortkontot
            (skapas automatiskt om det inte finns), kategoriseras av AI:n</li>
        </ul>
        <div className="mt-2 text-amber-700 text-xs">
          Dubbelbokföring undviks: autogiro-dragningen från gemensamt markeras
          som överföring, köpen blir de riktiga utgifterna. Krav: vision-kapabel
          modell i LM Studio (Qwen2.5-VL, Pixtral).
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
        <ImageIcon className="w-10 h-10 mx-auto text-slate-400 mb-2" />
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
              {j.status === "error" && j.message && (
                <div className="text-rose-600 text-xs truncate max-w-md">{j.message}</div>
              )}
            </div>
          ))}
        </div>
      )}

      {result && (
        <div className="mt-3 p-3 rounded bg-emerald-50 border border-emerald-200 text-sm">
          <div className="font-semibold mb-1">{result.card_account_name}</div>
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
