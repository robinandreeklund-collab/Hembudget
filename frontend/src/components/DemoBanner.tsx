import { useEffect, useState } from "react";
import { Zap } from "lucide-react";
import { api, clearRole, clearToken, setAsStudent } from "@/api/client";

type IsDemoResp = {
  is_demo: boolean;
  next_reset_at: string | null;
};

/**
 * Fast banner överst i app-vyn när inloggad som demo-konto.
 * - Visar "DEMOLÄGE – återställs om X min"
 * - Visar knapp för att lämna demo (rensar token)
 * Komponenten är tyst (returnerar null) om man inte är i demo.
 */
export function DemoBanner() {
  const [state, setState] = useState<IsDemoResp | null>(null);
  const [now, setNow] = useState(Date.now());

  useEffect(() => {
    api<IsDemoResp>("/demo/is-demo")
      .then(setState)
      .catch(() => setState(null));
  }, []);

  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 5000);
    return () => clearInterval(t);
  }, []);

  if (!state || !state.is_demo) return null;

  let countdown = "";
  if (state.next_reset_at) {
    const diff = new Date(state.next_reset_at).getTime() - now;
    if (diff > 0) {
      const mins = Math.floor(diff / 60000);
      const secs = Math.floor((diff % 60000) / 1000);
      countdown = ` · data resetas om ${mins} min ${secs.toString().padStart(2, "0")} s`;
    } else {
      countdown = " · reset pågår…";
    }
  }

  function leave() {
    clearToken();
    clearRole();
    setAsStudent(null);
    window.location.href = "/";
  }

  return (
    <div className="bg-amber-400 text-amber-950 px-4 py-2 text-sm flex items-center justify-between gap-3 shadow-sm">
      <div className="flex items-center gap-2">
        <Zap className="w-4 h-4 shrink-0" />
        <span className="font-semibold">DEMOLÄGE</span>
        <span className="hidden sm:inline">{countdown}</span>
      </div>
      <button
        onClick={leave}
        className="bg-amber-950 hover:bg-black text-amber-50 rounded px-3 py-1 text-xs"
      >
        Lämna demo
      </button>
    </div>
  );
}
