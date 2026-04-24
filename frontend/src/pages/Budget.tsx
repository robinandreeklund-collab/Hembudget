import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import {
  Sparkles, ChevronDown, ChevronRight, Info, AlertTriangle, CheckCircle2,
  TrendingUp, X,
} from "lucide-react";
import { api, formatSEK } from "@/api/client";
import { Card } from "@/components/Card";
import type { AutoFillSuggestion, BudgetGroup, BudgetLine, MonthSummary } from "@/types/models";

function defaultMonth(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

function monthLabel(month: string): string {
  const [y, m] = month.split("-").map((s) => Number(s));
  const names = [
    "januari", "februari", "mars", "april", "maj", "juni",
    "juli", "augusti", "september", "oktober", "november", "december",
  ];
  return `${names[m - 1]} ${y}`;
}

// Färg för progressbar: grön <80%, gul 80-100%, röd >100%
function progressColor(pct: number): string {
  if (pct > 100) return "bg-rose-500";
  if (pct > 80) return "bg-amber-400";
  return "bg-emerald-500";
}

function progressTextColor(pct: number): string {
  if (pct > 100) return "text-rose-700";
  if (pct > 80) return "text-amber-700";
  return "text-emerald-700";
}

function ProgressBar({ pct, color }: { pct: number; color: string }) {
  const clamped = Math.min(pct, 150);
  return (
    <div className="w-full bg-slate-200 rounded-full h-1.5 overflow-hidden">
      <div
        className={`h-full ${color} transition-all`}
        style={{ width: `${clamped}%` }}
      />
    </div>
  );
}

export default function Budget() {
  const qc = useQueryClient();
  const [month, setMonth] = useState(defaultMonth());
  const [showAutoFill, setShowAutoFill] = useState(false);
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});
  const [showHelp, setShowHelp] = useState(true);

  const summaryQ = useQuery({
    queryKey: ["budget", month],
    queryFn: () => api<MonthSummary>(`/budget/${month}`),
  });

  const setMut = useMutation({
    mutationFn: (p: { category_id: number; planned_amount: number }) =>
      api("/budget/", {
        method: "POST",
        body: JSON.stringify({
          month,
          category_id: p.category_id,
          planned_amount: p.planned_amount,
        }),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["budget", month] }),
  });

  const summary = summaryQ.data;

  // Plocka bort inkomster från det som visas som "utgifter totalt". KPIn
  // "Kvar att spendera" = budget totalt (utgifter) - utfall (utgifter).
  const expenseGroups = useMemo<BudgetGroup[]>(
    () => (summary?.groups ?? []).filter((g) => g.group !== "Inkomster"),
    [summary],
  );
  const incomeGroups = useMemo<BudgetGroup[]>(
    () => (summary?.groups ?? []).filter((g) => g.group === "Inkomster"),
    [summary],
  );

  const totalPlannedExpense = expenseGroups.reduce(
    (acc, g) => acc + Math.abs(g.planned),
    0,
  );
  const totalActualExpense = expenseGroups.reduce(
    (acc, g) => acc + Math.abs(g.actual),
    0,
  );
  const totalRemaining = totalPlannedExpense - totalActualExpense;
  const overallProgress = totalPlannedExpense > 0
    ? Math.round((totalActualExpense / totalPlannedExpense) * 100)
    : 0;

  function toggleGroup(key: string) {
    setCollapsed((c) => ({ ...c, [key]: !c[key] }));
  }

  return (
    <div className="p-3 md:p-6 space-y-4 max-w-5xl">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <h1 className="text-2xl font-semibold">Budget</h1>
        <div className="flex items-center gap-2 flex-wrap">
          <input
            type="month"
            value={month}
            onChange={(e) => setMonth(e.target.value)}
            className="border rounded px-2 py-1"
          />
          <button
            onClick={() => setShowAutoFill(true)}
            className="inline-flex items-center gap-1.5 text-sm bg-brand-600 text-white rounded-lg px-3 py-1.5 hover:bg-brand-700"
            title="Öppna auto-fyll-guiden"
          >
            <Sparkles className="w-4 h-4" />
            Auto-fyll budget
          </button>
        </div>
      </div>

      {showHelp && (
        <div className="bg-sky-50 border border-sky-200 rounded-lg px-3 py-2 text-sm text-sky-900 flex items-start gap-2">
          <Info className="w-4 h-4 mt-0.5 shrink-0" />
          <div className="flex-1">
            <strong>Så fungerar budgeten:</strong> Sätt ett planerat belopp per
            kategori — jämförs mot utfallet i realtid. Grön = under budget,
            gul = nära, röd = över. Klicka <em>Auto-fyll budget</em> för att
            få förslag baserat på senaste 6 månaderna (du godkänner varje rad
            för sig).
          </div>
          <button
            onClick={() => setShowHelp(false)}
            className="text-sky-700 hover:text-sky-900 shrink-0"
            title="Dölj"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {summaryQ.isLoading && (
        <div className="text-sm text-slate-700">Laddar budget…</div>
      )}

      {summary && (
        <>
          <KpiHeader
            income={summary.income}
            expenses={summary.expenses}
            plannedExpense={totalPlannedExpense}
            remaining={totalRemaining}
            overallProgress={overallProgress}
            savingsRate={summary.savings_rate}
          />

          {incomeGroups.map((g) => (
            <GroupCard
              key={`g-${g.group}`}
              group={g}
              lines={summary.lines.filter((l) => l.kind === "income")}
              collapsed={collapsed[g.group] ?? false}
              onToggle={() => toggleGroup(g.group)}
              onSetPlanned={(cid, v) =>
                setMut.mutate({ category_id: cid, planned_amount: v })
              }
            />
          ))}

          {expenseGroups.length === 0 && (
            <Card title="Inga utgifter denna månad">
              <div className="text-sm text-slate-700">
                När du bokför eller sätter budget för kategorier dyker de upp
                här.
              </div>
            </Card>
          )}

          {expenseGroups.map((g) => (
            <GroupCard
              key={`g-${g.group_id ?? "none"}-${g.group}`}
              group={g}
              lines={summary.lines.filter(
                (l) =>
                  l.kind !== "income" &&
                  (g.category_ids.includes(l.category_id)),
              )}
              collapsed={collapsed[g.group] ?? false}
              onToggle={() => toggleGroup(g.group)}
              onSetPlanned={(cid, v) =>
                setMut.mutate({ category_id: cid, planned_amount: v })
              }
            />
          ))}
        </>
      )}

      {showAutoFill && (
        <AutoFillModal
          month={month}
          onClose={() => setShowAutoFill(false)}
          onSaved={() => {
            setShowAutoFill(false);
            qc.invalidateQueries({ queryKey: ["budget", month] });
          }}
        />
      )}

      <div className="text-xs text-slate-500 pt-2">
        Månad: <strong>{monthLabel(month)}</strong>
      </div>
    </div>
  );
}

// -------- KPI header --------

function KpiHeader({
  income, expenses, plannedExpense, remaining, overallProgress, savingsRate,
}: {
  income: number;
  expenses: number;
  plannedExpense: number;
  remaining: number;
  overallProgress: number;
  savingsRate: number;
}) {
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-2 md:gap-3">
      <div className="bg-white border rounded-lg p-3 md:p-4">
        <div className="text-xs text-slate-700 uppercase tracking-wide">Inkomst</div>
        <div className="text-xl md:text-2xl font-semibold text-emerald-700">
          {formatSEK(income)}
        </div>
      </div>
      <div className="bg-white border rounded-lg p-3 md:p-4">
        <div className="text-xs text-slate-700 uppercase tracking-wide">Utgifter</div>
        <div className="text-xl md:text-2xl font-semibold text-rose-700">
          {formatSEK(-expenses)}
        </div>
        <div className="text-xs text-slate-500">
          av budget {formatSEK(-plannedExpense)}
        </div>
      </div>
      <div className="bg-white border rounded-lg p-3 md:p-4">
        <div className="text-xs text-slate-700 uppercase tracking-wide">
          Kvar i budget
        </div>
        <div
          className={`text-xl md:text-2xl font-semibold ${
            remaining < 0 ? "text-rose-700" : "text-emerald-700"
          }`}
        >
          {formatSEK(remaining)}
        </div>
        <div className="mt-1">
          <ProgressBar
            pct={overallProgress}
            color={progressColor(overallProgress)}
          />
          <div className="text-xs text-slate-500 mt-0.5">
            {overallProgress}% spenderat
          </div>
        </div>
      </div>
      <div className="bg-white border rounded-lg p-3 md:p-4">
        <div className="text-xs text-slate-700 uppercase tracking-wide">Sparkvot</div>
        <div
          className={`text-xl md:text-2xl font-semibold ${
            savingsRate < 0 ? "text-rose-700" : "text-emerald-700"
          }`}
        >
          {(savingsRate * 100).toFixed(1)} %
        </div>
        <div className="text-xs text-slate-500">
          {savingsRate >= 0.1
            ? "Bra! 10%+ sparkvot"
            : savingsRate >= 0
            ? "Du sparar — men lite"
            : "Minus denna månad"}
        </div>
      </div>
    </div>
  );
}

// -------- Group card --------

function GroupCard({
  group, lines, collapsed, onToggle, onSetPlanned,
}: {
  group: BudgetGroup;
  lines: BudgetLine[];
  collapsed: boolean;
  onToggle: () => void;
  onSetPlanned: (category_id: number, value: number) => void;
}) {
  const abs = (n: number) => Math.abs(n);
  const isIncome = group.group === "Inkomster";
  const pct = group.progress_pct;
  const barColor = isIncome
    ? "bg-emerald-500"
    : progressColor(pct);

  return (
    <div className="bg-white border rounded-lg overflow-hidden">
      <button
        onClick={onToggle}
        className="w-full flex items-center gap-3 px-3 md:px-4 py-2.5 hover:bg-slate-50 text-left"
      >
        {collapsed ? (
          <ChevronRight className="w-4 h-4 shrink-0 text-slate-500" />
        ) : (
          <ChevronDown className="w-4 h-4 shrink-0 text-slate-500" />
        )}
        <div className="flex-1 min-w-0">
          <div className="flex items-baseline justify-between gap-2 flex-wrap">
            <div className="font-semibold text-sm md:text-base">
              {group.group}
              <span className="ml-2 text-xs text-slate-500 font-normal">
                {lines.length} kat.
              </span>
            </div>
            <div className="text-sm">
              <span className="font-medium">{formatSEK(isIncome ? group.actual : -abs(group.actual))}</span>
              <span className="text-slate-500"> / {formatSEK(isIncome ? group.planned : -abs(group.planned))}</span>
              {group.planned !== 0 && (
                <span className={`ml-2 font-medium ${progressTextColor(pct)}`}>
                  {pct.toFixed(0)}%
                </span>
              )}
            </div>
          </div>
          {group.planned !== 0 && !isIncome && (
            <div className="mt-1.5">
              <ProgressBar pct={pct} color={barColor} />
            </div>
          )}
        </div>
      </button>

      {!collapsed && (
        <div className="border-t divide-y">
          {lines.length === 0 && (
            <div className="px-4 py-3 text-sm text-slate-500">
              Inga kategorier i gruppen.
            </div>
          )}
          {lines.map((l) => (
            <CategoryRow
              key={l.category_id}
              line={l}
              isIncome={isIncome}
              onSetPlanned={(v) => onSetPlanned(l.category_id, v)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// -------- Kategori-rad med progressbar + inline budget-input --------

function CategoryRow({
  line, isIncome, onSetPlanned,
}: {
  line: BudgetLine;
  isIncome: boolean;
  onSetPlanned: (v: number) => void;
}) {
  const pct = line.progress_pct ?? 0;
  const barColor = isIncome ? "bg-emerald-500" : progressColor(pct);
  const abs = Math.abs;
  const hasBudget = line.planned !== 0;
  const overBudget = !isIncome && hasBudget && abs(line.actual) > abs(line.planned);
  const remaining = hasBudget
    ? (isIncome ? line.planned - line.actual : abs(line.planned) - abs(line.actual))
    : 0;

  return (
    <div className="px-3 md:px-4 py-2.5">
      <div className="flex items-center gap-2 md:gap-3 flex-wrap">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5">
            <span className="font-medium text-sm truncate">{line.category}</span>
            {overBudget && (
              <AlertTriangle
                className="w-3.5 h-3.5 text-rose-600 shrink-0"
                aria-label="Över budget"
              />
            )}
            {hasBudget && !overBudget && !isIncome && pct < 80 && (
              <CheckCircle2
                className="w-3.5 h-3.5 text-emerald-600 shrink-0"
                aria-label="Under budget"
              />
            )}
          </div>
          <div className="text-xs text-slate-500 mt-0.5 flex items-center gap-2 flex-wrap">
            <span>
              Utfall: <span className="font-medium text-slate-800">
                {formatSEK(isIncome ? line.actual : -abs(line.actual))}
              </span>
            </span>
            {hasBudget && (
              <span className={progressTextColor(pct)}>
                {pct.toFixed(0)}% av budget
              </span>
            )}
            {hasBudget && (
              <span>
                Kvar: <span className={`font-medium ${remaining < 0 ? "text-rose-700" : "text-slate-800"}`}>
                  {formatSEK(remaining)}
                </span>
              </span>
            )}
            {(line.trend_median ?? 0) > 0 && (
              <span
                className="inline-flex items-center gap-0.5 text-slate-500"
                title="Median utfall senaste 3 månaderna"
              >
                <TrendingUp className="w-3 h-3" />
                snitt {formatSEK(line.trend_median ?? 0)}
              </span>
            )}
          </div>
        </div>
        <label className="shrink-0 text-right">
          <div className="text-[10px] uppercase text-slate-500 mb-0.5">Budget</div>
          <input
            type="number"
            defaultValue={line.planned}
            onBlur={(e) => {
              const v = Number(e.target.value);
              if (!Number.isNaN(v) && v !== line.planned) onSetPlanned(v);
            }}
            className="w-24 border rounded px-2 py-0.5 text-right text-sm"
          />
        </label>
      </div>
      {hasBudget && !isIncome && (
        <div className="mt-2">
          <ProgressBar pct={pct} color={barColor} />
        </div>
      )}
    </div>
  );
}

// -------- Auto-fyll-modal --------

function AutoFillModal({
  month, onClose, onSaved,
}: {
  month: string;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [overrides, setOverrides] = useState<Record<number, number>>({});

  const previewQ = useQuery({
    queryKey: ["budget-autofill", month],
    queryFn: () =>
      api<{ suggestions: AutoFillSuggestion[] }>(
        `/budget/${month}/auto-fill-preview?lookback_months=6`,
      ),
  });

  const suggestions = previewQ.data?.suggestions ?? [];

  const saveMut = useMutation({
    mutationFn: (rows: { category_id: number; planned_amount: number }[]) =>
      api<{ saved: number }>("/budget/bulk-set", {
        method: "POST",
        body: JSON.stringify({ month, rows }),
      }),
    onSuccess: () => onSaved(),
  });

  function toggleAll(filter: (s: AutoFillSuggestion) => boolean) {
    const set = new Set(selected);
    const matches = suggestions.filter(filter);
    const allIn = matches.every((s) => set.has(s.category_id));
    for (const s of matches) {
      if (allIn) set.delete(s.category_id);
      else set.add(s.category_id);
    }
    setSelected(set);
  }

  function toggleOne(cid: number) {
    const set = new Set(selected);
    if (set.has(cid)) set.delete(cid);
    else set.add(cid);
    setSelected(set);
  }

  function onSave() {
    const rows = Array.from(selected).map((cid) => ({
      category_id: cid,
      planned_amount:
        overrides[cid] ??
        suggestions.find((s) => s.category_id === cid)?.suggested ??
        0,
    }));
    if (rows.length === 0) return;
    saveMut.mutate(rows);
  }

  const emptyCount = suggestions.filter((s) => s.current_planned === null).length;

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-3">
      <div className="bg-white rounded-lg shadow-lg w-full max-w-2xl max-h-[90vh] flex flex-col">
        <div className="flex items-center justify-between px-4 py-3 border-b">
          <div>
            <h2 className="text-lg font-semibold">Auto-fyll budget</h2>
            <div className="text-xs text-slate-700">
              {monthLabel(month)} · förslag baserat på median senaste 6 mån
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-slate-500 hover:text-slate-800"
            title="Stäng"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="px-4 py-2 border-b flex items-center gap-2 flex-wrap text-xs">
          <button
            className="px-2 py-1 rounded bg-slate-100 hover:bg-slate-200"
            onClick={() => toggleAll((s) => s.current_planned === null)}
          >
            Markera tomma ({emptyCount})
          </button>
          <button
            className="px-2 py-1 rounded bg-slate-100 hover:bg-slate-200"
            onClick={() => toggleAll(() => true)}
          >
            Markera alla
          </button>
          <button
            className="px-2 py-1 rounded bg-slate-100 hover:bg-slate-200"
            onClick={() => setSelected(new Set())}
          >
            Avmarkera alla
          </button>
          <div className="ml-auto text-slate-700">
            {selected.size} av {suggestions.length} valda
          </div>
        </div>

        <div className="flex-1 overflow-auto">
          {previewQ.isLoading && (
            <div className="p-4 text-sm text-slate-700">
              Räknar fram förslag…
            </div>
          )}
          {!previewQ.isLoading && suggestions.length === 0 && (
            <div className="p-4 text-sm text-slate-700">
              Inga förslag. Troligen har du inte tillräckligt med historik
              (behöver minst några månaders transaktioner).
            </div>
          )}
          {suggestions.length > 0 && (
            <table className="w-full text-sm">
              <thead className="text-xs uppercase text-slate-700 bg-slate-50">
                <tr>
                  <th className="text-left px-3 py-1.5 w-8"></th>
                  <th className="text-left px-3 py-1.5">Kategori</th>
                  <th className="text-right px-3 py-1.5">Förslag</th>
                  <th className="text-right px-3 py-1.5">Nuvarande</th>
                  <th className="text-right px-3 py-1.5 pr-4">Mån med data</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {suggestions.map((s) => {
                  const isSelected = selected.has(s.category_id);
                  return (
                    <tr
                      key={s.category_id}
                      className={isSelected ? "bg-brand-50" : ""}
                    >
                      <td className="px-3 py-1.5">
                        <input
                          type="checkbox"
                          checked={isSelected}
                          onChange={() => toggleOne(s.category_id)}
                        />
                      </td>
                      <td className="px-3 py-1.5">
                        <div className="font-medium">{s.category}</div>
                        {s.group && (
                          <div className="text-xs text-slate-500">{s.group}</div>
                        )}
                      </td>
                      <td className="px-3 py-1.5 text-right">
                        <input
                          type="number"
                          defaultValue={s.suggested}
                          onChange={(e) =>
                            setOverrides((o) => ({
                              ...o,
                              [s.category_id]: Number(e.target.value),
                            }))
                          }
                          className="w-24 border rounded px-1.5 py-0.5 text-right"
                        />
                      </td>
                      <td className="px-3 py-1.5 text-right text-slate-700">
                        {s.current_planned === null
                          ? "—"
                          : formatSEK(s.current_planned)}
                      </td>
                      <td className="px-3 py-1.5 text-right pr-4 text-slate-700">
                        {s.months_with_data}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>

        <div className="px-4 py-3 border-t flex items-center justify-end gap-2">
          <button
            onClick={onClose}
            className="px-3 py-1.5 rounded text-sm hover:bg-slate-100"
          >
            Avbryt
          </button>
          <button
            onClick={onSave}
            disabled={selected.size === 0 || saveMut.isPending}
            className="bg-brand-600 text-white px-3 py-1.5 rounded text-sm disabled:opacity-50 hover:bg-brand-700"
          >
            {saveMut.isPending
              ? "Sparar…"
              : `Spara ${selected.size} valda`}
          </button>
        </div>
      </div>
    </div>
  );
}
