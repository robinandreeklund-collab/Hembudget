/**
 * V2-guard på /dashboard — auto-routar super-admin till /v2/hub.
 *
 * Anledning: efter login körs window.location.reload() vilket landar
 * på /dashboard direkt (inte /). V2RootRedirect aktiveras bara på /.
 * Den här guarden ser till att super-admin alltid hamnar på v2 även
 * om de råkar gå direkt till /dashboard.
 *
 * För vanliga lärare: rendera v1-dashboard som vanligt.
 * För elever: om eleven har v2_enabled, redirecta till /v2/hub.
 */
import { useEffect, useState, type ReactNode } from "react";
import { Navigate } from "react-router-dom";
import { v2Api, type V2Status } from "./api";

export function DashboardV2Guard({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<V2Status | null>(null);
  const [done, setDone] = useState(false);

  useEffect(() => {
    v2Api.status()
      .then((s) => setStatus(s))
      .catch(() => undefined)
      .finally(() => setDone(true));
  }, []);

  if (!done) {
    // Visa v1-dashboard direkt medan vi väntar — bättre UX än spinner
    return <>{children}</>;
  }

  // Super-admin auto-routas till v2/hub
  if (status?.is_super_admin) {
    return <Navigate to="/v2/hub" replace />;
  }

  // Elev som har v2 aktiverat → /v2/hub
  if (status?.role === "student" && status.v2_eligible) {
    if (!status.v2_onboarding_completed) {
      return <Navigate to="/v2/onboarding" replace />;
    }
    return <Navigate to="/v2/hub" replace />;
  }

  // Övriga (lärare utan super-admin, demo, elev utan v2) → v1-dashboard
  return <>{children}</>;
}
