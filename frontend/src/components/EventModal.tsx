/**
 * EventModal — visar ett pending event och låter eleven acceptera,
 * neka eller (V2) bjuda klasskompis.
 *
 * Pedagogisk princip: alla impacts visas i förväg så eleven gör ett
 * informerat val. Inga rekommendationer från systemet.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle, Calendar, Coins, Heart, UserPlus, Users, X,
} from "lucide-react";
import { useState } from "react";
import { api, formatSEK } from "@/api/client";

export interface PendingEvent {
  id: number;
  event_code: string;
  title: string;
  description: string;
  category: string;
  cost: number;
  proposed_date: string | null;
  deadline: string;
  source: string;
  status: string;
  social_invite_allowed: boolean;
  declinable: boolean;
}

interface AcceptResultOut {
  event_id: number;
  status: string;
  transaction_id: number | null;
  cost_applied: number;
  income_applied: number;
  impact_applied: Record<string, number>;
  pedagogical_note: string;
}

interface DeclineResultOut {
  event_id: number;
  status: string;
  impact_applied: Record<string, number>;
  pedagogical_note: string;
  current_decline_streak: number;
  show_streak_nudge: boolean;
}

interface EventTemplate {
  impact_economy: number;
  impact_health: number;
  impact_social: number;
  impact_leisure: number;
  impact_safety: number;
}

const CATEGORY_BADGE: Record<string, { label: string; color: string }> = {
  social: { label: "Sociala", color: "bg-amber-100 text-amber-800" },
  family: { label: "Familj", color: "bg-purple-100 text-purple-800" },
  culture: { label: "Kultur", color: "bg-indigo-100 text-indigo-800" },
  sport: { label: "Sport", color: "bg-emerald-100 text-emerald-800" },
  opportunity: { label: "Möjlighet", color: "bg-sky-100 text-sky-800" },
  unexpected: { label: "Oförutsett", color: "bg-red-100 text-red-800" },
  mat: { label: "Mat", color: "bg-orange-100 text-orange-800" },
  lifestyle: { label: "Lifestyle", color: "bg-slate-100 text-slate-800" },
};

const DIM_LABEL: Record<string, string> = {
  economy: "Ekonomi",
  health: "Hälsa",
  social: "Sociala band",
  leisure: "Fritid",
  safety: "Trygghet",
};

interface Props {
  event: PendingEvent;
  /** Master-templaten har impact-värden — front-end kallar /events/template/{code} eller får dem injicerat. */
  template?: EventTemplate;
  onClose: () => void;
}

interface ClassmatesResp {
  classmates: { student_id: number; display_name: string; class_label: string | null }[];
  invites_enabled: boolean;
  cost_split_model?: string;
  max_invites_per_week?: number;
}

interface InviteResultOut {
  invites_created: number;
  invite_ids: number[];
  cost_split_model: string;
  swish_amount_per_recipient: number;
  week_remaining: number;
}

export function EventModal({ event, template, onClose }: Props) {
  const qc = useQueryClient();
  const [reason, setReason] = useState("");
  const [result, setResult] = useState<AcceptResultOut | DeclineResultOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showInvite, setShowInvite] = useState(false);
  const [selectedClassmates, setSelectedClassmates] = useState<number[]>([]);
  const [inviteMessage, setInviteMessage] = useState("");
  const [inviteResult, setInviteResult] = useState<InviteResultOut | null>(null);

  // Fetcha klasskompisar bara om eleven öppnar bjud-vyn
  const classmatesQ = useQuery({
    queryKey: ["events-classmates"],
    queryFn: () => api<ClassmatesResp>("/events/classmates"),
    enabled: showInvite && event.social_invite_allowed,
  });

  const inviteMut = useMutation({
    mutationFn: (body: { event_id: number; classmate_ids: number[]; message: string }) =>
      api<InviteResultOut>("/events/invite-classmates", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: (data) => setInviteResult(data),
    onError: (e: unknown) => setError(e instanceof Error ? e.message : "Kunde inte skicka"),
  });

  const acceptMut = useMutation({
    mutationFn: () =>
      api<AcceptResultOut>(`/events/${event.id}/accept`, {
        method: "POST",
        body: JSON.stringify({}),
      }),
    onSuccess: (data) => {
      setResult(data);
      qc.invalidateQueries({ queryKey: ["events-pending"] });
      qc.invalidateQueries({ queryKey: ["wellbeing-current"] });
      qc.invalidateQueries({ queryKey: ["balances"] });
    },
    onError: (e: unknown) => {
      setError(e instanceof Error ? e.message : "Kunde inte acceptera");
    },
  });

  const declineMut = useMutation({
    mutationFn: () =>
      api<DeclineResultOut>(`/events/${event.id}/decline`, {
        method: "POST",
        body: JSON.stringify({ decision_reason: reason || undefined }),
      }),
    onSuccess: (data) => {
      setResult(data);
      qc.invalidateQueries({ queryKey: ["events-pending"] });
      qc.invalidateQueries({ queryKey: ["wellbeing-current"] });
    },
    onError: (e: unknown) => {
      setError(e instanceof Error ? e.message : "Kunde inte neka");
    },
  });

  const cat = CATEGORY_BADGE[event.category] ?? CATEGORY_BADGE.lifestyle;
  const isUnexpected = event.category === "unexpected" || !event.declinable;

  // Visa impact-rader om template är inladdad
  const impactsAccept: Array<[string, number]> = template
    ? [
        ["economy", template.impact_economy],
        ["health", template.impact_health],
        ["social", template.impact_social],
        ["leisure", template.impact_leisure],
        ["safety", template.impact_safety],
      ].filter(([, v]) => v !== 0) as Array<[string, number]>
    : [];

  return (
    <div
      role="dialog"
      aria-modal="true"
      onClick={onClose}
      className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4"
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="bg-white rounded-xl shadow-xl w-full max-w-md max-h-[90vh] overflow-y-auto"
      >
        <div className="border-b p-4">
          <div className="flex items-start justify-between gap-2">
            <div>
              <span className={`inline-block text-[11px] px-1.5 py-0.5 rounded mb-1 ${cat.color}`}>
                {cat.label}
              </span>
              <h2 className="font-semibold text-lg leading-tight">
                {event.title}
              </h2>
            </div>
            <button onClick={onClose} aria-label="Stäng">
              <X className="w-5 h-5 text-slate-500" />
            </button>
          </div>
        </div>

        <div className="p-5 space-y-4">
          {!result && (
            <>
              <p className="text-sm text-slate-700">{event.description}</p>

              <div className="bg-slate-50 border rounded p-3 text-sm space-y-1.5">
                <div className="flex items-center gap-2">
                  <Coins className="w-4 h-4 text-slate-500" />
                  <span className="font-medium">{formatSEK(event.cost)}</span>
                  {event.cost === 0 && (
                    <span className="text-xs text-emerald-700">(ingen direktkostnad)</span>
                  )}
                </div>
                {event.proposed_date && (
                  <div className="flex items-center gap-2 text-xs text-slate-600">
                    <Calendar className="w-3 h-3" />
                    Föreslaget datum: {new Date(event.proposed_date).toLocaleDateString("sv-SE")}
                  </div>
                )}
                <div className="text-xs text-slate-600">
                  Svara senast {new Date(event.deadline).toLocaleDateString("sv-SE")}
                </div>
              </div>

              {impactsAccept.length > 0 && (
                <div className="border rounded p-3 text-sm">
                  <div className="font-medium mb-1.5 flex items-center gap-1.5">
                    <Heart className="w-3.5 h-3.5 text-rose-500" />
                    Wellbeing-effekt om du accepterar
                  </div>
                  <div className="space-y-1">
                    {impactsAccept.map(([dim, val]) => (
                      <div key={dim} className="flex justify-between text-xs">
                        <span>{DIM_LABEL[dim]}</span>
                        <span
                          className={`font-mono font-semibold ${
                            val > 0 ? "text-emerald-700" : "text-red-700"
                          }`}
                        >
                          {val > 0 ? "+" : ""}{val}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {isUnexpected && (
                <div className="bg-red-50 border border-red-200 rounded p-2 text-xs text-red-900 flex gap-1.5 items-start">
                  <AlertTriangle className="w-3.5 h-3.5 mt-0.5 shrink-0" />
                  <span>
                    Detta är en oförutsedd kostnad — du kan inte neka. Klicka
                    "Acceptera" för att registrera utgiften.
                  </span>
                </div>
              )}

              {!isUnexpected && (
                <div>
                  <label className="text-xs font-medium text-slate-600 block mb-1">
                    Skäl om du nekar (valfritt — påverkar streak-räkning)
                  </label>
                  <input
                    type="text"
                    value={reason}
                    onChange={(e) => setReason(e.target.value)}
                    placeholder='Exempelvis: "valde sparande"'
                    className="w-full border rounded px-2 py-1.5 text-sm"
                  />
                </div>
              )}

              {error && (
                <div className="text-sm text-red-700 bg-red-50 border border-red-200 rounded p-2">
                  {error}
                </div>
              )}

              <div className="flex gap-2 justify-end pt-2 flex-wrap">
                {event.social_invite_allowed && !showInvite && (
                  <button
                    onClick={() => setShowInvite(true)}
                    className="px-3 py-2 rounded border bg-amber-50 border-amber-300 text-amber-900 hover:bg-amber-100 flex items-center gap-1 text-sm"
                  >
                    <UserPlus className="w-4 h-4" />
                    Bjud klasskompis
                  </button>
                )}
                {!isUnexpected && (
                  <button
                    onClick={() => declineMut.mutate()}
                    disabled={declineMut.isPending || acceptMut.isPending}
                    className="px-4 py-2 rounded border bg-white hover:bg-slate-50 disabled:opacity-50"
                  >
                    {declineMut.isPending ? "Nekar…" : "Neka"}
                  </button>
                )}
                <button
                  onClick={() => acceptMut.mutate()}
                  disabled={acceptMut.isPending || declineMut.isPending}
                  className="bg-emerald-600 text-white px-4 py-2 rounded disabled:opacity-50"
                >
                  {acceptMut.isPending ? "Genomför…" : "Acceptera"}
                </button>
              </div>
            </>
          )}

          {showInvite && !inviteResult && (
            <div className="space-y-3 border-t pt-3">
              <div className="flex items-center gap-2 font-medium">
                <Users className="w-4 h-4" />
                Bjud klasskompisar
              </div>
              {classmatesQ.isLoading && (
                <div className="text-sm text-slate-500">Laddar…</div>
              )}
              {classmatesQ.data && !classmatesQ.data.invites_enabled && (
                <div className="text-sm text-slate-700 bg-slate-50 border rounded p-2">
                  Klasskompis-bjudningar är avstängda av läraren.
                </div>
              )}
              {classmatesQ.data?.invites_enabled && (
                <>
                  <div className="text-xs text-slate-600">
                    Kostnadsmodell: <strong>{classmatesQ.data.cost_split_model}</strong>
                    {" · "}
                    Max {classmatesQ.data.max_invites_per_week} bjudningar/vecka
                  </div>
                  <div className="border rounded p-2 max-h-48 overflow-y-auto space-y-1">
                    {classmatesQ.data.classmates.length === 0 ? (
                      <div className="text-sm text-slate-500 p-2">
                        Inga klasskompisar i din klass än.
                      </div>
                    ) : (
                      classmatesQ.data.classmates.map((c) => {
                        const checked = selectedClassmates.includes(c.student_id);
                        return (
                          <label
                            key={c.student_id}
                            className="flex items-center gap-2 p-1.5 hover:bg-slate-50 rounded cursor-pointer text-sm"
                          >
                            <input
                              type="checkbox"
                              checked={checked}
                              onChange={(e) => {
                                if (e.target.checked) {
                                  setSelectedClassmates([...selectedClassmates, c.student_id]);
                                } else {
                                  setSelectedClassmates(
                                    selectedClassmates.filter((id) => id !== c.student_id),
                                  );
                                }
                              }}
                            />
                            <span className="flex-1">{c.display_name}</span>
                            <span className="text-xs text-slate-500">
                              {c.class_label ?? ""}
                            </span>
                          </label>
                        );
                      })
                    )}
                  </div>
                  <textarea
                    value={inviteMessage}
                    onChange={(e) => setInviteMessage(e.target.value)}
                    placeholder="Personligt meddelande (valfritt)"
                    rows={2}
                    className="w-full border rounded px-2 py-1.5 text-sm"
                  />
                  {selectedClassmates.length > 0 &&
                    classmatesQ.data.cost_split_model === "split" && (
                      <div className="text-xs text-slate-600 bg-slate-50 border rounded p-2">
                        Vid 'split': {formatSEK(event.cost / (selectedClassmates.length + 1))}{" "}
                        per person ({selectedClassmates.length + 1} personer totalt).
                      </div>
                    )}
                  <div className="flex gap-2 justify-end">
                    <button
                      onClick={() => {
                        setShowInvite(false);
                        setSelectedClassmates([]);
                      }}
                      className="px-3 py-2 rounded border"
                    >
                      Avbryt
                    </button>
                    <button
                      onClick={() =>
                        inviteMut.mutate({
                          event_id: event.id,
                          classmate_ids: selectedClassmates,
                          message: inviteMessage,
                        })
                      }
                      disabled={
                        selectedClassmates.length === 0 || inviteMut.isPending
                      }
                      className="bg-amber-600 text-white px-4 py-2 rounded disabled:opacity-50"
                    >
                      {inviteMut.isPending
                        ? "Skickar…"
                        : `Skicka till ${selectedClassmates.length}`}
                    </button>
                  </div>
                </>
              )}
            </div>
          )}

          {inviteResult && (
            <div className="bg-amber-50 border border-amber-200 rounded p-3 text-sm">
              <div className="font-medium mb-1 flex items-center gap-1">
                <UserPlus className="w-4 h-4" />
                Bjudningar skickade
              </div>
              <p className="text-xs text-slate-700">
                {inviteResult.invites_created} bjudningar gick iväg.
                {inviteResult.swish_amount_per_recipient > 0 && (
                  <>
                    {" "}Var och en får återbetala{" "}
                    <strong>
                      {formatSEK(inviteResult.swish_amount_per_recipient)}
                    </strong>{" "}
                    via Swish.
                  </>
                )}
                {" "}Du har {inviteResult.week_remaining} bjudningar kvar denna vecka.
              </p>
            </div>
          )}

          {result && (
            <>
              <div
                className={`rounded p-3 text-sm ${
                  result.status === "accepted"
                    ? "bg-emerald-50 border border-emerald-200 text-emerald-900"
                    : "bg-amber-50 border border-amber-200 text-amber-900"
                }`}
              >
                <div className="font-medium mb-1">
                  {result.status === "accepted" ? "Accepterat" : "Nekat"}
                </div>
                <p className="text-xs">{result.pedagogical_note}</p>
              </div>

              {"show_streak_nudge" in result && result.show_streak_nudge && (
                <div className="bg-rose-50 border-2 border-rose-300 rounded p-3 text-sm">
                  <div className="font-bold text-rose-900 flex items-center gap-1 mb-1">
                    <AlertTriangle className="w-4 h-4" />
                    Du har nekat {result.current_decline_streak} förslag i rad
                  </div>
                  <p className="text-rose-900 text-xs">
                    Att alltid säga nej har en kostnad för sociala band.
                    Inget krav att acceptera — men reflektera över vad det
                    säger om dina val. Du kan flagga "valde sparande" i
                    framtida nekanden om det är medvetet.
                  </p>
                </div>
              )}

              <div className="flex justify-end">
                <button
                  onClick={onClose}
                  className="bg-slate-700 text-white px-4 py-2 rounded"
                >
                  Klar
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
