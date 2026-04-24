import { useEffect, useState } from "react";
import { CheckCircle2, Hourglass, Users, XCircle } from "lucide-react";

/**
 * Animerad lärar-klassöversikt. Elever × uppdrag, statusen ändras från
 * "ej påbörjad" till "pågår" till "klar" cykliskt.
 */
export default function TeacherDemo() {
  const [tick, setTick] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setTick((x) => (x + 1) % 4), 2200);
    return () => clearInterval(t);
  }, []);

  const students = ["Anna", "Bosse", "Carla", "Didrik"];
  const assignments = ["Budget", "Dokument", "Spara 2 000 kr"];

  // Status per (student, uppdrag) i 4 tidslägen
  const matrix = [
    // tick=0: alla i början
    [["-", "-", "-"], ["-", "-", "-"], ["-", "-", "-"], ["-", "-", "-"]],
    // tick=1
    [["✓", "•", "-"], ["•", "-", "-"], ["-", "-", "-"], ["-", "-", "-"]],
    // tick=2
    [["✓", "✓", "•"], ["✓", "•", "-"], ["•", "-", "-"], ["-", "-", "-"]],
    // tick=3
    [["✓", "✓", "✓"], ["✓", "✓", "•"], ["✓", "•", "-"], ["•", "-", "-"]],
  ];

  return (
    <div className="bg-white rounded-2xl shadow-xl border border-slate-200 p-5 h-full min-h-[380px]">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2 text-sm font-semibold text-slate-700">
          <Users className="w-4 h-4 text-brand-600" /> Klassöversikt 9A
        </div>
        <div className="text-xs text-slate-500">live</div>
      </div>

      <table className="w-full text-xs">
        <thead>
          <tr className="text-slate-500">
            <th className="text-left pb-2">Elev</th>
            {assignments.map((a) => (
              <th key={a} className="pb-2 font-medium">{a}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {students.map((s, i) => (
            <tr
              key={s}
              className="border-t"
              style={{ animation: `fadeup 0.5s ${i * 0.1}s both` }}
            >
              <td className="py-2 font-medium text-slate-700">{s}</td>
              {matrix[tick][i].map((status, j) => (
                <td key={j} className="text-center py-2">
                  <Cell status={status} />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>

      <div className="mt-3 text-xs text-slate-500 flex items-center gap-3">
        <span className="flex items-center gap-1">
          <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" /> klar
        </span>
        <span className="flex items-center gap-1">
          <Hourglass className="w-3.5 h-3.5 text-amber-600" /> pågår
        </span>
        <span className="flex items-center gap-1">
          <XCircle className="w-3.5 h-3.5 text-slate-300" /> ej börjat
        </span>
      </div>
    </div>
  );
}

function Cell({ status }: { status: string }) {
  if (status === "✓") {
    return (
      <span className="inline-flex w-6 h-6 rounded-full bg-emerald-100 items-center justify-center">
        <CheckCircle2 className="w-4 h-4 text-emerald-600" />
      </span>
    );
  }
  if (status === "•") {
    return (
      <span className="inline-flex w-6 h-6 rounded-full bg-amber-100 items-center justify-center">
        <Hourglass className="w-3.5 h-3.5 text-amber-600" />
      </span>
    );
  }
  return <span className="text-slate-300">—</span>;
}
