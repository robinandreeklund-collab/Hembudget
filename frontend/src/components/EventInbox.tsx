/**
 * EventInbox — visar pending events och öppnar EventModal vid klick.
 *
 * Pedagogisk princip: events ska kännas som verklighet — kompisarna
 * ringer, livet händer. Inte som checklista.
 */
import { useQuery } from "@tanstack/react-query";
import { Bell, Calendar } from "lucide-react";
import { useState } from "react";
import { api, formatSEK } from "@/api/client";
import { Card } from "@/components/Card";
import { EventModal, type PendingEvent } from "@/components/EventModal";

interface EventTemplateImpacts {
  impact_economy: number;
  impact_health: number;
  impact_social: number;
  impact_leisure: number;
  impact_safety: number;
}

const CATEGORY_COLORS: Record<string, string> = {
  social: "bg-amber-50 border-amber-200",
  family: "bg-purple-50 border-purple-200",
  culture: "bg-indigo-50 border-indigo-200",
  sport: "bg-emerald-50 border-emerald-200",
  opportunity: "bg-sky-50 border-sky-200",
  unexpected: "bg-red-50 border-red-300",
  mat: "bg-orange-50 border-orange-200",
  lifestyle: "bg-slate-50 border-slate-200",
};

export function EventInbox() {
  const [selected, setSelected] = useState<PendingEvent | null>(null);
  const [selectedTemplate, setSelectedTemplate] = useState<EventTemplateImpacts | undefined>();

  const pendingQ = useQuery({
    queryKey: ["events-pending"],
    queryFn: () => api<{ events: PendingEvent[]; count: number }>("/events/pending"),
    refetchInterval: 60_000,
  });

  const events = pendingQ.data?.events ?? [];

  if (events.length === 0) {
    return null;  // Tomt: dölj kortet helt
  }

  return (
    <>
      <Card title={`Förslag att svara på (${events.length})`}>
        <div className="space-y-2">
          {events.map((e) => {
            const colorClass = CATEGORY_COLORS[e.category] ?? CATEGORY_COLORS.lifestyle;
            return (
              <button
                key={e.id}
                onClick={() => {
                  setSelected(e);
                  // V1: vi har inte template-impacts inladdade här
                  // (kräver extra fetch). EventModal visar utan dem
                  // tills user fattar beslut — då visas de i pedagogical_note.
                  setSelectedTemplate(undefined);
                }}
                className={`w-full text-left border rounded p-3 hover:bg-white transition-colors ${colorClass}`}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="flex-1 min-w-0">
                    <div className="font-medium text-sm">{e.title}</div>
                    <div className="text-xs text-slate-600 mt-0.5 line-clamp-2">
                      {e.description}
                    </div>
                  </div>
                  <div className="text-right shrink-0">
                    <div className="text-sm font-mono">
                      {e.cost === 0 ? "—" : formatSEK(e.cost)}
                    </div>
                    <div className="text-[10px] text-slate-500 mt-0.5 flex items-center gap-1 justify-end">
                      <Calendar className="w-3 h-3" />
                      {new Date(e.deadline).toLocaleDateString("sv-SE", {
                        day: "numeric", month: "short",
                      })}
                    </div>
                  </div>
                </div>
              </button>
            );
          })}
        </div>
        <div className="text-xs text-slate-500 mt-3 italic">
          Klicka på ett förslag för att svara. Att alltid säga nej har en
          kostnad för Wellbeing — och att alltid säga ja en annan.
        </div>
      </Card>

      {selected && (
        <EventModal
          event={selected}
          template={selectedTemplate}
          onClose={() => {
            setSelected(null);
            setSelectedTemplate(undefined);
          }}
        />
      )}
    </>
  );
}


/** Liten notifikations-bubbla i header — visar antal pending events. */
export function EventBadge() {
  const pendingQ = useQuery({
    queryKey: ["events-pending"],
    queryFn: () => api<{ count: number }>("/events/pending"),
    refetchInterval: 60_000,
  });
  const count = pendingQ.data?.count ?? 0;
  if (count === 0) return null;
  return (
    <span
      className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-amber-100 text-amber-800 text-xs font-medium"
      title={`${count} förslag att svara på`}
    >
      <Bell className="w-3 h-3" />
      {count}
    </span>
  );
}
