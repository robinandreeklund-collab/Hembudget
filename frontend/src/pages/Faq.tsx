import { Link } from "react-router-dom";
import { EditorialLightShell } from "@/components/editorial/EditorialLightShell";

type Q = {
  q: React.ReactNode;
  a: React.ReactNode;
};

type QGroup = {
  id: string;
  label: string;
  items: Q[];
};

const FAQ: QGroup[] = [
  {
    id: "vad-ar-det",
    label: "Vad är Ekonomilabbet?",
    items: [
      {
        q: (<>Vad är <em>Ekonomilabbet</em>, kort?</>),
        a: (
          <p>
            En lärplattform där elever, föräldrar och barn lär sig
            privatekonomi genom att <em>uppleva</em> en simulerad vardag —
            inte läsa om den. Linda får en lön, Peter signerar fakturor,
            Evelina hanterar en marknadskrasch. Varje val har en
            konsekvens. Inga riktiga pengar någonsin.
          </p>
        ),
      },
      {
        q: <>Är det riktiga pengar inblandade?</>,
        a: (
          <p>
            Nej. Allt är simulerat. Lönesamtal, autogiron,
            ISK-månadsspar, krasch-fredagar — ingenting flyttas på ett
            riktigt bankkonto. Läs mer i våra{" "}
            <Link to="/terms">villkor</Link>.
          </p>
        ),
      },
      {
        q: <>Är det gratis?</>,
        a: (
          <p>
            För enskilda lärare och familjer som testar plattformen — ja.
            För skolor och kommuner som vill rulla ut till en hel klass
            eller årskurs erbjuder vi en avtalsbaserad licens med
            support, lärar-utbildning och egen tenant. Skicka mail till{" "}
            <a href="mailto:info@ekonomilabbet.org">info@ekonomilabbet.org</a>.
          </p>
        ),
      },
      {
        q: <>Vad är det <em>inte</em>?</>,
        a: (
          <p>
            Inte en bank, inte en finansiell rådgivare, inte ett
            betalningssystem och inte en plattform för riktig handel.
            Echo (vår sokratiska AI) ger frågor — inte råd.
          </p>
        ),
      },
    ],
  },
  {
    id: "for-larare",
    label: "För lärare",
    items: [
      {
        q: <>Hur lägger jag till elever?</>,
        a: (
          <p>
            När du loggat in som lärare går du till <strong>Lärarverktyg →
            Elever</strong>. Klicka <em>Lägg till elev</em>, ange ett namn,
            och plattformen genererar en sex-teckens-kod automatiskt
            (t.ex. <code>K9M2P7</code>). Eleven loggar sen in på{" "}
            <Link to="/login/student">/login/student</Link> med koden.
            Inget e-post eller lösenord behövs för eleven.
          </p>
        ),
      },
      {
        q: <>Kan jag se vad eleverna gör?</>,
        a: (
          <p>
            Ja. Lärarvyn visar varje elevs WB-index (welbeing-pentagon),
            senaste val, mastery per kompetens, och om de loggat in
            nyligen. Du ser vem som behöver prata <em>innan</em> provet
            — inte efter.
          </p>
        ),
      },
      {
        q: <>Kan jag spela in en uppgift?</>,
        a: (
          <p>
            Ja, via <strong>Moduler</strong>. Du kan skapa en
            sekvens av val + reflektioner som elever genomgår. Plattformen
            kommer med 12 systemkompetenser och en "Din första månad"-modul
            redo att använda direkt.
          </p>
        ),
      },
      {
        q: <>Funkar det med Lgr22?</>,
        a: (
          <p>
            Ja. Lärarguiderna är mappade mot Lgr22:s mål för
            samhällsorienterande ämnen och hem- och konsumentkunskap.
            Bedömningsmallar finns att hämta som PDF.
          </p>
        ),
      },
    ],
  },
  {
    id: "for-elev",
    label: "För elever och föräldrar",
    items: [
      {
        q: <>Vad behöver jag som elev?</>,
        a: (
          <p>
            Bara den <strong>sex-teckens-kod</strong> du fått av din
            lärare eller förälder. Inget lösenord, ingen e-post. Gå till{" "}
            <Link to="/login/student">/login/student</Link>, skriv in
            koden och tryck Logga in.
          </p>
        ),
      },
      {
        q: <>Vad är skillnaden mellan ett familjekonto och ett lärarkonto?</>,
        a: (
          <p>
            Tekniskt sett samma flöde, men ett familjekonto har bara dina
            barn som "elever" och fokus är hemmet snarare än klassrummet.
            Det skapas via{" "}
            <Link to="/signup/parent">/signup/parent</Link>.
          </p>
        ),
      },
      {
        q: <>Kan barnet se andra elever?</>,
        a: (
          <p>
            Nej. Varje elev har en isolerad datalagring — bara läraren
            (eller föräldern) ser elevens egen progression. Klassens
            snitt visas anonymt om läraren har slagit på det.
          </p>
        ),
      },
    ],
  },
  {
    id: "ai-och-data",
    label: "AI och data",
    items: [
      {
        q: <>Vilken AI använder ni?</>,
        a: (
          <p>
            <strong>Claude</strong> (Anthropic, Haiku 4.5 och Sonnet 4.6).
            Echo, Maria och lärar-assistensen drivs alla av Claude. På
            desktop-läget används istället en lokal Nemotron Nano-modell
            via LM Studio.
          </p>
        ),
      },
      {
        q: <>Hur används mina svar?</>,
        a: (
          <p>
            För att svara dig i realtid och spara den pedagogiska
            reflektionen. Inget skickas till Anthropic utöver vad det
            specifika anropet kräver. Vi tränar inte modeller på din
            data.
          </p>
        ),
      },
      {
        q: <>Var sparas data?</>,
        a: (
          <p>
            Google Cloud Run i <em>europe-north1</em> (Finland). Multi-tenant
            isolering per elev/familj. Mer detaljer finns i våra{" "}
            <Link to="/terms">villkor</Link>.
          </p>
        ),
      },
      {
        q: <>Kan jag radera mitt konto?</>,
        a: (
          <p>
            Ja. Mejla{" "}
            <a href="mailto:info@ekonomilabbet.org">info@ekonomilabbet.org</a>{" "}
            från den adress kontot är kopplat till. Vi raderar allt
            (konto, progression, sex-teckens-koder för dina elever) inom
            14 dagar enligt GDPR-artikel 17.
          </p>
        ),
      },
    ],
  },
  {
    id: "tekniskt",
    label: "Tekniskt",
    items: [
      {
        q: <>Vilka enheter funkar plattformen på?</>,
        a: (
          <p>
            Alla moderna webbläsare på dator, surfplatta och mobil. Ingen
            app behöver installeras. För bästa upplevelse rekommenderar
            vi Chrome, Safari eller Firefox från senaste året.
          </p>
        ),
      },
      {
        q: <>Vad är "Vol. 01", "Vol. 02", "Vol. 03"?</>,
        a: (
          <p>
            Tre persona-spår: <em>Arbetslivet</em> (Linda),
            <em>Investering</em> (Evelina) och <em>Vardagsekonomin</em>{" "}
            (Peter). Varje spår är en sammanhängande veckosaga med fyra
            djupdyk i specifika funktioner.
          </p>
        ),
      },
      {
        q: <>Vad gör jag om något inte fungerar?</>,
        a: (
          <p>
            Vid bugg: skicka en kort beskrivning + skärmdump till{" "}
            <a href="mailto:info@ekonomilabbet.org">info@ekonomilabbet.org</a>.
            Vi svarar normalt inom två vardagar. Om plattformen är nere
            kollar vi <em>status.ekonomilabbet.org</em> innan du mailar.
          </p>
        ),
      },
    ],
  },
];

export default function Faq() {
  return (
    <EditorialLightShell
      eyebrow="Vanliga frågor · Vol. 01"
      title={
        <>
          Det vi får frågan om <em>oftast</em>.
        </>
      }
      intro="Hittar du inte svaret? Skriv till info@ekonomilabbet.org. Vi svarar inom två vardagar."
      topNavRight={
        <>
          <Link to="/login" className="edl-top-link">Logga in</Link>
          <Link to="/signup/teacher" className="edl-top-link is-primary">
            Skapa konto
          </Link>
        </>
      }
    >
      {FAQ.map((group) => (
        <section key={group.id} id={group.id} className="edl-section">
          <h2 className="edl-h2">{group.label}</h2>
          <div>
            {group.items.map((item, i) => (
              <div key={i} className="edl-faq-item">
                <h3 className="edl-faq-q">{item.q}</h3>
                <div className="edl-prose">{item.a}</div>
              </div>
            ))}
          </div>
        </section>
      ))}

      <div className="edl-callout">
        <div className="edl-callout-eye">Saknar du något?</div>
        <p>
          Det här är levande sidor. Hittar du inte ditt svar — eller har en
          fråga som vi borde ha här? Mejla{" "}
          <a href="mailto:info@ekonomilabbet.org" style={{ color: "#92400e", textDecoration: "underline" }}>
            info@ekonomilabbet.org
          </a>{" "}
          så lägger vi till frågan i nästa version.
        </p>
      </div>
    </EditorialLightShell>
  );
}
