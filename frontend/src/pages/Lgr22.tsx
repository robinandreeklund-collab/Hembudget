import { Link } from "react-router-dom";
import { EditorialLightShell } from "@/components/editorial/EditorialLightShell";
import { AuthAwareTopLinks } from "@/components/editorial/AuthAwareTopLinks";

export default function Lgr22() {
  return (
    <EditorialLightShell
      eyebrow="Lgr22 + Gy22 · Kunskapskrav"
      title={<>Mappning mot <em>Lgr22 + Gy22</em>.</>}
      intro="Varje moment i Ekonomilabbet matchar specifika kunskapskrav från svenska läroplanen. Den här sidan visar exakt hur — kurs för kurs, ämne för ämne."
      topNavRight={<AuthAwareTopLinks variant="light" />}
    >
      <div className="edl-callout is-accent">
        <div className="edl-callout-eye">Så används den här sidan</div>
        <p>
          Som lärare behöver du oftast inte gå hit — bedömningen är inbyggd.
          Men för rektors-rapportering, kursplaneskrivning och vid betygs­
          motivering är mappningen explicit dokumenterad här.
        </p>
      </div>

      <section id="hk-79" className="edl-section">
        <h2 className="edl-h2">Hem- och konsumentkunskap (åk 7–9)</h2>
        <div className="edl-prose">
          <p>
            <em>Centralt innehåll</em> som plattformen täcker:
          </p>
          <ul>
            <li>
              <strong>Ekonomi och konsumtion</strong> — privatekonomi,
              hushållsbudget, prioriteringar mellan behov och vill, jämförelser
              mellan olika konsumtionsval och deras konsekvenser.
            </li>
            <li>
              <strong>Lokal och global konsumtion</strong> — hur konsumtions­
              val påverkar miljö och samhälle (kompetens 10: konsumentval &
              impulsskatt täcker detta).
            </li>
            <li>
              <strong>Reklam och media</strong> — hur eleven granskar
              reklambudskap och tar informerade köpbeslut.
            </li>
          </ul>
          <h3 className="edl-h3">Kunskapskrav som tickas in</h3>
          <ul>
            <li>
              "Eleven kan föra <em>resonemang om hur konsumtion påverkar</em>
              den enskilde och samhället." → Peters konsumtionsval-scenarier.
            </li>
            <li>
              "Eleven kan göra <em>egna prioriteringar</em> i en hushållsbudget
              och motivera dessa." → Peter modul 5.
            </li>
            <li>
              "Eleven kan <em>jämföra olika alternativ</em> i en konsumtions­
              situation och föra resonemang om deras konsekvenser."
            </li>
          </ul>
        </div>
      </section>

      <section id="sh-79" className="edl-section">
        <h2 className="edl-h2">Samhällskunskap (åk 7–9)</h2>
        <div className="edl-prose">
          <p>
            <em>Centralt innehåll</em>:
          </p>
          <ul>
            <li>
              <strong>Samhällsekonomins delar</strong> — hushåll, företag,
              stat. Hur de samverkar och vilka beslut som tas.
            </li>
            <li>
              <strong>Privatekonomi</strong> — inkomst, utgift, sparande,
              skuld, ränta. Konsumentkrediter, lån, pensionssystemet.
            </li>
            <li>
              <strong>Arbetsmarknad och arbetsliv</strong> — lön, kollektivavtal,
              arbetsrätt, fackförbundens roll.
            </li>
          </ul>
          <h3 className="edl-h3">Kunskapskrav som tickas in</h3>
          <ul>
            <li>
              "Eleven har grundläggande kunskaper om <em>hur ekonomiska beslut
              i hushållet och samhället</em> påverkar varandra."
            </li>
            <li>
              "Eleven kan föra <em>enkla resonemang om centrala begrepp inom
              privatekonomi</em>, t.ex. inkomst, sparande, skuld, ränta."
            </li>
            <li>
              "Eleven kan föra resonemang om <em>lönebildning, arbetsmarknad
              och kollektivavtal</em>." → Lindas lönesamtal med Maria.
            </li>
          </ul>
        </div>
      </section>

      <section id="ma-79" className="edl-section">
        <h2 className="edl-h2">Matematik (åk 7–9)</h2>
        <div className="edl-prose">
          <p>
            Plattformen tränar svår-att-undervisa-områden i konkret kontext:
          </p>
          <ul>
            <li>
              <strong>Procent och proportionalitet</strong> — skattesats,
              ränta, lönelyft, allokeringsdrift. Procentanvändning som inte
              är artificiell.
            </li>
            <li>
              <strong>Ränta-på-ränta</strong> — pension över 30 år, ISK över
              decennier. Visualiseras som diagram och beräknas av plattformen.
            </li>
            <li>
              <strong>Sannolikhet och statistik</strong> — krasch-fredagar,
              marknadsåterhämtning, normalfördelad inkomstvariation.
            </li>
          </ul>
          <h3 className="edl-h3">Kunskapskrav som tickas in</h3>
          <ul>
            <li>
              "Eleven kan <em>tolka och använda</em> matematiska begrepp i
              vardagsnära sammanhang." → ISK-djupdyket.
            </li>
            <li>
              "Eleven kan <em>uttrycka sig matematiskt korrekt</em> om
              proportionalitet, procent och ränta-på-ränta."
            </li>
          </ul>
        </div>
      </section>

      <section id="privatekonomi-gy" className="edl-section">
        <h2 className="edl-h2">Privatekonomi (Gy22)</h2>
        <div className="edl-prose">
          <p>
            Gy22-kursen <em>Privatekonomi 100p</em> är nästan helt täckt av
            plattformen. Här mappas det centrala innehållet en-till-en:
          </p>
          <ul>
            <li>
              <strong>Lön, skatt och avdrag</strong> — Lindas saga + djupdyk
              <em> Lönespec</em> (slide 1–3): brutto → A-skatt + pensions­
              avgift → netto.
            </li>
            <li>
              <strong>Bostad — köp eller hyra</strong> — modul "Boende"
              (separat scenario, ej saga). Ränta, amortering, andrahand­svärde.
            </li>
            <li>
              <strong>Sparande och konsumtion</strong> — Peters budget +
              Evelinas ISK-månadsspar.
            </li>
            <li>
              <strong>Försäkringar</strong> — modul "Försäkringar" — hem,
              bil, person, ansvar.
            </li>
            <li>
              <strong>Lån och kreditkort</strong> — Konsumentverkets data,
              effektiv ränta, SMS-lånfälla.
            </li>
            <li>
              <strong>Pensioner</strong> — Lindas djupdyk Pension (allmän + tjänste).
            </li>
            <li>
              <strong>Aktier och fonder</strong> — Evelinas saga + djupdyk{" "}
              ISK / Portfolio / Krasch / Skatt.
            </li>
            <li>
              <strong>Konsumenträtt</strong> — modul "Konsumenträtt" —
              ångerrätt, garanti, reklamation.
            </li>
          </ul>
          <h3 className="edl-h3">Kunskapskrav (E/C/A)</h3>
          <p>
            Plattformens 4-nivå-rubrik (Saknar/Påbörjad/Säker/Förebild)
            mappas till betygsskalan E (Saknar=F, Påbörjad=E, Säker=C,
            Förebild=A). Varje slutreflektion ger en betygsbedömning som
            läraren bekräftar eller justerar.
          </p>
        </div>
      </section>

      <section id="foretagsekonomi-gy" className="edl-section">
        <h2 className="edl-h2">Företagsekonomi 1 + 2 (Gy22)</h2>
        <div className="edl-prose">
          <p>
            Linda och Evelina-spåren passar för:
          </p>
          <ul>
            <li>
              <strong>Resultat- och balansräkning</strong> — Evelinas portfolio
              som balansräkning över tid; månatlig P&amp;L i Lindas saga.
            </li>
            <li>
              <strong>Investering</strong> — ISK-modellen, schablon­
              beskattning, korrelation under stress (krasch-djupdyket).
            </li>
            <li>
              <strong>Kalkylering</strong> — NPV på tjänstepension (kollektiv­
              avtal-djupdyket), ränta-på-ränta-modeller.
            </li>
            <li>
              <strong>Marknadsföring &amp; pris</strong> — modul{" "}
              <em>Konsumentval &amp; impulsskatt</em> (för Företagsek 2).
            </li>
          </ul>
        </div>
      </section>

      <section id="sh-gy" className="edl-section">
        <h2 className="edl-h2">Samhällskunskap 1a1 / 1b (Gy22)</h2>
        <div className="edl-prose">
          <p>
            Plattformen täcker tunga delar:
          </p>
          <ul>
            <li>
              <strong>Välfärdsstaten</strong> — pensionspott + sjukförsäkring
              + arbetsmarknadens parter visas som ett system, inte som
              isolerade rader.
            </li>
            <li>
              <strong>Skattesystemet</strong> — A-skatt-tabell, kommunal +
              statlig skatt, IBB-cap, arbetsgivaravgift. Allt synligt i
              djupdyket Lönespec.
            </li>
            <li>
              <strong>Arbetsmarknad och kollektivavtal</strong> — djupdyket{" "}
              Kollektivavtal (Akavia ITP1) gör avtalets osynliga värde
              synligt.
            </li>
            <li>
              <strong>Svensk modell vs. andra länder</strong> — modul{" "}
              <em>Internationell jämförelse</em> (skattetryck, tjänste­
              pension, arbetslöshetsförsäkring).
            </li>
          </ul>
        </div>
      </section>

      <section id="bedomningsstod" className="edl-section">
        <h2 className="edl-h2">Bedömningsstöd</h2>
        <div className="edl-prose">
          <p>
            Skolverkets bedömningsstöd-mallar är inbyggda i plattformen:
            elevens reflektioner, val och kvalitativa svar (Echo-kommentarer)
            poängsätts automatiskt mot E/C/A-kriterierna och du som lärare
            bekräftar eller justerar.
          </p>
          <p>
            Detaljerad genomgång av rubrikerna finns på{" "}
            <Link to="/rubriker">Bedömningsmallar</Link>.
          </p>
          <p>
            Plattformen genererar en <strong>betygsmotivering-PDF</strong> per
            elev vid terminsslut — Skolverkets standardformat, en sida per
            kunskapskrav, kopplad till elevens egna reflektioner och
            mätpunkter.
          </p>
        </div>
      </section>

      <div className="edl-callout">
        <div className="edl-callout-eye">Skolverket-källa</div>
        <p>
          Citaten ovan är parafraseringar av centrala innehåll och kunskaps­
          krav i Lgr22 / Gy22. Originaltexterna finns publika på{" "}
          <a href="https://www.skolverket.se" target="_blank" rel="noopener" style={{ color: "#92400e", textDecoration: "underline" }}>skolverket.se</a>.
          Mappningen är vår tolkning — vi uppdaterar minst en gång per termin
          eller när Skolverket reviderar texterna.
        </p>
      </div>
    </EditorialLightShell>
  );
}
