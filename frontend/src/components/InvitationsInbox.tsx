/**
 * InvitationsInbox — visar invitationer från klasskompisar.
 *
 * Eleven ser vem som bjudit, vad och hur mycket. Acceptera skapar en
 * pending StudentEvent i scopet + Swish-skuld i Upcoming. Neka bara
 * stänger inbjudan.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Coins, MessageSquare, UserPlus } from "lucide-react";
import { useState } from "react";
import { api, formatSEK } from "@/api/client";
import { Card } from "@/components/Card";

interface Invitation {
  id: number;
  from_student_id: number;
  from_display_name: string | null;
  event_code: string;
  event_title: string;
  proposed_date: string | null;
  deadline: string;
  cost: number;
  cost_split_model: string;
  swish_amount: number | null;
  message: string | null;
  status: string;
  created_at: string;
}

interface RespondOut {
  invite_id: number;
  status: string;
  student_event_id: number | null;
  swish_upcoming_id: number | null;
  pedagogical_note: string;
}

export function InvitationsInbox() {
  const qc = useQueryClient();
  const [responseFor, setResponseFor] = useState<{ id: number; result: RespondOut } | null>(null);

  const invQ = useQuery({
    queryKey: ["events-invitations"],
    queryFn: () => api<{ invitations: Invitation[]; count: number }>("/events/invitations"),
    refetchInterval: 60_000,
  });

  const respondMut = useMutation({
    mutationFn: (body: { invite_id: number; accept: boolean }) =>
      api<RespondOut>("/events/invitations/respond", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: (data) => {
      setResponseFor({ id: data.invite_id, result: data });
      qc.invalidateQueries({ queryKey: ["events-invitations"] });
      qc.invalidateQueries({ queryKey: ["events-pending"] });
      qc.invalidateQueries({ queryKey: ["upcoming"] });
    },
  });

  const pending = (invQ.data?.invitations ?? []).filter(
    (i) => i.status === "pending",
  );

  if (pending.length === 0 && !responseFor) {
    return null;
  }

  return (
    <Card title={`Bjudningar från klasskompisar (${pending.length})`}>
      {responseFor && (
        <div
          className={`rounded p-3 text-sm mb-3 ${
            responseFor.result.status === "accepted"
              ? "bg-emerald-50 border border-emerald-200 text-emerald-900"
              : "bg-slate-50 border border-slate-200 text-slate-900"
          }`}
        >
          <p className="text-xs">{responseFor.result.pedagogical_note}</p>
          <button
            onClick={() => setResponseFor(null)}
            className="text-xs text-slate-600 underline mt-1"
          >
            Stäng
          </button>
        </div>
      )}

      <div className="space-y-2">
        {pending.map((inv) => (
          <div
            key={inv.id}
            className="border rounded p-3 bg-amber-50 border-amber-200 space-y-2"
          >
            <div className="flex items-start justify-between gap-2">
              <div className="flex-1 min-w-0">
                <div className="text-xs text-amber-800 flex items-center gap-1">
                  <UserPlus className="w-3 h-3" />
                  {inv.from_display_name ?? "Klasskompis"} bjuder dig
                </div>
                <div className="font-medium text-sm mt-0.5">{inv.event_title}</div>
                {inv.proposed_date && (
                  <div className="text-xs text-slate-600 mt-0.5">
                    Föreslaget: {new Date(inv.proposed_date).toLocaleDateString("sv-SE")}
                  </div>
                )}
                {inv.message && (
                  <div className="mt-1 bg-white border rounded p-1.5 text-xs italic flex gap-1">
                    <MessageSquare className="w-3 h-3 mt-0.5 shrink-0 text-slate-500" />
                    <span>"{inv.message}"</span>
                  </div>
                )}
              </div>
              <div className="text-right shrink-0">
                {inv.swish_amount !== null && inv.swish_amount > 0 ? (
                  <>
                    <div className="text-xs text-slate-600">Din del</div>
                    <div className="text-sm font-mono font-semibold flex items-center gap-1 justify-end">
                      <Coins className="w-3 h-3" />
                      {formatSEK(inv.swish_amount)}
                    </div>
                    <div className="text-[10px] text-slate-500">
                      Swish till {inv.from_display_name}
                    </div>
                  </>
                ) : (
                  <>
                    <div className="text-xs text-emerald-700">Bjudaren betalar</div>
                    <div className="text-[10px] text-slate-500 mt-0.5">
                      Ingen kostnad för dig
                    </div>
                  </>
                )}
              </div>
            </div>
            <div className="flex gap-2 justify-end pt-1 border-t">
              <button
                onClick={() => respondMut.mutate({ invite_id: inv.id, accept: false })}
                disabled={respondMut.isPending}
                className="px-3 py-1.5 rounded border text-sm hover:bg-slate-50 disabled:opacity-50"
              >
                Tacka nej
              </button>
              <button
                onClick={() => respondMut.mutate({ invite_id: inv.id, accept: true })}
                disabled={respondMut.isPending}
                className="bg-emerald-600 text-white px-3 py-1.5 rounded text-sm disabled:opacity-50"
              >
                Acceptera
              </button>
            </div>
          </div>
        ))}
      </div>

      <div className="text-xs text-slate-500 mt-3 italic">
        Du svarar bara på själva bjudningen här. Eventet hamnar sedan
        som ett vanligt förslag du kan acceptera/neka i din inbox.
      </div>
    </Card>
  );
}
