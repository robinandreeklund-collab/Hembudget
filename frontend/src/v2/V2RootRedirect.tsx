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
    // OBS: v2_force_v1-flaggan är ett LÄRAR-dev-verktyg och får ALDRIG
    // påverka elev-routing. Vi kollar status FÖRST, sen lägger på
    // dev-overriden bara om role är teacher.
    v2Api
      .status()
      .then((s: V2Status) => {
        const forceV1 =
          typeof window !== "undefined" &&
          window.localStorage.getItem("v2_force_v1") === "1";

        if (s.role === "teacher") {
          // Teacher: respektera force_v1-flaggan om satt
          setDestination("/teacher");
        } else if (s.role === "student") {
          // Student: ignorera force_v1 helt — det är lärar-flagga.
          // Rensa den om den råkar ligga kvar i samma browser.
          if (forceV1) {
            try {
              window.localStorage.removeItem("v2_force_v1");
            } catch {
              /* ignore */
            }
          }
          if (!s.v2_onboarding_completed)
            setDestination("/v2/onboarding");
          else setDestination("/v2/hub");
        } else {
          // Demo eller okänt
          setDestination("/dashboard");
        }
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
