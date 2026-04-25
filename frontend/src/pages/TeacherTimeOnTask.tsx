import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowLeft, Clock } from "lucide-react";
import { api } from "@/api/client";

type Row = {
  step_id: number;
  step_title: string;
  module_id: number;
  module_title: string;
  n_completed: number;
  median_minutes: number | null;
  n_stuck: number;
};

export default function TeacherTimeOnTask() {
  const [rows, setRows] = useState<Row[]>([]);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api<Row[]>("/teacher/time-on-task")
      .then(setRows)
      .catch((e) => setErr(e instanceof Error ? e.message : String(e)));
  }, []);

  return (
    <div className="max-w-5xl mx-auto p-6 space-y-5">
      <Link
        to="/teacher"
        className="text-sm text-slate-600 hover:text-ink flex items-center gap-1"
      >
        <ArrowLeft className="w-4 h-4" /> Tillbaka
      </Link>
      <div className="flex items-center gap-2">
        <Clock className="w-6 h-6 text-brand-600" />
        <h1 className="text-2xl font-semibold text-slate-900">Time on task</h1>
      </div>
      <p className="text-sm text-slate-600">
        Medianlängd per steg över alla dina elever plus antal som har
        börjat men inte avslutat. Fastnat-kolumnen visar var eleverna
        behöver hjälp.
      </p>
      {err && (
        <div className="bg-rose-50 border border-rose-200 text-rose-700 text-sm rounded p-3">
          {err}
        </div>
      )}
      {rows.length === 0 && !err && (
        <div className="text-sm text-slate-500">
          Ingen data än — elever behöver öppna minst ett steg.
        </div>
      )}
      {rows.length > 0 && (
        <table className="w-full bg-white rounded-xl border border-slate-200 text-sm">
          <thead className="bg-slate-50 text-slate-700 text-left">
            <tr>
              <th className="px-3 py-2">Modul</th>
              <th className="px-3 py-2">Steg</th>
              <th className="px-3 py-2 text-right">Median-tid</th>
              <th className="px-3 py-2 text-right">Klara</th>
              <th className="px-3 py-2 text-right">Fastnat</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.step_id} className="border-t border-slate-100">
                <td className="px-3 py-2 text-slate-600">{r.module_title}</td>
                <td className="px-3 py-2 font-medium text-slate-900">
                  {r.step_title}
                </td>
                <td className="px-3 py-2 text-right">
                  {r.median_minutes != null
                    ? `${r.median_minutes} min`
                    : "—"}
                </td>
                <td className="px-3 py-2 text-right">{r.n_completed}</td>
                <td
                  className={`px-3 py-2 text-right ${
                    r.n_stuck > 0 ? "text-amber-700 font-semibold" : "text-slate-500"
                  }`}
                >
                  {r.n_stuck}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
