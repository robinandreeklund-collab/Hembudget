import { Link } from "react-router-dom";
import { EditorialLightShell } from "@/components/editorial/EditorialLightShell";
import { AuthAwareTopLinks } from "@/components/editorial/AuthAwareTopLinks";

export default function Terms() {
  return (
    <EditorialLightShell
      eyebrow="Villkor · Vol. 01"
      title={
        <>
          Allt du ser här är <em>simulering</em>.
        </>
      }
      intro="Inga riktiga pengar. Inga riktiga konton. Bara konsekvensdriven inlärning — där varje val har en effekt, men ingen siffra du ser landar någonsin på ett bankkonto i den fysiska världen."
      topNavRight={<AuthAwareTopLinks variant="light" />}
    >
      <div className="edl-callout is-accent">
        <div className="edl-callout-eye">Det viktigaste först</div>
        <p>
          <strong>Ekonomilabbet är en lärplattform — inte en bank, inte en
          rådgivare och inte ett betalningssystem.</strong> Allt du upplever
          i Linda, Peter och Evelinas veckor är simulerade händelser som
          drivs av realistiska men fiktiva data. Inget värde flyttas mellan
          riktiga konton. Inget köps. Inga skatter betalas till
          Skatteverket. Inga lån tas upp.
        </p>
      </div>

      <section id="overview" className="edl-section">
        <h2 className="edl-h2">Vad är en <em>simulering</em>, egentligen?</h2>
        <div className="edl-prose">
          <p>
            En simulering är en modell av verkligheten som beter sig som
            verkligheten — men ingenting du gör i den påverkar världen
            utanför skärmen. När Linda förhandlar lön med AI-Maria sker
            samtalet i en isolerad sandlåda. När Peter signerar 18 fakturor
            med EkonomilabbetID drar inga riktiga pengar någonstans. När
            Evelinas globalfond tappar 8 % på en dag är det en
            återgivning av historiska kraschmönster, inte en faktisk
            marknadsrörelse.
          </p>
          <p>
            Plattformens kärna är <em>konsekvensdrivet lärande</em>. Vi
            simulerar svenska lönestatistik från Akavia, Skatteverkets
            tabeller, Konsumentverkets hushållsberäkningar 2026, ITP1:s
            tjänstepensionsregler och Bankgirots autogiro-flöde — så att
            besluten <em>känns</em> verkliga utan att <em>vara</em> det.
          </p>
        </div>
      </section>

      <section id="what-is-real" className="edl-section">
        <h2 className="edl-h2">Vad <em>är</em> riktigt?</h2>
        <div className="edl-prose">
          <p>
            Tre saker är riktiga:
          </p>
          <ul>
            <li>
              <strong>Datakällorna</strong> bakom modellerna —
              kommunalskatt, allmän pensionsavgift 7 %, statslåneräntan,
              IBB-cap, Konsumentverkets kategoribudgetar. Alla är
              dokumenterade och uppdateras minst en gång om året.
            </li>
            <li>
              <strong>Ditt konto</strong> — om du har skapat ett
              lärar-, familje- eller elevkonto sparas e-postadress,
              namn och en hashad lösenordsversion (bcrypt). Det är inte
              simulerat.
            </li>
            <li>
              <strong>Innehållet du producerar</strong> — anteckningar,
              reflektioner, beslut. De sparas i din egen databas och
              används för pedagogisk uppföljning.
            </li>
          </ul>
        </div>
      </section>

      <section id="what-is-not" className="edl-section">
        <h2 className="edl-h2">Vad är det <em>inte</em>?</h2>
        <div className="edl-prose">
          <ul>
            <li>
              <strong>Ekonomilabbet är inte finansiell rådgivning.</strong>
              Vi visar hur ISK fungerar, hur pension byggs över 30 år, hur
              kollektivavtalets förmåner värderas — men varken Echo
              (vår sokratiska AI) eller Maria (förhandlings-AI) är
              registrerade rådgivare. Inget vi säger ska tolkas som
              vägledning för dina egna pengar.
            </li>
            <li>
              <strong>Inga riktiga betalningar sker.</strong> EkonomilabbetID
              är vår simulerade BankID-motsvarighet och autogirona går
              till en simulerad Bankgirot-instans. Ingen riktig OCR-rad
              dras från ditt bankkonto.
            </li>
            <li>
              <strong>Ingen riktig deklaration.</strong> Skattedeklarationen
              som Evelina laddar in i K4-formatet är en pedagogisk
              illustration. Den lämnas aldrig in till Skatteverket.
            </li>
            <li>
              <strong>Inga riktiga investeringar.</strong> Avanza, AMF och
              andra fondnamn används som referens — de är inte affärspartners
              och ingen pengaöverföring sker till dem från plattformen.
            </li>
          </ul>
        </div>
      </section>

      <section id="data" className="edl-section">
        <h2 className="edl-h2">Hur hanteras <em>dina data</em>?</h2>
        <div className="edl-prose">
          <p>
            Plattformen är <strong>multi-tenant</strong> — varje elev har
            sin egen isolerade datalagring som bara läraren och eleven
            själv kan komma åt. För familjer gäller samma princip per
            barn.
          </p>
          <p>
            Vi sparar bara det vi behöver för att plattformen ska fungera
            pedagogiskt:
          </p>
          <ul>
            <li>E-postadress (för kontoåterställning och bekräftelser)</li>
            <li>Namn (för att kunna tala om eleven i lärar-vyn)</li>
            <li>Bcrypt-hashat lösenord (kan inte återskapas till klartext)</li>
            <li>Pedagogisk progression — moduler, reflektioner, beslut, mastery-poäng</li>
            <li>Sex-teckens-koder för elev-inloggning</li>
          </ul>
          <p>
            Vi delar <em>inte</em> data med tredje part i marknadsförings-
            eller analyssyfte. Vi använder Cloudflare Turnstile för bot-skydd
            (ingen cookie sätts) och Google Cloud Run för drift (data
            lagras i europe-north1, Finland).
          </p>
          <p>
            Ett konto kan raderas i sin helhet på begäran. Skicka mail till{" "}
            <a href="mailto:info@ekonomilabbet.org">info@ekonomilabbet.org</a>{" "}
            från den e-postadress som är kopplad till kontot.
          </p>
        </div>
      </section>

      <section id="ai" className="edl-section">
        <h2 className="edl-h2">AI och språkmodeller</h2>
        <div className="edl-prose">
          <p>
            Plattformen använder <strong>Claude</strong> (Anthropic) för
            tre saker:
          </p>
          <ul>
            <li>
              <strong>Echo</strong> — sokratisk reflektions-coach som
              ställer öppna frågor istället för att ge svar.
            </li>
            <li>
              <strong>AI-Maria</strong> — simulerad HR-chef i lönesamtal
              med Linda. Hon är en deterministisk förhandlingsmotor som
              styrs av Akavia-data, inte en rådgivare.
            </li>
            <li>
              <strong>Lärar-assistens</strong> — AI som kan hjälpa läraren
              med uppgifter, sammanfattningar och kursplanering.
            </li>
          </ul>
          <p>
            All AI-funktionalitet kräver att lärarens administrativa
            kontosida har <em>AI-funktioner aktiverade</em>. Detta är
            avstängt som standard. Eleven konsumerar tokens från lärarens
            konto — vi loggar varje anrop för transparens och budget-kontroll.
          </p>
          <p>
            Vi sparar inte AI-prompts eller AI-svar permanent utöver det
            som syns i pedagogiska reflektioner. Ingen elev-data skickas
            till Anthropic utöver det som behövs för det specifika anropet.
          </p>
        </div>
      </section>

      <section id="children" className="edl-section">
        <h2 className="edl-h2">Barn och GDPR</h2>
        <div className="edl-prose">
          <p>
            Plattformen är byggd för svensk skola och svenska familjer.
            Elever <strong>under 13 år</strong> kan endast registreras av
            sin lärare eller förälder — aldrig själva. Sex-teckens-koden
            är medvetet enkel för att fungera på lågstadiet utan
            personuppgifter.
          </p>
          <p>
            Föräldrar har rätt att begära ut, korrigera eller radera sitt
            barns data. Skicka mail till{" "}
            <a href="mailto:info@ekonomilabbet.org">info@ekonomilabbet.org</a>{" "}
            så svarar vi inom 14 dagar (lagstadgad gräns enligt artikel 12
            GDPR).
          </p>
        </div>
      </section>

      <section id="liability" className="edl-section">
        <h2 className="edl-h2">Ansvar och begränsningar</h2>
        <div className="edl-prose">
          <p>
            Vi gör vårt bästa för att modellerna ska spegla svensk
            lagstiftning, kollektivavtal och marknadsdata, men:
          </p>
          <ul>
            <li>
              Plattformen kan ha buggar. Felaktiga siffror, missade
              edge-case och drift-störningar förekommer.
            </li>
            <li>
              Datakällor uppdateras regelbundet men kan ligga något efter
              verkligheten (t.ex. en ny statslåneränta som just släppts).
            </li>
            <li>
              Pedagogisk effekt varierar. Plattformen är ett verktyg —
              utfallet beror på hur läraren använder den.
            </li>
          </ul>
          <p>
            Vi har inget skadeståndsansvar för beslut du tar i ditt eget
            ekonomiska liv baserat på vad du lärt dig här. Använd plattformen
            som vad den är: en simulering där det är säkert att göra fel.
          </p>
        </div>
      </section>

      <section id="changes" className="edl-section">
        <h2 className="edl-h2">När villkoren ändras</h2>
        <div className="edl-prose">
          <p>
            Vi uppdaterar villkoren när plattformen utvecklas. Vid
            väsentliga förändringar mailar vi alla aktiva konton minst
            två veckor innan ändringen träder i kraft. Mindre redaktionella
            justeringar publiceras direkt med datum längst ner.
          </p>
          <p>
            <em>Senast uppdaterad: 29 april 2026.</em>
          </p>
        </div>
      </section>

      <div className="edl-callout">
        <div className="edl-callout-eye">Frågor?</div>
        <p>
          Skriv till <a href="mailto:info@ekonomilabbet.org" style={{ color: "#92400e", textDecoration: "underline" }}>info@ekonomilabbet.org</a>.
          Vi svarar normalt inom två vardagar. Om du föredrar att läsa mer
          först — vår <Link to="/docs" style={{ color: "#92400e", textDecoration: "underline" }}>dokumentation</Link>{" "}
          och våra <Link to="/faq" style={{ color: "#92400e", textDecoration: "underline" }}>vanliga frågor</Link>{" "}
          täcker det mesta.
        </p>
      </div>
    </EditorialLightShell>
  );
}
