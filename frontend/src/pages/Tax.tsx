import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, formatSEK } from "@/api/client";
import { Card } from "@/components/Card";

export default function Tax() {
  const [year, setYear] = useState(new Date().getFullYear());
  const [isk, setIsk] = useState({
    year,
    opening_balance: 100000,
    deposits: 12000,
    q1: 101000,
    q2: 104000,
    q3: 108000,
    q4: 112000,
    statslaneranta_30_nov: 0.0262,
  });
  const [iskResult, setIskResult] = useState<Record<string, unknown> | null>(null);

  const iskMut = useMutation({
    mutationFn: () =>
      api<Record<string, unknown>>("/tax/isk", {
        method: "POST",
        body: JSON.stringify({
          year: isk.year,
          opening_balance: isk.opening_balance,
          deposits: isk.deposits,
          quarter_values: [isk.q1, isk.q2, isk.q3, isk.q4],
          statslaneranta_30_nov: isk.statslaneranta_30_nov,
        }),
      }),
    onSuccess: setIskResult,
  });

  const rotrutQ = useQuery({
    queryKey: ["rotrut", year],
    queryFn: () => api<Record<string, number | string[]>>(`/tax/rotrut/${year}`),
  });

  const salaryQ = useQuery({
    queryKey: ["tax-salary-summary", year],
    queryFn: () =>
      api<SalaryTaxSummary>(`/tax/salary-summary?year=${year}`),
  });

  return (
    <div className="p-3 md:p-6 space-y-4 md:space-y-4 max-w-4xl">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Skatt</h1>
        <input
          type="number"
          value={year}
          onChange={(e) => setYear(Number(e.target.value))}
          className="border rounded px-2 py-1 w-24"
        />
      </div>

      {salaryQ.data && salaryQ.data.overall.count > 0 && (
        <SalarySummaryCard data={salaryQ.data} />
      )}

      <Card title="ISK — schablonbeskattning">
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3">
          {(["opening_balance", "deposits", "q1", "q2", "q3", "q4"] as const).map((k) => (
            <label key={k} className="text-sm">
              <div className="text-slate-700">{k}</div>
              <input
                type="number"
                value={isk[k]}
                onChange={(e) => setIsk({ ...isk, [k]: Number(e.target.value) })}
                className="border rounded px-2 py-1 w-full"
              />
            </label>
          ))}
          <label className="text-sm">
            <div className="text-slate-700">Statslåneränta 30/11</div>
            <input
              type="number"
              step="0.0001"
              value={isk.statslaneranta_30_nov}
              onChange={(e) => setIsk({ ...isk, statslaneranta_30_nov: Number(e.target.value) })}
              className="border rounded px-2 py-1 w-full"
            />
          </label>
        </div>
        <button
          onClick={() => iskMut.mutate()}
          className="mt-3 bg-brand-600 text-white px-4 py-2 rounded"
        >
          Beräkna ISK
        </button>
        {iskResult && (
          <div className="mt-3 text-sm">
            <div>Underlag: <strong>{formatSEK(iskResult.underlag as number)}</strong></div>
            <div>Schablonränta: <strong>{((iskResult.schablonrate as number) * 100).toFixed(3)} %</strong></div>
            <div>Schablonintäkt: <strong>{formatSEK(iskResult.schablonintakt as number)}</strong></div>
            <div>Skatt (30 %): <strong>{formatSEK(iskResult.skatt as number)}</strong></div>
            {(iskResult.notes as string[])?.length > 0 && (
              <div className="text-slate-700 text-xs mt-1">{(iskResult.notes as string[]).join("; ")}</div>
            )}
          </div>
        )}
      </Card>

      <Card title={`ROT/RUT-användning ${year}`}>
        {rotrutQ.data ? (
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <div className="text-slate-700">ROT</div>
              <div className="text-xl font-semibold">{formatSEK(rotrutQ.data.rot_used as number)}</div>
              <div className="text-xs text-slate-700">
                Kvar: {formatSEK(rotrutQ.data.rot_remaining as number)} av tak {formatSEK(rotrutQ.data.rot_cap as number)}
              </div>
            </div>
            <div>
              <div className="text-slate-700">RUT</div>
              <div className="text-xl font-semibold">{formatSEK(rotrutQ.data.rut_used as number)}</div>
              <div className="text-xs text-slate-700">
                Kvar: {formatSEK(rotrutQ.data.rut_remaining as number)} av tak {formatSEK(rotrutQ.data.rut_cap as number)}
              </div>
            </div>
            {((rotrutQ.data.notes as string[]) ?? []).length > 0 && (
              <div className="col-span-2 text-amber-700 text-sm">
                {(rotrutQ.data.notes as string[]).join(" · ")}
              </div>
            )}
          </div>
        ) : (
          <div className="text-sm text-slate-700">Laddar…</div>
        )}
      </Card>

      <Card title="K4 — kapitalvinstberäkning">
        <div className="text-sm text-slate-700">
          K4 stöds via API <code>/tax/k4</code>. UI för manuell inmatning kan läggas till, men
          oftast är det bättre att importera trades från Avanza/Nordnet-CSV (kommande feature).
        </div>
      </Card>
    </div>
  );
}

interface SalaryPayslip {
  upcoming_id: number;
  employer: string;
  paid_date: string;
  gross: number;
  tax: number;
  extra_tax: number;
  benefit: number;
  net: number;
  tax_table: string | null;
  vacation_days_paid: number | null;
  vacation_days_saved: number | null;
}

interface SalaryOwnerBucket {
  gross: number;
  tax: number;
  extra_tax: number;
  benefit: number;
  net: number;
  count: number;
  suppliers: string[];
  payslips: SalaryPayslip[];
  projected_annual_gross: number;
  projected_annual_tax: number;
  projected_annual_extra_tax: number;
  effective_tax_rate: number;
  hint: string | null;
}

interface SalaryTaxSummary {
  year: number;
  by_owner: Record<string, SalaryOwnerBucket>;
  overall: {
    gross: number;
    tax: number;
    extra_tax: number;
    benefit: number;
    net: number;
    count: number;
  };
}

function SalarySummaryCard({ data }: { data: SalaryTaxSummary }) {
  const [expanded, setExpanded] = useState<string | null>(null);
  return (
    <Card title={`Lön & skatt ${data.year} — från uppladdade lönespec-PDFer`}>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4 text-sm">
        <div>
          <div className="text-xs uppercase text-slate-700">Total bruttolön</div>
          <div className="text-xl font-semibold text-slate-800">
            {formatSEK(data.overall.gross)}
          </div>
          <div className="text-xs text-slate-600 mt-0.5">
            {data.overall.count} lönespecs
          </div>
        </div>
        <div>
          <div className="text-xs uppercase text-slate-700">Skatt betald</div>
          <div className="text-xl font-semibold text-rose-700">
            {formatSEK(data.overall.tax)}
          </div>
          {data.overall.gross > 0 && (
            <div className="text-xs text-slate-600 mt-0.5">
              {((data.overall.tax / data.overall.gross) * 100).toFixed(1)} % effektiv
            </div>
          )}
        </div>
        <div>
          <div className="text-xs uppercase text-slate-700">Extra skatt</div>
          <div
            className={
              "text-xl font-semibold " +
              (data.overall.extra_tax > 0 ? "text-amber-700" : "text-slate-800")
            }
          >
            {formatSEK(data.overall.extra_tax)}
          </div>
          <div className="text-xs text-slate-600 mt-0.5">
            Frivilligt över tabell
          </div>
        </div>
        <div>
          <div className="text-xs uppercase text-slate-700">Netto totalt</div>
          <div className="text-xl font-semibold text-emerald-700">
            {formatSEK(data.overall.net)}
          </div>
        </div>
      </div>

      <div className="space-y-3">
        {Object.entries(data.by_owner)
          .sort(([, a], [, b]) => b.gross - a.gross)
          .map(([owner, b]) => {
            const isOpen = expanded === owner;
            const name = owner === "gemensamt" ? "Gemensamt" : owner;
            return (
              <div key={owner} className="border rounded-lg">
                <button
                  onClick={() => setExpanded(isOpen ? null : owner)}
                  className="w-full flex items-center gap-3 p-3 hover:bg-slate-50 text-left"
                >
                  <div className="flex-1">
                    <div className="font-medium">{name}</div>
                    <div className="text-xs text-slate-700">
                      {b.count} lönespecs · {b.suppliers.join(", ")}
                    </div>
                  </div>
                  <div className="text-right text-sm">
                    <div>
                      Brutto: <strong>{formatSEK(b.gross)}</strong>
                    </div>
                    <div className="text-rose-600">
                      Skatt: {formatSEK(b.tax)}{" "}
                      {b.effective_tax_rate > 0 && (
                        <span className="text-xs text-slate-600">
                          ({(b.effective_tax_rate * 100).toFixed(1)} %)
                        </span>
                      )}
                    </div>
                  </div>
                </button>
                {isOpen && (
                  <div className="border-t px-4 pt-3 pb-4 space-y-3">
                    {b.hint && (
                      <div className="bg-amber-50 border border-amber-200 rounded p-2 text-xs text-amber-900">
                        💡 {b.hint}
                      </div>
                    )}
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
                      <div>
                        <div className="text-slate-700">Projekt. helår brutto</div>
                        <div className="font-semibold">{formatSEK(b.projected_annual_gross)}</div>
                      </div>
                      <div>
                        <div className="text-slate-700">Projekt. helår skatt</div>
                        <div className="font-semibold">{formatSEK(b.projected_annual_tax)}</div>
                      </div>
                      <div>
                        <div className="text-slate-700">Projekt. helår extra</div>
                        <div className="font-semibold">{formatSEK(b.projected_annual_extra_tax)}</div>
                      </div>
                      <div>
                        <div className="text-slate-700">Förmån totalt</div>
                        <div className="font-semibold">{formatSEK(b.benefit)}</div>
                      </div>
                    </div>
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="text-left text-xs uppercase text-slate-700 border-b">
                            <th className="py-1.5 pr-2">Datum</th>
                            <th className="py-1.5 pr-2">Arbetsgivare</th>
                            <th className="py-1.5 pr-2 text-right">Brutto</th>
                            <th className="py-1.5 pr-2 text-right">Skatt</th>
                            <th className="py-1.5 pr-2 text-right">Extra</th>
                            <th className="py-1.5 pr-2 text-right">Netto</th>
                            <th className="py-1.5 pr-2 text-right">Tabell</th>
                            <th className="py-1.5 pr-2 text-right">Sem</th>
                          </tr>
                        </thead>
                        <tbody>
                          {b.payslips
                            .slice()
                            .sort((a, b) => (a.paid_date < b.paid_date ? 1 : -1))
                            .map((p) => (
                              <tr key={p.upcoming_id} className="border-b last:border-b-0">
                                <td className="py-1 pr-2 text-slate-700 text-xs">
                                  {p.paid_date}
                                </td>
                                <td className="py-1 pr-2">{p.employer}</td>
                                <td className="py-1 pr-2 text-right">{formatSEK(p.gross)}</td>
                                <td className="py-1 pr-2 text-right text-rose-600">
                                  {formatSEK(p.tax)}
                                </td>
                                <td
                                  className={
                                    "py-1 pr-2 text-right " +
                                    (p.extra_tax > 0 ? "text-amber-700" : "text-slate-400")
                                  }
                                >
                                  {p.extra_tax > 0 ? formatSEK(p.extra_tax) : "—"}
                                </td>
                                <td className="py-1 pr-2 text-right text-emerald-700">
                                  {formatSEK(p.net)}
                                </td>
                                <td className="py-1 pr-2 text-right text-xs">
                                  {p.tax_table ?? "—"}
                                </td>
                                <td className="py-1 pr-2 text-right text-xs">
                                  {p.vacation_days_paid != null
                                    ? `${p.vacation_days_paid}/${p.vacation_days_saved ?? 0}`
                                    : "—"}
                                </td>
                              </tr>
                            ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
      </div>
    </Card>
  );
}
