/**
 * V2-bootstrap · routar inkommande användare till rätt v2-sida.
 *
 * Anropar /v2/status och bestämmer:
 * - super-admin → /v2/hub direkt (för att se v2 från start)
 * - student utan onboarding → /v2/onboarding
 * - student med onboarding → /v2/hub
 * - teacher → /v2/hub (lärar-vy är minimal i denna PR)
 *
 * Visar laddnings-skärm under tiden /v2/status hämtas.
 */
import { useEffect, useState } from "react";
import { Navigate } from "react-router-dom";
import { v2Api, type V2Status } from "./api";

export function V2Bootstrap() {
  const [status, setStatus] = useState<V2Status | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    v2Api
      .status()
      .then(setStatus)
      .catch((e) => setError(e?.message || "Kunde inte hämta v2-status"));
  }, []);

  if (error) {
    return (
      <div style={{ padding: 40, fontFamily: "Inter, sans-serif" }}>
        <h2>V2-status kunde inte laddas</h2>
        <pre>{error}</pre>
      </div>
    );
  }

  if (!status) {
    return (
      <div style={{ padding: 40, fontFamily: "Inter, sans-serif" }}>
        Laddar v2…
      </div>
    );
  }

  // Routing-logik
  if (status.role === "student" && !status.v2_onboarding_completed) {
    return <Navigate to="/v2/onboarding" replace />;
  }
  return <Navigate to="/v2/hub" replace />;
}
