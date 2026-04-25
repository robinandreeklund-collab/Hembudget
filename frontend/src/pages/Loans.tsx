import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import {
  CalendarClock, CheckCircle2, ChevronDown, ChevronRight,
  Home, Image as ImageIcon, Loader2,
  Pencil, Sparkles, Trash2, Plus, X,
} from "lucide-react";
import { api, formatSEK, getToken } from "@/api/client";
import { Card } from "@/components/Card";

function apiBase(): string {
  let explicit = (import.meta as ImportMeta).env.VITE_API_BASE;
  if (explicit) {
    if (!/^https?:\/\//i.test(explicit)) explicit = `https://${explicit}`;
    return explicit.replace(/\/$/, "");
  }
  const port = localStorage.getItem("hembudget_api_port") || "8765";
  return `http://127.0.0.1:${port}`;
}

interface ScheduleEntry {
  id: number;
  loan_id: number;
  due_date: string;
  amount: number;
  payment_type: "interest" | "amortization";
  matched_transaction_id: number | null;
  notes: string | null;
}

interface LoanSummary {
  id: number;
  name: string;
  lender: string;
  principal_amount: number;
  outstanding_balance: number;
  amortization_paid: number;
  interest_paid: number;
  interest_paid_year: number;
  interest_year: number;
  interest_rate: number;
  binding_type: string;
  binding_end_date: string | null;
  ltv: number | null;
  payments_count: number;
}

interface Loan {
  id: number;
  name: string;
  lender: string;
  loan_number: string | null;
  principal_amount: number;
  current_balance_at_creation: number | null;
  start_date: string;
  interest_rate: number;
  binding_type: string;
  binding_end_date: string | null;
  amortization_monthly: number | null;
  property_value: number | null;
  match_pattern: string | null;
  notes: string | null;
  active: boolean;
  category_id: number | null;
}

interface LoanIn {
  name: string;
  lender: string;
  loan_number?: string | null;
  principal_amount: number;
  current_balance_at_creation?: number | null;
  start_date: string;
  interest_rate: number;
  binding_type: string;
  binding_end_date?: string | null;
  amortization_monthly?: number | null;
  property_value?: number | null;
  match_pattern?: string | null;
  notes?: string | null;
  category_id?: number | null;
}

export default function Loans() {
  const qc = useQueryClient();
  const [mode, setMode] = useState<
    | { kind: "idle" }
    | { kind: "create" }
    | { kind: "edit"; loan: Loan }
    | { kind: "upload" }
  >({ kind: "idle" });
  const [uploadJobs, setUploadJobs] = useState<
    { file: File; status: "uploading" | "done" | "error"; message?: string }[]
  >([]);
  const [expandedLoans, setExpandedLoans] = useState<Set<number>>(new Set());
  const toggleExpanded = (id: number) =>
    setExpandedLoans((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const summariesQ = useQuery({
    queryKey: ["loan-summaries"],
    queryFn: () => api<LoanSummary[]>("/loans/summaries/all"),
  });
  const loansQ = useQuery({
    queryKey: ["loans"],
    queryFn: () => api<Loan[]>("/loans/"),
  });
  const categoriesQ = useQuery({
    queryKey: ["categories"],
    queryFn: () =>
      api<Array<{ id: number; name: string }>>("/categories"),
  });

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["loan-summaries"] });
    qc.invalidateQueries({ queryKey: ["loans"] });
    qc.invalidateQueries({ queryKey: ["transactions"] });
  };

  const createMut = useMutation({
    mutationFn: (p: LoanIn) =>
      api<LoanSummary>("/loans/", { method: "POST", body: JSON.stringify(p) }),
    onSuccess: () => {
      invalidate();
      setMode({ kind: "idle" });
    },
  });
  const updateMut = useMutation({
    mutationFn: (p: { id: number; data: Partial<LoanIn> }) =>
      api<LoanSummary>(`/loans/${p.id}`, { method: "PATCH", body: JSON.stringify(p.data) }),
    onSuccess: () => {
      invalidate();
      setMode({ kind: "idle" });
    },
  });
  const deleteMut = useMutation({
    mutationFn: (id: number) => api(`/loans/${id}`, { method: "DELETE" }),
    onSuccess: invalidate,
  });
  const rescanMut = useMutation({
    mutationFn: () =>
      api<{ linked: number; unclassified: number }>("/loans/rescan", { method: "POST" }),
    onSuccess: invalidate,
  });

  const summaries = summariesQ.data ?? [];
  const loans = loansQ.data ?? [];
  const totalDebt = summaries.reduce((s, l) => s + Number(l.outstanding_balance), 0);
  const totalInterest = summaries.reduce((s, l) => s + Number(l.interest_paid), 0);
  const totalInterestYtd = summaries.reduce((s, l) => s + Number(l.interest_paid_year ?? 0), 0);
  const interestYear = summaries[0]?.interest_year ?? new Date().getFullYear();
  const totalAmortized = summaries.reduce((s, l) => s + Number(l.amortization_paid), 0);

  return (
    <div className="p-3 md:p-6 space-y-4 md:space-y-5 max-w-5xl">
      <div className="flex items-center justify-between">
        <h1 className="serif text-3xl leading-tight">
          <Home className="w-6 h-6" />
          Lån
        </h1>
        <div className="flex gap-2">
          <button
            onClick={() => rescanMut.mutate()}
            disabled={rescanMut.isPending}
            className="px-3 py-1.5 text-sm rounded-lg border border-slate-300 bg-white"
          >
            {rescanMut.isPending ? "Scannar…" : "Scanna om alla betalningar"}
          </button>
          <button
            onClick={() => setMode(mode.kind === "upload" ? { kind: "idle" } : { kind: "upload" })}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-lg bg-emerald-600 text-white"
          >
            <ImageIcon className="w-4 h-4" />
            Skapa från bilder
          </button>
          <button
            onClick={() => setMode(mode.kind === "create" ? { kind: "idle" } : { kind: "create" })}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-lg bg-brand-600 text-white"
          >
            <Plus className="w-4 h-4" />
            Nytt lån
          </button>
        </div>
      </div>

      {mode.kind === "upload" && (
        <LoanFromImagesUploader
          jobs={uploadJobs}
          setJobs={setUploadJobs}
          onDone={() => {
            qc.invalidateQueries({ queryKey: ["loans"] });
            qc.invalidateQueries({ queryKey: ["loan-summaries"] });
            qc.invalidateQueries({ queryKey: ["transactions"] });
          }}
          onClose={() => {
            setMode({ kind: "idle" });
            setUploadJobs([]);
          }}
        />
      )}

      {rescanMut.data && (
        <div className="text-sm text-slate-600">
          {rescanMut.data.linked} betalningar länkade.
          {rescanMut.data.unclassified > 0 &&
            ` ${rescanMut.data.unclassified} matchade lån men kunde inte klassificeras som ränta/amortering.`}
        </div>
      )}

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card>
          <div className="text-xs uppercase text-slate-700">Total skuld</div>
          <div className="text-2xl font-semibold text-rose-600">{formatSEK(totalDebt)}</div>
        </Card>
        <Card>
          <div className="text-xs uppercase text-slate-700">
            Betald ränta i år
          </div>
          <div className="text-2xl font-semibold">{formatSEK(totalInterestYtd)}</div>
          <div className="text-xs text-slate-600 mt-1">{interestYear}</div>
        </Card>
        <Card>
          <div className="text-xs uppercase text-slate-700">Betald ränta (total)</div>
          <div className="text-2xl font-semibold">{formatSEK(totalInterest)}</div>
        </Card>
        <Card>
          <div className="text-xs uppercase text-slate-700">Amorterat</div>
          <div className="text-2xl font-semibold text-emerald-600">{formatSEK(totalAmortized)}</div>
        </Card>
      </div>

      {mode.kind === "create" && (
        <LoanForm
          title="Nytt lån"
          categories={categoriesQ.data ?? []}
          onSubmit={(data) => createMut.mutate(data)}
          onCancel={() => setMode({ kind: "idle" })}
          busy={createMut.isPending}
          error={createMut.error as Error | null}
        />
      )}
      {mode.kind === "edit" && (
        <LoanForm
          title={`Redigera "${mode.loan.name}"`}
          categories={categoriesQ.data ?? []}
          initial={{
            name: mode.loan.name,
            lender: mode.loan.lender,
            loan_number: mode.loan.loan_number,
            principal_amount: mode.loan.principal_amount,
            current_balance_at_creation: mode.loan.current_balance_at_creation,
            start_date: mode.loan.start_date,
            interest_rate: mode.loan.interest_rate,
            binding_type: mode.loan.binding_type,
            binding_end_date: mode.loan.binding_end_date,
            amortization_monthly: mode.loan.amortization_monthly,
            property_value: mode.loan.property_value,
            match_pattern: mode.loan.match_pattern,
            notes: mode.loan.notes,
            category_id: mode.loan.category_id,
          }}
          submitLabel="Spara ändringar"
          onSubmit={(data) => updateMut.mutate({ id: mode.loan.id, data })}
          onCancel={() => setMode({ kind: "idle" })}
          busy={updateMut.isPending}
          error={updateMut.error as Error | null}
        />
      )}

      <Card title="Registrerade lån">
        {summaries.length === 0 ? (
          <div className="text-sm text-slate-700">
            Inga lån registrerade. Lägg till ett så kopplar systemet dina
            betalningar automatiskt och räknar ned skulden per amortering.
          </div>
        ) : (
          <div className="space-y-3">
            {summaries.map((s) => {
              const full = loans.find((l) => l.id === s.id);
              const expanded = expandedLoans.has(s.id);
              return (
                <div key={s.id} className="border rounded-lg">
                  {/* Alltid synlig kompakt header — klick för att expandera */}
                  <button
                    onClick={() => toggleExpanded(s.id)}
                    className="w-full flex items-center gap-3 p-3 hover:bg-slate-50 text-left"
                  >
                    {expanded ? (
                      <ChevronDown className="w-4 h-4 text-slate-600 shrink-0" />
                    ) : (
                      <ChevronRight className="w-4 h-4 text-slate-600 shrink-0" />
                    )}
                    <div className="flex-1 min-w-0">
                      <div className="font-semibold truncate">{s.name}</div>
                      <div className="text-xs text-slate-700 truncate">
                        {s.lender} · {(s.interest_rate * 100).toFixed(2)} % · {s.payments_count} betalningar
                      </div>
                    </div>
                    <div className="hidden md:flex gap-6 text-sm shrink-0">
                      <div className="text-right">
                        <div className="text-xs text-slate-600">Kvar</div>
                        <div className="font-semibold">{formatSEK(s.outstanding_balance)}</div>
                      </div>
                      <div className="text-right">
                        <div className="text-xs text-slate-600">Ränta {s.interest_year ?? ""}</div>
                        <div>{formatSEK(s.interest_paid_year ?? 0)}</div>
                      </div>
                    </div>
                    <div className="md:hidden text-right shrink-0">
                      <div className="font-semibold">{formatSEK(s.outstanding_balance)}</div>
                      <div className="text-xs text-slate-700">kvar</div>
                    </div>
                  </button>

                  {expanded && (
                    <div className="border-t px-4 pt-3 pb-4">
                      <div className="flex justify-between items-start">
                        <div className="text-xs text-slate-700">
                          {s.binding_type}
                          {full?.match_pattern ? ` · matchar "${full.match_pattern}"` : ""}
                          {s.ltv !== null && ` · LTV ${(s.ltv * 100).toFixed(1)} %`}
                          {s.binding_end_date && ` · bindning slut ${s.binding_end_date}`}
                        </div>
                        <div className="flex gap-1">
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              if (full) setMode({ kind: "edit", loan: full });
                            }}
                            disabled={!full}
                            className="p-1.5 text-slate-600 hover:text-brand-600 disabled:opacity-40"
                            title="Redigera"
                          >
                            <Pencil className="w-4 h-4" />
                          </button>
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              if (confirm(`Ta bort lånet '${s.name}'?`)) deleteMut.mutate(s.id);
                            }}
                            className="p-1.5 text-slate-600 hover:text-rose-600"
                            title="Ta bort"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        </div>
                      </div>
                      <div className="grid grid-cols-2 md:grid-cols-5 gap-3 md:gap-4 mt-3 text-sm">
                        <Stat label="Ursprung" value={formatSEK(s.principal_amount)} />
                        <Stat label="Kvarvarande" value={formatSEK(s.outstanding_balance)} strong />
                        <Stat label="Amorterat" value={formatSEK(s.amortization_paid)} />
                        <Stat
                          label={`Ränta ${s.interest_year ?? ""}`}
                          value={formatSEK(s.interest_paid_year ?? 0)}
                        />
                        <Stat label="Ränta (total)" value={formatSEK(s.interest_paid)} />
                      </div>
                      <LoanSchedule loanId={s.id} />
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </Card>
    </div>
  );
}

function Stat({ label, value, strong }: { label: string; value: string; strong?: boolean }) {
  return (
    <div>
      <div className="text-xs text-slate-700">{label}</div>
      <div className={strong ? "font-semibold" : ""}>{value}</div>
    </div>
  );
}

const DEFAULT_FORM: LoanIn = {
  name: "",
  lender: "",
  principal_amount: 2500000,
  current_balance_at_creation: null,
  start_date: new Date().toISOString().slice(0, 10),
  interest_rate: 0.042,
  binding_type: "rörlig",
  match_pattern: "",
};

function LoanForm({
  title,
  initial,
  submitLabel,
  onSubmit,
  onCancel,
  busy,
  error,
  categories,
}: {
  title: string;
  initial?: LoanIn;
  submitLabel?: string;
  onSubmit: (d: LoanIn) => void;
  onCancel: () => void;
  busy: boolean;
  error: Error | null;
  categories: Array<{ id: number; name: string }>;
}) {
  const [f, setF] = useState<LoanIn>(initial ?? DEFAULT_FORM);
  return (
    <Card title={title}>
      <div className="grid grid-cols-2 gap-3 text-sm">
        <Field label="Namn">
          <input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} className="input" placeholder="Bostadslån" />
        </Field>
        <Field label="Långivare">
          <input value={f.lender} onChange={(e) => setF({ ...f, lender: e.target.value })} className="input" placeholder="SBAB, SEB, Länsförsäkringar…" />
        </Field>
        <Field label="Lånenummer (valfritt)">
          <input value={f.loan_number ?? ""} onChange={(e) => setF({ ...f, loan_number: e.target.value || null })} className="input" />
        </Field>
        <Field label="Originalbelopp (kr)">
          <input type="number" value={f.principal_amount} onChange={(e) => setF({ ...f, principal_amount: Number(e.target.value) })} className="input" />
        </Field>
        <Field label="Kvarvarande skuld nu (kr, valfritt)">
          <input
            type="number"
            value={f.current_balance_at_creation ?? ""}
            onChange={(e) =>
              setF({
                ...f,
                current_balance_at_creation: e.target.value ? Number(e.target.value) : null,
              })
            }
            className="input"
            placeholder="Ex. 39081 för billån med 39k kvar"
            title="Används för billån/lån där originalbelopp redan är delvis amorterat — gamla amorteringar subtraheras inte, bara nya efter startdatum"
          />
        </Field>
        <Field label="Startdatum">
          <input type="date" value={f.start_date} onChange={(e) => setF({ ...f, start_date: e.target.value })} className="input" />
        </Field>
        <Field label="Ränta (decimal, 0.042 = 4,2 %)">
          <input type="number" step="0.0001" value={f.interest_rate} onChange={(e) => setF({ ...f, interest_rate: Number(e.target.value) })} className="input" />
        </Field>
        <Field label="Bindningstyp">
          <select value={f.binding_type} onChange={(e) => setF({ ...f, binding_type: e.target.value })} className="input">
            <option value="rörlig">Rörlig (3 mån)</option>
            <option value="1år">1 år</option>
            <option value="2år">2 år</option>
            <option value="3år">3 år</option>
            <option value="5år">5 år</option>
            <option value="10år">10 år</option>
          </select>
        </Field>
        <Field label="Budgetkategori">
          <select
            value={f.category_id ?? ""}
            onChange={(e) =>
              setF({
                ...f,
                category_id: e.target.value ? Number(e.target.value) : null,
              })
            }
            className="input"
          >
            <option value="">— ingen (använder Bolåneränta/Amortering)</option>
            {categories.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Bindning slut">
          <input type="date" value={f.binding_end_date ?? ""} onChange={(e) => setF({ ...f, binding_end_date: e.target.value || null })} className="input" />
        </Field>
        <Field label="Månadsamortering (kr, valfritt)">
          <input type="number" value={f.amortization_monthly ?? ""} onChange={(e) => setF({ ...f, amortization_monthly: e.target.value ? Number(e.target.value) : null })} className="input" />
        </Field>
        <Field label="Bostadsvärde (för LTV, valfritt)">
          <input type="number" value={f.property_value ?? ""} onChange={(e) => setF({ ...f, property_value: e.target.value ? Number(e.target.value) : null })} className="input" />
        </Field>
        <Field label="Matchningsmönster" hint="Text som ska finnas i transaktionens beskrivning (t.ex. 'SBAB', 'Länsförsäkringar Bank', '104-4882')">
          <input value={f.match_pattern ?? ""} onChange={(e) => setF({ ...f, match_pattern: e.target.value || null })} className="input" placeholder="SBAB" />
        </Field>
        <Field label="Anteckningar" full>
          <textarea value={f.notes ?? ""} onChange={(e) => setF({ ...f, notes: e.target.value || null })} className="input h-20" />
        </Field>
      </div>
      {error && <div className="text-sm text-rose-600 mt-2">{error.message}</div>}
      <div className="flex justify-end gap-2 mt-4">
        <button onClick={onCancel} className="px-3 py-1.5 rounded border border-slate-300 bg-white">Avbryt</button>
        <button
          onClick={() => onSubmit(f)}
          disabled={busy || !f.name || !f.lender}
          className="px-4 py-1.5 rounded bg-brand-600 text-white disabled:opacity-40"
        >
          {busy ? "Sparar…" : submitLabel ?? "Spara lån"}
        </button>
      </div>
      <style>{`.input{border:1px solid rgb(203 213 225);border-radius:0.5rem;padding:0.375rem 0.75rem;width:100%}`}</style>
    </Card>
  );
}

function Field({
  label,
  children,
  hint,
  full,
}: {
  label: string;
  children: React.ReactNode;
  hint?: string;
  full?: boolean;
}) {
  return (
    <label className={full ? "col-span-2 block" : "block"}>
      <div className="text-slate-700 text-xs mb-0.5">{label}</div>
      {children}
      {hint && <div className="text-xs text-slate-600 mt-0.5">{hint}</div>}
    </label>
  );
}

function LoanSchedule({ loanId }: { loanId: number }) {
  const qc = useQueryClient();
  const [adding, setAdding] = useState(false);
  const [newEntry, setNewEntry] = useState({
    due_date: new Date().toISOString().slice(0, 10),
    amount: 0,
    payment_type: "interest" as "interest" | "amortization",
  });

  const scheduleQ = useQuery({
    queryKey: ["loan-schedule", loanId],
    queryFn: () => api<ScheduleEntry[]>(`/loans/${loanId}/schedule`),
  });

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["loan-schedule", loanId] });
    qc.invalidateQueries({ queryKey: ["loan-summaries"] });
    qc.invalidateQueries({ queryKey: ["transactions"] });
  };

  const generateMut = useMutation({
    mutationFn: () =>
      api<ScheduleEntry[]>(`/loans/${loanId}/schedule/generate`, {
        method: "POST",
        body: JSON.stringify({ months: 3 }),
      }),
    onSuccess: invalidate,
  });

  const createMut = useMutation({
    mutationFn: () =>
      api<ScheduleEntry>(`/loans/${loanId}/schedule`, {
        method: "POST",
        body: JSON.stringify(newEntry),
      }),
    onSuccess: () => {
      invalidate();
      setAdding(false);
      setNewEntry({ ...newEntry, amount: 0 });
    },
  });

  const deleteMut = useMutation({
    mutationFn: (id: number) =>
      api(`/loans/${loanId}/schedule/${id}`, { method: "DELETE" }),
    onSuccess: invalidate,
  });

  const pruneMut = useMutation({
    mutationFn: () =>
      api<{ deleted: number; cutoff: string }>(
        `/loans/${loanId}/schedule/prune-history`,
        { method: "POST" },
      ),
    onSuccess: invalidate,
  });

  const entries = scheduleQ.data ?? [];

  return (
    <div className="mt-4 pt-3 border-t">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-1.5 text-sm text-slate-600">
          <CalendarClock className="w-4 h-4" />
          Planerade betalningar
        </div>
        <div className="flex gap-2 text-xs">
          <button
            onClick={() => generateMut.mutate()}
            disabled={generateMut.isPending}
            className="nav-link"
          >
            {generateMut.isPending ? "Genererar…" : "Generera 3 mån"}
          </button>
          <span className="text-slate-300">·</span>
          <button
            onClick={() => {
              if (
                confirm(
                  "Radera alla omatchade planerade betalningar från innan " +
                    "du började importera transaktioner? De kan ändå aldrig " +
                    "matchas.",
                )
              ) {
                pruneMut.mutate();
              }
            }}
            disabled={pruneMut.isPending}
            className="text-rose-600 hover:underline"
            title="Rensa historiska rader som aldrig kan matchas"
          >
            {pruneMut.isPending ? "Rensar…" : "Rensa historik"}
          </button>
          <span className="text-slate-300">·</span>
          <button
            onClick={() => setAdding((a) => !a)}
            className="nav-link flex items-center gap-1"
          >
            <Plus className="w-3 h-3" /> Lägg till manuellt
          </button>
        </div>
      </div>

      {pruneMut.data && (
        <div className="text-xs text-emerald-700 mb-2">
          Raderade {pruneMut.data.deleted} rader före {pruneMut.data.cutoff}.
        </div>
      )}

      {adding && (
        <div className="bg-slate-50 rounded p-2 mb-2 flex items-end gap-2 text-xs">
          <label className="flex-1">
            <div className="text-slate-700">Förväntat datum</div>
            <input
              type="date"
              value={newEntry.due_date}
              onChange={(e) => setNewEntry({ ...newEntry, due_date: e.target.value })}
              className="border rounded px-2 py-1 w-full"
            />
          </label>
          <label className="w-28">
            <div className="text-slate-700">Belopp (kr)</div>
            <input
              type="number"
              value={newEntry.amount || ""}
              onChange={(e) => setNewEntry({ ...newEntry, amount: Number(e.target.value) })}
              className="border rounded px-2 py-1 w-full"
              placeholder="0"
            />
          </label>
          <label className="w-36">
            <div className="text-slate-700">Typ</div>
            <select
              value={newEntry.payment_type}
              onChange={(e) =>
                setNewEntry({ ...newEntry, payment_type: e.target.value as "interest" | "amortization" })
              }
              className="border rounded px-2 py-1 w-full"
            >
              <option value="interest">Ränta</option>
              <option value="amortization">Amortering</option>
            </select>
          </label>
          <button
            onClick={() => createMut.mutate()}
            disabled={!newEntry.amount || createMut.isPending}
            className="bg-brand-600 text-white px-3 py-1 rounded disabled:opacity-40"
          >
            Spara
          </button>
          <button
            onClick={() => setAdding(false)}
            className="text-slate-600"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {entries.length === 0 ? (
        <div className="text-xs text-slate-600 italic">
          Inga planerade betalningar. Klicka "Generera 3 mån" så skapas ränta +
          amortering automatiskt från lånevillkoren — då matchas kommande
          transaktioner på exakt belopp + datum.
        </div>
      ) : (
        <div className="space-y-1">
          {entries.map((e) => (
            <div
              key={e.id}
              className="flex items-center gap-2 text-xs border rounded px-2 py-1.5 bg-white"
            >
              <div className="w-24 text-slate-700">{e.due_date}</div>
              <div className="w-20 font-medium">{formatSEK(e.amount)}</div>
              <div className="w-24 text-slate-600">
                {e.payment_type === "interest" ? "Ränta" : "Amortering"}
              </div>
              <div className="flex-1">
                {e.matched_transaction_id ? (
                  <span className="inline-flex items-center gap-1 text-emerald-600">
                    <CheckCircle2 className="w-3 h-3" />
                    Matchad mot transaktion #{e.matched_transaction_id}
                  </span>
                ) : (
                  <span className="text-amber-600">Väntar på matchning</span>
                )}
              </div>
              <button
                onClick={() => {
                  if (confirm("Ta bort planerad rad?")) deleteMut.mutate(e.id);
                }}
                className="text-slate-300 hover:text-rose-600"
              >
                <Trash2 className="w-3 h-3" />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function LoanFromImagesUploader({
  jobs,
  setJobs,
  onDone,
  onClose,
}: {
  jobs: { file: File; status: "uploading" | "done" | "error"; message?: string }[];
  setJobs: React.Dispatch<
    React.SetStateAction<
      { file: File; status: "uploading" | "done" | "error"; message?: string }[]
    >
  >;
  onDone: () => void;
  onClose: () => void;
}) {
  const [isDragging, setIsDragging] = useState(false);

  async function upload(files: FileList | File[]) {
    const arr = Array.from(files);
    if (arr.length === 0) return;
    setJobs(arr.map((f) => ({ file: f, status: "uploading" })));

    const token = getToken();
    const form = new FormData();
    for (const f of arr) form.append("files", f);
    try {
      const res = await fetch(`${apiBase()}/loans/parse-from-images`, {
        method: "POST",
        body: form,
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) {
        const text = await res.text();
        setJobs(arr.map((f) => ({ file: f, status: "error", message: text })));
        return;
      }
      await res.json();
      setJobs(arr.map((f) => ({ file: f, status: "done" })));
      onDone();
    } catch (e) {
      setJobs(arr.map((f) => ({ file: f, status: "error", message: String(e) })));
    }
  }

  return (
    <Card
      title="Skapa lån automatiskt från bankbilder"
      action={
        <button onClick={onClose} className="text-slate-600 hover:text-slate-700">
          <X className="w-4 h-4" />
        </button>
      }
    >
      <div className="text-sm text-slate-600 mb-3">
        Dra in skärmdumpar eller PDF:er från bankens lånesida. Vision-modellen
        läser <strong>Låneinformation</strong> (grunden), <strong>Betalningsplan</strong>{" "}
        (skapar schema) och eventuellt <strong>Transaktioner</strong>. Du kan
        släppa flera bilder samtidigt — systemet sammanställer dem till ett lån
        med komplett betalningsplan.
        <div className="mt-1 text-xs text-amber-700">
          Kräver vision-kapabel modell i LM Studio (Qwen2.5-VL, Pixtral, Llava).
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
          isDragging ? "border-emerald-500 bg-emerald-50" : "border-slate-300 bg-slate-50"
        }`}
      >
        <ImageIcon className="w-10 h-10 mx-auto text-slate-600 mb-2" />
        <div className="text-sm text-slate-600">
          Dra flera bilder hit, eller{" "}
          <label className="text-emerald-700 cursor-pointer underline">
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
            <div
              key={i}
              className="flex items-center gap-3 p-2 border rounded bg-white text-sm"
            >
              {j.status === "uploading" && (
                <Loader2 className="w-4 h-4 animate-spin text-emerald-600" />
              )}
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
    </Card>
  );
}
