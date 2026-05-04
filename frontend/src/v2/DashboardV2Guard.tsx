/**
 * V2-guard på /dashboard — auto-routar både elever och lärare till
 * v2-vyer.
 *
 * Anledning: efter login körs window.location.reload() vilket landar
 * på /dashboard direkt (inte /). V2RootRedirect aktiveras bara på /.
 * Den här guarden hanterar fallet då användaren landar på /dashboard
 * direkt efter login eller via gamla länkar.
 *
 * Lärare (inkl. super-admin) skickas till /teacher/v2 (klass-hubben)
 * sedan Fas 2AK. Tidigare gick lärare till v1-dashboard. Använd
 * "Tvinga v1" i V2DevFooter för att tillfälligt komma åt v1.
 *
 * Dev-override: localStorage.v2_force_v1 = "1" stoppar all v2-redirect
 * för lärare (för att se v1 även för v2-elever).
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

  // OBS: v2_force_v1-flaggan får ALDRIG påverka elever — det är ett
  // lärar-dev-verktyg. Vi kollar status först, sen lägger vi på
  // overriden bara om role är teacher.
  const forceV1 =
    typeof window !== "undefined" &&
    window.localStorage.getItem("v2_force_v1") === "1";

  // Elev som har v2 aktiverat → /v2/hub eller /v2/onboarding.
  // Ignorera force_v1 helt för elever och rensa flaggan om den läckte
  // från en lärar-session i samma browser.
  if (status?.role === "student" && status.v2_eligible) {
    if (forceV1) {
      try {
        window.localStorage.removeItem("v2_force_v1");
      } catch {
        /* ignore */
      }
    }
    if (!status.v2_onboarding_completed) {
      return <Navigate to="/v2/onboarding" replace />;
    }
    return <Navigate to="/v2/hub" replace />;
  }

  // Lärare → /teacher/v2 (om inte force_v1 är satt)
  if (status?.role === "teacher") {
    if (forceV1) {
      // Respektera dev-flaggan och rendera v1-dashboard
      return <>{children}</>;
    }
    return <Navigate to="/teacher/v2" replace />;
  }

  // Övriga (demo, elev utan v2) → v1-dashboard
  return <>{children}</>;
}
