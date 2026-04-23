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
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Activity, Key, RefreshCw, Trash2, Upload, X, Zap } from "lucide-react";
import { api, formatSEK, getApiBase, getToken, uploadFile } from "@/api/client";
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
  readings?: Record<
    string,
    Record<string, { consumption: number; cost_kr: number; unit: string | null }>
  >;
  previous?: UtilityHistory;
  previous_readings?: UtilityHistory["readings"];
  yoy_diff?: Record<string, Record<string, number>>;
  yoy_summary?: { year_diff: number; avg_diff: number };
}

interface Reading {
  id: number;
  supplier: string;
  meter_type: string;
  period_start: string;
  period_end: string;
  consumption: number | null;
  consumption_unit: string | null;
  cost_kr: number;
  source: string;
  source_file: string | null;
  notes: string | null;
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
  const qc = useQueryClient();
  const [year, setYear] = useState(new Date().getFullYear());
  const [yoy, setYoy] = useState(false);
  const [breakdownCell, setBreakdownCell] = useState<{
    category: string;
    month: string;
  } | null>(null);
  const q = useQuery({
    queryKey: ["utility", year, yoy],
    queryFn: () =>
      api<UtilityHistory>(
        `/utility/history?year=${year}${yoy ? "&compare_previous_year=true" : ""}`,
      ),
  });
  const readingsQ = useQuery({
    queryKey: ["utility-readings", year],
    queryFn: () =>
      api<{ readings: Reading[] }>(`/utility/readings?year=${year}`),
  });
  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["utility", year, yoy] });
    qc.invalidateQueries({ queryKey: ["utility-readings", year] });
    qc.invalidateQueries({ queryKey: ["tibber-realtime"] });
  };

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
        <div className="flex items-center gap-3 text-sm">
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={yoy}
              onChange={(e) => setYoy(e.target.checked)}
            />
            Jämför mot föregående år
          </label>
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

      {/* Tibber real-time widget + PDF uploader (ovanför historiken) */}
      <TibberWidget />
      <UtilityPdfUploader onDone={invalidate} />
      <RescanExistingButton onDone={invalidate} />
      <TibberSettings onSync={invalidate} />

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
              hint={
                data.yoy_summary
                  ? `${data.yoy_summary.year_diff >= 0 ? "+" : ""}${formatSEK(data.yoy_summary.year_diff)} vs ${data.year - 1}`
                  : undefined
              }
            />
            <Kpi
              label="Snitt per månad"
              value={
                data.summary.months_with_data > 0
                  ? formatSEK(data.summary.avg_per_month)
                  : "—"
              }
              hint={
                data.yoy_summary
                  ? `${data.yoy_summary.avg_diff >= 0 ? "+" : ""}${formatSEK(data.yoy_summary.avg_diff)} vs ${data.year - 1}`
                  : `${data.summary.months_with_data} månader med data`
              }
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

          {/* Faktisk förbrukning i enheter (kWh/GB/m³) om sådan finns */}
          {data.readings && Object.keys(data.readings).length > 0 && (
            <Card title={`Faktisk förbrukning i enheter — ${year}`}>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-xs uppercase text-slate-700 border-b">
                      <th className="py-2 pr-3">Mätare</th>
                      {data.months.map((m, i) => (
                        <th key={m} className="py-2 px-2 text-right text-xs capitalize">
                          {SV_MONTHS_SHORT[i]}
                        </th>
                      ))}
                      <th className="py-2 pl-3 text-right font-semibold">Totalt</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(data.readings).map(([meter, perMonth]) => {
                      const total = Object.values(perMonth).reduce(
                        (s, v) => s + v.consumption, 0,
                      );
                      const unit = Object.values(perMonth).find((v) => v.unit)?.unit ?? "";
                      return (
                        <tr key={meter} className="border-b last:border-b-0">
                          <td className="py-1.5 pr-3 font-medium">
                            {meter} {unit && <span className="text-xs text-slate-600">({unit})</span>}
                          </td>
                          {data.months.map((m) => {
                            const v = perMonth[m]?.consumption ?? 0;
                            return (
                              <td
                                key={m}
                                className={
                                  "py-1.5 px-2 text-right " +
                                  (v === 0 ? "text-slate-400" : "")
                                }
                              >
                                {v === 0 ? "—" : v.toFixed(0)}
                              </td>
                            );
                          })}
                          <td className="py-1.5 pl-3 text-right font-semibold">
                            {total.toFixed(0)} {unit}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </Card>
          )}

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
                              (v === 0
                                ? "text-slate-400"
                                : "cursor-pointer hover:bg-brand-50 hover:text-brand-700")
                            }
                            onClick={() => {
                              if (v > 0) setBreakdownCell({ category: c, month: m });
                            }}
                            title={v > 0 ? "Klicka för att se vad som ingår" : undefined}
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

          {/* YoY per kategori */}
          {data.yoy_diff && Object.keys(data.yoy_diff).length > 0 && (
            <Card title={`Y/Y-diff per kategori (${year} vs ${year - 1})`}>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-xs uppercase text-slate-700 border-b">
                      <th className="py-2 pr-3">Kategori</th>
                      {data.months.map((m, i) => (
                        <th key={m} className="py-2 px-2 text-right text-xs capitalize">
                          {SV_MONTHS_SHORT[i]}
                        </th>
                      ))}
                      <th className="py-2 pl-3 text-right font-semibold">Totalt</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(data.yoy_diff).map(([cat, perMonth]) => {
                      const total = Object.values(perMonth).reduce(
                        (s, v) => s + v, 0,
                      );
                      return (
                        <tr key={cat} className="border-b last:border-b-0">
                          <td className="py-1.5 pr-3 font-medium">{cat}</td>
                          {data.months.map((m) => {
                            const v = perMonth[m] ?? 0;
                            return (
                              <td
                                key={m}
                                className={
                                  "py-1.5 px-2 text-right " +
                                  (v > 0 ? "text-rose-600" : v < 0 ? "text-emerald-700" : "text-slate-400")
                                }
                              >
                                {v === 0 ? "—" : (v > 0 ? "+" : "") + formatSEK(v)}
                              </td>
                            );
                          })}
                          <td
                            className={
                              "py-1.5 pl-3 text-right font-semibold " +
                              (total > 0 ? "text-rose-600" : total < 0 ? "text-emerald-700" : "")
                            }
                          >
                            {total === 0 ? "—" : (total > 0 ? "+" : "") + formatSEK(total)}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              <div className="mt-2 text-xs text-slate-700">
                <span className="text-rose-600">Röd</span> = dyrare än förra året.{" "}
                <span className="text-emerald-700">Grön</span> = billigare.
              </div>
            </Card>
          )}

          {/* Lista over UtilityReading-rader (PDF / Tibber / manuellt) */}
          {readingsQ.data && readingsQ.data.readings.length > 0 && (
            <Card title={`Läsningar från fakturor & Tibber (${readingsQ.data.readings.length})`}>
              <ReadingsList
                readings={readingsQ.data.readings}
                onDelete={(id) => {
                  if (confirm("Ta bort denna läsning?")) {
                    api(`/utility/readings/${id}`, { method: "DELETE" }).then(
                      invalidate,
                    );
                  }
                }}
                onOpen={(id) => {
                  const token = getToken();
                  fetch(`${getApiBase()}/utility/readings/${id}/source`, {
                    headers: token ? { Authorization: `Bearer ${token}` } : {},
                  })
                    .then((r) => {
                      if (!r.ok) throw new Error("Filen saknas");
                      return r.blob();
                    })
                    .then((b) => window.open(URL.createObjectURL(b), "_blank"))
                    .catch((e) => alert(String(e.message ?? e)));
                }}
                onReparse={(id) => {
                  api<{ supplier: string; cost_kr: number; consumption: number | null; consumption_unit: string | null; detected_format: string }>(
                    `/utility/readings/${id}/reparse`,
                    { method: "POST" },
                  )
                    .then((res) => {
                      alert(
                        `Parsade om: ${res.supplier} · ${res.detected_format}\n` +
                        `Kostnad: ${res.cost_kr} kr\n` +
                        (res.consumption != null
                          ? `Förbrukning: ${res.consumption} ${res.consumption_unit}`
                          : "Ingen förbrukning extraherad"),
                      );
                      invalidate();
                    })
                    .catch((e: Error) => alert("Fel: " + e.message));
                }}
              />
            </Card>
          )}
        </>
      )}
      {breakdownCell && (
        <BreakdownModal
          category={breakdownCell.category}
          month={breakdownCell.month}
          onClose={() => setBreakdownCell(null)}
          onUpdated={() => {
            qc.invalidateQueries({ queryKey: ["utility", year, yoy] });
            qc.invalidateQueries({ queryKey: ["utility-readings", year] });
          }}
        />
      )}
    </div>
  );
}

function ReadingsList({
  readings,
  onDelete,
  onOpen,
  onReparse,
}: {
  readings: Reading[];
  onDelete: (id: number) => void;
  onOpen: (id: number) => void;
  onReparse: (id: number) => void;
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-xs uppercase text-slate-700 border-b">
            <th className="py-2 pr-3">Leverantör</th>
            <th className="py-2 pr-3">Typ</th>
            <th className="py-2 pr-3">Period</th>
            <th className="py-2 pr-3 text-right">Förbrukning</th>
            <th className="py-2 pr-3 text-right">Kostnad</th>
            <th className="py-2 pr-3">Källa</th>
            <th className="py-2 pr-3 text-right w-40">Åtgärder</th>
          </tr>
        </thead>
        <tbody>
          {readings.map((r) => (
            <tr key={r.id} className="border-b last:border-b-0">
              <td className="py-1.5 pr-3 font-medium">{r.supplier}</td>
              <td className="py-1.5 pr-3 text-slate-700">{r.meter_type}</td>
              <td className="py-1.5 pr-3 text-slate-700 text-xs">
                {r.period_start} — {r.period_end}
              </td>
              <td className="py-1.5 pr-3 text-right">
                {r.consumption != null
                  ? `${r.consumption.toFixed(1)} ${r.consumption_unit ?? ""}`
                  : "—"}
              </td>
              <td className="py-1.5 pr-3 text-right font-medium">
                {formatSEK(r.cost_kr)}
              </td>
              <td className="py-1.5 pr-3 text-xs text-slate-600">
                {r.source}
              </td>
              <td className="py-1.5 pr-3 text-right">
                <div className="inline-flex items-center gap-2">
                  {r.source_file && (
                    <>
                      <button
                        onClick={() => onOpen(r.id)}
                        className="text-brand-600 hover:text-brand-800 text-xs"
                        title="Öppna original-PDF:en"
                      >
                        📎 Öppna
                      </button>
                      <button
                        onClick={() => onReparse(r.id)}
                        className="text-emerald-700 hover:text-emerald-900 text-xs"
                        title="Parsa om PDF:en → uppdatera reading (rör inte tx/upcoming)"
                      >
                        <RefreshCw className="w-3.5 h-3.5 inline" /> Parsa om
                      </button>
                    </>
                  )}
                  <button
                    onClick={() => onDelete(r.id)}
                    className="text-slate-600 hover:text-rose-600"
                    title="Ta bort"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

interface ParsePreview {
  supplier: string;
  meter_type: string;
  period_start: string | null;
  period_end: string | null;
  consumption: number | null;
  consumption_unit: string | null;
  cost_kr: number | null;
  saved_id?: number;
  parse_errors: string[];
}

function RescanExistingButton({ onDone }: { onDone: () => void }) {
  const mut = useMutation({
    mutationFn: () =>
      api<{
        scanned: number;
        parsed_ok: number;
        created: number;
        skipped_duplicate: number;
        skipped_no_data: number;
        errors: Array<{ upcoming_id: number; error: string }>;
      }>("/utility/rescan-existing", { method: "POST" }),
    onSuccess: onDone,
  });
  return (
    <Card title="Scanna befintliga fakturor">
      <div className="text-sm text-slate-700 mb-2">
        Gå igenom alla PDF-fakturor som redan finns i systemet (från
        tidigare <a href="/upcoming" className="text-brand-600 underline">
        /upcoming</a>-uppladdningar) och extrahera förbrukningsdata.
        Idempotent — dubletter hoppas över via filsökväg. Kör när du
        vill bygga historik utan att ladda upp PDF:erna igen.
      </div>
      <div className="flex items-center gap-3">
        <button
          onClick={() => mut.mutate()}
          disabled={mut.isPending}
          className="bg-slate-700 text-white px-4 py-2 rounded text-sm disabled:opacity-50 inline-flex items-center gap-2"
        >
          <RefreshCw className={"w-4 h-4 " + (mut.isPending ? "animate-spin" : "")} />
          {mut.isPending ? "Scannar…" : "Scanna befintliga fakturor"}
        </button>
        {mut.data && (
          <div className="text-xs text-slate-700">
            Scannade <strong>{mut.data.scanned}</strong>,{" "}
            <span className="text-emerald-700">{mut.data.created} nya läsningar skapade</span>
            {mut.data.skipped_duplicate > 0 &&
              `, ${mut.data.skipped_duplicate} redan scannade`}
            {mut.data.skipped_no_data > 0 &&
              `, ${mut.data.skipped_no_data} saknar period/kostnad`}
            {mut.data.errors.length > 0 &&
              `, ${mut.data.errors.length} fel`}
          </div>
        )}
      </div>
      {mut.data && mut.data.errors.length > 0 && (
        <div className="mt-2 text-xs text-rose-600 bg-rose-50 rounded p-2 max-h-32 overflow-y-auto">
          {mut.data.errors.slice(0, 10).map((e, i) => (
            <div key={i}>
              #{e.upcoming_id}: {e.error}
            </div>
          ))}
          {mut.data.errors.length > 10 && (
            <div>… och {mut.data.errors.length - 10} till</div>
          )}
        </div>
      )}
    </Card>
  );
}

function UtilityPdfUploader({ onDone }: { onDone: () => void }) {
  const [results, setResults] = useState<
    Array<{ file: string; ok: boolean; data?: ParsePreview; error?: string }>
  >([]);
  const [uploading, setUploading] = useState(false);

  async function upload(files: File[]) {
    if (files.length === 0) return;
    setUploading(true);
    setResults([]);
    const out: typeof results = [];
    for (const file of files) {
      try {
        const form = new FormData();
        form.append("file", file);
        form.append("save", "true");
        const data = await uploadFile<ParsePreview>(
          "/utility/parse-pdf",
          form,
        );
        out.push({ file: file.name, ok: true, data });
      } catch (e) {
        out.push({
          file: file.name,
          ok: false,
          error: String((e as Error).message ?? e),
        });
      }
    }
    setResults(out);
    setUploading(false);
    onDone();
  }

  return (
    <Card title="Ladda upp energi-/bredbandsfaktura (PDF)">
      <div className="text-sm text-slate-700 mb-2">
        Stöd: <strong>Hjo Energi</strong>, <strong>Telinet</strong>,{" "}
        <strong>Tibber</strong>, <strong>Vattenfall</strong>, <strong>E.ON</strong>,{" "}
        <strong>Fortum</strong> + generisk extraktion av kWh/GB/m³ + kostnad.
        Parsade rader syns i tabellen "Läsningar från fakturor & Tibber" nedan.
      </div>
      <label className="flex items-center gap-2 border-2 border-dashed border-slate-300 rounded p-4 cursor-pointer hover:bg-slate-50">
        <Upload className="w-5 h-5 text-slate-600" />
        <span className="text-sm">
          Välj PDF-filer (flera går att ladda upp samtidigt)
        </span>
        <input
          type="file"
          multiple
          accept=".pdf,application/pdf"
          className="hidden"
          onChange={(e) =>
            e.target.files && upload(Array.from(e.target.files))
          }
        />
      </label>
      {uploading && (
        <div className="text-xs text-slate-600 mt-2">Parsar…</div>
      )}
      {results.length > 0 && (
        <div className="mt-3 space-y-1">
          {results.map((r, i) => (
            <div
              key={i}
              className={
                "text-xs rounded p-2 border " +
                (r.ok
                  ? "bg-emerald-50 border-emerald-200 text-emerald-800"
                  : "bg-rose-50 border-rose-200 text-rose-700")
              }
            >
              {r.ok ? (
                <>
                  ✓ <strong>{r.file}</strong> → {r.data?.supplier} ({r.data?.meter_type}),{" "}
                  {r.data?.period_start}
                  {r.data?.consumption != null && (
                    <> · {r.data.consumption.toFixed(1)} {r.data.consumption_unit}</>
                  )}
                  , {formatSEK(r.data?.cost_kr ?? 0)}
                </>
              ) : (
                <>
                  ✗ <strong>{r.file}</strong>: {r.error}
                </>
              )}
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

interface TibberHome {
  id: string;
  address: string;
  currency: string;
  has_pulse: boolean;
}

function TibberSettings({ onSync }: { onSync: () => void }) {
  const qc = useQueryClient();
  const tokenQ = useQuery({
    queryKey: ["setting", "tibber_api_token"],
    queryFn: async () => {
      try {
        const r = await api<{ value: string | null }>(
          "/settings/tibber_api_token",
        );
        return r.value ?? "";
      } catch {
        return "";
      }
    },
  });
  const [tokenInput, setTokenInput] = useState("");
  const [homes, setHomes] = useState<TibberHome[]>([]);
  const [testError, setTestError] = useState<string | null>(null);

  const setMut = useMutation({
    mutationFn: (value: string) =>
      api(`/settings/tibber_api_token`, {
        method: "PUT",
        body: JSON.stringify({ value }),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["setting", "tibber_api_token"] });
      setTokenInput("");
    },
  });
  const testMut = useMutation({
    mutationFn: () =>
      api<{ homes: TibberHome[] }>("/utility/tibber/test", { method: "POST" }),
    onSuccess: (data) => {
      setHomes(data.homes ?? []);
      setTestError(null);
    },
    onError: (e: Error) => {
      setTestError(e.message);
      setHomes([]);
    },
  });
  const syncMut = useMutation({
    mutationFn: () =>
      api<{ saved: number; updated: number; home_address: string }>(
        "/utility/tibber/sync?months=24",
        { method: "POST" },
      ),
    onSuccess: onSync,
  });

  const hasToken = (tokenQ.data ?? "").length > 0;

  return (
    <Card title="Tibber-integration">
      <div className="text-sm text-slate-700 mb-3">
        Synka månadsförbrukning + realtidspris från ditt Tibber-konto.
        Generera en token på{" "}
        <a
          href="https://developer.tibber.com/settings/access-token"
          target="_blank"
          rel="noreferrer"
          className="text-brand-600 underline"
        >
          developer.tibber.com
        </a>
        .
      </div>
      {!hasToken ? (
        <div className="flex gap-2 text-sm">
          <div className="flex-1 relative">
            <Key className="w-4 h-4 absolute left-2 top-1/2 -translate-y-1/2 text-slate-600" />
            <input
              type="password"
              value={tokenInput}
              onChange={(e) => setTokenInput(e.target.value)}
              placeholder="Tibber API-token (sha-256-sträng)"
              className="border rounded pl-8 pr-2 py-1.5 w-full font-mono text-xs"
            />
          </div>
          <button
            onClick={() => tokenInput.trim() && setMut.mutate(tokenInput.trim())}
            disabled={!tokenInput.trim() || setMut.isPending}
            className="bg-brand-600 text-white px-4 py-1.5 rounded text-sm disabled:opacity-50"
          >
            Spara token
          </button>
        </div>
      ) : (
        <div className="space-y-2 text-sm">
          <div className="flex items-center gap-2">
            <Key className="w-4 h-4 text-emerald-600" />
            <span className="text-emerald-700">Token sparad</span>
            <button
              onClick={() => {
                if (confirm("Ta bort token?")) {
                  setMut.mutate("");
                  setHomes([]);
                }
              }}
              className="text-xs text-rose-600 hover:underline ml-auto"
            >
              Ta bort
            </button>
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => testMut.mutate()}
              disabled={testMut.isPending}
              className="bg-slate-700 text-white px-3 py-1.5 rounded text-xs disabled:opacity-50"
            >
              {testMut.isPending ? "Testar…" : "Testa + hämta hem"}
            </button>
            <button
              onClick={() => syncMut.mutate()}
              disabled={syncMut.isPending}
              className="bg-brand-600 text-white px-3 py-1.5 rounded text-xs disabled:opacity-50 inline-flex items-center gap-1.5"
            >
              <RefreshCw className={"w-3.5 h-3.5 " + (syncMut.isPending ? "animate-spin" : "")} />
              {syncMut.isPending ? "Synkar…" : "Synka 24 månader"}
            </button>
          </div>
          {testError && (
            <div className="text-xs text-rose-600">{testError}</div>
          )}
          {syncMut.data && (
            <div className="text-xs text-emerald-700">
              ✓ {syncMut.data.saved} nya + {syncMut.data.updated} uppdaterade
              läsningar från {syncMut.data.home_address}
            </div>
          )}
          {homes.length > 0 && (
            <div className="mt-2 text-xs">
              <div className="text-slate-700 font-medium mb-1">Dina hem:</div>
              {homes.map((h) => (
                <div key={h.id} className="border rounded p-2 mb-1 bg-slate-50">
                  <div>{h.address}</div>
                  <div className="text-slate-600">
                    {h.has_pulse ? "✓ Pulse aktiv (realtid)" : "Pulse saknas"} ·{" "}
                    {h.currency}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </Card>
  );
}

interface RealtimeResponse {
  home: { id: string; address: string; has_pulse: boolean };
  realtime: {
    power_watts: number | null;
    consumption_today_kwh: number | null;
    cost_today_kr: number | null;
    currency: string;
    timestamp: string | null;
  } | null;
  prices: {
    current?: { total: number; level: string; currency: string };
    today?: Array<{ startsAt: string; total: number; level: string }>;
    tomorrow?: Array<{ startsAt: string; total: number; level: string }>;
  };
}

function TibberWidget() {
  const q = useQuery({
    queryKey: ["tibber-realtime"],
    queryFn: () => api<RealtimeResponse>("/utility/tibber/realtime"),
    refetchInterval: 60_000, // 1 min
    retry: false,
  });
  if (q.isError || !q.data) return null;
  const d = q.data;
  const cur = d.prices?.current;
  return (
    <Card title={`Tibber realtid — ${d.home.address}`}>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
        <div>
          <div className="text-xs uppercase text-slate-700">Pris just nu</div>
          <div className="text-xl font-semibold">
            {cur ? `${cur.total.toFixed(2)} ${cur.currency}/kWh` : "—"}
          </div>
          {cur && (
            <div
              className={
                "text-xs mt-0.5 " +
                (cur.level === "VERY_CHEAP" || cur.level === "CHEAP"
                  ? "text-emerald-600"
                  : cur.level === "EXPENSIVE" || cur.level === "VERY_EXPENSIVE"
                  ? "text-rose-600"
                  : "text-slate-600")
              }
            >
              {cur.level}
            </div>
          )}
        </div>
        <div>
          <div className="text-xs uppercase text-slate-700">Förbr. idag</div>
          <div className="text-xl font-semibold">
            {d.realtime?.consumption_today_kwh != null
              ? `${d.realtime.consumption_today_kwh.toFixed(1)} kWh`
              : "—"}
          </div>
        </div>
        <div>
          <div className="text-xs uppercase text-slate-700">Kostnad idag</div>
          <div className="text-xl font-semibold">
            {d.realtime?.cost_today_kr != null
              ? formatSEK(d.realtime.cost_today_kr)
              : "—"}
          </div>
        </div>
        <div>
          <div className="text-xs uppercase text-slate-700">Pulse</div>
          <div className="text-xl font-semibold flex items-center gap-1.5">
            <Zap
              className={
                "w-5 h-5 " +
                (d.home.has_pulse ? "text-emerald-600" : "text-slate-400")
              }
            />
            {d.home.has_pulse ? "Ansluten" : "Ej ansluten"}
          </div>
        </div>
      </div>
    </Card>
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

interface BreakdownItem {
  type: "transaction" | "split";
  id: number;
  transaction_id?: number;
  date: string;
  amount: number;
  description: string;
  normalized_merchant: string | null;
  account_id: number;
  account_name: string;
  can_move: boolean;
  upcoming_id: number | null;
  has_invoice_pdf: boolean;
  reading_id: number | null;
}

interface BreakdownData {
  category: string;
  month: string;
  total: number;
  items: BreakdownItem[];
}

function BreakdownModal({
  category,
  month,
  onClose,
  onUpdated,
}: {
  category: string;
  month: string;
  onClose: () => void;
  onUpdated: () => void;
}) {
  const qc = useQueryClient();
  const breakdownQ = useQuery({
    queryKey: ["utility-breakdown", category, month],
    queryFn: () =>
      api<BreakdownData>(
        `/utility/breakdown?category=${encodeURIComponent(category)}&month=${month}`,
      ),
  });
  const moveMut = useMutation({
    mutationFn: (p: { tx_id: number; new_date: string }) =>
      api(`/transactions/${p.tx_id}`, {
        method: "PATCH",
        body: JSON.stringify({ date: p.new_date, create_rule: false }),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["utility-breakdown", category, month] });
      onUpdated();
    },
  });

  const data = breakdownQ.data;

  return (
    <div className="fixed inset-0 bg-black/40 flex items-start justify-center z-50 p-4 overflow-y-auto">
      <div className="bg-white rounded-lg shadow-xl max-w-4xl w-full my-8">
        <div className="flex items-center justify-between p-4 border-b">
          <div>
            <h2 className="text-lg font-semibold">
              {category} — {month}
            </h2>
            {data && (
              <div className="text-sm text-slate-700 mt-0.5">
                {data.items.length} poster · totalt {formatSEK(data.total)}
              </div>
            )}
          </div>
          <button onClick={onClose} className="text-slate-600 hover:text-slate-900">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-4">
          {breakdownQ.isLoading ? (
            <div className="text-sm text-slate-700">Laddar…</div>
          ) : !data || data.items.length === 0 ? (
            <div className="text-sm text-slate-700">Inga poster hittade.</div>
          ) : (
            <div className="space-y-2">
              <div className="text-xs text-slate-700 mb-2">
                Klicka <strong>"Flytta"</strong> för att byta månad på en
                transaktion (t.ex. om betalningen gjordes i mars men avser
                februari). Splits följer transaktionens datum — flytta
                hela transaktionen istället.
              </div>
              {data.items.map((item) => (
                <BreakdownRow
                  key={`${item.type}-${item.id}`}
                  item={item}
                  onMove={(newDate) => {
                    const txId =
                      item.type === "transaction" ? item.id : item.transaction_id;
                    if (txId) moveMut.mutate({ tx_id: txId, new_date: newDate });
                  }}
                  moving={moveMut.isPending}
                  onReparsed={() => {
                    qc.invalidateQueries({
                      queryKey: ["utility-breakdown", category, month],
                    });
                    onUpdated();
                  }}
                />
              ))}
              {moveMut.error && (
                <div className="text-xs text-rose-600 mt-2">
                  Fel: {(moveMut.error as Error).message}
                </div>
              )}
            </div>
          )}
        </div>

        <div className="flex justify-end p-4 border-t">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded border border-slate-300 bg-white text-sm"
          >
            Stäng
          </button>
        </div>
      </div>
    </div>
  );
}

function BreakdownRow({
  item,
  onMove,
  moving,
  onReparsed,
}: {
  item: BreakdownItem;
  onMove: (newDate: string) => void;
  moving: boolean;
  onReparsed: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [newDate, setNewDate] = useState(item.date);
  const [reparsing, setReparsing] = useState(false);

  function openInvoice() {
    if (!item.upcoming_id) return;
    const token = getToken();
    fetch(`${getApiBase()}/upcoming/${item.upcoming_id}/source`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
      .then((r) => {
        if (!r.ok) throw new Error("Filen saknas");
        return r.blob();
      })
      .then((b) => window.open(URL.createObjectURL(b), "_blank"))
      .catch((e) => alert(String(e.message ?? e)));
  }

  async function reparseInvoice() {
    if (!item.upcoming_id) return;
    setReparsing(true);
    try {
      const res = await api<{
        action: "created" | "updated";
        reading_id: number;
        detected_format: string;
      }>(`/utility/parse-upcoming/${item.upcoming_id}`, { method: "POST" });
      alert(
        `${res.action === "created" ? "Skapade" : "Uppdaterade"} utility-läsning #${res.reading_id}\n` +
        `Format: ${res.detected_format}`,
      );
      onReparsed();
    } catch (e) {
      alert("Fel: " + (e as Error).message);
    } finally {
      setReparsing(false);
    }
  }

  return (
    <div className="border rounded p-2 bg-white">
      <div className="flex items-start gap-3 text-sm">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-medium">{item.description}</span>
            {item.type === "split" && (
              <span className="text-xs bg-slate-100 text-slate-700 px-1.5 py-0.5 rounded">
                split
              </span>
            )}
            {item.has_invoice_pdf && (
              <span className="text-xs bg-emerald-100 text-emerald-700 px-1.5 py-0.5 rounded">
                PDF
              </span>
            )}
            {item.reading_id != null && (
              <span
                className="text-xs bg-brand-100 text-brand-700 px-1.5 py-0.5 rounded"
                title={`Kopplad till utility-läsning #${item.reading_id}`}
              >
                utility
              </span>
            )}
          </div>
          <div className="text-xs text-slate-600 mt-0.5">
            {item.date} · {item.account_name}
          </div>
        </div>
        <div className="text-right font-semibold shrink-0">
          {formatSEK(item.amount)}
        </div>
        {item.has_invoice_pdf && (
          <button
            onClick={openInvoice}
            className="text-xs text-brand-600 hover:underline shrink-0"
            title="Öppna original-fakturan i ny flik"
          >
            📎 Faktura
          </button>
        )}
        {item.has_invoice_pdf && (
          <button
            onClick={reparseInvoice}
            disabled={reparsing}
            className="text-xs text-emerald-700 hover:text-emerald-900 disabled:opacity-50 shrink-0 inline-flex items-center gap-1"
            title={
              item.reading_id != null
                ? "Kör parsern igen och uppdatera utility-datan (rör inte tx)"
                : "Skapa utility-läsning från fakturan"
            }
          >
            <RefreshCw className={"w-3 h-3 " + (reparsing ? "animate-spin" : "")} />
            {reparsing
              ? "Parsar…"
              : item.reading_id != null
              ? "Parsa om"
              : "Skapa utility"}
          </button>
        )}
        {item.can_move ? (
          <button
            onClick={() => setEditing(!editing)}
            className="text-xs text-brand-600 hover:underline shrink-0"
          >
            {editing ? "Avbryt" : "Flytta"}
          </button>
        ) : (
          <span className="text-xs text-slate-500 shrink-0" title="Följer transaktionens datum">
            —
          </span>
        )}
      </div>
      {editing && (
        <div className="mt-2 pt-2 border-t bg-slate-50 -mx-2 px-2 pb-2 flex items-end gap-2">
          <label className="flex-1">
            <div className="text-xs text-slate-700 mb-0.5">Nytt datum</div>
            <input
              type="date"
              value={newDate}
              onChange={(e) => setNewDate(e.target.value)}
              className="border rounded px-2 py-1 text-sm w-full"
            />
          </label>
          <button
            onClick={() => {
              if (newDate !== item.date) {
                onMove(newDate);
                setEditing(false);
              }
            }}
            disabled={moving || newDate === item.date}
            className="bg-brand-600 text-white px-3 py-1.5 rounded text-xs disabled:opacity-50"
          >
            {moving ? "Flyttar…" : "Spara"}
          </button>
        </div>
      )}
    </div>
  );
}
