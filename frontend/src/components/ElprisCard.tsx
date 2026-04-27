/**
 * ElprisCard — visualisering av elpris per timme för aktuell prisregion.
 *
 * Visas på /utility (förbrukning) — naturlig plats eftersom
 * eleven där tittar på sin elförbrukning. Tidigare låg den på Dashboard
 * men användes då som dekoration utan koppling till data.
 */
import { useQuery } from "@tanstack/react-query";
import { Zap } from "lucide-react";
import {
  Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { api } from "@/api/client";
import { Card } from "@/components/Card";

interface ElprisHour {
  start: string;
  end: string;
  sek_per_kwh: number;
  sek_per_kwh_inc_vat: number;
}

interface ElprisDay {
  date: string;
  zone: string;
  avg_sek_per_kwh_inc_vat: number;
  cheapest_hours: Array<{ start: string; end: string; sek_per_kwh_inc_vat: number }>;
  hours: ElprisHour[];
}

export function ElprisCard() {
  const elprisZone = (localStorage.getItem("elpris_zone") || "SE3") as
    "SE1" | "SE2" | "SE3" | "SE4";
  const elprisQ = useQuery({
    queryKey: ["elpris", "today", elprisZone],
    queryFn: () => api<ElprisDay>(`/elpris/today?zone=${elprisZone}`),
  });

  if (!elprisQ.data || elprisQ.data.hours.length === 0) return null;
  const data = elprisQ.data;

  return (
    <Card
      title={`Elpris idag — ${data.zone}`}
      action={
        <div className="flex items-center gap-2 text-xs">
          <span className="text-slate-700">Snitt</span>
          <span className="font-semibold">
            {(data.avg_sek_per_kwh_inc_vat * 100).toFixed(0)} öre/kWh
          </span>
          <select
            value={elprisZone}
            onChange={(e) => {
              localStorage.setItem("elpris_zone", e.target.value);
              location.reload();
            }}
            className="border rounded px-1.5 py-0.5 text-xs"
          >
            <option value="SE1">SE1</option>
            <option value="SE2">SE2</option>
            <option value="SE3">SE3</option>
            <option value="SE4">SE4</option>
          </select>
        </div>
      }
    >
      <ResponsiveContainer width="100%" height={160}>
        <BarChart
          data={data.hours.map((h) => ({
            hour: new Date(h.start).getHours(),
            öre: Math.round(h.sek_per_kwh_inc_vat * 100),
          }))}
        >
          <XAxis dataKey="hour" tick={{ fontSize: 11 }} />
          <YAxis tick={{ fontSize: 11 }} tickFormatter={(v) => `${v}`} />
          <Tooltip
            formatter={(v: number) => `${v} öre/kWh`}
            labelFormatter={(h) => `Timme ${h}:00`}
          />
          <Bar dataKey="öre" fill="#4f46e5" radius={[2, 2, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
      <div className="mt-2 text-xs text-slate-600">
        <Zap className="inline w-3.5 h-3.5 mr-1 text-amber-500" />
        Billigaste timmar:{" "}
        {data.cheapest_hours.map((h) => {
          const hr = new Date(h.start).getHours();
          return (
            <span key={h.start} className="mx-1 font-mono">
              {String(hr).padStart(2, "0")}:00 ({(h.sek_per_kwh_inc_vat * 100).toFixed(0)}öre)
            </span>
          );
        })}
      </div>
    </Card>
  );
}
