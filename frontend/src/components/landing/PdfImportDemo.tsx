import { useEffect, useState } from "react";
import { CheckCircle2, Download, FileText, Upload } from "lucide-react";

/**
 * Animerad demo av PDF-import-flödet:
 * 1. Läraren skickar ut batch (PDF:er glider in)
 * 2. Eleven laddar ner (download-ikon pulserar)
 * 3. Eleven importerar (PDF "flyter upp" och transformas till en tx-lista)
 * Loop.
 */
export default function PdfImportDemo() {
  const [step, setStep] = useState(0); // 0-3
  useEffect(() => {
    const t = setInterval(() => setStep((x) => (x + 1) % 4), 2200);
    return () => clearInterval(t);
  }, []);

  const pdfs = [
    { name: "Lönespec april.pdf", kind: "Lönespec", color: "bg-emerald-500" },
    { name: "Kontoutdrag april.pdf", kind: "Kontoutdrag", color: "bg-brand-500" },
    { name: "Lånebesked.pdf", kind: "Lånebesked", color: "bg-amber-500" },
    { name: "Kreditkortsfaktura.pdf", kind: "Kreditkort", color: "bg-rose-500" },
  ];

  return (
    <div className="bg-white rounded-2xl shadow-xl border border-slate-200 p-5 h-full min-h-[380px]">
      <div className="flex items-center justify-between mb-3">
        <div className="text-sm font-semibold text-slate-700">
          Dina dokument
        </div>
        <div className="text-xs text-slate-500">april 2026</div>
      </div>

      <ul className="space-y-2">
        {pdfs.map((p, i) => {
          // Olika animationer beroende på step och vilken PDF
          const arriving = step === 0;
          const downloading = step === 1 && i === 1;
          const importing = step === 2 && i <= 1;
          const done = step === 3 || (step === 2 && i === 0);

          return (
            <li
              key={p.name}
              className={`flex items-center gap-3 p-2.5 rounded-lg border transition-all duration-500 ${
                importing
                  ? "border-brand-400 bg-brand-50 -translate-y-1 shadow-md"
                  : done
                  ? "border-emerald-200 bg-emerald-50"
                  : "border-slate-200 bg-white"
              }`}
              style={{
                opacity: arriving ? 1 : 1,
                animation: arriving
                  ? `fadeup 0.5s ${i * 0.15}s both`
                  : undefined,
              }}
            >
              <div
                className={`w-8 h-8 rounded ${p.color} text-white grid place-items-center text-xs font-bold shrink-0`}
              >
                <FileText className="w-4 h-4" />
              </div>
              <div className="flex-1 min-w-0">
                <div className="text-sm font-medium text-slate-800 truncate">
                  {p.name}
                </div>
                <div className="text-xs text-slate-500">{p.kind}</div>
              </div>
              {done && (
                <CheckCircle2 className="w-5 h-5 text-emerald-600 animate-fadein" />
              )}
              {downloading && (
                <Download className="w-5 h-5 text-brand-600 animate-pulse" />
              )}
              {importing && (
                <Upload className="w-5 h-5 text-brand-600 animate-pulse" />
              )}
            </li>
          );
        })}
      </ul>

      <div className="mt-4 text-xs text-center text-slate-500">
        {step === 0 && "Läraren skickade ut dokumenten"}
        {step === 1 && "Eleven laddar ner och läser dem"}
        {step === 2 && "Eleven importerar till appen"}
        {step === 3 && "Klart — allt hamnar på rätt plats"}
      </div>
    </div>
  );
}
