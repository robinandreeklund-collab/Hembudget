import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { api, uploadFile } from "@/api/client";
import { Card } from "@/components/Card";
import type { Account } from "@/types/models";

// OBS: Decimal-fält (units, market_value, last_price osv.) serialiseras
// som STRING av Pydantic. Vi typar därför som 'number | string' och
// coerce:ar i format-helpers innan vi anropar .toFixed osv.
type Num = number | string;

interface Holding {
  id: number;
  account_id: number;
  fund_name: string;
  units: Num | null;
  market_value: Num;
  last_price: Num | null;
  change_pct: Num | null;
  change_value: Num | null;
  day_change_pct: Num | null;
  currency: string;
  last_update_date: string;
}

interface Summary {
  account_id: number;
  account_name: string;
  total_value: Num;
  available_cash: Num | null;
  fund_count: number;
  last_update_date: string | null;
  holdings: Holding[];
}

interface HistoryPoint {
  date: string;
  market_value: Num;
}

// Decimal-fält från Pydantic kommer som STRING i JSON. Vi coerce:ar så
// UI:t inte kraschar när det anropar .toLocaleString/.toFixed på en string.
function formatKr(n: number | string | null | undefined): string {
  if (n == null) return "—";
  const num = typeof n === "number" ? n : Number(n);
  if (!Number.isFinite(num)) return "—";
  return num.toLocaleString("sv-SE", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }) + " kr";
}

function formatPct(n: number | string | null | undefined): string {
  if (n == null) return "—";
  const num = typeof n === "number" ? n : Number(n);
  if (!Number.isFinite(num)) return "—";
  const sign = num >= 0 ? "+" : "";
  return sign + num.toFixed(2) + "%";
}

export default function FundsPage() {
  const qc = useQueryClient();
  const accountsQ = useQuery({
    queryKey: ["accounts"],
    queryFn: () => api<Account[]>("/accounts"),
  });
  const fundAccounts = useMemo(
    () =>
      (accountsQ.data ?? []).filter(
        (a) => a.type === "isk" || a.type === "savings",
      ),
    [accountsQ.data],
  );
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const activeId = selectedId ?? fundAccounts[0]?.id ?? null;

  const summaryQ = useQuery({
    queryKey: ["funds-summary", activeId],
    queryFn: () => api<Summary>(`/funds/${activeId}`),
    enabled: activeId != null,
  });
  const historyQ = useQuery({
    queryKey: ["funds-history", activeId],
    queryFn: () =>
      api<{ points: HistoryPoint[] }>(`/funds/${activeId}/history`),
    enabled: activeId != null,
  });

  const [image, setImage] = useState<File | null>(null);
  const [snapDate, setSnapDate] = useState<string>(
    new Date().toISOString().slice(0, 10),
  );
  const [parseResult, setParseResult] = useState<unknown>(null);
  const parseMut = useMutation({
    mutationFn: async () => {
      if (!image || activeId == null) throw new Error("Välj konto och bild");
      const form = new FormData();
      form.append("file", image);
      if (snapDate) form.append("snapshot_date", snapDate);
      return uploadFile(`/funds/${activeId}/parse-image`, form);
    },
    onSuccess: (data) => {
      setParseResult(data);
      qc.invalidateQueries({ queryKey: ["funds-summary", activeId] });
      qc.invalidateQueries({ queryKey: ["funds-history", activeId] });
      qc.invalidateQueries({ queryKey: ["balances"] });
    },
    onError: (err: Error) => setParseResult({ error: err.message }),
  });

  const summary = summaryQ.data;
  const history = historyQ.data?.points ?? [];

  return (
    <div className="p-3 md:p-6 space-y-4 md:space-y-5 max-w-5xl">
      <h1 className="text-2xl font-semibold">Fonder &amp; ISK</h1>

      {fundAccounts.length === 0 ? (
        <Card title="Inga fondkonton">
          <div className="text-sm text-slate-700">
            Importera först ett ISK-kontoutdrag via Importera-sidan — systemet
            upptäcker "ISK" i namnet och sätter rätt kontotyp automatiskt.
          </div>
        </Card>
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-2">
            {fundAccounts.map((a) => {
              const active = a.id === activeId;
              return (
                <button
                  key={a.id}
                  onClick={() => setSelectedId(a.id)}
                  className={
                    "px-3 py-1.5 rounded-full text-sm border " +
                    (active
                      ? "bg-brand-600 text-white border-brand-600"
                      : "bg-white text-slate-700 border-slate-200 hover:bg-slate-50")
                  }
                >
                  {a.name}
                </button>
              );
            })}
          </div>

          {summary && (
            <Card title={`${summary.account_name} — aktuella innehav`}>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
                <Kpi label="Totalt värde" value={formatKr(summary.total_value)} />
                <Kpi
                  label="Tillgängligt"
                  value={
                    summary.available_cash != null
                      ? formatKr(summary.available_cash)
                      : "—"
                  }
                />
                <Kpi label="Antal fonder" value={String(summary.fund_count)} />
                <Kpi
                  label="Senast uppdaterad"
                  value={summary.last_update_date ?? "—"}
                />
              </div>
              {summary.holdings.length === 0 ? (
                <div className="text-sm text-slate-700">
                  Inga innehav än. Ladda upp en skärmdump av fondvyn nedan.
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-left text-slate-600 border-b">
                        <th className="py-2 pr-2">Fond</th>
                        <th className="py-2 pr-2 text-right">Andelar</th>
                        <th className="py-2 pr-2 text-right">Kurs</th>
                        <th className="py-2 pr-2 text-right">Värde</th>
                        <th className="py-2 pr-2 text-right">Förändring</th>
                        <th className="py-2 pr-2 text-right">1 dag</th>
                      </tr>
                    </thead>
                    <tbody>
                      {summary.holdings.map((h) => {
                        // OBS: Decimal-fält kommer som STRING från backend,
                        // så Number()-cast innan vi anropar .toFixed().
                        const units = h.units != null ? Number(h.units) : null;
                        return (
                        <tr key={h.id} className="border-b last:border-b-0">
                          <td className="py-2 pr-2 font-medium">{h.fund_name}</td>
                          <td className="py-2 pr-2 text-right">
                            {units != null && Number.isFinite(units)
                              ? units.toFixed(2) + " st"
                              : "—"}
                          </td>
                          <td className="py-2 pr-2 text-right">
                            {formatKr(h.last_price)}
                          </td>
                          <td className="py-2 pr-2 text-right font-medium">
                            {formatKr(h.market_value)}
                          </td>
                          <td
                            className={
                              "py-2 pr-2 text-right " +
                              (Number(h.change_pct ?? 0) >= 0
                                ? "text-emerald-700"
                                : "text-rose-600")
                            }
                          >
                            {formatPct(h.change_pct)}
                            {h.change_value != null && (
                              <div className="text-xs text-slate-600">
                                {formatKr(h.change_value)}
                              </div>
                            )}
                          </td>
                          <td
                            className={
                              "py-2 pr-2 text-right " +
                              (Number(h.day_change_pct ?? 0) >= 0
                                ? "text-emerald-700"
                                : "text-rose-600")
                            }
                          >
                            {formatPct(h.day_change_pct)}
                          </td>
                        </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </Card>
          )}

          <Card title="Uppdatera med skärmdump (vision AI)">
            <div className="text-sm text-slate-700 mb-3">
              Logga in på bankens ISK-sida, ta en skärmdump av fondöversikten
              (så hela tabellen syns) och ladda upp den här. Gör det en gång
              per månad — historiken sparas så du kan följa utvecklingen per
              fond över tid.
            </div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
              <input
                type="file"
                accept="image/png,image/jpeg,application/pdf"
                onChange={(e) => setImage(e.target.files?.[0] ?? null)}
                className="md:col-span-2 border rounded px-2 py-1.5 text-sm"
              />
              <input
                type="date"
                value={snapDate}
                onChange={(e) => setSnapDate(e.target.value)}
                className="border rounded px-2 py-1.5 text-sm"
              />
            </div>
            <button
              className="mt-3 bg-brand-600 text-white px-4 py-2 rounded disabled:opacity-50"
              disabled={!image || activeId == null || parseMut.isPending}
              onClick={() => parseMut.mutate()}
            >
              {parseMut.isPending ? "Läser bilden…" : "Analysera & uppdatera"}
            </button>
            {parseResult !== null && (
              <pre className="mt-3 bg-slate-900 text-slate-100 text-xs p-3 rounded overflow-x-auto max-h-64">
                {JSON.stringify(parseResult, null, 2)}
              </pre>
            )}
          </Card>

          {history.length > 1 && (
            <Card title="Utveckling över tid (totalvärde)">
              <MiniLineChart points={history} />
            </Card>
          )}
        </>
      )}
    </div>
  );
}

function Kpi({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-xs text-slate-600 uppercase tracking-wide">
        {label}
      </div>
      <div className="text-xl font-semibold text-slate-800 mt-0.5">
        {value}
      </div>
    </div>
  );
}

function MiniLineChart({ points }: { points: HistoryPoint[] }) {
  if (points.length < 2) return null;
  const W = 600;
  const H = 160;
  const PAD = 8;
  // market_value kan vara string från Pydantic Decimal → Number-casta
  const values = points.map((p) => Number(p.market_value));
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const coords = points.map((_, i) => {
    const x = PAD + (i * (W - 2 * PAD)) / (points.length - 1);
    const y = H - PAD - ((values[i] - min) / range) * (H - 2 * PAD);
    return `${x},${y}`;
  });
  return (
    <div className="space-y-2">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-40">
        <polyline
          fill="none"
          stroke="#2563eb"
          strokeWidth="2"
          points={coords.join(" ")}
        />
        {points.map((_, i) => {
          const x = PAD + (i * (W - 2 * PAD)) / (points.length - 1);
          const y =
            H - PAD - ((values[i] - min) / range) * (H - 2 * PAD);
          return <circle key={i} cx={x} cy={y} r="3" fill="#2563eb" />;
        })}
      </svg>
      <div className="flex justify-between text-xs text-slate-600">
        <span>{points[0].date}</span>
        <span>{points[points.length - 1].date}</span>
      </div>
    </div>
  );
}
