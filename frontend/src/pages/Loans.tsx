import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Home, Pencil, Trash2, Plus } from "lucide-react";
import { api, formatSEK } from "@/api/client";
import { Card } from "@/components/Card";

interface LoanSummary {
  id: number;
  name: string;
  lender: string;
  principal_amount: number;
  outstanding_balance: number;
  amortization_paid: number;
  interest_paid: number;
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
  start_date: string;
  interest_rate: number;
  binding_type: string;
  binding_end_date: string | null;
  amortization_monthly: number | null;
  property_value: number | null;
  match_pattern: string | null;
  notes: string | null;
  active: boolean;
}

interface LoanIn {
  name: string;
  lender: string;
  loan_number?: string | null;
  principal_amount: number;
  start_date: string;
  interest_rate: number;
  binding_type: string;
  binding_end_date?: string | null;
  amortization_monthly?: number | null;
  property_value?: number | null;
  match_pattern?: string | null;
  notes?: string | null;
}

export default function Loans() {
  const qc = useQueryClient();
  const [mode, setMode] = useState<
    | { kind: "idle" }
    | { kind: "create" }
    | { kind: "edit"; loan: Loan }
  >({ kind: "idle" });

  const summariesQ = useQuery({
    queryKey: ["loan-summaries"],
    queryFn: () => api<LoanSummary[]>("/loans/summaries/all"),
  });
  const loansQ = useQuery({
    queryKey: ["loans"],
    queryFn: () => api<Loan[]>("/loans/"),
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
  const totalDebt = summaries.reduce((s, l) => s + l.outstanding_balance, 0);
  const totalInterest = summaries.reduce((s, l) => s + l.interest_paid, 0);
  const totalAmortized = summaries.reduce((s, l) => s + l.amortization_paid, 0);

  return (
    <div className="p-6 space-y-5 max-w-5xl">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold flex items-center gap-2">
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
            onClick={() => setMode(mode.kind === "create" ? { kind: "idle" } : { kind: "create" })}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-lg bg-brand-600 text-white"
          >
            <Plus className="w-4 h-4" />
            Nytt lån
          </button>
        </div>
      </div>

      {rescanMut.data && (
        <div className="text-sm text-slate-600">
          {rescanMut.data.linked} betalningar länkade.
          {rescanMut.data.unclassified > 0 &&
            ` ${rescanMut.data.unclassified} matchade lån men kunde inte klassificeras som ränta/amortering.`}
        </div>
      )}

      <div className="grid grid-cols-3 gap-4">
        <Card>
          <div className="text-xs uppercase text-slate-500">Total skuld</div>
          <div className="text-2xl font-semibold text-rose-600">{formatSEK(totalDebt)}</div>
        </Card>
        <Card>
          <div className="text-xs uppercase text-slate-500">Betald ränta (total)</div>
          <div className="text-2xl font-semibold">{formatSEK(totalInterest)}</div>
        </Card>
        <Card>
          <div className="text-xs uppercase text-slate-500">Amorterat</div>
          <div className="text-2xl font-semibold text-emerald-600">{formatSEK(totalAmortized)}</div>
        </Card>
      </div>

      {mode.kind === "create" && (
        <LoanForm
          title="Nytt lån"
          onSubmit={(data) => createMut.mutate(data)}
          onCancel={() => setMode({ kind: "idle" })}
          busy={createMut.isPending}
          error={createMut.error as Error | null}
        />
      )}
      {mode.kind === "edit" && (
        <LoanForm
          title={`Redigera "${mode.loan.name}"`}
          initial={{
            name: mode.loan.name,
            lender: mode.loan.lender,
            loan_number: mode.loan.loan_number,
            principal_amount: mode.loan.principal_amount,
            start_date: mode.loan.start_date,
            interest_rate: mode.loan.interest_rate,
            binding_type: mode.loan.binding_type,
            binding_end_date: mode.loan.binding_end_date,
            amortization_monthly: mode.loan.amortization_monthly,
            property_value: mode.loan.property_value,
            match_pattern: mode.loan.match_pattern,
            notes: mode.loan.notes,
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
          <div className="text-sm text-slate-500">
            Inga lån registrerade. Lägg till ett så kopplar systemet dina
            betalningar automatiskt och räknar ned skulden per amortering.
          </div>
        ) : (
          <div className="space-y-3">
            {summaries.map((s) => {
              const full = loans.find((l) => l.id === s.id);
              return (
                <div key={s.id} className="border rounded-lg p-4">
                  <div className="flex justify-between items-start">
                    <div>
                      <div className="font-semibold">{s.name}</div>
                      <div className="text-xs text-slate-500">
                        {s.lender} · {s.binding_type} · {(s.interest_rate * 100).toFixed(2)} %
                        {full?.match_pattern ? ` · matchar "${full.match_pattern}"` : ""}
                      </div>
                    </div>
                    <div className="flex gap-1">
                      <button
                        onClick={() => full && setMode({ kind: "edit", loan: full })}
                        disabled={!full}
                        className="p-1.5 text-slate-400 hover:text-brand-600 disabled:opacity-40"
                        title="Redigera"
                      >
                        <Pencil className="w-4 h-4" />
                      </button>
                      <button
                        onClick={() => {
                          if (confirm(`Ta bort lånet '${s.name}'?`)) deleteMut.mutate(s.id);
                        }}
                        className="p-1.5 text-slate-400 hover:text-rose-600"
                        title="Ta bort"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </div>
                  <div className="grid grid-cols-4 gap-4 mt-3 text-sm">
                    <Stat label="Ursprung" value={formatSEK(s.principal_amount)} />
                    <Stat label="Kvarvarande" value={formatSEK(s.outstanding_balance)} strong />
                    <Stat label="Amorterat" value={formatSEK(s.amortization_paid)} />
                    <Stat label="Betald ränta" value={formatSEK(s.interest_paid)} />
                  </div>
                  <div className="flex gap-4 mt-2 text-xs text-slate-500">
                    <span>{s.payments_count} betalningar länkade</span>
                    {s.ltv !== null && <span>LTV {(s.ltv * 100).toFixed(1)} %</span>}
                    {s.binding_end_date && <span>Bindning slut {s.binding_end_date}</span>}
                  </div>
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
      <div className="text-xs text-slate-500">{label}</div>
      <div className={strong ? "font-semibold" : ""}>{value}</div>
    </div>
  );
}

const DEFAULT_FORM: LoanIn = {
  name: "",
  lender: "",
  principal_amount: 2500000,
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
}: {
  title: string;
  initial?: LoanIn;
  submitLabel?: string;
  onSubmit: (d: LoanIn) => void;
  onCancel: () => void;
  busy: boolean;
  error: Error | null;
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
      <div className="text-slate-500 text-xs mb-0.5">{label}</div>
      {children}
      {hint && <div className="text-xs text-slate-400 mt-0.5">{hint}</div>}
    </label>
  );
}
