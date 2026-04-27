/**
 * /teacher/negotiations — lärar-vy: alla lönesamtal i klassen.
 *
 * Pedagogiskt fokus: hjälpa läraren spotta elever som hamnat under
 * avtalsnivå (flag='below_norm'). Klick på rad öppnar transkriptet
 * för granskning.
 */
import { useQuery } from "@tanstack/react-query";
import { Briefcase, AlertCircle, ChevronRight } from "lucide-react";
import { useState } from "react";
import { api, formatSEK } from "@/api/client";
import { Card } from "@/components/Card";


interface NegotiationRow {
  id: number;
  student_id: number;
  display_name: string;
  profession: string;
  started_at: string;
  completed_at: string | null;
  status: "active" | "completed" | "abandoned";
  final_pct: number | null;
  avtal_norm_pct: number | null;
  delta_vs_norm: number | null;
  flag: "below_norm" | null;
}


interface NegotiationListOut {
  rows: NegotiationRow[];
  below_norm_count: number;
}


interface DetailRound {
  round_no: number;
  student_message: string;
  employer_response: string;
  proposed_pct: number | null;
  created_at: string;
}


interface NegotiationDetail {
  id: number;
  student_id: number;
  display_name: string;
  profession: string;
  employer: string;
  starting_salary: number;
  avtal_norm_pct: number | null;
  final_pct: number | null;
  final_salary: number | null;
  status: string;
  started_at: string;
  completed_at: string | null;
  teacher_summary_md: string | null;
  rounds: DetailRound[];
}


export default function TeacherNegotiations() {
  const listQ = useQuery({
    queryKey: ["teacher-negotiations"],
    queryFn: () =>
      api<NegotiationListOut>("/teacher/employer/negotiations"),
  });
  const [openId, setOpenId] = useState<number | null>(null);

  return (
    <div className="p-3 md:p-6 space-y-4 md:space-y-5">
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <h1 className="serif text-3xl leading-tight flex items-center gap-2">
            <Briefcase className="w-7 h-7" />
            Lönesamtal i klassen
          </h1>
          <div className="text-sm text-slate-700 mt-1">
            Alla samtal som dina elever genomfört. Markerade rader
            har landat under avtalsnivå — pedagogisk anledning till
            uppföljning.
          </div>
        </div>
      </div>

      {listQ.isLoading ? (
        <Card><div className="text-sm text-slate-600">Laddar…</div></Card>
      ) : listQ.error ? (
        <Card>
          <div className="text-sm text-rose-700">
            Kunde inte hämta lönesamtal: {String(listQ.error)}
          </div>
        </Card>
      ) : listQ.data ? (
        <>
          {listQ.data.below_norm_count > 0 && (
            <div className="border-l-4 border-amber-400 bg-amber-50 p-3 rounded-md flex items-start gap-2">
              <AlertCircle className="w-5 h-5 text-amber-700 flex-shrink-0 mt-0.5" />
              <div className="text-sm text-amber-900">
                <strong>{listQ.data.below_norm_count} elev(er)</strong>{" "}
                landade under avtals-norm. Värt att ta upp i klassrummet
                — kanske som case för förhandlingsteknik.
              </div>
            </div>
          )}

          <Card title={`Samtal (${listQ.data.rows.length})`}>
            {listQ.data.rows.length === 0 ? (
              <div className="text-sm text-slate-600">
                Inga lönesamtal genomförda än. När en elev startar och
                avslutar ett samtal under /arbetsgivare syns det här.
              </div>
            ) : (
              <table className="w-full text-sm">
                <thead className="text-xs text-slate-500 border-b">
                  <tr>
                    <th className="text-left py-2 px-1">Elev</th>
                    <th className="text-left py-2 px-1">Yrke</th>
                    <th className="text-left py-2 px-1">Status</th>
                    <th className="text-right py-2 px-1">Slutbud</th>
                    <th className="text-right py-2 px-1">Avtal</th>
                    <th className="text-right py-2 px-1">Δ</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {listQ.data.rows.map((r) => (
                    <tr
                      key={r.id}
                      className={`border-b border-slate-100 hover:bg-slate-50 cursor-pointer ${
                        r.flag === "below_norm" ? "bg-rose-50/40" : ""
                      }`}
                      onClick={() => setOpenId(r.id)}
                    >
                      <td className="py-2 px-1">
                        <div className="font-medium">{r.display_name}</div>
                      </td>
                      <td className="py-2 px-1 text-slate-600">
                        {r.profession}
                      </td>
                      <td className="py-2 px-1">
                        <StatusBadge status={r.status} />
                      </td>
                      <td className="py-2 px-1 text-right tabular-nums">
                        {r.final_pct !== null
                          ? `${r.final_pct.toFixed(1)} %`
                          : "—"}
                      </td>
                      <td className="py-2 px-1 text-right text-slate-600 tabular-nums">
                        {r.avtal_norm_pct !== null
                          ? `${r.avtal_norm_pct.toFixed(1)} %`
                          : "—"}
                      </td>
                      <td
                        className={`py-2 px-1 text-right tabular-nums ${
                          r.delta_vs_norm !== null && r.delta_vs_norm < -0.5
                            ? "text-rose-700"
                            : r.delta_vs_norm !== null && r.delta_vs_norm > 0.5
                              ? "text-emerald-700"
                              : "text-slate-700"
                        }`}
                      >
                        {r.delta_vs_norm !== null
                          ? `${r.delta_vs_norm > 0 ? "+" : ""}${r.delta_vs_norm.toFixed(1)}`
                          : "—"}
                      </td>
                      <td className="py-2 px-1 text-right">
                        <ChevronRight className="w-4 h-4 text-slate-400 inline" />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Card>
        </>
      ) : null}

      {openId !== null && (
        <DetailModal
          negotiationId={openId}
          onClose={() => setOpenId(null)}
        />
      )}
    </div>
  );
}


function StatusBadge({ status }: { status: string }) {
  const base = "inline-block text-[10px] uppercase tracking-wide rounded px-1.5 py-0.5";
  if (status === "completed") {
    return (
      <span className={`${base} bg-emerald-100 text-emerald-800`}>
        klart
      </span>
    );
  }
  if (status === "abandoned") {
    return (
      <span className={`${base} bg-slate-100 text-slate-700`}>
        avbrutet
      </span>
    );
  }
  return (
    <span className={`${base} bg-amber-100 text-amber-800`}>
      pågår
    </span>
  );
}


function DetailModal({
  negotiationId,
  onClose,
}: {
  negotiationId: number;
  onClose: () => void;
}) {
  const detailQ = useQuery({
    queryKey: ["teacher-negotiation", negotiationId],
    queryFn: () =>
      api<NegotiationDetail>(
        `/teacher/employer/negotiations/${negotiationId}`,
      ),
  });

  return (
    <div className="fixed inset-0 z-50 bg-black/30 flex items-center justify-center p-4">
      <div className="bg-white rounded-lg max-w-3xl w-full max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between p-4 border-b sticky top-0 bg-white">
          <h2 className="font-semibold">Lönesamtal</h2>
          <button
            onClick={onClose}
            className="text-slate-500 hover:text-slate-900"
          >
            ✕
          </button>
        </div>
        <div className="p-4 space-y-3">
          {detailQ.isLoading ? (
            <div className="text-sm text-slate-600">Laddar…</div>
          ) : detailQ.data ? (
            <>
              <div className="text-sm text-slate-700">
                <strong>{detailQ.data.display_name}</strong> —{" "}
                {detailQ.data.profession} på {detailQ.data.employer}
              </div>
              <div className="text-xs text-slate-500">
                Startade: {detailQ.data.started_at}
                {detailQ.data.completed_at && (
                  <> · Avslutat: {detailQ.data.completed_at}</>
                )}
              </div>
              {detailQ.data.final_pct !== null && (
                <div className="border-l-4 border-brand-400 bg-brand-50 p-2 rounded-r text-sm">
                  Slutbud:{" "}
                  <strong>{detailQ.data.final_pct.toFixed(1)} %</strong>
                  {detailQ.data.final_salary !== null && (
                    <>
                      {" "}({formatSEK(detailQ.data.starting_salary)} →{" "}
                      {formatSEK(detailQ.data.final_salary)})
                    </>
                  )}
                  {detailQ.data.avtal_norm_pct !== null && (
                    <>
                      {" "}· Avtal: {detailQ.data.avtal_norm_pct.toFixed(1)} %
                    </>
                  )}
                </div>
              )}
              {detailQ.data.teacher_summary_md && (
                <div className="text-sm text-slate-700 whitespace-pre-wrap border-l-2 border-slate-300 pl-2">
                  {detailQ.data.teacher_summary_md}
                </div>
              )}
              <div className="space-y-2 pt-3">
                <div className="text-xs uppercase text-slate-500">
                  Transkript ({detailQ.data.rounds.length} ronder)
                </div>
                {detailQ.data.rounds.map((r) => (
                  <div key={r.round_no} className="space-y-1">
                    <div className="text-sm bg-slate-50 border-l-2 border-slate-300 pl-2 py-1">
                      <div className="text-[10px] uppercase text-slate-500">
                        Eleven · rond {r.round_no}
                      </div>
                      <div>{r.student_message}</div>
                    </div>
                    <div className="text-sm bg-brand-50 border-l-2 border-brand-400 pl-2 py-1">
                      <div className="text-[10px] uppercase text-brand-700">
                        Maria (HR) · rond {r.round_no}
                        {r.proposed_pct !== null && (
                          <span className="ml-2">
                            bud: {r.proposed_pct.toFixed(1)} %
                          </span>
                        )}
                      </div>
                      <div>{r.employer_response}</div>
                    </div>
                  </div>
                ))}
              </div>
            </>
          ) : (
            <div className="text-sm text-rose-700">Kunde inte ladda.</div>
          )}
        </div>
      </div>
    </div>
  );
}
