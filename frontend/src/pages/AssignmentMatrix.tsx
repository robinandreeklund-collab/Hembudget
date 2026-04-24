import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowLeft, CheckCircle2, Grid3x3, Hourglass, X, Minus } from "lucide-react";
import { api } from "@/api/client";

type Column = {
  title: string;
  kind: string;
  target_year_month: string | null;
};
type Cell = {
  assignment_id: number | null;
  status: "not_started" | "in_progress" | "completed" | "missing";
  progress: string | null;
};
type Row = {
  student_id: number;
  display_name: string;
  class_label: string | null;
  cells: Cell[];
};
type Matrix = { columns: Column[]; rows: Row[] };

export default function AssignmentMatrix() {
  const [data, setData] = useState<Matrix | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api<Matrix>("/teacher/assignments/matrix")
      .then(setData)
      .catch((e) => setErr(e instanceof Error ? e.message : String(e)));
  }, []);

  if (err) {
    return (
      <div className="p-6 text-rose-700 bg-rose-50 m-6 rounded">{err}</div>
    );
  }
  if (!data) return <div className="p-6 text-slate-500">Laddar…</div>;

  const { columns, rows } = data;

  return (
    <div className="p-6 max-w-none space-y-4">
      <Link
        to="/teacher"
        className="text-sm text-slate-600 hover:text-brand-700 flex items-center gap-1"
      >
        <ArrowLeft className="w-4 h-4" /> Lärarpanel
      </Link>

      <div className="flex items-center gap-2">
        <Grid3x3 className="w-6 h-6 text-brand-600" />
        <h1 className="text-2xl font-semibold">Klassöversikt</h1>
      </div>
      <p className="text-sm text-slate-600">
        Elever på rader, uppdrag i kolumner. Grön = klar, gul = pågår, grå =
        inte påbörjad, — = eleven har inte uppdraget.
      </p>

      {columns.length === 0 ? (
        <div className="bg-amber-50 border border-amber-200 rounded p-4 text-amber-800">
          Inga uppdrag skapade ännu.
        </div>
      ) : (
        <div className="overflow-auto border rounded-lg bg-white">
          <table className="text-sm">
            <thead>
              <tr className="bg-slate-50">
                <th className="sticky left-0 bg-slate-50 text-left p-2 min-w-40 border-r">
                  Elev
                </th>
                {columns.map((c, i) => (
                  <th
                    key={i}
                    title={`${c.title}${c.target_year_month ? ` (${c.target_year_month})` : ""}`}
                    className="p-2 text-left font-medium text-xs max-w-32 min-w-24 border-r"
                  >
                    <div className="truncate">{c.title}</div>
                    {c.target_year_month && (
                      <div className="text-slate-400 text-[10px]">
                        {c.target_year_month}
                      </div>
                    )}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.student_id} className="border-t hover:bg-slate-50">
                  <td className="sticky left-0 bg-white hover:bg-slate-50 p-2 border-r">
                    <Link
                      to={`/teacher/students/${r.student_id}`}
                      className="text-brand-700 hover:underline font-medium"
                    >
                      {r.display_name}
                    </Link>
                    {r.class_label && (
                      <div className="text-xs text-slate-500">
                        {r.class_label}
                      </div>
                    )}
                  </td>
                  {r.cells.map((cell, i) => (
                    <td
                      key={i}
                      title={cell.progress ?? ""}
                      className="p-2 border-r text-center"
                    >
                      <StatusPill status={cell.status} />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="text-xs text-slate-500">
        Hover på en cell för att se elevens status. Klicka på elevnamnet för
        detaljer.
      </div>
    </div>
  );
}

function StatusPill({ status }: { status: Cell["status"] }) {
  if (status === "completed") {
    return (
      <div className="inline-flex w-7 h-7 rounded-full bg-emerald-100 items-center justify-center">
        <CheckCircle2 className="w-4 h-4 text-emerald-600" />
      </div>
    );
  }
  if (status === "in_progress") {
    return (
      <div className="inline-flex w-7 h-7 rounded-full bg-amber-100 items-center justify-center">
        <Hourglass className="w-4 h-4 text-amber-600" />
      </div>
    );
  }
  if (status === "not_started") {
    return (
      <div className="inline-flex w-7 h-7 rounded-full bg-slate-100 items-center justify-center">
        <X className="w-4 h-4 text-slate-400" />
      </div>
    );
  }
  return (
    <div className="inline-flex w-7 h-7 rounded-full items-center justify-center">
      <Minus className="w-4 h-4 text-slate-300" />
    </div>
  );
}
