import { Link } from "react-router-dom";
import { EditorialLightShell } from "@/components/editorial/EditorialLightShell";
import { AuthAwareTopLinks } from "@/components/editorial/AuthAwareTopLinks";

export default function Lararguider() {
  return (
    <EditorialLightShell
      eyebrow="Lärarguider · Vol. 01"
      title={<>Lärarguider för <em>klassrummet</em>.</>}
      intro="Allt du behöver för att rulla ut Ekonomilabbet i en svensk klass — från åk 6 till gymnasiet. Färdiga veckoplaner, sokratiska diskussioner, differentiering, bedömning."
      topNavRight={<AuthAwareTopLinks variant="light" />}
    >
      <section id="snabbstart" className="edl-section">
        <h2 className="edl-h2">Snabbstart för läraren</h2>
        <div className="edl-prose">
          <p>
            Femton minuter, ingen IT-support behövs. När du är klar har
            klassen sex-teckens-koder och du har en första modul tilldelad.
          </p>
          <ol>
            <li>
              <strong>Skapa lärarkonto</strong> via{" "}
              <Link to="/signup/teacher">/signup/teacher</Link> och bekräfta
              mailet (länken är giltig 24 h).
            </li>
            <li>
              <strong>Skapa klass</strong> i lärarvyn — namn, årskurs, ämne.
              Plattformen genererar 30 sex-teckens-koder direkt.
            </li>
            <li>
              <strong>Skriv ut kodlistan</strong> som PDF (en kod per rad,
              elevnamn ifyllda om du vill). Eller maila ut via skolans
              Office-365-koppling.
            </li>
            <li>
              <strong>Tilldela "Din första månad"</strong> — den färdig­in­lästa
              modulen om 4 lektioner som introducerar lön, skatt, budget.
            </li>
            <li>
              <strong>Kör första lektionen</strong> i klassrummet. 8 min
              demonstration, 25 min eget arbete, 12 min diskussion.
            </li>
          </ol>
          <p>
            Direkt efter första lektionen ser du WB-pentagonen för varje
            elev. Du vet redan vem som behöver prat innan provet.
          </p>
        </div>
      </section>

      <section id="veckoplaner" className="edl-section">
        <h2 className="edl-h2">Veckoplaner — sagorna som <em>lektionsmaterial</em></h2>
        <div className="edl-prose">
          <p>
            Varje persona-saga (Linda, Peter, Evelina) är strukturerad som
            5–7 lektioner. Du kan köra dem i ordning, mixa, eller hoppa
            mellan beroende på var klassen är.
          </p>

          <h3 className="edl-h3">Lindas saga · 6 lektioner · åk 9 → gym</h3>
          <ul>
            <li><strong>Lektion 1</strong> — Söndagskvällen + lönesamtalet (45 min)</li>
            <li><strong>Lektion 2</strong> — Pensionsavgiften som upptäcks (Echo-djupdyk, 60 min)</li>
            <li><strong>Lektion 3</strong> — Den oförutsedda tandläkaren + buffert-resonemang (45 min)</li>
            <li><strong>Lektion 4</strong> — Karriärsamtalet: avvägning fritid vs. lön (60 min)</li>
            <li><strong>Lektion 5</strong> — Pentagon-review + WB-index (60 min)</li>
            <li><strong>Lektion 6</strong> — Lärarvy + reflektion (45 min)</li>
          </ul>

          <h3 className="edl-h3">Peters saga · 5 lektioner · gym + komvux</h3>
          <ul>
            <li><strong>Lektion 1</strong> — Söndag kväll: 23 fakturor + autogiro</li>
            <li><strong>Lektion 2</strong> — Bilen i verkstad: bufferten testas</li>
            <li><strong>Lektion 3</strong> — Kategorisering + huvudbok</li>
            <li><strong>Lektion 4</strong> — Lönen kommer in + prioriteringar</li>
            <li><strong>Lektion 5</strong> — Månadsprognos + lärarvy</li>
          </ul>

          <h3 className="edl-h3">Evelinas saga · 6 lektioner · gym + företagsekonomi</h3>
          <ul>
            <li><strong>Lektion 1</strong> — Marknadsöppning + ISK-grunderna</li>
            <li><strong>Lektion 2</strong> — Portföljallokering + diversifiering</li>
            <li><strong>Lektion 3</strong> — Krasch-fredagen: tid i marknaden, inte timing</li>
            <li><strong>Lektion 4</strong> — Skattedeklaration + K4-blanketten</li>
            <li><strong>Lektion 5</strong> — 12-mån-review + index</li>
            <li><strong>Lektion 6</strong> — Lärarvy + krasch-pedagogik</li>
          </ul>
        </div>
      </section>

      <section id="diskussioner" className="edl-section">
        <h2 className="edl-h2">Klassrumsdiskussioner</h2>
        <div className="edl-prose">
          <p>
            Echo ställer sokratiska frågor i plattformen — samma frågor
            funkar utmärkt som diskussionsuppslag. Skriv frågan på tavlan,
            låt klassen prata 10 minuter, summera.
          </p>
          <ul>
            <li>
              <em>Lönesamtal:</em> "Akavia säger 39&nbsp;500. Du tjänar
              38&nbsp;000. Var börjar du förhandlingen — på medianen, över,
              eller vid förra budet?"
            </li>
            <li>
              <em>Pension:</em> "Var detta avdrag som händer dig — eller
              en investering du gör i ditt 67-åriga jag?"
            </li>
            <li>
              <em>Krasch:</em> "Vad ändrade sig fundamentalt i bolagen? Eller
              är det bara priset?"
            </li>
            <li>
              <em>Buffert:</em> "Bufferten räcker till en kris till. Vad
              gör du om det kommer en till nästa månad?"
            </li>
            <li>
              <em>Wellbeing:</em> "Skulle dina vikter se annorlunda ut? Är
              ekonomi 25 % för dig — eller mindre? Mer?"
            </li>
          </ul>
        </div>
      </section>

      <section id="differentiering" className="edl-section">
        <h2 className="edl-h2">Differentiering</h2>
        <div className="edl-prose">
          <h3 className="edl-h3">Åk 6–9 vs. gymnasium</h3>
          <p>
            För åk 6–7: kör bara <em>Lindas första två dagar</em> (söndag +
            lönesamtal) och <em>Peters fakturor</em>. Begränsa Echo till
            10 frågor per session.
          </p>
          <p>
            För gymnasium: hela sagan + djupdyk + Wellbeing-pentagon-
            kalibrering. Tilldela egna scenarier som hemarbete.
          </p>

          <h3 className="edl-h3">Svaga vs. starka elever</h3>
          <p>
            <strong>Svaga:</strong> stäng av Echo:s sokratiska frågor och
            sätt på <em>Echo-förklara</em> istället. Eleven får en pedagogisk
            förklaring direkt vid fel-svar. Lås upp moduler i ordning.
          </p>
          <p>
            <strong>Starka:</strong> ge dem öppen tillgång till alla djupdyk.
            Tilldela en <em>egen scenario</em>-uppgift där de bygger en
            modul åt en yngre klass.
          </p>

          <h3 className="edl-h3">Nyanlända elever</h3>
          <p>
            Plattformen visar all UI på svenska men språknivån i scenarier
            är åk 7 (Lix ~38). Echo kan be om förklaringar på enklare svenska.
            Sex-teckens-kod-inloggningen funkar utan att eleven behöver kunna
            stava sin email.
          </p>
        </div>
      </section>

      <section id="bedomning" className="edl-section">
        <h2 className="edl-h2">Bedömning i tre nivåer</h2>
        <div className="edl-prose">
          <p>
            Plattformen ger dig formativ, summativ och autentisk bedömning
            samtidigt — utan extra arbete för dig.
          </p>
          <ol>
            <li>
              <strong>Formativ</strong> — WB-pentagonen uppdateras varje
              gång eleven gör ett val. Du ser i realtid vem som behöver stöd.
            </li>
            <li>
              <strong>Summativ</strong> — reflektioner och quiz-resultat
              aggregeras till mastery per kompetens (12 systemkompetenser).
              Mappade mot Lgr22/Gy25.
            </li>
            <li>
              <strong>Autentisk</strong> — eleven producerar riktiga
              dokument (lönespec, kontoutdrag, K4-blankett) som visar
              tillämpning, inte bara kunskap.
            </li>
          </ol>
          <p>
            Mer detaljer i <Link to="/rubriker">Bedömningsmallar</Link> och{" "}
            <Link to="/lgr22">Lgr22-mappningen</Link>.
          </p>
        </div>
      </section>

      <section id="fallgropar" className="edl-section">
        <h2 className="edl-h2">Vanliga fallgropar</h2>
        <div className="edl-prose">
          <ul>
            <li>
              <strong>Att låta eleverna hoppa över Echo.</strong> Echo:s
              frågor är poängen — utan dem blir plattformen ett räkne-quiz.
              Sätt aldrig <em>autoaccept</em> på Echo-prompts.
            </li>
            <li>
              <strong>Att börja med pensions-djupdyket först.</strong> Det
              är 30 år bort — för abstrakt. Börja med lönesamtalet eller
              fakturorna, sen pension.
            </li>
            <li>
              <strong>Att jämföra elevers WB-index direkt.</strong>{" "}
              Pentagonen mäter välbefinnande, inte rätt/fel. Lärar-vyn
              visar trend per elev, inte ranking.
            </li>
            <li>
              <strong>Att inte använda lärarvyn på söndagskvällen.</strong>{" "}
              Tio minuter söndagskväll = du vet vem som behöver prat på
              måndag morgon. Det är där plattformens värde är störst.
            </li>
            <li>
              <strong>Att välja AI av i lärar-kontot.</strong> Då försvinner
              Echo, Maria och förklaringarna. Eleven får bara siffror, inte
              insikter. Sätt på AI på första försöket.
            </li>
            <li>
              <strong>Att modulen "Din första månad" känns för enkel.</strong>{" "}
              Den är medvetet låg friktion för att alla ska komma igenom
              första veckan. Riktig fördjupning kommer i sagorna.
            </li>
          </ul>
        </div>
      </section>

      <section id="material" className="edl-section">
        <h2 className="edl-h2">Material att hämta</h2>
        <div className="edl-prose">
          <p>
            Allt material genereras direkt i plattformen och kan hämtas som
            PDF. Du loggar in som lärare och går till{" "}
            <strong>Lärarverktyg → Material</strong>.
          </p>
          <ul>
            <li>Lärarguider (PDF, A4) — en per saga, 12–18 sidor</li>
            <li>Lektionsplaner (PDF) — 45 / 60 min, mål, tidsplan, hemarbete</li>
            <li>Bedömningsmallar (PDF) — 12 kompetenser × 4 nivåer</li>
            <li>Slides (Google Slides + PowerPoint) — för introduktion</li>
            <li>Klass-portfolio (ZIP) — alla elevers PDF:er på en gång</li>
          </ul>
          <p>
            Saknar du något? Skriv till{" "}
            <a href="mailto:info@ekonomilabbet.org">info@ekonomilabbet.org</a>{" "}
            — vi bygger material löpande baserat på lärar-feedback.
          </p>
        </div>
      </section>

      <div className="edl-callout">
        <div className="edl-callout-eye">Lärar-utbildning</div>
        <p>
          Skolor som rullar ut Ekonomilabbet till en hel årskurs får tillgång
          till en 90-min onboarding-workshop. Vi går igenom plattformen,
          kör en demo-klass och svarar på frågor. Boka via{" "}
          <a href="mailto:info@ekonomilabbet.org" style={{ color: "#92400e", textDecoration: "underline" }}>info@ekonomilabbet.org</a>.
        </p>
      </div>
    </EditorialLightShell>
  );
}
