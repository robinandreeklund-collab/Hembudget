/**
 * V2 root-redirect · väljer rätt destination för "/".
 *
 * Logik:
 * - localStorage `v2_force_v1` = "1" → /dashboard alltid (dev-toggle)
 * - student utan v2-onboarding → /v2/onboarding (default ny flow)
 * - student med v2-onboarding klar → /v2/hub
 * - lärare (inkl. super-admin) → /teacher (lärar-dashboard, inte
 *   v2/hub som är elev-vy). Super-admin kan manuellt navigera till
 *   /v2/hub via V2-toggle-bannern för att förhandsgranska elev-vyn.
 * - demo → /dashboard
 *
 * Om /v2/status fail:ar så fallback:ar vi till /dashboard så v1
 * inte påverkas av v2-bugg.
 */
import { useEffect, useState } from "react";
import { Navigate } from "react-router-dom";
import { v2Api, type V2Status } from "./api";

export function V2RootRedirect() {
  const [destination, setDestination] = useState<string | null>(null);

  useEffect(() => {
    // Dev-override: om användaren explicit valt v1-läge, respektera det
    if (
      typeof window !== "undefined" &&
      window.localStorage.getItem("v2_force_v1") === "1"
    ) {
      setDestination("/dashboard");
      return;
    }
    v2Api
      .status()
      .then((s: V2Status) => {
        if (s.role === "teacher") setDestination("/teacher");
        else if (s.role === "student" && !s.v2_onboarding_completed)
          setDestination("/v2/onboarding");
        else if (s.role === "student") setDestination("/v2/hub");
        else setDestination("/dashboard");
      })
      .catch(() => setDestination("/dashboard"));
  }, []);

  if (!destination) {
    return (
      <div style={{ padding: 40, fontFamily: "Inter, sans-serif" }}>
        Laddar…
      </div>
    );
  }
  return <Navigate to={destination} replace />;
}
