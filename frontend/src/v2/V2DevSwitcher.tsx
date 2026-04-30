/**
 * V2 dev-switcher · floating knapp i nedre högra hörnet.
 *
 * Synlig för LÄRARE under utvecklingsfasen så de enkelt kan hoppa
 * mellan v1 och v2 utan att rensa localStorage manuellt.
 *
 * Beteende:
 * - På v1-sidor: visar "→ Testa v2"-knapp som rensar `v2_force_v1`
 *   och navigerar till /v2/hub.
 * - På v2-sidor: ingen knapp (V2Banner har redan en "Tvinga v1"-knapp).
 *
 * Elever ser aldrig detta — toggle är dev-verktyg, inte UX.
 */
import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { v2Api, type V2Status } from "./api";

const FORCE_V1_KEY = "v2_force_v1";

export function V2DevSwitcher() {
  const [status, setStatus] = useState<V2Status | null>(null);
  const navigate = useNavigate();
  const location = useLocation();

  useEffect(() => {
    v2Api.status().then(setStatus).catch(() => undefined);
  }, []);

  // Bara lärare ser knappen (super-admin är också lärare).
  if (!status || status.role !== "teacher") return null;

  // Visa inte på v2-sidor — V2Banner har redan en "Tvinga v1"-knapp.
  if (location.pathname.startsWith("/v2/")) return null;

  function gotoV2() {
    window.localStorage.removeItem(FORCE_V1_KEY);
    navigate("/v2/hub");
  }

  return (
    <button
      type="button"
      onClick={gotoV2}
      title="Förhandsgranska v2 (lärar-dev)"
      style={{
        position: "fixed",
        bottom: 16,
        right: 16,
        zIndex: 200,
        background: "#0f172a",
        color: "#fbbf24",
        border: "1px solid #fbbf24",
        padding: "8px 14px",
        borderRadius: 100,
        fontFamily: "JetBrains Mono, ui-monospace, monospace",
        fontSize: 11,
        fontWeight: 700,
        letterSpacing: 1.4,
        textTransform: "uppercase",
        cursor: "pointer",
        boxShadow: "0 4px 12px rgba(0,0,0,0.18)",
      }}
    >
      ● Testa v2 →
    </button>
  );
}
