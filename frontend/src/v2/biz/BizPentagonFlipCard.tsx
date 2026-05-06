/**
 * BizPentagonFlipCard · klick på en axel-label flippar pentagonen och
 * visar vad som påverkar just den axeln (faktorer + händelser).
 *
 * Speglar privat-pentagonens PentagonFlipCard (rad 1265+ i prototypen)
 * fast med biz-data: omsättning / kundbas / likviditet / tidsåtgång /
 * vinst. Återanvänder pent-flip.css för identisk 3D-flip-animation.
 */
import { useEffect, useState, type ReactNode } from "react";
import { bizApi, type BizAxis, type BizAxisDetail } from "./api";
import "../pent-flip.css";


type Props = {
  /** Vilken axel är aktiv (null = framsidan visas) */
  activeAxis: BizAxis | null;
  /** Callback när användaren stänger flip-kortet */
  onClose: () => void;
  /** Pentagon-fram-sidan (SVG + axis-tags) */
  front: ReactNode;
};

export function BizPentagonFlipCard({
  activeAxis,
  onClose,
  front,
}: Props) {
  const [detail, setDetail] = useState<BizAxisDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (activeAxis === null) {
      setDetail(null);
      return;
    }
    setLoading(true);
    setError(null);
    bizApi
      .pentagonAxisDetail(activeAxis)
      .then(setDetail)
      .catch((e) => setError(String((e as Error)?.message || e)))
      .finally(() => setLoading(false));
  }, [activeAxis]);

  const flipped = activeAxis !== null;

  return (
    <div className={`pent-flip-stage${flipped ? " is-flipped" : ""}`}>
      <div className="pent-flip-inner">
        <div className="pent-front">{front}</div>
        <div className={`pent-back${flipped ? " show" : ""}`}>
          <button
            type="button"
            className="pent-back-close"
            onClick={onClose}
            aria-label="Stäng axel-detalj"
          >
            ← Pentagonen
          </button>
          {loading && (
            <div className="pent-back-loading">Laddar axel-detalj…</div>
          )}
          {error && (
            <div
              className="pent-back-loading"
              style={{ color: "#fda594" }}
            >
              Kunde inte ladda: {error}
            </div>
          )}
          {detail && !loading && !error && <BizAxisBack detail={detail} />}
        </div>
      </div>
    </div>
  );
}


function BizAxisBack({ detail }: { detail: BizAxisDetail }) {
  const trendSign = detail.score - 50;
  return (
    <>
      <div
        className="pent-back-eye"
        style={{ color: "#c7d2fe" }}
      >
        Axel {detail.axis_number} · {detail.axis_label}
      </div>
      <h2 className="pent-back-h">
        {detail.axis_label}{" "}
        <em style={{ color: "#c7d2fe" }}>
          {trendSign >= 0 ? `${detail.score}` : `${detail.score}`}
        </em>{" "}
        av 100.
      </h2>
      <div
        className="pent-back-score"
        style={{
          color: "#c7d2fe",
          textShadow: "0 4px 24px rgba(99,102,241,0.4)",
        }}
      >
        {detail.score}
        <span style={{ fontSize: 28, color: "rgba(255,255,255,0.55)" }}>
          /100
        </span>
      </div>
      <div className="pent-back-score-meta">
        Faktorer: <strong>{detail.factors.length}</strong> · Händelser:{" "}
        <strong>{detail.events.length}</strong>
      </div>

      <p
        style={{
          fontFamily: "Source Serif 4, Georgia, serif",
          fontSize: 14.5,
          color: "rgba(255,255,255,0.85)",
          lineHeight: 1.55,
          marginBottom: 18,
        }}
      >
        {detail.summary_text}
      </p>

      <div className="pent-back-grid">
        {/* Vänster · faktorer + händelser */}
        <div className="pent-history">
          <div className="pent-history-head">
            Faktorer som bidrar nu (live)
          </div>
          {detail.factors.length === 0 ? (
            <div
              style={{
                padding: "16px 18px",
                fontFamily: "Source Serif 4, Georgia, serif",
                fontSize: 13,
                color: "rgba(255,255,255,0.5)",
              }}
            >
              Inga aktuella faktorer registrerade för denna axel.
            </div>
          ) : (
            detail.factors.map((f, i) => (
              <div className="pent-event" key={`f-${i}`}>
                <span className="pent-event-date">live</span>
                <div>
                  <div className="pent-event-name">{f.explanation}</div>
                  <div className="pent-event-meta">
                    Pentagon-bidrag · auto-räknat
                  </div>
                </div>
                <span
                  className={`pent-event-delta ${
                    f.points > 0 ? "up" : f.points < 0 ? "down" : "flat"
                  }`}
                >
                  {f.delta_label}
                </span>
              </div>
            ))
          )}

          <div className="pent-history-head" style={{ marginTop: 4 }}>
            Beslut & händelser som påverkat
          </div>
          {detail.events.length === 0 ? (
            <div
              style={{
                padding: "16px 18px",
                fontFamily: "Source Serif 4, Georgia, serif",
                fontSize: 13,
                color: "rgba(255,255,255,0.5)",
              }}
            >
              Inga konkreta händelser registrerade än.
            </div>
          ) : (
            detail.events.map((ev, i) => (
              <div className="pent-event" key={`e-${i}`}>
                <span className="pent-event-date">{ev.date_label}</span>
                <div>
                  <div className="pent-event-name">{ev.title}</div>
                  {ev.detail && (
                    <div className="pent-event-meta">{ev.detail}</div>
                  )}
                </div>
                <span
                  className={`pent-event-delta ${
                    (ev.delta || 0) > 0
                      ? "up"
                      : (ev.delta || 0) < 0
                      ? "down"
                      : "flat"
                  }`}
                >
                  {ev.delta_label || "—"}
                </span>
              </div>
            ))
          )}
        </div>

        {/* Höger · pedagogik + side-cards */}
        <aside>
          <div
            className="pent-side-card"
            style={{ borderLeftColor: "#818cf8" }}
          >
            <div
              className="pent-side-card-eye"
              style={{ color: "#c7d2fe" }}
            >
              Vad axeln mäter
            </div>
            <div className="pent-side-card-h">
              {bizAxisHeadline(detail.axis)}
            </div>
            <div className="pent-side-card-meta">
              {bizAxisExplanation(detail.axis)}
            </div>
          </div>

          <div
            className="pent-side-card"
            style={{ borderLeftColor: "#818cf8" }}
          >
            <div
              className="pent-side-card-eye"
              style={{ color: "#c7d2fe" }}
            >
              Hur du höjer
            </div>
            <div className="pent-side-card-h">
              {bizAxisHowToImprove(detail.axis)}
            </div>
            <div className="pent-side-card-meta">
              {bizAxisHowToImproveDetails(detail.axis)}
            </div>
          </div>
        </aside>
      </div>
    </>
  );
}


function bizAxisHeadline(axis: BizAxis): string {
  switch (axis) {
    case "omsattning": return "Intäkter senaste 4 v";
    case "kundbas":    return "Aktiva fakturor + offerter";
    case "likviditet": return "Företagskontots saldo";
    case "tidsatgang": return "Debiterbar/admin-mix";
    case "vinst":      return "Marginal · intäkter minus kostnader";
  }
}

function bizAxisExplanation(axis: BizAxis): string {
  switch (axis) {
    case "omsattning":
      return (
        "Omsättningen är total fakturerat exkl moms senaste 4 veckorna, "
        + "jämfört mot rolling-baseline (4-12v sedan). Stigande = bra. "
        + "Sjunkande = pipelinen torkar — fler offerter ut."
      );
    case "kundbas":
      return (
        "Antal aktiva fakturor + offert-status (vunna/förlorade) styr "
        + "ryktet, som driver pipeline-vikten. Ju fler nöjda kunder "
        + "(4+ stjärnor) → fler liknande förfrågningar nästa vecka."
      );
    case "likviditet":
      return (
        "Pengar på företagskontot just nu, minus kommande moms-due och "
        + "F-skatt. Tunn likviditet → svårt att betala leverantörer i tid "
        + "→ försämrad relation + risk för förseningsavgifter."
      );
    case "tidsatgang":
      return (
        "Förenklat 60/40 (debiterbar / admin) just nu. När du levererar "
        + "fler jobb och hanterar fakturor snabbt stiger axeln. Lärar-"
        + "feedback kan justera om eleven uppenbart underrapporterar."
      );
    case "vinst":
      return (
        "Vinst = intäkter − kostnader. Marginal i procent. Tunn marginal "
        + "tyder på för låga priser eller för höga inköp. Lärar-bedömt "
        + "lyft via reflektion om prisstrategi."
      );
  }
}

function bizAxisHowToImprove(axis: BizAxis): string {
  switch (axis) {
    case "omsattning": return "Skicka fler offerter · högre vinstgrad";
    case "kundbas":    return "Leverera 4+ stjärnor · bygg ryktet";
    case "likviditet": return "Pris upp · betalbart snabbare";
    case "tidsatgang": return "Effektivisera bokföringen · auto-bokade utgifter";
    case "vinst":      return "Höj pris eller sänk kostnader";
  }
}

function bizAxisHowToImproveDetails(axis: BizAxis): string {
  switch (axis) {
    case "omsattning":
      return (
        "Sätt pris i mitten av spannet (Konsumentverket-schablon) · skriv "
        + "tydlig pitch · svara på offert-förfrågningar inom 24h."
      );
    case "kundbas":
      return (
        "Leverera tjänsten med kvalitet 4+ stjärnor · be om referens · "
        + "håll deadline. Branschmix-vikten höjs när du levererar inom samma "
        + "kategori upprepade gånger."
      );
    case "likviditet":
      return (
        "Sätt 14-dagars förfallodatum istället för 30 · skicka påminnelser · "
        + "spara 25 % av varje faktura till moms-buffer · undvik att blanda "
        + "med privatkonto."
      );
    case "tidsatgang":
      return (
        "Använd auto-bokföring för återkommande utgifter (Adobe, Bokio) · "
        + "fakturera direkt vid leverans · en bokföringsbatch i veckan, ej "
        + "samlad till månadsslut."
      );
    case "vinst":
      return (
        "Höj pris med 5-10 % på återkommande kunder · omförhandla leverantörs-"
        + "abonnemang · sänk fasta kostnader · välj jobb med hög marginal "
        + "(IT-tjänster ofta 35-50 % mot fysiska tjänster 15-25 %)."
      );
  }
}
