/**
 * HouseholdSummaryCard — visar hushållsfördelningen permanent.
 *
 * Visas BARA om eleven har sambo + redan gjort cost-split-valet.
 * Pedagogiskt: påminner om valet löpande och låter eleven ändra
 * (med varning att första ärliga valet alltid kvarstår i loggen).
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Heart, Home, Pencil } from "lucide-react";
import { useState } from "react";
import { api, formatSEK } from "@/api/client";
import { Card } from "@/components/Card";

interface CostSplitOut {
  family_status: string;
  needs_decision: boolean;
  cost_split_preference: string | null;
  cost_split_decided_at: string | null;
  partner_profession: string | null;
  partner_gross_salary: number | null;
  student_share_pct: number | null;
}

const PREF_LABEL: Record<string, string> = {
  even_50_50: "50/50 — jämnt fördelat",
  pro_rata: "Proportionellt mot inkomst",
  all_shared: "Gemensam ekonomi",
};

export function HouseholdSummaryCard() {
  const qc = useQueryClient();
  const [editing, setEditing] = useState(false);

  const splitQ = useQuery({
    queryKey: ["student-cost-split"],
    queryFn: () => api<CostSplitOut>("/student/cost-split"),
  });

  const profileQ = useQuery({
    queryKey: ["student-profile"],
    queryFn: () => api<{ gross_salary_monthly: number; family_status: string }>("/student/profile"),
  });

  const changeMut = useMutation({
    mutationFn: (preference: string) =>
      api<CostSplitOut>("/student/cost-split", {
        method: "POST",
        body: JSON.stringify({ preference }),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["student-cost-split"] });
      qc.invalidateQueries({ queryKey: ["student-profile"] });
      setEditing(false);
    },
  });

  const data = splitQ.data;
  if (!data) return null;
  // Visa BARA om eleven har partner OCH redan beslutat
  if (data.family_status === "ensam") return null;
  if (!data.cost_split_preference) return null;
  if (!data.partner_gross_salary) return null;

  const studentSalary = profileQ.data?.gross_salary_monthly ?? 0;
  const partnerSalary = data.partner_gross_salary;
  const totalIncome = studentSalary + partnerSalary;

  return (
    <Card title={
      <span className="flex items-center gap-2">
        <Home className="w-4 h-4 text-rose-500" />
        Ditt hushåll
      </span> as unknown as string
    }>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-sm">
        <div className="bg-slate-50 border rounded p-2">
          <div className="text-xs text-slate-600">Du</div>
          <div className="font-medium">{formatSEK(studentSalary)}</div>
          <div className="text-[10px] text-slate-500">brutto/mån</div>
        </div>
        <div className="bg-slate-50 border rounded p-2">
          <div className="text-xs text-slate-600 flex items-center gap-1">
            <Heart className="w-3 h-3 text-rose-400" />
            Sambo ({data.partner_profession})
          </div>
          <div className="font-medium">{formatSEK(partnerSalary)}</div>
          <div className="text-[10px] text-slate-500">brutto/mån</div>
        </div>
        <div className="bg-emerald-50 border border-emerald-200 rounded p-2">
          <div className="text-xs text-emerald-800">Totalt hushållet</div>
          <div className="font-medium">{formatSEK(totalIncome)}</div>
          <div className="text-[10px] text-emerald-700">brutto/mån</div>
        </div>
      </div>

      <div className="mt-3 pt-3 border-t flex items-center justify-between flex-wrap gap-2">
        <div className="text-sm">
          <span className="text-slate-600">Fördelning: </span>
          <span className="font-medium">
            {PREF_LABEL[data.cost_split_preference] ?? data.cost_split_preference}
          </span>
          <span className="ml-2 text-xs text-slate-500">
            (du betalar <strong>{data.student_share_pct?.toFixed(0)} %</strong> av gemensamma kostnader)
          </span>
        </div>
        {!editing && (
          <button
            onClick={() => setEditing(true)}
            className="text-xs text-slate-600 hover:text-slate-900 flex items-center gap-1"
          >
            <Pencil className="w-3 h-3" />
            Ändra
          </button>
        )}
      </div>

      {editing && (
        <div className="mt-3 pt-3 border-t space-y-2">
          <div className="text-xs italic text-slate-600">
            Ditt första ärliga val ({data.cost_split_decided_at?.slice(0, 10)})
            sparas alltid — men du får ändra hur det fungerar framåt.
          </div>
          {Object.entries(PREF_LABEL).map(([value, label]) => (
            <button
              key={value}
              onClick={() => changeMut.mutate(value)}
              disabled={
                changeMut.isPending ||
                value === data.cost_split_preference
              }
              className={`w-full text-left p-2 rounded border text-sm ${
                value === data.cost_split_preference
                  ? "bg-emerald-50 border-emerald-300 text-emerald-900 cursor-default"
                  : "bg-white border-slate-200 hover:border-amber-300"
              }`}
            >
              {label}
              {value === data.cost_split_preference && " ✓ (nuvarande)"}
            </button>
          ))}
          <button
            onClick={() => setEditing(false)}
            className="text-xs text-slate-500 underline"
          >
            Avbryt
          </button>
        </div>
      )}
    </Card>
  );
}
