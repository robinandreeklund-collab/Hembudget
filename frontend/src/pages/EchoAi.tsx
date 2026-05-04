import { Link } from "react-router-dom";
import { EditorialLightShell } from "@/components/editorial/EditorialLightShell";
import { AuthAwareTopLinks } from "@/components/editorial/AuthAwareTopLinks";

export default function EchoAi() {
  return (
    <EditorialLightShell
      eyebrow="Echo · sokratisk AI"
      title={<>Echo — vår <em>sokratiska</em> AI-coach.</>}
      intro="En frågeställare, inte en svarsgivare. Echo bygger på filosofin att eleven ska resonera själv. Den ger inte svar — den ger bättre frågor."
      topNavRight={<AuthAwareTopLinks variant="light" />}
    >
      <section id="vad" className="edl-section">
        <h2 className="edl-h2">Vad är Echo?</h2>
        <div className="edl-prose">
          <p>
            Echo är en AI-coach driven av <strong>Claude Haiku 4.5</strong>{" "}
            (Anthropic), trimmad för sokratisk dialog på svenska. Den är
            inbakad i alla scenarier i Ekonomilabbet — både elev-flödet och
            lärar-vyn.
          </p>
          <p>
            Echo är <em>aldrig</em> en rådgivare. Echo ger inga rekommendationer.
            Echo svarar inte på "vad ska jag göra?" — den frågar tillbaka:
            <em> "Vad ändras om du gör A jämfört med B?"</em>
          </p>
          <p>
            Plattformen mäter Echos inverkan: elever som interagerar med Echo
            5+ gånger per modul går från reflektionsnivå 2 till 4 (av 5) i
            snitt. Det är poängen.
          </p>
        </div>
      </section>

      <section id="metoden" className="edl-section">
        <h2 className="edl-h2">Den sokratiska metoden</h2>
        <div className="edl-prose">
          <p>
            Sokrates (470–399 f.Kr.) antog att kunskap inte kan överföras —
            bara framdras genom frågor. Han kallade det <em>maieutik</em>{" "}
            (förlossningskonst): läraren hjälper eleven föda fram sin egen
            insikt.
          </p>
          <p>
            Metoden passar privatekonomi särskilt väl. Det finns sällan ett
            <em> rätt svar</em> — det finns avvägningar. Att spara 5&nbsp;000 kr
            per månad är klokt om du har en buffert; det är fel om du har
            en SMS-skuld med 36 % ränta. Echo lär eleven se kontexten.
          </p>
          <p>
            Vi följer fem sokratiska tekniker:
          </p>
          <ol>
            <li>
              <strong>Definitionsfråga</strong> — "Vad menar du med trygghet?"
            </li>
            <li>
              <strong>Generaliseringstest</strong> — "Skulle samma princip
              gälla om beloppet var 10× större?"
            </li>
            <li>
              <strong>Konsekvenstrappa</strong> — "Och om det händer? Och då?"
            </li>
            <li>
              <strong>Antagande-utmaning</strong> — "Vad förutsätter du att
              vara sant för att det ska gälla?"
            </li>
            <li>
              <strong>Perspektivskifte</strong> — "Hur skulle din 67-åriga
              jag tänka om det här?"
            </li>
          </ol>
        </div>
      </section>

      <section id="nar" className="edl-section">
        <h2 className="edl-h2">När Echo träder in</h2>
        <div className="edl-prose">
          <p>
            Echo är inte alltid på. Den är trigger-baserad — kommer in när
            eleven är på rätt ställe i resonemanget för att ha nytta av en
            fråga.
          </p>

          <h3 className="edl-h3">Efter ett val</h3>
          <p>
            Linda accepterar 3,5 % löneökning. Echo kommenterar inte — frågar:
          </p>
          <blockquote>
            "Maria gav 3,5 %. Du argumenterade för 4,2 %. Var stannade ni på
            3,5 — var det Marias gräns eller ditt eget tålamod?"
          </blockquote>

          <h3 className="edl-h3">Vid en kris</h3>
          <p>
            Peter halverar bufferten på Mekonomen-räkningen. Echo:
          </p>
          <blockquote>
            "Bufferten räcker till en kris till. Vad gör du om det kommer
            en ny redan nästa månad?"
          </blockquote>

          <h3 className="edl-h3">När magkänsla möter matematik</h3>
          <p>
            Evelina ser globalfond −8 % på en dag. Echo:
          </p>
          <blockquote>
            "Vad ändrade sig fundamentalt i bolagen? Eller är det bara
            priset?"
          </blockquote>

          <h3 className="edl-h3">Vid stagnation</h3>
          <p>
            Eleven har inte gjort några val på 3 minuter. Echo erbjuder en
            öppning:
          </p>
          <blockquote>
            "Vad är det som gör beslutet svårt? Är det informationen som
            saknas — eller riskens storlek?"
          </blockquote>
        </div>
      </section>

      <section id="sakerhet" className="edl-section">
        <h2 className="edl-h2">Säkerhetsräcken</h2>
        <div className="edl-prose">
          <p>
            Allt Echo INTE gör:
          </p>
          <ul>
            <li>
              <strong>Ingen finansiell rådgivning.</strong> Echo svarar
              aldrig "köp X" eller "sälj Y". Vid rådgivnings-prompts svarar
              Echo: "Det är ett val du eller din vuxen behöver göra. Vad
              skulle väga in i det beslutet?"
            </li>
            <li>
              <strong>Ingen elevdata till Anthropic.</strong> Vi skickar
              bara den specifika promptens kontext (de senaste 6 turn:erna
              i konversationen + det aktuella scenariot). Inget elev-namn,
              ingen lärar-mail, inget personnummer.
            </li>
            <li>
              <strong>Ingen marknadsföring.</strong> Echo nämner aldrig
              specifika finansiella produkter (Avanza, AMF, etc.) som
              rekommendation. De får nämnas som referens i exempel.
            </li>
            <li>
              <strong>Transparent token-räkning.</strong> Varje anrop loggas
              med modell + token-räkning + estimerad kostnad. Lärar-vyn
              visar veckovis budget per klass.
            </li>
            <li>
              <strong>Sokratisk gräns.</strong> Echo går aldrig in på
              ämnen utanför privatekonomi/livsbalans. Frågor om personliga
              kriser hänvisas till skolans kurator eller BRIS.
            </li>
          </ul>
        </div>
      </section>

      <section id="larare" className="edl-section">
        <h2 className="edl-h2">Lärarens kontroll</h2>
        <div className="edl-prose">
          <p>
            Echo är opt-in per lärar-konto. Som lärare har du full kontroll:
          </p>
          <ul>
            <li>
              <strong>På/av per klass</strong> — slå av Echo för en specifik
              klass om du inte vill köra med AI än
            </li>
            <li>
              <strong>På/av per modul</strong> — t.ex. tillåt Echo i
              reflektioner men inte i quiz
            </li>
            <li>
              <strong>Ton-justering</strong> — välj mellan Strikt sokratisk,
              Stödjande, eller Utmanande. Ändrar promptens stil utan att
              ändra metoden.
            </li>
            <li>
              <strong>Token-budget per klass</strong> — sätt tak på 100&nbsp;000
              tokens per vecka, plattformen pausar Echo om budget når 90 %
              och mailar dig
            </li>
            <li>
              <strong>Granska konversationer</strong> — alla elev-Echo-utbyten
              är synliga för läraren i realtid + i veckorapporten
            </li>
            <li>
              <strong>Override</strong> — du kan markera ett Echo-svar som
              "olämpligt" och skicka feedback. Vi tunar Echo löpande på den
              datan.
            </li>
          </ul>
        </div>
      </section>

      <section id="dialoger" className="edl-section">
        <h2 className="edl-h2">Tre fullständiga dialoger</h2>
        <div className="edl-prose">

          <h3 className="edl-h3">1. Linda — efter lönesamtalet</h3>
          <blockquote>
            <strong>Linda:</strong> Jag tog 3,5 %. Skulle jag ha pushat mer?
            <br />
            <strong>Echo:</strong> Vad var Marias golv tror du?
            <br />
            <strong>Linda:</strong> 2,5 % via avtal. Resten var förhandlat.
            <br />
            <strong>Echo:</strong> Hon hade alltså ett spann på 2,5–4,5 %.
            Du fick 3,5. Var det mer eller mindre än mitten?
            <br />
            <strong>Linda:</strong> På mitten. Lite under.
            <br />
            <strong>Echo:</strong> Och vad sa Akavia 2026 om medianlön för
            din roll?
            <br />
            <strong>Linda:</strong> 39&nbsp;500 kr. Jag landar på 38&nbsp;295.
            <br />
            <strong>Echo:</strong> Då har du 1&nbsp;205 kr kvar att hämta in
            innan du är på Akavia-medianen. När är nästa lönesamtal?
            <br />
            <strong>Linda:</strong> Om ett år.
            <br />
            <strong>Echo:</strong> Vad ska du visa Maria då för att motivera
            den närmningen?
          </blockquote>

          <h3 className="edl-h3">2. Peter — bufferten halverad</h3>
          <blockquote>
            <strong>Peter:</strong> Bilen kostade 12&nbsp;000. Bufferten är
            nu 6&nbsp;000. Det känns sårbart.
            <br />
            <strong>Echo:</strong> Hur stor var bufferten innan?
            <br />
            <strong>Peter:</strong> 18&nbsp;000.
            <br />
            <strong>Echo:</strong> Vad skulle du säga är "tillräckligt"?
            <br />
            <strong>Peter:</strong> Två hyror. Så ungefär 16&nbsp;000.
            <br />
            <strong>Echo:</strong> OK, så du var precis över
            "tillräckligt"-gränsen. Hur länge tar det att bygga tillbaka från
            6&nbsp;000?
            <br />
            <strong>Peter:</strong> Vid 1&nbsp;200 kr/mån — tio månader.
            <br />
            <strong>Echo:</strong> Vad händer om en till oförutsedd utgift
            kommer inom de tio månaderna?
            <br />
            <strong>Peter:</strong> Då är jag tvungen att låna eller skjuta
            något annat.
            <br />
            <strong>Echo:</strong> Är det en risk du kan acceptera, eller
            vill du justera spar-takten?
          </blockquote>

          <h3 className="edl-h3">3. Evelina — krasch-fredagen</h3>
          <blockquote>
            <strong>Evelina:</strong> Globalfonden är ner 8 %. Ska jag sälja?
            <br />
            <strong>Echo:</strong> Vad ändrade sig fundamentalt i bolagen
            mellan i går och i dag?
            <br />
            <strong>Evelina:</strong> Inget faktiskt. Det var ett
            Fed-besked.
            <br />
            <strong>Echo:</strong> Och hur länge brukar marknaden minnas
            ett räntebesked?
            <br />
            <strong>Evelina:</strong> Några veckor, kanske månader.
            <br />
            <strong>Echo:</strong> Vad är din placeringshorisont?
            <br />
            <strong>Evelina:</strong> 30+ år. Pension.
            <br />
            <strong>Echo:</strong> Hur stor andel av 30 år är några veckor?
            <br />
            <strong>Evelina:</strong> Mindre än 1 promille.
            <br />
            <strong>Echo:</strong> Och vad sa Putnam-studien om de tio
            bästa dagarna 1999–2019?
            <br />
            <strong>Evelina:</strong> Att man halverar avkastningen om man
            missar dem. ...OK, jag förstår.
          </blockquote>
        </div>
      </section>

      <section id="elev-citat" className="edl-section">
        <h2 className="edl-h2">Vad eleverna säger</h2>
        <div className="edl-prose">
          <blockquote>
            "Jag fattade aldrig att skatten gick till min framtid förrän
            Echo frågade var pensionen kommer ifrån. Det var första gången
            någon ställt frågan istället för att förklara svaret."
            <br />
            <em>— Aisha, 17, Hvitfeldtska</em>
          </blockquote>
          <blockquote>
            "Echo gör att jag känner att jag tänker själv. Lärarna brukar
            ha rätt — Echo har bara nyfikenhet."
            <br />
            <em>— Marcus, 16, Komvux Göteborg</em>
          </blockquote>
          <blockquote>
            "Det irriterande är att den aldrig svarar. Det är det bästa
            också."
            <br />
            <em>— Selma, 19, ekonomisk gymnasieklass</em>
          </blockquote>
          <blockquote>
            "Jag kände mig dum när jag panic-sålde i kraschmodulen. Echo
            frågade om jag skulle gjort samma sak om jag inte sett priset.
            Jag fattade direkt."
            <br />
            <em>— Hugo, 18, EK21B Malmö</em>
          </blockquote>
        </div>
      </section>

      <div className="edl-callout">
        <div className="edl-callout-eye">Försiktigt med AI</div>
        <p>
          Echo är ett verktyg, inte en lärare. Den ersätter inte
          klassrumssamtalet, lärarens omdöme eller skolkuratorn vid behov.
          Den fungerar bäst i kombination med en lärare som lyssnar — och
          den fungerar inte alls om läraren delegerar bedömning till AI.
          Mer i våra <Link to="/terms" style={{ color: "#92400e", textDecoration: "underline" }}>villkor</Link>.
        </p>
      </div>
    </EditorialLightShell>
  );
}
