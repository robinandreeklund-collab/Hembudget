import { Link } from "react-router-dom";
import { EditorialAuthShell } from "@/components/editorial/EditorialAuthShell";
import { AuthAwareTopLinks } from "@/components/editorial/AuthAwareTopLinks";
import { LiveTime, LiveCountdown } from "@/components/editorial/LiveClock";

export default function LoginChoice() {
  return (
    <EditorialAuthShell
      topNavRight={<AuthAwareTopLinks />}
    >
      <div className="ed-eyebrow">Välkommen tillbaka</div>

      <div className="ed-clock">
        <div className="ed-clock-time">
          Klockan är <LiveTime />.
        </div>
        <LiveCountdown minutes={1} />
      </div>

      <p className="ed-subhead">
        Vem är du? <em>Lärare</em> loggar in med e-post och lösenord.
        <em>Förälder</em> har samma flöde med ett familjekonto.
        <em>Elev</em> använder bara sin sextecknade kod.
      </p>

      <Link to="/demo" className="ed-demo-tile">
        <span className="ed-demo-tile-icon" aria-hidden="true">⚡</span>
        <div>
          <div className="ed-demo-tile-title">Prova demoläge direkt</div>
          <div className="ed-demo-tile-body">
            Logga in utan konto — färdig klass att utforska.
          </div>
        </div>
      </Link>

      <div className="ed-choices">
        <Link to="/login/teacher" className="ed-choice">
          <span className="ed-choice-eye">Lä · Lärare</span>
          <span className="ed-choice-title">Logga in som lärare</span>
          <span className="ed-choice-body">
            E-post och lösenord. Hela klassen i en pentagon, varje elev en rad.
          </span>
          <span className="ed-choice-go">
            Till inloggning <span className="ed-choice-go-arrow">→</span>
          </span>
        </Link>

        <Link to="/signup/parent" className="ed-choice">
          <span className="ed-choice-eye">Fö · Familj</span>
          <span className="ed-choice-title">Skapa familjekonto</span>
          <span className="ed-choice-body">
            För dig och dina barn — varje barn får sin egen sex-teckens-kod.
          </span>
          <span className="ed-choice-go">
            Skapa konto <span className="ed-choice-go-arrow">→</span>
          </span>
        </Link>

        <Link to="/login/student" className="ed-choice">
          <span className="ed-choice-eye">El · Elev</span>
          <span className="ed-choice-title">Logga in som elev</span>
          <span className="ed-choice-body">
            Använd sex-teckens-koden från din lärare eller förälder.
          </span>
          <span className="ed-choice-go">
            Till elevkod <span className="ed-choice-go-arrow">→</span>
          </span>
        </Link>
      </div>
    </EditorialAuthShell>
  );
}
