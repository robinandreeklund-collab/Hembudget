import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  ArrowLeft, BookOpen, ChevronRight, GraduationCap, Users,
  Lightbulb, MessageCircle,
} from "lucide-react";

type Section = {
  id: string;
  title: string;
  group: "student" | "teacher" | "pedagogy";
  body: () => React.ReactNode;
};

const SECTIONS: Section[] = [
  {
    id: "student-intro",
    title: "Vad är Ekonomilabbet?",
    group: "student",
    body: () => (
      <>
        <p>
          Ekonomilabbet är en simulator för privatekonomi. Du får en
          simulerad vardag — ett jobb, en lön, en lägenhet — och ska lära
          dig att hantera pengarna precis som när du flyttat hemifrån.
        </p>
        <p>
          Alla siffror är fiktiva, men de är realistiska (baserade på
          svenska lönestatistik och Konsumentverkets hushållsberäkningar
          för 2026). När du övar här möter du samma beslut som i verkliga
          livet — men utan att någon riktig kronor påverkas.
        </p>
      </>
    ),
  },
  {
    id: "student-login",
    title: "Hur du loggar in",
    group: "student",
    body: () => (
      <>
        <p>
          Din lärare har gett dig en <strong>6-teckens kod</strong> (t.ex.
          ABC123). Gå till Ekonomilabbet och klicka "Jag är elev", skriv in
          koden och tryck Logga in.
        </p>
        <p>
          Om du tappat koden — fråga din lärare. Hen kan visa en QR-kod att
          skanna.
        </p>
      </>
    ),
  },
  {
    id: "student-onboarding",
    title: "Onboarding – din första gång",
    group: "student",
    body: () => (
      <>
        <p>Första gången du loggar in får du tre steg:</p>
        <ol>
          <li>
            <strong>Din situation</strong> — yrke, arbetsgivare, lön, bostad
            och ev. familj. Detta är din simulerade identitet.
          </li>
          <li>
            <strong>Skatten förklaras</strong> — vi visar exakt hur skatten
            beräknas och varför din nettolön är lägre än bruttolönen.
          </li>
          <li>
            <strong>Sätt en budget</strong> — baserad på Konsumentverkets
            2026-siffror. Du justerar varje kategori så det passar dig.
          </li>
        </ol>
        <p>
          Efter det är du igång! Din budget sparas och jämförs automatiskt
          mot dina faktiska utgifter.
        </p>
      </>
    ),
  },
  {
    id: "student-documents",
    title: "Dina dokument",
    group: "student",
    body: () => (
      <>
        <p>
          Varje månad får du dokument från din lärare:{" "}
          <strong>kontoutdrag, lönespec, lånebesked</strong> och{" "}
          <strong>kreditkortsfaktura</strong>. De ligger på sidan{" "}
          <em>"Dina dokument"</em>.
        </p>
        <p>
          Klicka <strong>⬇ Ladda ner</strong> för att titta på PDF:en som
          hon vore riktig — fundera över innehållet, räkna själv.
        </p>
        <p>
          Klicka <strong>⬆ Importera</strong> för att låta appen läsa in
          siffrorna. Då visas de på din dashboard och i din budget.
        </p>
        <p className="text-sm text-slate-500">
          Tips: klicka "Importera alla" för att ta alla fyra i ett svep.
        </p>
      </>
    ),
  },
  {
    id: "student-dashboard",
    title: "Din dashboard",
    group: "student",
    body: () => (
      <>
        <p>
          Dashboarden är din översikt. Fyra kort längst upp:
        </p>
        <ul>
          <li>
            <strong>Nettolön</strong> – det du faktiskt får in på kontot.
          </li>
          <li>
            <strong>Utgifter</strong> – summan av allt spenderat.
          </li>
          <li>
            <strong>Sparat</strong> – dina överföringar till sparkonto (med
            sparmål om du fått ett).
          </li>
          <li>
            <strong>Överskott/Underskott</strong> – skillnaden. Grön = bra,
            röd = måste ses över.
          </li>
        </ul>
        <p>
          Under det ser du budget-staplar per kategori och de största
          oväntade utgifterna.
        </p>
      </>
    ),
  },
  {
    id: "student-assignments",
    title: "Uppdrag",
    group: "student",
    body: () => (
      <>
        <p>Din lärare ger dig uppdrag — de syns på dashboarden och i "Dina dokument". Ikonerna visar status:</p>
        <ul>
          <li>✓ <strong>Grön</strong> — klar</li>
          <li>⧖ <strong>Gul</strong> — pågår (du är på god väg)</li>
          <li>○ <strong>Grå</strong> — inte påbörjad</li>
        </ul>
        <p>
          Vanliga uppdrag: "sätt din budget", "importera månadens dokument",
          "spara 2 000 kr", "kategorisera alla köp". Systemet uppdaterar
          statusen automatiskt när du jobbat vidare.
        </p>
      </>
    ),
  },
  {
    id: "student-messages",
    title: "Meddela din lärare",
    group: "student",
    body: () => (
      <>
        <p>
          Klicka på <strong>Meddelanden</strong> i menyn för att ställa en
          fråga eller be om feedback. Läraren får ett meddelande och svarar.
          Det är en vanlig chat.
        </p>
        <p>
          Lärarna kan också skriva saker som "bra jobbat!" eller ge feedback
          på specifika transaktioner.
        </p>
      </>
    ),
  },

  // --- Lärarens del ---
  {
    id: "teacher-intro",
    title: "För dig som är lärare",
    group: "teacher",
    body: () => (
      <>
        <p>
          Ekonomilabbet är byggt för klassrummet. Du skapar elever, skickar
          ut månadens dokument, sätter uppdrag — och ser i realtid hur
          varje elev klarar sig.
        </p>
        <p>
          Varje elev får en <strong>unik slumpad vardag</strong> (yrke,
          lön, stad, familj). Ingen kan "fuska" genom att titta på en
          kompis siffror.
        </p>
      </>
    ),
  },
  {
    id: "teacher-first-time",
    title: "Första gången",
    group: "teacher",
    body: () => (
      <>
        <ol>
          <li>Skapa ditt lärarkonto via "Lärarinloggning".</li>
          <li>
            Klicka "Ny elev" och lägg till varje elev (namn + klass). De
            får en 6-teckens kod som du skriver ut eller skickar.
          </li>
          <li>
            (Valfritt) Skapa en <strong>familj</strong> — två elever som
            delar samma ekonomi (sambo-hushåll).
          </li>
          <li>
            Tryck "Generera" och välj månad. Alla elever får sina personliga
            PDF:er att importera.
          </li>
        </ol>
      </>
    ),
  },
  {
    id: "teacher-generate",
    title: "Generera månadens dokument",
    group: "teacher",
    body: () => (
      <>
        <p>
          Tryck "Generera" → välj år/månad → klicka kör. Varje elev får:
        </p>
        <ul>
          <li>
            <strong>Lönespec</strong> med bruttolön, skatt och ev. sjukavdrag.
          </li>
          <li>
            <strong>Kontoutdrag</strong> med alla månadens transaktioner
            (mat, räkningar, köp på kortet, amortering m.m.).
          </li>
          <li>
            <strong>Lånebesked</strong> för ev. bolån/billån.
          </li>
          <li>
            <strong>Kreditkortsfaktura</strong> om eleven använt kortet.
          </li>
        </ul>
        <p>
          Varje månad är <strong>slumpad</strong> men deterministisk —
          samma elev + samma månad ger alltid samma data. Olika elever
          får helt olika utgiftsmönster beroende på personlighet
          (sparsam/blandad/slösaktig).
        </p>
        <p>
          Ibland händer saker: sjukdagar sänker lönen, diskmaskinen går
          sönder, julen sliter hårt på shoppingbudgeten. Pedagogiskt
          värdefullt.
        </p>
      </>
    ),
  },
  {
    id: "teacher-assignments",
    title: "Uppdrag",
    group: "teacher",
    body: () => (
      <>
        <p>
          Klicka på en elev → <strong>Uppdrag</strong> → "Nytt uppdrag".
          Välj typ:
        </p>
        <ul>
          <li><strong>Sätt budget</strong> — eleven ska ha minst 5 budgetrader.</li>
          <li><strong>Importera månadens dokument</strong> — kräver alla PDF:er importerade.</li>
          <li><strong>Balansera månaden</strong> — nettoresultat ≥ 0.</li>
          <li><strong>Kategorisera alla</strong> — alla tx har en kategori.</li>
          <li><strong>Spara X kr</strong> — mät överföringar till sparkonto.</li>
          <li><strong>Bolåne-beslut</strong> — elev ska binda eller köra rörlig.</li>
          <li><strong>Annan uppgift (free text)</strong> — du markerar själv när klart.</li>
        </ul>
        <p>
          Klassöversikten (📊 i toppen) visar alla elever × alla uppdrag i
          en matris. Grön = klart, gul = pågår, grå = inte börjat.
        </p>
      </>
    ),
  },
  {
    id: "teacher-facit",
    title: "Kategori-facit",
    group: "teacher",
    body: () => (
      <>
        <p>
          När du öppnar en elevs detaljsida ser du <strong>Facit</strong> för
          kategoriseringen. Varje transaktion har en "rätt kategori"
          (slumpad av scenario-generatorn). Systemet jämför med elevens val
          och rapporterar:
        </p>
        <ul>
          <li>Antal rätt / fel / okategoriserade</li>
          <li>Tabell med alla avvikelser</li>
        </ul>
        <p>
          Föräldra-kategorier räknas som rätt (t.ex. "Mat" som facit och
          "Livsmedel" som elevens val — bägge godkänns).
        </p>
      </>
    ),
  },
  {
    id: "teacher-families",
    title: "Familjer",
    group: "teacher",
    body: () => (
      <>
        <p>
          Två elever kan dela ekonomi som sambos. Skapa en familj under
          "Familjer" och tilldela 2+ elever. De delar en bankkonto, budget,
          räkningar och sparmål.
        </p>
        <p>
          För att ta bort en familj: flytta ut medlemmarna först (så deras
          data inte förloras), sedan radera familjen.
        </p>
      </>
    ),
  },

  // --- Pedagogiskt ---
  {
    id: "pedagogy-konsumentverket",
    title: "Konsumentverkets 2026-siffror",
    group: "pedagogy",
    body: () => (
      <>
        <p>
          Budgetförslagen bygger på{" "}
          <a
            href="https://www.konsumentverket.se/ekonomi/vilka-kostnader-har-ett-hushall/"
            target="_blank" rel="noreferrer"
            className="text-brand-600 underline"
          >
            Konsumentverkets hushållskostnader för 2026
          </a>:
          matkostnad per åldersgrupp, hushållsgemensamma kostnader per
          personantal, kläder, hygien, hemutrustning m.m.
        </p>
        <p>
          När eleven fyller i sin budget räknas förslagen ut utifrån hens
          profil — ensamstående vs. par vs. familj med barn ger helt olika
          siffror. Det är <em>realistiska</em> belopp, inte påhittade.
        </p>
      </>
    ),
  },
  {
    id: "pedagogy-tax",
    title: "Skatten — förenklat men realistiskt",
    group: "pedagogy",
    body: () => (
      <>
        <p>
          Skatten beräknas så:
        </p>
        <ul>
          <li>Grundavdrag ~1 250 kr/mån</li>
          <li>Kommunalskatt 32 % (svenskt genomsnitt, kan justeras)</li>
          <li>Statlig skatt 20 % över brytpunkten (~52 150 kr/mån 2026)</li>
        </ul>
        <p>
          Som lärare kan du ändra kommunalskatt och brytpunkt via{" "}
          <em>Inställningar → Skatt</em> — t.ex. om din kommun har annan
          skattesats, eller för att följa 2027-värden.
        </p>
      </>
    ),
  },
  {
    id: "pedagogy-mortgage",
    title: "Bolåne-scenariot",
    group: "pedagogy",
    body: () => (
      <>
        <p>
          Skapa ett bolåne-uppdrag och välj en historisk beslutsmånad
          (t.ex. 2022-06) och horisont (typiskt 24-36 mån). Eleven väljer
          rörlig eller bunden ränta. Systemet jämför sedan elevens val mot
          verkligheten — med <strong>Riksbankens faktiska räntedata</strong>.
        </p>
        <p>
          Facit visar: kostnad rörlig vs bunden 3 år vs bunden 5 år,
          markerar billigaste, räknar hur mycket eleven "förlorade" på
          sitt val.
        </p>
        <p className="text-sm text-slate-500">
          Bolåneräntor härleds från Riksbankens styrränta + typisk spread
          (rörlig: +1,5 pp, 3 år: +1,2 pp, 5 år: +1,4 pp). Uppdatera
          till senaste värden via "Uppdatera räntor" i inställningar.
        </p>
      </>
    ),
  },
  {
    id: "pedagogy-privacy",
    title: "Integritet & databehandling",
    group: "pedagogy",
    body: () => (
      <>
        <p>
          All data är simulerad — inga riktiga bankkonton eller personnummer
          används. Varje elev har sin egen isolerade SQLite-DB som inte kan
          kommas åt av andra elever.
        </p>
        <p>
          Lärare ser bara sina egna elevers data. Meddelandetråden är
          1-till-1 och osynlig för andra.
        </p>
      </>
    ),
  },
];


export default function Docs() {
  const [activeSection, setActiveSection] = useState(SECTIONS[0].id);

  useEffect(() => {
    // Hash-scroll om URL:en har #id
    if (window.location.hash) {
      const id = window.location.hash.slice(1);
      const el = document.getElementById(id);
      if (el) {
        el.scrollIntoView({ behavior: "smooth" });
        setActiveSection(id);
      }
    }
  }, []);

  const groupLabels = {
    student: { label: "För elever", icon: GraduationCap },
    teacher: { label: "För lärare", icon: Users },
    pedagogy: { label: "Bakgrund & pedagogik", icon: Lightbulb },
  };

  return (
    <div className="min-h-screen bg-white">
      <header className="sticky top-0 z-30 bg-white/90 backdrop-blur border-b border-slate-200">
        <div className="max-w-6xl mx-auto px-6 py-3 flex items-center justify-between">
          <Link
            to="/"
            className="flex items-center gap-2 text-slate-700 hover:text-ink"
          >
            <ArrowLeft className="w-4 h-4" /> Startsidan
          </Link>
          <div className="flex items-center gap-2 text-brand-600 font-semibold">
            <BookOpen className="w-5 h-5" /> Dokumentation
          </div>
          <div className="w-20" />
        </div>
      </header>

      <div className="max-w-6xl mx-auto px-6 py-10 grid md:grid-cols-[240px_1fr] gap-8">
        {/* Sidomeny */}
        <aside className="md:sticky md:top-20 self-start space-y-6">
          {(["student", "teacher", "pedagogy"] as const).map((group) => {
            const { label, icon: Icon } = groupLabels[group];
            const items = SECTIONS.filter((s) => s.group === group);
            return (
              <div key={group}>
                <div className="flex items-center gap-2 text-xs uppercase tracking-wide text-slate-500 font-semibold mb-2">
                  <Icon className="w-3.5 h-3.5" /> {label}
                </div>
                <ul className="space-y-1">
                  {items.map((s) => (
                    <li key={s.id}>
                      <a
                        href={`#${s.id}`}
                        onClick={() => setActiveSection(s.id)}
                        className={`block rounded px-3 py-1.5 text-sm ${
                          activeSection === s.id
                            ? "bg-brand-100 text-brand-800 font-medium"
                            : "text-slate-700 hover:bg-slate-100"
                        }`}
                      >
                        {s.title}
                      </a>
                    </li>
                  ))}
                </ul>
              </div>
            );
          })}
          <div className="border-t pt-4">
            <Link
              to="/messages"
              className="text-sm text-slate-600 hover:text-ink flex items-center gap-1"
            >
              <MessageCircle className="w-4 h-4" />
              Fråga din lärare
              <ChevronRight className="w-3 h-3" />
            </Link>
          </div>
        </aside>

        {/* Innehåll */}
        <main className="space-y-12 prose prose-slate max-w-none">
          {SECTIONS.map((s) => (
            <section
              key={s.id}
              id={s.id}
              className="scroll-mt-24"
            >
              <h2 className="text-2xl font-bold text-slate-900 mb-3 border-b border-slate-200 pb-2">
                {s.title}
              </h2>
              <div className="space-y-3 text-slate-700 leading-relaxed">
                {s.body()}
              </div>
            </section>
          ))}
        </main>
      </div>

      <footer className="border-t border-slate-200 bg-slate-50 py-8 mt-16">
        <div className="max-w-6xl mx-auto px-6 text-center text-sm text-slate-500">
          Har du förslag på vad som kan förbättras i dokumentationen? Använd
          meddelandefunktionen i appen eller öppna en issue på GitHub.
        </div>
      </footer>
    </div>
  );
}
