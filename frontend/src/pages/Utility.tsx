/**
 * Förbrukning — månadsvis historik över el, vatten, bredband,
 * uppvärmning och andra hushållskostnader som varierar.
 *
 * Datakälla: backend /utility/history som aggregerar Transaction-rader
 * och TransactionSplit-rader kategoriserade med utility-kategorier
 * (El, Vatten/Avgift, Uppvärmning, Bredband, Mobil, Renhållning…).
 *
 * Vision: senare utökas med PDF-parser för Hjo Energi + Telinet som
 * extraherar kWh-förbrukning, och Tibber Pulse API för realtidspris.
 * MVP:n ger redan värde: se totala kostnader per månad och identifiera
 * abnormaliter.
 */
import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Activity } from "lucide-react";
import { api, formatSEK } from "@/api/client";
import { Card } from "@/components/Card";

interface UtilityHistory {
  year: number;
  categories: string[];
  months: string[];
  by_category: Record<string, Record<string, number>>;
  category_totals: Record<string, number>;
  month_totals: Record<string, number>;
  summary: {
    year_total: number;
    avg_per_month: number;
    months_with_data: number;
  };
}

const SV_MONTHS_SHORT = [
  "jan", "feb", "mar", "apr", "maj", "jun",
  "jul", "aug", "sep", "okt", "nov", "dec",
];

const COLORS = [
  "bg-amber-400",
  "bg-sky-400",
  "bg-emerald-400",
  "bg-rose-400",
  "bg-indigo-400",
  "bg-orange-400",
  "bg-teal-400",
  "bg-violet-400",
];

export default function Utility() {
  const [year, setYear] = useState(new Date().getFullYear());
  const q = useQuery({
    queryKey: ["utility", year],
    queryFn: () => api<UtilityHistory>(`/utility/history?year=${year}`),
  });

  const data = q.data;
  const maxMonth = useMemo(() => {
    if (!data) return 0;
    return Math.max(...Object.values(data.month_totals), 1);
  }, [data]);

  return (
    <div className="p-3 md:p-6 space-y-4 md:space-y-5 max-w-6xl">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <h1 className="text-2xl font-semibold flex items-center gap-2">
          <Activity className="w-6 h-6" />
          Förbrukning
        </h1>
        <div className="flex items-center gap-2 text-sm">
          <label className="flex items-center gap-2">
            År
            <input
              type="number"
              value={year}
              onChange={(e) => setYear(Number(e.target.value))}
              className="border rounded px-2 py-1 w-24"
              min={2020}
              max={2100}
            />
          </label>
        </div>
      </div>

      {q.isLoading ? (
        <div className="text-sm text-slate-700">Laddar…</div>
      ) : !data || data.categories.length === 0 ? (
        <Card>
          <div className="text-sm text-slate-700">
            Ingen förbrukningsdata hittad för {year}. Säkerställ att
            transaktioner är kategoriserade som <em>El</em>,{" "}
            <em>Vatten/Avgift</em>, <em>Uppvärmning</em>, <em>Bredband</em>,{" "}
            <em>Mobil</em> eller <em>Renhållning</em>. Fakturor från Hjo
            Energi / Telinet parsas automatiskt på /upcoming med split-
            rader — de räknas också här.
          </div>
        </Card>
      ) : (
        <>
          {/* KPI-strip */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <Kpi
              label={`Total ${year}`}
              value={formatSEK(data.summary.year_total)}
              tone="good"
            />
            <Kpi
              label="Snitt per månad"
              value={
                data.summary.months_with_data > 0
                  ? formatSEK(data.summary.avg_per_month)
                  : "—"
              }
              hint={`${data.summary.months_with_data} månader med data`}
            />
            <Kpi
              label="Kategorier"
              value={String(data.categories.length)}
            />
            <Kpi
              label="Projekt. helår"
              value={
                data.summary.months_with_data > 0
                  ? formatSEK(data.summary.avg_per_month * 12)
                  : "—"
              }
              hint="Snitt × 12"
            />
          </div>

          {/* Månadsvis stapeldiagram */}
          <Card title={`Månadsvis förbrukning — ${year}`}>
            <div className="grid grid-cols-12 gap-2 items-end min-h-[160px]">
              {data.months.map((m, i) => {
                const total = data.month_totals[m] ?? 0;
                const height = total > 0 ? (total / maxMonth) * 150 : 0;
                return (
                  <div
                    key={m}
                    className="flex flex-col items-center justify-end gap-1"
                    title={`${SV_MONTHS_SHORT[i]} ${year}: ${formatSEK(total)}`}
                  >
                    <StackedMonthBar
                      data={data}
                      month={m}
                      heightPx={height}
                    />
                    <div className="text-xs text-slate-600 capitalize">
                      {SV_MONTHS_SHORT[i]}
                    </div>
                  </div>
                );
              })}
            </div>
            <div className="mt-4 flex flex-wrap gap-3 text-xs">
              {data.categories.map((c, i) => (
                <div key={c} className="flex items-center gap-1.5">
                  <span
                    className={`inline-block w-3 h-3 rounded ${
                      COLORS[i % COLORS.length]
                    }`}
                  />
                  {c}: <strong>{formatSEK(data.category_totals[c] ?? 0)}</strong>
                </div>
              ))}
            </div>
          </Card>

          {/* Tabell per kategori */}
          <Card title={`Tabell per kategori — ${year}`}>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs uppercase text-slate-700 border-b">
                    <th className="py-2 pr-3 sticky left-0 bg-white">Kategori</th>
                    {data.months.map((m, i) => (
                      <th
                        key={m}
                        className="py-2 px-2 text-right text-xs capitalize"
                      >
                        {SV_MONTHS_SHORT[i]}
                      </th>
                    ))}
                    <th className="py-2 pl-3 text-right font-semibold">Totalt</th>
                  </tr>
                </thead>
                <tbody>
                  {data.categories.map((c) => (
                    <tr key={c} className="border-b last:border-b-0">
                      <td className="py-1.5 pr-3 font-medium sticky left-0 bg-white">
                        {c}
                      </td>
                      {data.months.map((m) => {
                        const v = data.by_category[c]?.[m] ?? 0;
                        return (
                          <td
                            key={m}
                            className={
                              "py-1.5 px-2 text-right " +
                              (v === 0 ? "text-slate-400" : "")
                            }
                          >
                            {v === 0 ? "—" : formatSEK(v)}
                          </td>
                        );
                      })}
                      <td className="py-1.5 pl-3 text-right font-semibold">
                        {formatSEK(data.category_totals[c] ?? 0)}
                      </td>
                    </tr>
                  ))}
                  <tr className="bg-slate-50 font-semibold">
                    <td className="py-2 pr-3 sticky left-0 bg-slate-50">
                      Totalt
                    </td>
                    {data.months.map((m) => (
                      <td key={m} className="py-2 px-2 text-right">
                        {data.month_totals[m] > 0
                          ? formatSEK(data.month_totals[m])
                          : "—"}
                      </td>
                    ))}
                    <td className="py-2 pl-3 text-right">
                      {formatSEK(data.summary.year_total)}
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </Card>

          <Card title="Kommer snart">
            <ul className="text-sm text-slate-700 space-y-1 list-disc pl-5">
              <li>
                <strong>PDF-parser för Hjo Energi + Telinet</strong> som
                extraherar kWh-förbrukning utöver kr, så du kan följa
                faktisk förbrukning över tid.
              </li>
              <li>
                <strong>Tibber Pulse-integration</strong> — realtidspris
                och löpande förbrukning mot ditt API så du kan förutse
                nästa fakturas kostnad.
              </li>
              <li>
                <strong>År-mot-år-jämförelse</strong> för varje månad.
              </li>
            </ul>
          </Card>
        </>
      )}
    </div>
  );
}

function Kpi({
  label,
  value,
  hint,
  tone,
}: {
  label: string;
  value: string;
  hint?: string;
  tone?: "good" | "neutral";
}) {
  return (
    <div className="border rounded-lg p-3 bg-white">
      <div className="text-xs uppercase text-slate-700 tracking-wide">
        {label}
      </div>
      <div
        className={
          "text-xl font-semibold mt-1 " +
          (tone === "good" ? "text-emerald-700" : "text-slate-800")
        }
      >
        {value}
      </div>
      {hint && <div className="text-xs text-slate-600 mt-0.5">{hint}</div>}
    </div>
  );
}

function StackedMonthBar({
  data,
  month,
  heightPx,
}: {
  data: UtilityHistory;
  month: string;
  heightPx: number;
}) {
  const total = data.month_totals[month] ?? 0;
  if (total === 0) {
    return <div className="w-full h-0" />;
  }
  return (
    <div
      className="w-full rounded overflow-hidden flex flex-col"
      style={{ height: `${heightPx}px` }}
    >
      {data.categories.map((c, i) => {
        const v = data.by_category[c]?.[month] ?? 0;
        if (v === 0) return null;
        const pct = (v / total) * 100;
        return (
          <div
            key={c}
            className={COLORS[i % COLORS.length]}
            style={{ height: `${pct}%` }}
            title={`${c}: ${formatSEK(v)}`}
          />
        );
      })}
    </div>
  );
}
