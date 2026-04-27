/**
 * /arbetsgivare — central hub för arbetsgivar-dynamik (idé 1 i
 * dev_v1.md).
 *
 * Samlar lönespec, lönesamtal, kollektivavtal, satisfaction-score
 * och slumpade frågor på en plats. Banken hanterar bank-saker
 * (kontoutdrag etc); arbetsgivaren är där allt jobb-relaterat sker.
 *
 * F2a — skelett med flikar och "Kommer snart"-stubbar. Översikt,
 * Avtal, Eventlogg och Frågor fylls i F2b–F2e. Lönespec och
 * Lönesamtal hör till PR 4 (efter idé 2-backend).
 */
import { Building2 } from "lucide-react";
import { useState } from "react";

type Tab =
  | "oversikt"
  | "lonespec"
  | "avtal"
  | "lonesamtal"
  | "fragor"
  | "events";

const TABS: { id: Tab; label: string; comingSoon?: boolean }[] = [
  { id: "oversikt", label: "Översikt" },
  { id: "lonespec", label: "Lönespec", comingSoon: true },
  { id: "avtal", label: "Kollektivavtal" },
  { id: "lonesamtal", label: "Lönesamtal", comingSoon: true },
  { id: "fragor", label: "Frågor" },
  { id: "events", label: "Eventlogg" },
];


export default function Arbetsgivare() {
  const [tab, setTab] = useState<Tab>("oversikt");

  return (
    <div className="p-3 md:p-6 space-y-4 md:space-y-5">
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <h1 className="serif text-3xl leading-tight flex items-center gap-2">
            <Building2 className="w-7 h-7" />
            Arbetsgivare
          </h1>
          <div className="text-sm text-slate-700 mt-1">
            Här samlas allt som rör ditt jobb: lönespec, kollektivavtal,
            lönesamtal och din relation till arbetsgivaren. Banken sköter
            själva pengarna; det här är var du <em>jobbar</em>.
          </div>
        </div>
      </div>

      <div className="flex gap-2 border-b overflow-x-auto">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`px-3 py-2 text-sm border-b-2 whitespace-nowrap ${
              tab === t.id
                ? "border-brand-600 text-brand-700"
                : "border-transparent text-slate-600 hover:text-slate-900"
            }`}
          >
            {t.label}
            {t.comingSoon && (
              <span className="ml-1 text-[10px] text-slate-400 align-top">
                snart
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Stub-tabbar; fylls i F2b–F2e */}
      {tab === "oversikt" && <ComingSoon what="Översikt" />}
      {tab === "lonespec" && (
        <ComingSoon
          what="Lönespec"
          note="Hör till PR 4 — kommer efter att lönesamtals-backenden är klar."
        />
      )}
      {tab === "avtal" && <ComingSoon what="Kollektivavtal" />}
      {tab === "lonesamtal" && (
        <ComingSoon
          what="Lönesamtal"
          note="Hör till PR 4 — kommer efter att lönesamtals-backenden är klar."
        />
      )}
      {tab === "fragor" && <ComingSoon what="Frågor" />}
      {tab === "events" && <ComingSoon what="Eventlogg" />}
    </div>
  );
}


function ComingSoon({ what, note }: { what: string; note?: string }) {
  return (
    <div className="bg-white border border-slate-200 rounded-md p-6">
      <div className="text-base font-semibold text-slate-900 mb-1">
        {what}
      </div>
      <div className="text-sm text-slate-600">
        Kommer i nästa commit. {note}
      </div>
    </div>
  );
}
