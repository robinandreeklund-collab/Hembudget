/**
 * V2 root-redirect · väljer rätt destination för "/".
 *
 * Logik:
 * - super-admin → /v2/hub direkt (de följer migrations-fronten)
 * - student utan v2-onboarding → /v2/onboarding (default ny flow)
 * - student med v2-onboarding klar → /v2/hub
 * - alla andra (lärare, demo) → /dashboard (v1, befintligt)
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
    v2Api
      .status()
      .then((s: V2Status) => {
        if (s.is_super_admin) setDestination("/v2/hub");
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
