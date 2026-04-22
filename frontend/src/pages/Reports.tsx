import { useState } from "react";
import { Card } from "@/components/Card";
import { getToken } from "@/api/client";

function defaultMonth(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

export default function Reports() {
  const [month, setMonth] = useState(defaultMonth());
  const token = getToken();
  const port = localStorage.getItem("hembudget_api_port") || "8765";
  const base = `http://127.0.0.1:${port}`;

  async function download(path: string, filename: string) {
    const res = await fetch(`${base}${path}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) {
      alert(`Kunde inte hämta rapporten (${res.status})`);
      return;
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="p-3 md:p-6 space-y-4 md:space-y-4 max-w-2xl">
      <h1 className="text-2xl font-semibold">Rapporter</h1>
      <Card title="Månadsrapport">
        <div className="flex items-end gap-3">
          <label className="text-sm">
            <div className="text-slate-700">Månad</div>
            <input
              type="month"
              value={month}
              onChange={(e) => setMonth(e.target.value)}
              className="border rounded px-2 py-1"
            />
          </label>
          <button
            className="bg-slate-800 text-white px-3 py-1.5 rounded"
            onClick={() => download(`/reports/month/${month}/excel`, `hembudget-${month}.xlsx`)}
          >
            Ladda ner Excel
          </button>
          <button
            className="bg-brand-600 text-white px-3 py-1.5 rounded"
            onClick={() => download(`/reports/month/${month}/pdf`, `hembudget-${month}.pdf`)}
          >
            Ladda ner PDF
          </button>
        </div>
      </Card>
    </div>
  );
}
