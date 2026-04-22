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
