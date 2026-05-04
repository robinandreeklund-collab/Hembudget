import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { EditorialLightShell } from "@/components/editorial/EditorialLightShell";
import { AuthAwareTopLinks } from "@/components/editorial/AuthAwareTopLinks";

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
        <p>
          Lärare har eget login med e-post och lösenord. Glömt lösen →
          klicka "Glömt lösenord?" på inloggningssidan så skickar vi en
          återställningslänk till mailen (länken gäller i 60 minuter).
          Nya lärarkonton bekräftas via mail innan första inloggningen.
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
    id: "student-modules",
    title: "Din kursplan (moduler)",
    group: "student",
    body: () => (
      <>
        <p>
          Din lärare bygger upp en kursplan med <strong>moduler</strong> —
          mini-kurser om 4–7 steg vardera. Du hittar dem under
          <em> Din kursplan</em> i menyn.
        </p>
        <p>Varje steg är ett av fem:</p>
        <ul>
          <li><strong>Läs</strong> — text att läsa, klicka "klar" när du är färdig</li>
          <li><strong>Titta</strong> — video (oftast YouTube) plus klar-knapp</li>
          <li><strong>Reflektera</strong> — skriv ett svar på en öppen fråga (minst 10 tecken)</li>
          <li><strong>Quiz</strong> — flerval. Du får direkt rätt/fel + förklaring. Är det fel kan du fråga Ekon om en pedagogisk förklaring.</li>
          <li><strong>Uppdrag</strong> — gör något i appen (sätt budget, kategorisera, etc.)</li>
        </ul>
        <p>
          När du klarar steg fylls din <strong>mastery</strong> per kompetens
          (synlig på dashboarden). När hela modulen är klar markeras den
          grön och nästa öppnas.
        </p>
      </>
    ),
  },
  {
    id: "student-quiz",
    title: "Quiz: rätt, fel och Ekons förklaring",
    group: "student",
    body: () => (
      <>
        <p>
          När du svarar på ett quiz får du direkt rätt/fel — den valda
          ringen blir grön eller röd. Förklaringstexten från frågans
          författare visas under.
        </p>
        <p>
          Om du svarade fel och din lärare har AI på får du en knapp
          "<strong>Fråga Ekon varför ditt svar inte stämmer</strong>". Då
          streamar Claude en pedagogisk förklaring som tar in just ditt
          val, inte bara generella rätta svaret.
        </p>
        <p>
          Du kan svara om — mastery räknar dock första försöket. Läraren
          kan se att du svarade om och vid behov rätta auto-grading
          (t.ex. om frågan var dåligt formulerad).
        </p>
      </>
    ),
  },
  {
    id: "student-mastery",
    title: "Mastery & milstolpar",
    group: "student",
    body: () => (
      <>
        <p>
          På dashboarden ser du din <strong>mastery</strong> per kompetens
          — staplar mellan 0 % och 100 %. Den fylls upp när du klarar steg
          som tränar respektive kompetens.
        </p>
        <p>
          Tickmarks på 25 / 50 / 75 / 100 % visar nästa milstolpe. Under
          stapeln står "Nästa: 50 %, 3 steg kvar" så du vet vad som krävs.
          När du når 75 % på en kompetens räknas den som "mästrad" och du
          får en prestation.
        </p>
      </>
    ),
  },
  {
    id: "student-achievements",
    title: "Prestationer & streaks",
    group: "student",
    body: () => (
      <>
        <p>
          Under <strong>Prestationer</strong> i menyn ser du badges du
          tjänat och vilka som finns kvar att jaga:
        </p>
        <ul>
          <li>🎯 Första steget</li>
          <li>📚 Första modulen klar</li>
          <li>✍️ Tio reflektioner skickade</li>
          <li>🏆 Tre kompetenser mästrade (≥75%)</li>
          <li>🔥 Sju dagar i rad med klart steg (streak)</li>
          <li>💯 Quiz på första försöket</li>
        </ul>
        <p>
          Streaken räknar konsekutiva dagar med minst ett klart steg.
          Tappar du en dag börjar räkningen om — men din längsta serie
          historiskt finns alltid kvar.
        </p>
      </>
    ),
  },
  {
    id: "student-ask-ekon",
    title: "Fråga Ekon (AI-coach)",
    group: "student",
    body: () => (
      <>
        <p>
          Knappen <strong>Fråga Ekon</strong> nere i högra hörnet öppnar
          en chat med en AI-coach (Claude Sonnet). Den anpassar svaret
          till var du är i kursplanen — har du låg mastery på området
          frågar Ekon snarare tillbaka för att få dig att tänka själv,
          har du högre mastery svarar den direkt.
        </p>
        <p>
          Multi-turn: du kan följdfråga inom samma samtal. Klicka på
          plus-knappen för att starta ett nytt. Trådarna sparas så du
          kan komma tillbaka.
        </p>
        <p>
          Ekon ger inte personliga råd om vad du ska köpa eller spara —
          den hjälper dig <em>förstå</em>.
        </p>
      </>
    ),
  },
  {
    id: "student-peer-review",
    title: "Kamratrespons",
    group: "student",
    body: () => (
      <>
        <p>
          Under <strong>Kamratrespons</strong> får du läsa en anonym
          reflektion från en klasskamrat och skriva en kort återkoppling.
          Du ser inte vem du svarar — och eleven du recenserar ser inte
          att det var du.
        </p>
        <p>
          När någon ger dig kamratrespons syns den under reflektionen i
          modulen. Läraren ser båda namnen i moderationsvyn.
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
    id: "teacher-modules",
    title: "Moduler & kursplan",
    group: "teacher",
    body: () => (
      <>
        <p>
          Under <strong>Kursmoduler</strong> bygger du kursplanen elev för
          elev eller för hela klassen. En modul är en serie steg av fem typer:
        </p>
        <ul>
          <li><strong>Läs</strong> — markdown-text</li>
          <li><strong>Titta</strong> — YouTube/Vimeo-embed</li>
          <li><strong>Reflektera</strong> — öppen fråga med rubric-bedömning</li>
          <li><strong>Quiz</strong> — flerval med direkt rätt/fel + AI-förklaring vid fel</li>
          <li><strong>Uppdrag</strong> — koppla till ett uppdrag i plattformen</li>
        </ul>
        <p>
          Skapa från scratch eller klona en system-mall (t.ex. "Din första
          månad") och anpassa. Tilldela till elever via knappen på modulen.
          När eleven öppnar modulen byggs framsteg upp per steg.
        </p>
        <p>
          Modulen kan publiceras som <strong>delad mall</strong> så andra
          lärare i instansen kan klona den. Klick "Publicera" på din modul.
        </p>
      </>
    ),
  },
  {
    id: "teacher-reflections",
    title: "Reflektioner & rubric",
    group: "teacher",
    body: () => (
      <>
        <p>
          Under <strong>Reflektioner</strong> hittar du elevernas svar på alla
          reflect-steg, sorterade per modul. Du skriver feedback direkt och
          ger ev. rubric-betyg per kriterium.
        </p>
        <p>
          För återanvändning: under <strong>Rubric-mallar</strong> kan du
          skapa namngivna kriteriematriser ("Djup", "Tydlighet", "Källor"
          ×&nbsp;3 nivåer) och klicka in dem på reflect-steg när du bygger
          moduler. Markera mallen som delad så kollegor kan klona den.
        </p>
        <p>
          Om AI är aktiverat (super-admin sätter detta) kan Claude föreslå
          rubric-betyg per kriterium med motivering — du skriver under eller
          ändrar med två klick.
        </p>
      </>
    ),
  },
  {
    id: "teacher-quiz-override",
    title: "Quiz-override",
    group: "teacher",
    body: () => (
      <>
        <p>
          Auto-grading på quiz är ibland fel — frågan var dåligt formulerad
          eller eleven hade en bättre tolkning. På elevens detalj-vy kan du
          välja "Rätta som rätt" på ett quiz-steg och skriva en kort
          motivering.
        </p>
        <p>
          Mastery räknar då lärarens override istället för auto-grade. Eleven
          ser banner "Läraren har kommenterat" på sitt quiz-steg.
        </p>
      </>
    ),
  },
  {
    id: "teacher-time-on-task",
    title: "Time on task",
    group: "teacher",
    body: () => (
      <>
        <p>
          Under <strong>Time on task</strong> ser du median-tid per steg över
          alla dina elever, plus antal som börjat men inte avslutat ("fastnat").
          Bra för att hitta steg som är för svåra eller otydliga.
        </p>
        <p>
          Datan kommer från en heartbeat som elevens app pingar var 20:e
          sekund medan ett steg är öppet. Avslutat steg = senaste heartbeat
          minus första. Stuck = heartbeat finns men ingen completion.
        </p>
      </>
    ),
  },
  {
    id: "teacher-portfolio",
    title: "Klass-portfolio (ZIP)",
    group: "teacher",
    body: () => (
      <>
        <p>
          Knappen <strong>Klass-portfolio (ZIP)</strong> i lärarpanelen
          genererar en portfolio-PDF per aktiv elev och packar dem i ett
          ZIP-arkiv (filnamn <code>klass_portfolio.zip</code>). Bra
          underlag inför betygsperiod eller utvecklingssamtal.
        </p>
        <p>
          Varje PDF innehåller elevens reflektioner, mastery-grafer, klara
          moduler och uppdragsstatus. Tar några sekunder per elev — för en
          klass på 30 räkna med ~30 sek.
        </p>
      </>
    ),
  },
  {
    id: "teacher-students-summary",
    title: "AI-elevsammanfattning",
    group: "teacher",
    body: () => (
      <>
        <p>
          På varje elevs detalj-vy finns en <strong>AI-lägesbild</strong>
          som genereras med Claude Sonnet. Tre sektioner: styrkor, gap,
          nästa steg. Bygger på mastery, senaste reflektioner och uppdrag.
        </p>
        <p>
          Kräver att AI är aktiverat på ditt konto (super-admin styr detta).
          Genereras on-demand när du klickar knappen — inga automatiska
          körningar.
        </p>
      </>
    ),
  },
  {
    id: "teacher-super-admin",
    title: "Super-admin & inställningar",
    group: "teacher",
    body: () => (
      <>
        <p>
          Den första läraren som registrerar sig blir <strong>super-admin</strong>
          automatiskt. I lärarpanelen syns då en extra knapp "🧠 AI-admin"
          som leder till <code>/teacher/admin-ai</code>.
        </p>
        <p>Där styr super-admin:</p>
        <ul>
          <li>
            <strong>AI-toggel per lärare</strong> — vilka av kollegorna som
            får använda Claude-funktionerna (kostar pengar per anrop).
          </li>
          <li>
            <strong>Anthropic API-nyckel</strong> — klistra in
            <code> sk-ant-api03-…</code>. Lagras krypterat i master-DB.
          </li>
          <li>
            <strong>SMTP-konfiguration</strong> — Gmail app-password eller
            annan SMTP-server. Krävs för signup-mail, lösenords-återställning
            och e-post-verifiering. Knappen "Skicka testmail" verifierar
            inställningen utan att triggra ett riktigt signup.
          </li>
          <li>
            <strong>Super-admin-toggel</strong> — utse fler super-admins.
          </li>
        </ul>
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


const GROUP_LABELS = {
  student: "För elever",
  teacher: "För lärare",
  pedagogy: "Bakgrund & pedagogik",
} as const;

export default function Docs() {
  const [activeSection, setActiveSection] = useState(SECTIONS[0].id);

  useEffect(() => {
    if (window.location.hash) {
      const id = window.location.hash.slice(1);
      const el = document.getElementById(id);
      if (el) {
        el.scrollIntoView({ behavior: "smooth" });
        setActiveSection(id);
      }
    }
  }, []);

  // Spåra vilken sektion som är synlig så aside-länken markeras live
  useEffect(() => {
    const obs = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((e) => e.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)[0];
        if (visible) setActiveSection(visible.target.id);
      },
      { rootMargin: "-100px 0px -60% 0px", threshold: [0, 1] },
    );
    SECTIONS.forEach((s) => {
      const el = document.getElementById(s.id);
      if (el) obs.observe(el);
    });
    return () => obs.disconnect();
  }, []);

  return (
    <EditorialLightShell
      eyebrow="Dokumentation · Vol. 01"
      title={
        <>
          Allt du behöver veta om <em>Ekonomilabbet</em>.
        </>
      }
      intro="För elever, lärare och föräldrar. Sökbart, indexerat, alltid uppdaterat mot plattformen."
      topNavRight={<AuthAwareTopLinks variant="light" />}
      withAsideSidebar
      aside={
        <>
          {(["student", "teacher", "pedagogy"] as const).map((group) => {
            const items = SECTIONS.filter((s) => s.group === group);
            return (
              <div key={group} className="edl-aside-group">
                <div className="edl-aside-eye">{GROUP_LABELS[group]}</div>
                <ul className="edl-aside-list">
                  {items.map((s) => (
                    <li key={s.id}>
                      <a
                        href={`#${s.id}`}
                        onClick={() => setActiveSection(s.id)}
                        className={activeSection === s.id ? "is-active" : ""}
                      >
                        {s.title}
                      </a>
                    </li>
                  ))}
                </ul>
              </div>
            );
          })}
          <div className="edl-aside-group">
            <div className="edl-aside-eye">Mer</div>
            <ul className="edl-aside-list">
              <li><Link to="/faq">Vanliga frågor</Link></li>
              <li><Link to="/terms">Villkor &amp; simulering</Link></li>
              <li><a href="mailto:info@ekonomilabbet.org">Kontakt</a></li>
            </ul>
          </div>
        </>
      }
    >
      {SECTIONS.map((s) => (
        <section key={s.id} id={s.id} className="edl-section">
          <h2 className="edl-h2">{s.title}</h2>
          <div className="edl-prose">{s.body()}</div>
        </section>
      ))}
    </EditorialLightShell>
  );
}
