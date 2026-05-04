import { useEffect, useState } from "react";

/** Levande klocka — visar nuvarande tid HH:MM och uppdateras varje
 *  sekund. Tabular-numerals + tick-anim när minutsiffran byter, så
 *  blicken fastnar precis när tiden klickar förbi. */
export function LiveTime() {
  const [time, setTime] = useState(() => formatTime(new Date()));
  const [tickKey, setTickKey] = useState(0);

  useEffect(() => {
    let prev = time;
    const id = setInterval(() => {
      const next = formatTime(new Date());
      if (next !== prev) {
        prev = next;
        setTime(next);
        setTickKey((k) => k + 1);
      }
    }, 1000);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <em key={tickKey} className="ed-clock-tick" aria-live="off">
      {time}
    </em>
  );
}

function formatTime(d: Date) {
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  return `${hh}:${mm}`;
}

/** "Om N minuter" — softa pulser med en svag animering. För
 *  sign-up tar det typ 1 minut, så vi hardcodar `minutes={1}` på
 *  signup-sidor. På inlogg används `seconds`-läge istället. */
export function LiveCountdown({
  minutes,
  prefix = "om",
}: {
  minutes: number;
  prefix?: string;
}) {
  const label = minutes === 1 ? "minut" : "minuter";
  return (
    <span className="ed-clock-countdown">
      Din vecka börjar {prefix} <em>{minutes} {label}</em>.
    </span>
  );
}

/** Sekund-räknare som tickar nedåt från `seconds` till 0 och loopar
 *  om sig så det alltid känns levande. För "Logga in"-sidor där
 *  inloggningen tar några sekunder. */
export function LiveSecondsCountdown({ start = 9 }: { start?: number }) {
  const [n, setN] = useState(start);
  useEffect(() => {
    const id = setInterval(() => {
      setN((cur) => (cur <= 1 ? start : cur - 1));
    }, 1000);
    return () => clearInterval(id);
  }, [start]);
  return (
    <span className="ed-clock-countdown">
      Din vecka börjar om <em key={n} className="ed-clock-tick">{n} sek</em>.
    </span>
  );
}
