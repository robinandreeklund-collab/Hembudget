/**
 * GameTimeWidget · live spel-tid på hub-headern.
 *
 * Visar:
 *  - SPEL-TID-eyebrow
 *  - Stort datum ("Fredag 2 januari 2026") med fade-slide-animation
 *    när dagen byter
 *  - Progress-bar för "dagens framsteg" (0-100 % över SECONDS_PER_GAME_DAY)
 *  - Live countdown "Nästa dag om HH:MM:SS" som tickar var sekund
 *  - Mikro-text om takten
 *
 * Klient-driven: använder real_anchor_at + Date.now() för att räkna fram
 * spel-datum lokalt, så vi inte behöver pinga backend var sekund. Re-fetchar
 * mot /v2/game-time var 60 sek för att synka mot serverns klocka (annars
 * driftar browser-tid om elev har hibernate-skärm eller fel klocka).
 */
import { useEffect, useRef, useState } from "react";
import type { HubGameTime } from "./api";


type ComputedDate = {
  iso: string;
  weekday: string;
  fullLabel: string;
  yearMonth: string;
};

const WEEKDAYS = [
  "Måndag", "Tisdag", "Onsdag", "Torsdag",
  "Fredag", "Lördag", "Söndag",
];
const MONTHS = [
  "januari", "februari", "mars", "april", "maj",
  "juni", "juli", "augusti", "september", "oktober",
  "november", "december",
];
const GAME_ANCHOR_DATE = new Date(Date.UTC(2026, 0, 1));  // 2026-01-01


function computeDate(
  initial: HubGameTime,
  now: number,
): ComputedDate {
  const realAnchor = new Date(initial.real_anchor_at).getTime();
  const elapsedSec = Math.max(0, (now - realAnchor) / 1000);
  const elapsedDays = Math.floor(
    elapsedSec / initial.seconds_per_game_day,
  );
  const game = new Date(GAME_ANCHOR_DATE.getTime());
  game.setUTCDate(game.getUTCDate() + elapsedDays);
  const y = game.getUTCFullYear();
  const m = game.getUTCMonth();
  const d = game.getUTCDate();
  const localDate = new Date(y, m, d);  // för weekday-beräkning
  const wd = WEEKDAYS[(localDate.getDay() + 6) % 7];
  const mn = MONTHS[m];
  return {
    iso: `${y}-${String(m + 1).padStart(2, "0")}-${String(d).padStart(2, "0")}`,
    weekday: wd,
    fullLabel: `${wd} ${d} ${mn} ${y}`,
    yearMonth: `${y}-${String(m + 1).padStart(2, "0")}`,
  };
}


function computeProgress(
  initial: HubGameTime,
  now: number,
): { secondsIntoDay: number; secondsUntilNext: number; pct: number } {
  const realAnchor = new Date(initial.real_anchor_at).getTime();
  const elapsedSec = Math.max(0, (now - realAnchor) / 1000);
  const secIntoDay = Math.floor(
    elapsedSec % initial.seconds_per_game_day,
  );
  const secUntilNext = initial.seconds_per_game_day - secIntoDay;
  const pct = Math.min(
    100, Math.max(0, (secIntoDay / initial.seconds_per_game_day) * 100),
  );
  return {
    secondsIntoDay: secIntoDay,
    secondsUntilNext: secUntilNext,
    pct,
  };
}


function fmtCountdown(seconds: number): string {
  if (seconds <= 0) return "0 s";
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  if (m === 0) return `${s} s`;
  return `${m} min ${String(s).padStart(2, "0")} s`;
}


export function GameTimeWidget({ gameTime }: { gameTime: HubGameTime }) {
  const [now, setNow] = useState(Date.now());
  const prevIsoRef = useRef<string>(gameTime.iso_date);
  const [flashKey, setFlashKey] = useState(0);

  // Tick var sekund för smooth countdown + progress-bar
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, []);

  const computed = computeDate(gameTime, now);
  const progress = computeProgress(gameTime, now);

  // Trigga flash-animation när dagen byter
  useEffect(() => {
    if (computed.iso !== prevIsoRef.current) {
      prevIsoRef.current = computed.iso;
      setFlashKey((k) => k + 1);
    }
  }, [computed.iso]);

  return (
    <div style={{
      marginBottom: 18,
      fontFamily: "Source Serif 4, Georgia, serif",
      position: "relative",
    }}>
      <style>{`
        @keyframes gametime-flash {
          0% { transform: translateY(-12px); opacity: 0; filter: blur(4px); }
          50% { opacity: 1; filter: blur(0); }
          100% { transform: translateY(0); opacity: 1; }
        }
        @keyframes gametime-pulse {
          0%, 100% { opacity: 0.55; }
          50% { opacity: 1; }
        }
        .gametime-date {
          animation: gametime-flash 0.7s cubic-bezier(0.2, 0.8, 0.3, 1);
        }
        .gametime-pulse-dot {
          animation: gametime-pulse 2s ease-in-out infinite;
        }
        .gametime-bar-fill {
          transition: width 1s linear;
        }
      `}</style>

      <div style={{
        fontFamily: "JetBrains Mono, monospace",
        fontSize: 10.5, fontWeight: 700, letterSpacing: 1.6,
        color: "rgba(255,255,255,0.5)",
        textTransform: "uppercase",
        marginBottom: 6,
        display: "flex",
        alignItems: "center",
        gap: 8,
      }}>
        <span
          className="gametime-pulse-dot"
          style={{
            width: 8, height: 8, borderRadius: "50%",
            background: "#fbbf24",
            display: "inline-block",
          }}
        />
        SPEL-TID
      </div>

      <div
        key={flashKey}
        className="gametime-date"
        style={{
          fontSize: 38, fontWeight: 700,
          color: "#fff",
          letterSpacing: -0.6,
          lineHeight: 1.1,
        }}
      >
        {computed.fullLabel}
      </div>

      {/* Progress-bar för dagens framsteg */}
      <div style={{
        marginTop: 14,
        height: 4,
        background: "rgba(255,255,255,0.08)",
        borderRadius: 100,
        overflow: "hidden",
      }}>
        <div
          className="gametime-bar-fill"
          style={{
            height: "100%",
            width: `${progress.pct}%`,
            background:
              progress.pct > 80
                ? "linear-gradient(90deg, #fbbf24, #f59e0b)"
                : "linear-gradient(90deg, #818cf8, #a78bfa)",
            borderRadius: 100,
          }}
        />
      </div>

      <div style={{
        display: "flex",
        gap: 12,
        marginTop: 8,
        alignItems: "center",
        fontFamily: "JetBrains Mono, monospace",
        fontSize: 10.5,
        color: "rgba(255,255,255,0.55)",
        letterSpacing: 0.5,
      }}>
        <span>
          NÄSTA DAG OM{" "}
          <strong style={{ color: "#fbbf24", fontWeight: 700 }}>
            {fmtCountdown(progress.secondsUntilNext)}
          </strong>
        </span>
        <span style={{ opacity: 0.45 }}>·</span>
        <span style={{ opacity: 0.7 }}>
          1 H = 1 V · LÖN ~3 H · NY MÅN ~4 H
        </span>
      </div>
    </div>
  );
}
