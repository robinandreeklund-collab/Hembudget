import { useQuery } from "@tanstack/react-query";
import { TrendingUp, ArrowDown, ArrowUp } from "lucide-react";
import { useState } from "react";
import { api, formatSEK } from "@/api/client";
import { Card } from "@/components/Card";

interface OverviewRow {
  student_id: number;
  display_name: string;
  class_label: string | null;
  n_holdings: number;
  cost_basis: number;
  buy_volume: number;
  sell_volume: number;
  total_courtage: number;
  realized_pnl: number;
  n_buys: number;
  n_sells: number;
  last_trade_at: string | null;
}

interface OverviewResponse {
  rows: OverviewRow[];
  aggregate: {
    students: number;
    total_buy_volume: number;
    total_sell_volume: number;
    total_courtage: number;
    total_realized_pnl: number;
    active_traders: number;
  };
}

interface LedgerRow {
  id: number;
  ticker: string;
  side: "buy" | "sell";
  quantity: number;
  price: number;
  courtage: number;
  total_amount: number;
  realized_pnl: number | null;
  quote_id: number | null;
  student_rationale: string | null;
  executed_at: string;
}

export default function TeacherInvestments() {
  const [selectedStudent, setSelectedStudent] = useState<OverviewRow | null>(null);

  const overviewQ = useQuery({
    queryKey: ["teacher-stocks-overview"],
    queryFn: () => api<OverviewResponse>("/teacher/stocks/overview"),
    refetchInterval: 60_000,
  });

  const ledgerQ = useQuery({
    queryKey: ["teacher-stocks-ledger", selectedStudent?.student_id],
    queryFn: () =>
      api<{ ledger: LedgerRow[]; count: number }>(
        `/teacher/stocks/student/${selectedStudent!.student_id}/ledger`,
      ),
    enabled: selectedStudent !== null,
  });

  const data = overviewQ.data;

  return (
    <div className="p-3 md:p-6 space-y-4 max-w-6xl">
      <div>
        <h1 className="serif text-3xl flex items-center gap-2">
          <TrendingUp className="w-7 h-7" />
          Aktiehandel — klassöversikt
        </h1>
        <div className="text-sm text-slate-700 mt-1">
          Per-elev-aggregat över aktier, omsättning, courtage och vinst.
          Klicka en elev för full ledger-drilldown.
        </div>
      </div>

      {data && (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
          <Card title="Elever">
            <div className="text-2xl serif">
              {data.aggregate.active_traders}/{data.aggregate.students}
            </div>
            <div className="text-xs text-slate-600">aktiva handlare</div>
          </Card>
          <Card title="Klassens köpvolym">
            <div className="text-2xl serif">{formatSEK(data.aggregate.total_buy_volume)}</div>
          </Card>
          <Card title="Klassens säljvolym">
            <div className="text-2xl serif">{formatSEK(data.aggregate.total_sell_volume)}</div>
          </Card>
          <Card title="Klassens vinst/förlust">
            <div className={`text-2xl serif ${
              data.aggregate.total_realized_pnl >= 0 ? "text-emerald-700" : "text-red-700"
            }`}>
              {data.aggregate.total_realized_pnl >= 0 ? "+" : ""}
              {formatSEK(data.aggregate.total_realized_pnl)}
            </div>
            <div className="text-xs text-slate-600">
              courtage: {formatSEK(data.aggregate.total_courtage)}
            </div>
          </Card>
        </div>
      )}

      <Card title={`Elever (${data?.rows.length ?? 0})`}>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-slate-600 border-b">
              <tr>
                <th className="py-2">Elev</th>
                <th>Klass</th>
                <th>Innehav</th>
                <th>Köpvolym</th>
                <th>Säljvolym</th>
                <th>Courtage</th>
                <th>Vinst/förlust</th>
                <th>Senaste affär</th>
              </tr>
            </thead>
            <tbody>
              {data?.rows.map((r) => (
                <tr
                  key={r.student_id}
                  className="border-b last:border-0 hover:bg-slate-50 cursor-pointer"
                  onClick={() => setSelectedStudent(r)}
                >
                  <td className="py-2 font-medium">{r.display_name}</td>
                  <td>{r.class_label ?? "—"}</td>
                  <td>{r.n_holdings}</td>
                  <td>{formatSEK(r.buy_volume)}</td>
                  <td>{formatSEK(r.sell_volume)}</td>
                  <td>{formatSEK(r.total_courtage)}</td>
                  <td className={
                    r.realized_pnl >= 0 ? "text-emerald-700" : "text-red-700"
                  }>
                    {r.realized_pnl >= 0 ? "+" : ""}
                    {formatSEK(r.realized_pnl)}
                  </td>
                  <td className="text-xs text-slate-600">
                    {r.last_trade_at
                      ? new Date(r.last_trade_at).toLocaleString("sv-SE")
                      : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      {selectedStudent && ledgerQ.data && (
        <Card title={`Ledger: ${selectedStudent.display_name}`}>
          <div className="text-xs text-slate-600 mb-2">
            Append-only — varje rad är en låst affär. Quote ID länkar till exakt kursdata.
            <button
              onClick={() => setSelectedStudent(null)}
              className="ml-2 text-slate-500 underline"
            >
              Stäng
            </button>
          </div>
          {ledgerQ.data.ledger.length === 0 ? (
            <div className="text-slate-500">Inga affärer än.</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-left text-slate-600 border-b">
                  <tr>
                    <th className="py-2">Tid</th>
                    <th>Köp/Sälj</th>
                    <th>Aktie</th>
                    <th>Antal</th>
                    <th>Kurs</th>
                    <th>Courtage</th>
                    <th>Total</th>
                    <th>Vinst/förlust</th>
                    <th>Quote ID</th>
                    <th>Motivering</th>
                  </tr>
                </thead>
                <tbody>
                  {ledgerQ.data.ledger.map((r) => (
                    <tr key={r.id} className="border-b last:border-0">
                      <td className="py-2 text-xs">
                        {new Date(r.executed_at).toLocaleString("sv-SE")}
                      </td>
                      <td>
                        {r.side === "buy" ? (
                          <span className="inline-flex items-center gap-1 text-emerald-700">
                            <ArrowDown className="w-3 h-3" />Köp
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 text-amber-700">
                            <ArrowUp className="w-3 h-3" />Sälj
                          </span>
                        )}
                      </td>
                      <td>{r.ticker}</td>
                      <td>{r.quantity}</td>
                      <td>{formatSEK(r.price)}</td>
                      <td>{formatSEK(r.courtage)}</td>
                      <td>{formatSEK(r.total_amount)}</td>
                      <td className={
                        r.realized_pnl === null
                          ? ""
                          : r.realized_pnl >= 0
                          ? "text-emerald-700"
                          : "text-red-700"
                      }>
                        {r.realized_pnl === null
                          ? "—"
                          : `${r.realized_pnl >= 0 ? "+" : ""}${formatSEK(r.realized_pnl)}`}
                      </td>
                      <td className="text-xs text-slate-500">{r.quote_id ?? "—"}</td>
                      <td className="text-xs italic max-w-xs truncate">
                        {r.student_rationale ?? "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      )}
    </div>
  );
}
