/**
 * /teacher/credit — klassöversikt över kreditaktivitet.
 * Per-elev: ansökningar, score, lån, total skuld, högkostnadskrediter.
 * Klick på elev → drilldown med full ansökningshistorik.
 */
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, CreditCard, Info } from "lucide-react";
import { useState } from "react";
import { api, formatSEK } from "@/api/client";
import { Card } from "@/components/Card";

interface OverviewRow {
  student_id: number;
  display_name: string;
  class_label: string | null;
  n_applications: number;
  n_approved: number;
  n_accepted: number;
  n_declined: number;
  n_sms_applications: number;
  avg_credit_score: number | null;
  active_loans: number;
  total_debt: number;
  high_cost_loans: number;
}

interface OverviewResponse {
  rows: OverviewRow[];
  aggregate: {
    students: number;
    total_applications: number;
    total_accepted: number;
    total_declined: number;
    total_sms: number;
    total_debt: number;
    students_with_high_cost: number;
  };
}

interface ApplicationRow {
  id: number;
  kind: string;
  requested_amount: number;
  requested_months: number;
  purpose: string | null;
  result: string;
  score_value: number | null;
  decline_reason: string | null;
  simulated_lender: string | null;
  offered_rate: number | null;
  offered_monthly_payment: number | null;
  resulting_loan_id: number | null;
  created_at: string;
  decided_at: string | null;
}

export default function TeacherCredit() {
  const [selected, setSelected] = useState<OverviewRow | null>(null);

  const overviewQ = useQuery({
    queryKey: ["teacher-credit-overview"],
    queryFn: () => api<OverviewResponse>("/teacher/credit/overview"),
    refetchInterval: 60_000,
  });

  const appsQ = useQuery({
    queryKey: ["teacher-credit-apps", selected?.student_id],
    queryFn: () =>
      api<{ display_name: string; applications: ApplicationRow[]; count: number }>(
        `/teacher/credit/student/${selected!.student_id}/applications`,
      ),
    enabled: selected !== null,
  });

  const data = overviewQ.data;

  return (
    <div className="p-3 md:p-6 space-y-4 max-w-6xl">
      <div>
        <h1 className="serif text-3xl flex items-center gap-2">
          <CreditCard className="w-7 h-7" />
          Kredit — klassöversikt
        </h1>
        <div className="text-sm text-slate-700 mt-1">
          Vilka elever har sökt lån? Vilka tog SMS-lån? Skulde-läge,
          ansöknings-historik och avslag.
        </div>
      </div>

      {data && (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
          <Card title="Aktiva ansökningar">
            <div className="text-2xl serif">{data.aggregate.total_applications}</div>
            <div className="text-xs text-slate-600">
              {data.aggregate.total_accepted} accepterade ·{" "}
              {data.aggregate.total_declined} avslag
            </div>
          </Card>
          <Card title="Klassens skuld">
            <div className="text-2xl serif">{formatSEK(data.aggregate.total_debt)}</div>
          </Card>
          <Card title="SMS-låne-ansökningar">
            <div className={`text-2xl serif ${
              data.aggregate.total_sms > 0 ? "text-red-700" : ""
            }`}>
              {data.aggregate.total_sms}
            </div>
          </Card>
          <Card title="Elever med högkostnadskredit">
            <div className={`text-2xl serif ${
              data.aggregate.students_with_high_cost > 0 ? "text-red-700" : ""
            }`}>
              {data.aggregate.students_with_high_cost}
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
                <th>Ansökningar</th>
                <th>Snitt-score</th>
                <th>Aktiva lån</th>
                <th>Total skuld</th>
                <th>SMS-lån</th>
              </tr>
            </thead>
            <tbody>
              {data?.rows.map((r) => (
                <tr
                  key={r.student_id}
                  className={`border-b last:border-0 hover:bg-slate-50 cursor-pointer ${
                    r.high_cost_loans > 0 ? "bg-red-50" : ""
                  }`}
                  onClick={() => setSelected(r)}
                >
                  <td className="py-2 font-medium">
                    {r.display_name}
                    {r.high_cost_loans > 0 && (
                      <AlertTriangle
                        className="inline w-3 h-3 text-red-600 ml-1"
                      />
                    )}
                  </td>
                  <td>{r.class_label ?? "—"}</td>
                  <td>{r.n_applications}</td>
                  <td>{r.avg_credit_score ?? "—"}</td>
                  <td>{r.active_loans}</td>
                  <td>{formatSEK(r.total_debt)}</td>
                  <td className={r.n_sms_applications > 0 ? "text-red-700 font-medium" : ""}>
                    {r.n_sms_applications}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      {selected && appsQ.data && (
        <Card title={`Ansökningshistorik: ${selected.display_name}`}>
          <div className="text-xs text-slate-600 mb-2 flex items-start gap-1">
            <Info className="w-3 h-3 mt-0.5" />
            <span>
              Append-only audit-spår. Varje ansökan loggas — även de
              som avslogs eller eleven själv tackade nej till.
              <button
                onClick={() => setSelected(null)}
                className="ml-2 underline"
              >
                Stäng
              </button>
            </span>
          </div>
          {appsQ.data.applications.length === 0 ? (
            <div className="text-slate-500">
              Inga ansökningar än.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-left text-slate-600 border-b">
                  <tr>
                    <th className="py-2">Tid</th>
                    <th>Typ</th>
                    <th>Belopp</th>
                    <th>Löptid</th>
                    <th>Ändamål</th>
                    <th>Resultat</th>
                    <th>Score</th>
                    <th>Bank</th>
                    <th>Ränta</th>
                    <th>Skäl/nota</th>
                  </tr>
                </thead>
                <tbody>
                  {appsQ.data.applications.map((a) => (
                    <tr
                      key={a.id}
                      className={`border-b last:border-0 ${
                        a.kind === "sms" ? "bg-red-50" : ""
                      }`}
                    >
                      <td className="py-2 text-xs">
                        {new Date(a.created_at).toLocaleString("sv-SE")}
                      </td>
                      <td>
                        {a.kind === "sms" ? (
                          <span className="text-red-700 font-medium">SMS</span>
                        ) : (
                          "Privat"
                        )}
                      </td>
                      <td>{formatSEK(a.requested_amount)}</td>
                      <td>{a.requested_months} mån</td>
                      <td className="text-xs">{a.purpose ?? "—"}</td>
                      <td>
                        {a.result === "accepted" && (
                          <span className="text-emerald-700">Accepterat</span>
                        )}
                        {a.result === "approved" && (
                          <span className="text-emerald-600">Godkänd</span>
                        )}
                        {a.result === "declined" && (
                          <span className="text-red-700">Avslag</span>
                        )}
                        {a.result === "rejected" && (
                          <span className="text-slate-700">Tackat nej</span>
                        )}
                      </td>
                      <td>{a.score_value ?? "—"}</td>
                      <td>{a.simulated_lender ?? "—"}</td>
                      <td>
                        {a.offered_rate
                          ? `${(a.offered_rate * 100).toFixed(2)} %`
                          : "—"}
                      </td>
                      <td className="text-xs italic max-w-md">
                        {a.decline_reason ?? "—"}
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
