import { Link } from "react-router-dom";
import { EditorialLightShell } from "@/components/editorial/EditorialLightShell";
import { AuthAwareTopLinks } from "@/components/editorial/AuthAwareTopLinks";

const COMPETENCES: Array<{ n: number; name: string; brief: string }> = [
  { n: 1, name: "Lönespec & nettolön", brief: "Brutto → A-skatt + pensionsavgift → netto. OB, övertid, semesterersättning." },
  { n: 2, name: "Skattesystemet", brief: "Kommunal + statlig + jobbskatteavdrag + grundavdrag. Skiktgränser. Arbetsgivaravgift." },
  { n: 3, name: "Pensionspotten", brief: "Allmän 7 % + tjänste 4,5 % + premiepension. Ränta-på-ränta över 30+ år." },
  { n: 4, name: "Kollektivavtalets förmåner", brief: "ITP1, sjukförsäkring, semesterlön, föräldralön, övertidsersättning." },
  { n: 5, name: "ISK & kapitalvinstskatt", brief: "Schablonintäkt, kapitalbas, K4. När ISK vinner mot AF (avkastningsfond)." },
  { n: 6, name: "Portföljallokering", brief: "Risk-anpassning över tid. Globalfond / svensk index / räntefond. Re-balansering." },
  { n: 7, name: "Marknadsrisk & krasch", brief: "Volatilitet, drawdown, återhämtning. Tid i marknaden, inte timing av marknaden." },
  { n: 8, name: "Hushållsbudget & buffert", brief: "Konsumentverkets kategorier, prioriteringar, oförutsedda utgifter, buffertstorlek." },
  { n: 9, name: "Autogiro & EkonomilabbetID", brief: "Bankgirot, OCR, kollektiv signering, stoppfrist, granskning av oregelbundna belopp." },
  { n: 10, name: "Konsumentval & impulsskatt", brief: "Marginalskatt på köpglädje, behov vs. vill, jämförpris, ångerrätt och garanti." },
  { n: 11, name: "Lån, ränta & avbetalning", brief: "Effektiv ränta, amortering, KALP, SMS-lån-fällor, konsolideringslån." },
  { n: 12, name: "Wellbeing & livsbalans", brief: "WB-pentagonens fem axlar. Vägt snitt 25/20/20/15/20. Trade-offs över tid." },
];

export default function Rubriker() {
  return (
    <EditorialLightShell
      eyebrow="Bedömningsmallar · Vol. 01"
      title={<>Bedömningsmallar med <em>fingerkänsla</em>.</>}
      intro="Tre lager bedömning samtidigt — formativ, summativ, autentisk. Mappade mot Lgr22, Gy25 och Skolverkets bedömningsstöd. Allt utan att eleven märker att de bedöms."
      topNavRight={<AuthAwareTopLinks variant="light" />}
    >
      <section id="tre-lager" className="edl-section">
        <h2 className="edl-h2">Tre lager — formativ, summativ, autentisk</h2>
        <div className="edl-prose">
          <p>
            Traditionell bedömning är binär: prov på fredagen, betyg vecka
            därpå. Plattformen jobbar tre lager parallellt så du har data
            innan provet — och så eleven aldrig sitter och slipas mot ett
            slutomdöme.
          </p>
          <h3 className="edl-h3">Formativ — i realtid</h3>
          <p>
            WB-pentagonen uppdateras varje gång eleven gör ett val. Du ser
            vem som spendrar i panik, vem som planerar, vem som blir
            paralyserad av oförutsedda utgifter. Lärar-vyn larmar vid
            5 dagars passivitet eller WB &lt; 50.
          </p>
          <h3 className="edl-h3">Summativ — terminsslut</h3>
          <p>
            12 systemkompetenser, 4 nivåer per kompetens. Eleven får
            mastery-poäng genom reflektioner, quiz, och beslut. Plattformen
            föreslår betyg E/C/A baserat på snitt + djup. Du bekräftar
            eller justerar.
          </p>
          <h3 className="edl-h3">Autentisk — produkter, inte prov</h3>
          <p>
            Eleven producerar riktiga dokument: lönespec som ReportLab-PDF,
            kontoutdrag, K4-blankett, månadsprognos. De visar tillämpning,
            inte bara kunskap — och kan inte fuskas via Google.
          </p>
        </div>
      </section>

      <section id="mastery" className="edl-section">
        <h2 className="edl-h2">Mastery-rubriken — 12 systemkompetenser</h2>
        <div className="edl-prose">
          <p>
            Varje kompetens bedöms i 4 nivåer: <strong>Saknar</strong> /{" "}
            <strong>Påbörjad</strong> / <strong>Säker</strong> /{" "}
            <strong>Förebild</strong>. Saknar = F, Påbörjad = E, Säker = C,
            Förebild = A.
          </p>
          <ul>
            {COMPETENCES.map((c) => (
              <li key={c.n}>
                <strong>{c.n.toString().padStart(2, "0")} · {c.name}</strong>
                {" — "}
                {c.brief}
              </li>
            ))}
          </ul>

          <h3 className="edl-h3">Exempel — Lönespec &amp; nettolön (kompetens 01)</h3>
          <ul>
            <li>
              <strong>Saknar (F)</strong> — eleven läser lönespecen som en
              siffra, kan inte förklara skillnaden mellan brutto och netto.
            </li>
            <li>
              <strong>Påbörjad (E)</strong> — eleven kan peka ut brutto,
              skatt, netto. Vet att skatt är en procentandel.
            </li>
            <li>
              <strong>Säker (C)</strong> — eleven förklarar A-skatt-tabellen,
              kan räkna effektiv skattesats, ser pensionsavgiften som en
              egen rad.
            </li>
            <li>
              <strong>Förebild (A)</strong> — eleven jämför sin lönespec med
              Akavia-data, identifierar OB &amp; övertid, förklarar
              arbetsgivaravgiften som "Vismas verkliga kostnad" + visar
              den till en annan elev.
            </li>
          </ul>
        </div>
      </section>

      <section id="reflektion" className="edl-section">
        <h2 className="edl-h2">Reflektionsrubriken</h2>
        <div className="edl-prose">
          <p>
            Echo:s sokratiska frågor utlöser reflektioner som plattformen
            poängsätter i 5 nivåer:
          </p>
          <ol>
            <li>
              <strong>Ytlig (1 av 5)</strong> — "Det var lätt." / "Jag vet inte."
            </li>
            <li>
              <strong>Beskrivande (2)</strong> — "Lönen var 32&nbsp;000.
              Skatten tog 28 %."
            </li>
            <li>
              <strong>Förklarande (3)</strong> — "Lönen var 32&nbsp;000 men
              kommunalskatten är 30 % i Stockholm, så efter avdrag…"
            </li>
            <li>
              <strong>Resonerande (4)</strong> — "Om jag jobbar OB jämfört
              med rakt schema får jag 480 kr extra. Det motsvarar 1,5 % av
              månadslönen — men kostar mig en helgkväll."
            </li>
            <li>
              <strong>Reflekterande (5)</strong> — "Jag fattade inte hur
              mycket av min lön som är osynlig förmån via avtalet. Det
              ändrade min syn på fast vs. tillsvidare-anställning."
            </li>
          </ol>
          <p>
            Plattformen detekterar nivå via natural language-mönster (svensk
            modell, tränad på 4&nbsp;000 elev-reflektioner från pilot­studien
            2025). Du som lärare kan justera per reflektion och se
            poängdistribution över klassen.
          </p>
        </div>
      </section>

      <section id="klass" className="edl-section">
        <h2 className="edl-h2">Klass-rubriken (för rektor &amp; admin)</h2>
        <div className="edl-prose">
          <p>
            Skolledningen får en aggregerad vy:
          </p>
          <ul>
            <li>
              Klassens snittvärde per kompetens (12 staplar)
            </li>
            <li>
              Spridning (standardavvikelse) — visar om klassen är
              homogen eller om vissa elever släpar
            </li>
            <li>
              Trend över terminer (12-veckors-snapshots)
            </li>
            <li>
              Jämförelse mot skolans övriga klasser (anonymt)
            </li>
            <li>
              Anpassningar enligt Skolverket — flagga elever med särskilt
              stöd, IUP eller åtgärdsprogram
            </li>
          </ul>
          <p>
            Rektor ser inte enskilda elev-svar — bara aggregerad data. Den
            elevspecifika nivån är skyddad bakom lärar-rollen.
          </p>
        </div>
      </section>

      <section id="anpassning" className="edl-section">
        <h2 className="edl-h2">Anpassningar enligt Skolverket</h2>
        <div className="edl-prose">
          <p>
            För elever med särskilt stöd, IUP eller åtgärdsprogram kan du
            justera:
          </p>
          <ul>
            <li>
              <strong>Förenkla språknivå</strong> — Echo svarar på enklare
              svenska (Lix &lt;30), korta meningar, faktarutor istället för
              utvecklat resonemang.
            </li>
            <li>
              <strong>Skip vissa kompetenser</strong> — t.ex. om eleven inte
              ska bedömas på <em>ISK &amp; kapitalvinstskatt</em>, exkludera
              den från slut-snittet.
            </li>
            <li>
              <strong>Fler försök på quiz</strong> — eleven får 3 försök
              istället för 1 på varje fråga, med Echo-förklaring mellan.
            </li>
            <li>
              <strong>Tids-flexibel reflektion</strong> — minimum 10 tecken
              istället för 30; minimum 1 av 5 nivåer accepteras.
            </li>
            <li>
              <strong>Privat lärar-feedback</strong> — eleven får en personlig
              kommentar från läraren istället för auto-scoring.
            </li>
          </ul>
          <p>
            Anpassningarna dokumenteras automatiskt i elevens IUP-journal som
            kan hämtas som PDF för åtgärdsprogrammets uppföljning.
          </p>
        </div>
      </section>

      <section id="exempel" className="edl-section">
        <h2 className="edl-h2">Exempel — Linda får B i Privatekonomi</h2>
        <div className="edl-prose">
          <p>
            Linda går termin 4 i gymnasiet, kursen Privatekonomi 100p. Vid
            slutet kommer plattformen med ett underlag.
          </p>

          <h3 className="edl-h3">Plattformens betyg-förslag: B</h3>
          <p>
            Snitt över de 12 kompetenserna: 3,2 av 4. Säker eller bättre på
            10 av 12. Två kompetenser på Påbörjad-nivå:{" "}
            <em>Lån, ränta &amp; avbetalning</em> och <em>Marknadsrisk &amp; krasch</em>{" "}
            — Linda har inte mött scenarion där hennes egen ekonomi var i
            kris.
          </p>

          <h3 className="edl-h3">Lärar-motivering (auto-genererad utkast)</h3>
          <blockquote>
            "Linda visar säker tillämpning av lön/skatt/pensions-systemet
            (kompetens 01–04) och ISK-investering (05–07) — där hon når
            <em> Förebild-nivå</em> på lönesamtalet och ISK-djupdyket.
            Hennes reflektioner ligger på 4–5 av 5 (resonerande till
            reflekterande). Två områden kvar att fördjupa — kreditmarknad
            och kraschpsykologi — där hon når Påbörjad-nivå men ännu inte
            Säker. Sammantaget motsvarar prestationen <strong>betyget B</strong>{" "}
            enligt kursens kunskapskrav (E/C/A-skalan)."
          </blockquote>

          <h3 className="edl-h3">Vad Linda själv ser</h3>
          <p>
            Eleven ser bara sin egen progression — inte ett betyg förrän
            läraren har bekräftat. Plattformen visar "Du är på god väg" +
            specifika tips: <em>"Prova krasch-djupdyket en gång till för att
            befästa kompetens 07"</em>.
          </p>
        </div>
      </section>

      <div className="edl-callout">
        <div className="edl-callout-eye">Hämta som PDF</div>
        <p>
          Hela rubrik-strukturen (12 kompetenser × 4 nivåer + reflektions­
          rubriken) kan hämtas som PDF från lärarvyn — A4, 8 sidor, redo att
          dela med kollegor eller arkivera per termin. Den finns också som{" "}
          <Link to="/larguider" style={{ color: "#92400e", textDecoration: "underline" }}>lärarguide</Link>{" "}
          med konkreta exempel och justeringsförslag.
        </p>
      </div>
    </EditorialLightShell>
  );
}
