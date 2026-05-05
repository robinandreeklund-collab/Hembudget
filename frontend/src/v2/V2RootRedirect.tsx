/**
 * V2 root-redirect · väljer rätt destination för "/".
 *
 * Logik (V1-frontend är avvecklad — alla destinations är V2):
 * - student utan v2-onboarding → /v2/onboarding
 * - student med v2-onboarding klar → /v2/hub
 * - lärare (inkl. super-admin) → /teacher/v2 (klass-hubben)
 * - demo → /v2/hub
 *
 * Om /v2/status fail:ar fallback:ar vi till /v2/hub. Lärare som
 * accidentellt landar där redirectas vidare av övriga routes.
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
        if (s.role === "teacher") {
          setDestination("/teacher/v2");
        } else if (s.role === "student") {
          if (!s.v2_onboarding_completed)
            setDestination("/v2/onboarding");
          else setDestination("/v2/hub");
        } else {
          // Demo eller okänt
          setDestination("/v2/hub");
        }
      })
      .catch(() => setDestination("/v2/hub"));
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
