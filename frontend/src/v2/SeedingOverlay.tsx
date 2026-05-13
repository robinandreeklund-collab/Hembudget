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
 * Tre robusthetstrick mot timing-race:
 *
 *  1. Overlay visas DIREKT vid mount (`shouldRender=true` default).
 *     Hide:as bara efter att /v2/status BEVISLIGEN sagt "complete".
 *     Då undgår vi att första poll kommer in efter att seeden redan
 *     hunnit göra status='complete' → overlay hade aldrig synts → eleven
 *     såg en sekund tom postlåda.
 *
 *  2. Komplettering cachas i sessionStorage per student-id. Andra/tredje
 *     navigationen visar därför ingen overlay-flash trots aggressiv
 *     default. Cachen lever per browsersession så reseed (lärar-detalj)
 *     fungerar via reload + nytt session-tab.
 *
 *  3. Pollar var 1000 ms (var 1500 ms innan) och börjar med 1 omedelbar
 *     poll. När statusen lämnar "pending" lagras complete-cache och
 *     ev. fortsatt polling stoppas.
 *
 * Komponenten pollar bara aktivt när användaren är elev. Lärare/demo
 * får ingen overlay (de har ingen egen seed-livscykel).
 */
import { useEffect, useState } from "react";
import { v2Api, type V2Status } from "./api";

const POLL_INTERVAL_MS = 1000;
const CACHE_PREFIX = "v2-seed-complete-";

function readCachedComplete(studentId: number | string): boolean {
  try {
    return sessionStorage.getItem(`${CACHE_PREFIX}${studentId}`) === "1";
  } catch {
    return false;
  }
}

function writeCachedComplete(studentId: number | string): void {
  try {
    sessionStorage.setItem(`${CACHE_PREFIX}${studentId}`, "1");
  } catch {
    // sessionStorage kan vara avstängt (incognito-läge på vissa browsers).
    // Då får eleven en kortare overlay-flash vid varje navigation — inget
    // hindrar funktionalitet.
  }
}

export function SeedingOverlay() {
  const [status, setStatus] = useState<V2Status | null>(null);
  // Overlay visas tills vi har bekräftat "complete" eller sett att
  // användaren inte är elev. Default true så vi täcker tomma vyer
  // medan första pollen är in-flight.
  const [hidden, setHidden] = useState(false);

  useEffect(() => {
    let cancelled = false;
    let timer: number | null = null;

    async function poll() {
      try {
        const s = await v2Api.status();
        if (cancelled) return;
        setStatus(s);
        // Icke-elev → ingen overlay alls (lärare/demo har ingen seed).
        if (s.role !== "student") {
          setHidden(true);
          return;
        }
        const cacheKey = s.student_id ?? "current";

        // Om vi redan sett complete för denna elev i denna session,
        // göm overlayn omedelbart utan vidare polling.
        if (readCachedComplete(cacheKey)) {
          setHidden(true);
          return;
        }
        if (s.seed_status === "complete" || s.seed_status === undefined) {
          // undefined betyder att backend inte har fältet (legacy före
          // SKV-seed-fix). Vi behandlar det som complete så overlayn
          // inte fastnar för existerande elever utan migrerad kolumn.
          writeCachedComplete(cacheKey);
          setHidden(true);
          return;
        }
        // pending eller failed → fortsätt polla
        timer = window.setTimeout(poll, POLL_INTERVAL_MS);
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

  if (hidden) return null;
  // Visa overlay tills vi vet att seeden är complete. Inkluderar:
  //   - First-load (status === null) · annars hade vi flashat tom postlåda
  //   - Pending · seed pågår
  //   - Failed · seed havererade, visa felmeddelande
  const failed = status?.seed_status === "failed";

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
              <em style={{ color: "var(--accent, #dc4c2b)" }}>
                postlåda, bankkonton, försäkringar
              </em>
              .
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
