/**
 * SeedingOverlay · pedagogisk wait-state medan en ny elevs initial-
 * data byggs upp i bakgrunden.
 *
 * VARFÖR: v2_create_student returnerar direkt och schemalägger seeden
 * som FastAPI BackgroundTask (lön, postlådan, försäkringar, pension,
 * rental, events tar 3-5 s). Tidigare landade eleven på /v2/hub eller
 * /v2/postladan INNAN seeden var klar och såg helt tomma vyer ("0 brev",
 * "0 kr saldo") som var omöjliga att skilja från en bugg.
 *
 * Den här komponenten pollar /v2/status och täcker hela skärmen så
 * länge `seed_status === "pending"`. När statusen flippar till
 * "complete" lyfts overlayn och eleven landar på den färdiga vyn.
 * Vid "failed" visar vi ett tydligt felmeddelande istället för att
 * snurra evigt — läraren kan reseeda via lärar-detaljvyn.
 *
 * Komponenten poll:ar bara aktivt när användaren är elev. Lärare/demo
 * får ingen overlay (de har ingen egen seed-livscykel).
 */
import { useEffect, useState } from "react";
import { v2Api, type V2Status } from "./api";

const POLL_INTERVAL_MS = 1500;

export function SeedingOverlay() {
  const [status, setStatus] = useState<V2Status | null>(null);

  useEffect(() => {
    let cancelled = false;
    let timer: number | null = null;

    async function poll() {
      try {
        const s = await v2Api.status();
        if (cancelled) return;
        setStatus(s);
        // Sluta polla så fort statusen lämnat "pending". Vi pollar
        // inte heller om användaren inte är elev — overlayn visas inte
        // ändå och vi vill inte spamma /v2/status från lärar-vyer.
        if (s.role !== "student") return;
        if (s.seed_status === "pending") {
          timer = window.setTimeout(poll, POLL_INTERVAL_MS);
        }
      } catch {
        // Tysta nätverksfel · försök igen vid nästa intervall så
        // overlayn inte fastnar om backend hickar i 1 s.
        if (cancelled) return;
        timer = window.setTimeout(poll, POLL_INTERVAL_MS);
      }
    }
    poll();

    return () => {
      cancelled = true;
      if (timer !== null) window.clearTimeout(timer);
    };
  }, []);

  if (!status || status.role !== "student") return null;
  if (status.seed_status === "complete" || status.seed_status === undefined) {
    return null;
  }

  const failed = status.seed_status === "failed";

  return (
    <div
      role="status"
      aria-live="polite"
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(11, 11, 14, 0.96)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 9999,
        fontFamily: "var(--serif, 'Source Serif Pro', Georgia, serif)",
        color: "var(--text, #f5f0e8)",
        padding: "40px 20px",
      }}
    >
      <div style={{ maxWidth: 520, textAlign: "center" }}>
        <div
          style={{
            fontSize: 12,
            letterSpacing: 2,
            textTransform: "uppercase",
            color: failed ? "#fca5a5" : "var(--accent, #dc4c2b)",
            marginBottom: 18,
            fontFamily: "var(--sans, 'Inter', system-ui, sans-serif)",
          }}
        >
          {failed ? "Något gick fel" : "Bygger upp ditt liv"}
        </div>
        <h2
          style={{
            fontSize: 28,
            lineHeight: 1.25,
            fontWeight: 500,
            margin: "0 0 18px",
          }}
        >
          {failed ? (
            <>Datan kunde inte skapas.</>
          ) : (
            <>
              Vi förbereder din karaktär —{" "}
              <em style={{ color: "var(--accent, #dc4c2b)" }}>postlåda,
              bankkonton, försäkringar</em>.
            </>
          )}
        </h2>
        <p
          style={{
            fontSize: 15,
            lineHeight: 1.55,
            color: "var(--text-mid, #c9c2b7)",
            marginBottom: 22,
            fontFamily:
              "var(--sans, 'Inter', system-ui, sans-serif)",
          }}
        >
          {failed ? (
            <>
              Initialdatan kunde inte seedas. Be din lärare öppna
              elev-detaljvyn — auto-recovery startar då en ny seed.
            </>
          ) : (
            <>
              Tar några sekunder. Vi seedar lönehistorik, fakturor från
              de senaste tre månaderna och dina försäkringar så du
              startar med en realistisk vardag.
            </>
          )}
        </p>
        {!failed && (
          <div
            style={{
              width: 220,
              margin: "0 auto",
              height: 3,
              background: "rgba(220, 76, 43, 0.18)",
              borderRadius: 2,
              overflow: "hidden",
            }}
          >
            <div
              style={{
                width: "40%",
                height: "100%",
                background: "var(--accent, #dc4c2b)",
                borderRadius: 2,
                animation: "seeding-shimmer 1.4s ease-in-out infinite",
              }}
            />
          </div>
        )}
      </div>
      <style>{`
        @keyframes seeding-shimmer {
          0%   { transform: translateX(-120%); }
          100% { transform: translateX(370%); }
        }
      `}</style>
    </div>
  );
}
