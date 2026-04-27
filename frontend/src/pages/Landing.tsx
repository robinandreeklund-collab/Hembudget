/**
 * Landing.tsx — paper-design migrerat från demo3-periodic.html.
 *
 * Strukturen följer exakt demo3:
 *   Header → Hero (text + grid + prof) → Funktioner → Flow → Stats →
 *   Logiken-strip → Why → Social proof → Vyer → Pricing → FAQ →
 *   Founder-citat → CTA → Kontakt → Footer
 *
 * Alla 32 cellerna i hero-griden, eye-tracking, heatmap-toggle,
 * cell-modal och drift-partiklar är React-portade från standalone-HTML:en.
 */
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api, getApiBase } from "@/api/client";

// ---------- Cell-data (32 begrepp) ----------

type CellColor = "grund" | "fordj" | "expert" | "konto" | "risk" | "special";

type Cell = {
  num: number;
  sym: string;
  name: string;
  val: string;
  tip: string;       // kort en-rads-tooltip vid hover
  long: string;      // 2-3 meningar förklaring i modal
  example: string;   // konkret vardagsexempel
  trains: string;    // var i kursplanen detta tränas
  color: CellColor;
};

const CELLS: Cell[] = [
  { num: 1, sym: "Lö", name: "Lön", val: "brutto · netto", color: "grund",
    tip: "Lön = bruttolön minus skatt = det du faktiskt får",
    long: "Bruttolön är vad du tjänar på pappret. Nettolön är vad som landar på kontot efter att skatten dragits. Skillnaden är ofta 25–35 % beroende på kommun och inkomstnivå.",
    example: "Anna har en bruttolön på 32 000 kr. Efter ~28 % skatt får hon ut 23 040 kr i handen den 25:e varje månad.",
    trains: "Steg 2 i Din första månad — eleven läser sin egen lönespec." },
  { num: 2, sym: "Sk", name: "Skatt", val: "kommun · stat", color: "grund",
    tip: "Skatt = din andel av samhället",
    long: "Inkomstskatt består av kommunalskatt (~30 %) och statlig skatt (på inkomster över ~615 000 kr/år). Den dras direkt från lönen och betalar för skola, vård, vägar och allt annat det offentliga gör.",
    example: "Av Annas 32 000 kr går ~9 000 kr till kommunal- och statsskatt — varav merparten till Stockholms kommun.",
    trains: "Steg 3 i Din första månad — eleven jämför kommun-skattesatser." },
  { num: 3, sym: "Bu", name: "Budget", val: "in − ut", color: "grund",
    tip: "Budget = planen innan pengarna försvinner",
    long: "En budget är en plan över vad pengarna SKA gå till. Inkomster minus utgifter ska gå plus eller minst gå jämnt upp. Konsumentverkets siffror är ett bra startläge.",
    example: "Anna budgeterar 4 000 kr/mån för mat, 1 500 kr för nöje, 800 kr för hygien. Totalt 6 300 kr — verkligheten avgör om det räcker.",
    trains: "Steg 5–6 i Din första månad — eleven sätter sin egen budget och jämför mot Konsumentverkets riktvärden." },
  { num: 4, sym: "Ku", name: "Kontoutdrag", val: "rörelser", color: "konto",
    tip: "Kontoutdrag = bankens dagbok över dig",
    long: "Kontoutdraget visar varje krona in och ut. Det är facit för månaden — där ser du om du höll budgeten eller inte. Att läsa ett kontoutdrag är en grundläggande färdighet som många unga aldrig övat på.",
    example: "Annas november-utdrag har 47 rader. Lön +23 040, hyra −9 200, ICA Maxi 14 ggr för totalt 4 120 kr...",
    trains: "Steg 4 i Din första månad — eleven importerar PDF:en läraren genererat." },
  { num: 5, sym: "Ka", name: "Kategori", val: "mat · hyra", color: "grund",
    tip: "Kategorisering = första steget till förståelse",
    long: "Att sortera utgifter i kategorier (Mat, Boende, Transport, Nöje...) gör det möjligt att se var pengarna faktiskt går. Utan kategorisering syns bara att pengarna är slut.",
    example: "ICA Maxi → Mat. SL-kort → Transport. Spotify → Nöje. Hyresvärden → Boende.",
    trains: "Steg 7 i Din första månad — eleven kategoriserar månadens köp; läraren ser facit." },
  { num: 6, sym: "Sa", name: "Saldo", val: "kontot nu", color: "konto",
    tip: "Saldo = sanningen just nu",
    long: "Saldot är vad som faktiskt finns på kontot — inte vad du \"tror\" du har. Att kolla saldot innan ett köp är en grundvana som hindrar övertrasseringar.",
    example: "På Annas konto den 15:e: 8 880 kr. Hyran nästa månad är 9 200. Hon behöver vänta med Black Friday.",
    trains: "Visas live i Dashboard — eleven ser saldot uppdateras vid varje import." },
  { num: 7, sym: "Sp", name: "Sparande", val: "buffert", color: "fordj",
    tip: "Sparande = framtida du tackar nuvarande du",
    long: "Att sätta undan pengar regelbundet är skillnaden mellan ekonomisk frihet och stress. Tumregeln 10 % av inkomsten är en bra start — bygg först en buffert på 2–3 månadslöner, sedan långsiktigt.",
    example: "Anna sparar 1 500 kr/mån. På ett år har hon 18 000 kr — räcker för en oväntad räkning eller en bilreparation.",
    trains: "Modulen Buffert &amp; sparmål — eleven sätter ett konkret mål och spårar månadsvis." },
  { num: 8, sym: "Hu", name: "Hushållskost.", val: "Konsumentv.", color: "fordj",
    tip: "Hushållskostnader = vad det faktiskt kostar att leva",
    long: "Konsumentverket räknar varje år ut vad det kostar att leva med rimlig levnadsstandard — mat, kläder, hygien, fritid, etc. För en ensamboende vuxen 2026: ~5 700 kr/mån (utan boendekostnad).",
    example: "Anna får ut 23 040 kr. Konsumentverket säger 5 700. Hon har 17 340 kr till hyra, sparande och nöje.",
    trains: "Steg 6 i Din första månad — eleven jämför sin egen budget mot Konsumentverkets nivå." },
  { num: 9, sym: "Bl", name: "Bolån", val: "räntebärande", color: "fordj",
    tip: "Bolån = ditt största ekonomiska beslut",
    long: "Ett bolån är räntebärande och ofta löper över 30–50 år. En procentenhet ränta gör enorm skillnad — på ett 2 mkr-lån är 1 % = 20 000 kr/år.",
    example: "Anna och hennes sambo köper en lägenhet för 3,2 mkr. De lånar 2,4 mkr (75 %) — räntekostnaden vid 4 % blir 96 000 kr/år.",
    trains: "Modulen Första bolånet — eleven får en lånesimulator att leka med." },
  { num: 10, sym: "Am", name: "Amortering", val: "betala av", color: "fordj",
    tip: "Amortering = att krympa skulden, inte bara räntan",
    long: "Amortering är när du betalar av själva skulden, inte bara räntan. I Sverige finns krav på minst 1–3 % amortering/år beroende på belåningsgrad och inkomst. Räntan är priset, amorteringen är att verkligen bli av med lånet.",
    example: "Annas månadskostnad: 8 000 kr ränta + 4 000 kr amortering = 12 000 kr. Bara amorteringen krymper lånet.",
    trains: "Modulen Första bolånet — eleven jämför ränta vs amortering över tid." },
  { num: 11, sym: "Ov", name: "Oväntat", val: "buffert", color: "risk",
    tip: "Oväntat = tandläkare, kyl som går sönder, en tisdag",
    long: "Det oväntade händer alltid. Tandläkaren, en bilreparation, en trasig diskmaskin. Utan buffert blir varje sådan händelse en kris. Med buffert är det bara en räkning.",
    example: "Anna går till tandläkaren — får en räkning på 4 200 kr. Hon har 18 000 i buffert. Inget drama.",
    trains: "Modulen Buffert &amp; oväntat — slumpade händelser i scenariomånaden." },
  { num: 12, sym: "Kk", name: "Kreditkort", val: "kostar om...", color: "risk",
    tip: "Kreditkort = bra verktyg, dålig vana",
    long: "Kreditkort är gratis OM du betalar fakturan i sin helhet varje månad. Annars ligger räntan ofta kring 18–25 % per år — bland de dyraste lånen som finns. Många bygger upp dyra skulder genom att bara betala minimibeloppet.",
    example: "Anna handlar för 6 000 på sitt Visa. Betalar bara 500 minimum → kvarvarande 5 500 kostar 92 kr/mån i ränta tills det är betalt.",
    trains: "Modulen Kreditkortsmånaden — eleven får en faktura och måste välja strategi." },
  { num: 13, sym: "Lp", name: "Långsiktig plan", val: "3–5 år", color: "expert",
    tip: "Långsiktig plan = du vet vart du är på väg",
    long: "En långsiktig plan svarar på 'var vill jag vara om 3, 5, 10 år?'. Bostad, utbildning, resor, pensionsavsättningar. Utan plan rinner pengarna ut i konsumtion utan riktning.",
    example: "Anna vill bo i egen bostad om 5 år. Mål: 350 000 kr i kontantinsats. Sparkrav: ~5 800 kr/mån.",
    trains: "Modulen Mina mål — eleven sätter konkreta mål och tidsplan." },
  { num: 14, sym: "Rb", name: "Räntebindning", val: "rörlig/bunden", color: "expert",
    tip: "Räntebindning = risk vs. förutsägbarhet",
    long: "Rörlig ränta följer marknaden — kan gå upp eller ner när som helst. Bunden ränta låses fast i 1–10 år. Bunden ger förutsägbarhet men du betalar oftast lite mer i utbyte.",
    example: "2024 var rörlig 4,2 % och 5-årig bunden 4,5 %. Anna valde rörlig — och hade rätt: 2026 är den 3,1 %.",
    trains: "Modulen Bolåneval — eleven gör ett riktigt val mot Riksbankens historiska data." },
  { num: 15, sym: "AI", name: "Fråga Ekon", val: "Claude Sonnet", color: "special",
    tip: "AI-coach som kan hela kursplanen",
    long: "Ekon är en AI-coach byggd på Claude Sonnet 4.6 som svarar på elevens frågor om ekonomi. Den anpassar svaret till elevens mastery-nivå — mer Socrates där grunden saknas, direkt svar där eleven är mästrad.",
    example: "Eleven frågar: 'Vad är ränta-på-ränta?'. Ekon: 'Berätta först — vad tror du händer med 100 kr på ett konto med 5 % ränta efter 10 år?'",
    trains: "Tillgänglig i alla moduler — flytande knapp i nedre högra hörnet." },
  { num: 16, sym: "Pf", name: "Portfolio", val: "PDF-export", color: "special",
    tip: "Portfolio-PDF = lärarens betygsunderlag",
    long: "Portfolio-PDF:en samlar elevens reflektioner, mastery, klara moduler och uppdrag i ett snyggt dokument läraren kan använda som betygsunderlag eller utvecklingssamtal-bilaga.",
    example: "Lärare exporterar Annas portfolio inför betyg. Får en 12-sidig PDF med tre månader av reflektioner och mastery-grafer.",
    trains: "Bygger på all data eleven genererat — laddas ner från lärarens elev-vy." },
  { num: 17, sym: "In", name: "Inkomst", val: "lön · bidrag", color: "konto",
    tip: "Inkomst = allt som kommer in",
    long: "Inkomst är inte bara lön. Studiebidrag, CSN, swish från jobb, försäljning på Tradera — allt räknas. Att se HELA bilden hjälper när man planerar månaden.",
    example: "Anna har lön 23 040 + extra-Swish från cykelförsäljning 1 200 = 24 240 kr in i november.",
    trains: "Steg 1 i Din första månad — eleven listar alla sina inkomstkällor." },
  { num: 18, sym: "Ut", name: "Utgift", val: "fast · rörlig", color: "konto",
    tip: "Utgift = allt som går ut",
    long: "Utgifter delas i fasta (hyra, abonnemang, försäkringar — kommer varje månad oavsett) och rörliga (mat, nöje, kläder — du styr själv hur mycket). Den första gruppen är svårare att skära i, den andra är där du har handlingsutrymme.",
    example: "Annas fasta: 9 200 hyra + 99 Spotify + 590 SL + 89 Netflix = 9 978 kr/mån redan låsta.",
    trains: "Modulen Fast vs rörligt — eleven sorterar sina egna utgifter." },
  { num: 19, sym: "Öv", name: "Överskott", val: "sparat", color: "konto",
    tip: "Överskott = pengar kvar i slutet av månaden",
    long: "Överskott är när inkomsterna är större än utgifterna. Det är ENDA sättet att bygga ekonomi över tid. Två sätt att skapa överskott: tjäna mer eller spendera mindre. Oftast lättare att fixa det andra.",
    example: "Anna har +2 800 kr i november — överförs automatiskt till sparkonto.",
    trains: "Visas som balansraden i Dashboard varje månad." },
  { num: 20, sym: "Un", name: "Underskott", val: "varning", color: "risk",
    tip: "Underskott = du spenderade mer än du fick in",
    long: "Underskott betyder att pengarna kommer från någonstans annars — sparkonto, kreditkort, lån. Ett enstaka underskott är inget drama. Återkommande underskott är ekonomiska problem som växer.",
    example: "Anna får −1 800 i december (julshopping). Hon tar från bufferten denna gång — men måste se över januari.",
    trains: "Dashboard visar underskott i orange/röd; AI-coach föreslår orsaksanalys." },
  { num: 21, sym: "Rä", name: "Ränta", val: "% per år", color: "fordj",
    tip: "Ränta = priset för att låna pengar",
    long: "Ränta är det banken eller långivaren tar betalt för att låna ut pengar. Anges nästan alltid som procent per år. Lägre ränta = billigare lån. Räntan beror på risk (hur säker är banken på att få tillbaka), längd och konkurrens.",
    example: "4 % ränta på 100 000 kr = 4 000 kr/år = 333 kr/månad. Per dag: 11 kr.",
    trains: "Modulen Vad är ränta? — eleven räknar på olika räntor och horisonter." },
  { num: 22, sym: "Ef", name: "Effektiv ränta", val: "verkligt", color: "fordj",
    tip: "Effektiv ränta = den ränta du faktiskt betalar inkl. avgifter",
    long: "Den nominella räntan ('3,5 %') är inte hela kostnaden. Effektiv ränta inkluderar alla avgifter (uppläggning, autogiro, etc.) och visar vad lånet egentligen kostar. Lagstiftning kräver att den anges för konsumentkrediter.",
    example: "SMS-lån marknadsförs som '0 % ränta första månaden' men har 89 % effektiv ränta när alla avgifter räknats in.",
    trains: "Modulen Lånets verkliga pris — eleven jämför nominell vs effektiv ränta på olika krediter." },
  { num: 23, sym: "Rp", name: "Rubric", val: "bedömning", color: "special",
    tip: "Rubric = lärarens betygskriterier per kompetens",
    long: "Rubric är en matris med kriterier (t.ex. djup, struktur, källor) och nivåer (1–4). Läraren använder den för att bedöma reflektioner och uppdrag. Eleven ser kriterierna i förväg så bedömningen blir transparent.",
    example: "Reflektionsuppdrag bedöms på Djup (1–4) och Konkretion (1–4). Eleven får 3 + 4 = mycket bra.",
    trains: "Skapas av lärare i Rubric-mallar — kopplas till reflect-steg i moduler." },
  { num: 24, sym: "Qr", name: "QR-kod", val: "login", color: "special",
    tip: "QR-login = elev loggar in genom att skanna en kod",
    long: "Eleven får en personlig QR-kod att skriva ut eller ha i mobilen. Skannar man koden öppnas Ekonomilabbet inloggat som rätt elev — ingen 6-teckenskod att memorera.",
    example: "Lärare delar ut 27 utskrivna QR-kort i klassrummet. Två minuter senare är hela klassen inloggad.",
    trains: "Skapas automatiskt när läraren lägger upp en elev. Print-as-PDF-funktion." },
  { num: 25, sym: "Pe", name: "Pension", val: "premie", color: "grund",
    tip: "Pension = lön du får utan att jobba — så småningom",
    long: "Pension består av tre delar: allmän pension (staten, ~18,5 % av bruttolön), tjänstepension (arbetsgivaren, ~4,5 %) och privat sparande (frivilligt). Att börja tidigt spelar enorm roll — ränta-på-ränta över 40 år.",
    example: "1 000 kr/mån från 25 års ålder, 6 % årlig avkastning → 2 mkr vid 65. Samma 1 000 kr från 45 → 460 000 kr.",
    trains: "Modulen Pension från start — eleven leker med en pensionssimulator." },
  { num: 26, sym: "Fs", name: "Försäkring", val: "trygghet", color: "grund",
    tip: "Försäkring = du betalar lite varje månad för att slippa krasch",
    long: "Hemförsäkring, sjukförsäkring, bilförsäkring. Du betalar en mindre summa regelbundet för att slippa stå med jättekostnaden om något går fel. Man behöver inte alla — men hemförsäkring är ett måste.",
    example: "Anna betalar 250 kr/mån för hemförsäkring. När hennes laptop blir stulen får hon 14 000 kr i ersättning.",
    trains: "Modulen Försäkringar 101 — eleven jämför olika typer mot vad de täcker." },
  { num: 27, sym: "Fo", name: "Fondspar.", val: "index", color: "fordj",
    tip: "Fondsparande = långsiktigt ägande av flera bolag samtidigt",
    long: "En fond är en korg med många aktier. Indexfonder följer marknaden och har låga avgifter (~0,2–0,4 %). Aktivt förvaltade fonder försöker slå marknaden men tar 1–2 % i avgift — och slår sällan index över tid.",
    example: "Anna sätter 1 500 kr/mån i en global indexfond. Genomsnittlig årlig avkastning: ~7 %.",
    trains: "Modulen Fonder &amp; index — eleven jämför avgifter över 30-årshorisont." },
  { num: 28, sym: "Ak", name: "Aktie", val: "ägarskap", color: "expert",
    tip: "Aktie = en liten del av ett bolag",
    long: "När du köper en aktie äger du en bit av ett bolag. Du får utdelning om bolaget delar ut vinsten, och kursen rör sig efter hur marknaden värderar bolaget. Hög potentiell avkastning, hög risk — speciellt för enstaka bolag.",
    example: "Anna köper 10 aktier i H&amp;M för 150 kr/styck. Bolaget delar ut 6,50 kr/aktie → 65 kr i utdelning.",
    trains: "Modulen Aktier från noll — eleven får en simulerad portfölj och följer den i 6 månader." },
  { num: 29, sym: "Sn", name: "SMS-lån", val: "undvik", color: "risk",
    tip: "SMS-lån = den dyraste formen av kredit",
    long: "Snabblån, SMS-lån, mikrolån — alla namn på samma sak: små, dyra krediter med hög effektiv ränta (40–200 %+). De marknadsförs som lättillgängliga lösningar men leder ofta till skuldspiraler.",
    example: "5 000 kr på 30 dagar med 489 kr i avgift = 117 % effektiv ränta. Att rulla över 6 ggr → skulden dubbleras.",
    trains: "Modulen Skuldfällor — eleven analyserar verkliga SMS-lånvillkor." },
  { num: 30, sym: "Bg", name: "Bankgiro", val: "fakturor", color: "konto",
    tip: "Bankgiro = systemet svenska företag använder för räkningar",
    long: "Bankgiro är ett konto-format för företag (t.ex. 5050-1055). När du betalar en faktura skriver du in bankgironumret och OCR-numret. Pengarna går till företaget oavsett vilken bank de använder.",
    example: "Annas elräkning: bankgiro 123-4567, OCR 987654321, belopp 850 kr. Hon betalar via Swish-faktura eller bankens app.",
    trains: "Steg 4 i Din första månad — eleven betalar en simulerad faktura." },
  { num: 31, sym: "Ba", name: "Batch-PDF", val: "scenarier", color: "special",
    tip: "Batch = lärare genererar månadens dokument till hela klassen",
    long: "Läraren trycker på en knapp → systemet genererar en uppsättning realistiska PDF:er per elev: kontoutdrag, lönespec, lånebesked, kreditkortsfaktura. Eleverna importerar själva — får upplevelsen av att hantera riktiga dokument.",
    example: "Lärare genererar november-batch för klassen NA22. 27 elever får var sin unik uppsättning på 4 PDF:er.",
    trains: "Lärarverktyg i Teacher-vyn — knappen 'Generera exempeldata för månad'." },
  { num: 32, sym: "Mo", name: "Modul", val: "7 steg", color: "special",
    tip: "Modul = en kursvecka med läs/titta/reflektera/quiz/uppdrag",
    long: "En modul är en serie steg som lär ut ett specifikt tema. Stegtyper: läs (text), titta (video), reflektera (öppen fråga), quiz (flervalsfråga med direkt feedback), uppdrag (gör något i plattformen). Mastery byggs upp per kompetens.",
    example: "Modulen 'Din första månad' har 7 steg: 2 läs, 2 reflektera, 1 quiz, 2 uppdrag. Tar ~1 timme.",
    trains: "Hela kursplanen — bygg egna eller klona från lärarbiblioteket." },
];

// ---------- Default export ----------

export default function Landing() {
  return (
    <div className="bg-paper text-ink min-h-screen">
      <Header />
      <Hero />
      <Features />
      <Flow />
      <Stats />
      <Logiken />
      <Why />
      <Audiences />
      <SalaryNegotiation />
      <BankSimulation />
      <StockEmotion />
      <EntreprenorSneak />
      {/* <SocialProof /> — utkommenterad tills vi har riktiga pilotkunder */}
      <Gallery />
      <Pricing />
      <Faq />
      <FounderQuote />
      <Cta />
      <Contact />
      <Footer />
    </div>
  );
}

// ---------- Header ----------

function Header() {
  // Hamburger-state för mobil-menyn. På desktop (>=md) renderas den
  // klassiska två-spaltlayouten — på mobil får vi en hamburger som
  // öppnar både nav-länkar och login-knappar i en panel.
  const [mobileOpen, setMobileOpen] = useState(false);

  // Stäng menyn när man klickar en länk så man inte fastnar med
  // panelen öppen efter scroll.
  const close = () => setMobileOpen(false);

  return (
    <header className="border-b border-rule relative z-40">
      <div className="max-w-7xl mx-auto px-4 md:px-6 h-14 md:h-16 flex items-center justify-between">
        <Link to="/" className="flex items-center gap-2.5 shrink-0">
          <svg width="26" height="26" viewBox="0 0 40 40" aria-hidden="true">
            <circle cx="20" cy="20" r="18" fill="none" stroke="#111217" strokeWidth="2" />
            <text x="20" y="26" textAnchor="middle" fontFamily="Spectral" fontWeight="800" fontSize="18">Ek</text>
          </svg>
          <span className="serif text-lg md:text-xl">Ekonomilabbet</span>
        </Link>

        {/* Desktop: nav + tre login-knappar */}
        <nav className="hidden md:flex items-center gap-7 text-sm">
          <a href="#funktioner" className="nav-link">Funktioner</a>
          <a href="#flow" className="nav-link">Så funkar det</a>
          <a href="#malgrupper" className="nav-link">Skola/Hemma</a>
          <a href="#pricing" className="nav-link">Pris</a>
          <a href="#faq" className="nav-link">FAQ</a>
          <a href="#kontakt" className="nav-link">Kontakt</a>
        </nav>
        <div className="hidden md:flex gap-2">
          <Link to="/login/student" className="btn-outline text-sm px-4 py-2 rounded-md">
            Elev/Barn
          </Link>
          <Link to="/login/teacher" className="btn-outline text-sm px-4 py-2 rounded-md">
            Lärare
          </Link>
          <Link to="/signup/parent" className="btn-dark text-sm px-4 py-2 rounded-md">
            Förälder
          </Link>
        </div>

        {/* Mobil: en knapp för logga in + en hamburger */}
        <div className="md:hidden flex items-center gap-2">
          <Link
            to="/login"
            className="btn-dark text-xs px-3 py-1.5 rounded-md"
          >
            Logga in
          </Link>
          <button
            type="button"
            onClick={() => setMobileOpen((v) => !v)}
            aria-label={mobileOpen ? "Stäng meny" : "Öppna meny"}
            aria-expanded={mobileOpen}
            className="p-2 -mr-2 text-ink"
          >
            {mobileOpen ? (
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M6 6 L18 18 M6 18 L18 6" />
              </svg>
            ) : (
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M4 7h16 M4 12h16 M4 17h16" />
              </svg>
            )}
          </button>
        </div>
      </div>

      {/* Mobil-panel — slide-down under headern */}
      {mobileOpen && (
        <div className="md:hidden border-t border-rule bg-white">
          <nav className="max-w-7xl mx-auto px-4 py-3 flex flex-col text-sm">
            <a onClick={close} href="#funktioner" className="nav-link py-2 border-b border-rule/60">Funktioner</a>
            <a onClick={close} href="#flow" className="nav-link py-2 border-b border-rule/60">Så funkar det</a>
            <a onClick={close} href="#malgrupper" className="nav-link py-2 border-b border-rule/60">Skola/Hemma</a>
            <a onClick={close} href="#pricing" className="nav-link py-2 border-b border-rule/60">Pris</a>
            <a onClick={close} href="#faq" className="nav-link py-2 border-b border-rule/60">FAQ</a>
            <a onClick={close} href="#kontakt" className="nav-link py-2 border-b border-rule/60">Kontakt</a>
            <div className="grid grid-cols-3 gap-2 mt-4">
              <Link onClick={close} to="/login/student" className="btn-outline text-xs px-2 py-2 rounded-md text-center">
                Elev/Barn
              </Link>
              <Link onClick={close} to="/login/teacher" className="btn-outline text-xs px-2 py-2 rounded-md text-center">
                Lärare
              </Link>
              <Link onClick={close} to="/signup/parent" className="btn-dark text-xs px-2 py-2 rounded-md text-center">
                Förälder
              </Link>
            </div>
          </nav>
        </div>
      )}
    </header>
  );
}

// ---------- Hero (text + grid + professor) ----------

function Hero() {
  // Hålls i Landing-state och drillas ner till PeriodicGrid + button.
  const [heatmapOn, setHeatmapOn] = useState(false);
  const [openCell, setOpenCell] = useState<Cell | null>(null);

  // Sätter body-klassen för heatmap-overlay (CSS triggar via .heatmap-on)
  useEffect(() => {
    document.body.classList.toggle("heatmap-on", heatmapOn);
    return () => {
      document.body.classList.remove("heatmap-on");
    };
  }, [heatmapOn]);

  return (
    <section className="relative max-w-7xl mx-auto px-4 md:px-6 pt-10 md:pt-16 pb-10 md:pb-12 grid md:grid-cols-[1fr_1.4fr] gap-8 md:gap-12 items-start">
      <DriftParticles />
      <div className="relative z-[1]">
        <div className="eyebrow mb-4 md:mb-5">Ekonomilabbet · utgåva 2026</div>
        <h1 className="serif text-4xl md:text-6xl leading-[1.05] md:leading-[1.02]">
          Det periodiska<br />systemet för pengar.
        </h1>
        <p className="mt-6 lead max-w-md">
          Från <span className="kbd">Lö</span> (lön) till <span className="kbd">Rb</span> (räntebindning) —
          32 grundbegrepp varje ungdom behöver för att inte krocka
          med vuxenlivet. Tryck eller hovra över en cell — resten av
          kartan öppnar sig.
        </p>
        <div className="mt-7 md:mt-8 grid grid-cols-2 sm:flex sm:flex-wrap gap-2.5 md:gap-3">
          <Link to="/signup/teacher" className="btn-dark px-4 md:px-5 py-3 rounded-md text-center text-sm md:text-base">
            För skolan
          </Link>
          <Link to="/signup/parent" className="btn-dark px-4 md:px-5 py-3 rounded-md text-center text-sm md:text-base">
            För hemmet
          </Link>
          <a href="#flow" className="btn-outline px-4 md:px-5 py-3 rounded-md text-center text-sm md:text-base">
            Se hur det funkar
          </a>
          <button
            type="button"
            onClick={() => setHeatmapOn((v) => !v)}
            aria-pressed={heatmapOn}
            className="btn-outline px-4 md:px-5 py-3 rounded-md text-center text-sm md:text-base"
          >
            {heatmapOn ? "Ta bort värmekarta" : "Lägg på värmekarta"}
          </button>
        </div>

        <ul className="mt-8 md:mt-10 text-sm space-y-2.5 md:space-y-3">
          <li className="flex items-center gap-3"><LegendDot bg="#eef3ff" />Grundkompetens (5)</li>
          <li className="flex items-center gap-3"><LegendDot bg="#fff3e6" />Fördjupning (5)</li>
          <li className="flex items-center gap-3"><LegendDot bg="#f3eaff" />Expert (2)</li>
          <li className="flex items-center gap-3"><LegendDot bg="#e8f7ef" />Konto &amp; flöde</li>
          <li className="flex items-center gap-3"><LegendDot bg="#fdecec" />Riskgrupp</li>
          <li className="flex items-center gap-3"><LegendDot bg="#111217" />Professorns tillskott</li>
        </ul>
      </div>

      <div className="relative z-[1]">
        <ProfessorWithBubble />
        <PeriodicGrid onPick={setOpenCell} />
        <p className="mt-4 text-xs text-[#777] serif-italic">
          Prototyp · 32 celler motsvarar 12 kompetenser + 20 stödbegrepp i kursplan 2026.
        </p>
      </div>

      {openCell && <CellModal cell={openCell} onClose={() => setOpenCell(null)} />}
    </section>
  );
}

function LegendDot({ bg }: { bg: string }) {
  return (
    <span
      className="inline-block w-2.5 h-2.5 border border-ink"
      style={{ background: bg }}
    />
  );
}

// ---------- Periodic-grid (32 celler) ----------

function PeriodicGrid({ onPick }: { onPick: (c: Cell) => void }) {
  // Deterministiska heatmap-värden per cellposition (0-1)
  const heat = [
    0.92, 0.74, 0.88, 0.82, 0.71, 0.66, 0.54, 0.48,
    0.38, 0.32, 0.64, 0.58, 0.22, 0.18, 0.41, 0.36,
    0.52, 0.46, 0.42, 0.28, 0.26, 0.14, 0.50, 0.71,
    0.67, 0.55, 0.34, 0.12, 0.08, 0.44, 0.62, 0.58,
  ];

  // Pilar mellan celler (8-kolumn grid)
  function onKeyDown(e: React.KeyboardEvent<HTMLDivElement>) {
    const focused = document.activeElement as HTMLElement | null;
    if (!focused?.classList.contains("elem")) return;
    const cells = Array.from(
      e.currentTarget.querySelectorAll<HTMLElement>(".elem")
    );
    const idx = cells.indexOf(focused);
    if (idx < 0) return;
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      const cell = CELLS[idx];
      if (cell) onPick(cell);
      return;
    }
    const dx = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
    const dy = e.key === "ArrowDown" ? 1 : e.key === "ArrowUp" ? -1 : 0;
    if (dx === 0 && dy === 0) return;
    e.preventDefault();
    const cols = window.innerWidth >= 768 ? 8 : 4;
    const next = idx + dx + dy * cols;
    if (cells[next]) cells[next].focus();
  }

  return (
    <div
      className="grid grid-cols-4 md:grid-cols-8 gap-1.5"
      role="grid"
      aria-label="Periodiska systemet för pengar — 32 begrepp"
      onKeyDown={onKeyDown}
    >
      {CELLS.map((c, i) => (
        <button
          key={c.num}
          type="button"
          role="gridcell"
          tabIndex={0}
          onClick={() => onPick(c)}
          className={`elem ${c.color}`}
          aria-label={`${c.name}, ${c.val}. ${c.tip}`}
          style={{ ["--h" as never]: String(heat[i] ?? 0) }}
        >
          <span className="num">{c.num}</span>
          <span className="elem-body">
            <span className="sym">{c.sym}</span>
            <span className="name">{c.name}</span>
          </span>
          <span className="val">{c.val}</span>
          {/* Tooltip flippas under cellen för översta raden så den inte
              klipps mot sectionkanten / professorns pratbubbla. */}
          <span className={`elem-tooltip ${i < 8 ? "below" : ""}`}>{c.tip}</span>
          <span className="heatmap" />
        </button>
      ))}
    </div>
  );
}

// ---------- Cell-modal ----------

function CellModal({ cell, onClose }: { cell: Cell; onClose: () => void }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      role="dialog"
      aria-modal="true"
      onClick={onClose}
      className="fixed inset-0 z-40 bg-ink/55 flex items-center justify-center p-4"
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="bg-white border-[1.5px] border-ink p-7 max-w-lg w-full max-h-[85vh] overflow-y-auto"
      >
        <div className="flex items-baseline gap-4">
          <span className={`feature-chip ${cell.color}`}>{cell.sym}</span>
          <div>
            <div className="serif text-2xl leading-tight">{cell.name}</div>
            <div className="eyebrow mt-1">
              {cell.color === "grund" ? "Grundkompetens"
                : cell.color === "fordj" ? "Fördjupning"
                : cell.color === "expert" ? "Expert"
                : cell.color === "konto" ? "Konto &amp; flöde"
                : cell.color === "risk" ? "Riskgrupp"
                : "Professorns tillskott"} · #{cell.num}
            </div>
          </div>
        </div>

        <p className="mt-5 body-prose text-[15px]">{cell.long}</p>

        <div className="mt-5 border-l-[3px] border-ink pl-4 py-1">
          <div className="eyebrow mb-1">Exempel</div>
          <p className="serif-italic text-[15px] leading-snug">{cell.example}</p>
        </div>

        <div className="mt-5 pt-4 border-t border-rule">
          <div className="eyebrow mb-1">Tränas i</div>
          <p className="text-sm text-[#444]">{cell.trains}</p>
        </div>

        <div className="mt-6 flex justify-end">
          <button onClick={onClose} className="btn-dark px-5 py-2 rounded-md text-sm">
            Stäng
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------- Professor + speech-bubble ----------

function ProfessorWithBubble() {
  const eyeLRef = useRef<SVGCircleElement | null>(null);
  const eyeRRef = useRef<SVGCircleElement | null>(null);
  const svgRef = useRef<SVGSVGElement | null>(null);

  useEffect(() => {
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduce) return;
    const onMove = (e: MouseEvent) => {
      const svg = svgRef.current;
      if (!svg || !eyeLRef.current || !eyeRRef.current) return;
      const r = svg.getBoundingClientRect();
      const cx = r.left + r.width / 2;
      const cy = r.top + r.height / 2;
      const dx = Math.max(-1, Math.min(1, (e.clientX - cx) / 200));
      const dy = Math.max(-1, Math.min(1, (e.clientY - cy) / 200));
      eyeLRef.current.setAttribute("cx", String(48 + dx * 2));
      eyeLRef.current.setAttribute("cy", String(68 + dy * 2));
      eyeRRef.current.setAttribute("cx", String(72 + dx * 2));
      eyeRRef.current.setAttribute("cy", String(68 + dy * 2));
    };
    window.addEventListener("mousemove", onMove);
    return () => window.removeEventListener("mousemove", onMove);
  }, []);

  return (
    <div className="prof-wrap" aria-hidden="true">
      <div className="prof-bubble">
        Hovra över en cell — den du följer ser samma karta som du.
      </div>
      <svg ref={svgRef} className="prof-svg" viewBox="0 0 120 120">
        <ellipse cx="60" cy="70" rx="36" ry="38" fill="#ffd7b0" stroke="#111" strokeWidth="3" />
        <path
          d="M24 50 Q10 10 40 30 Q30 -5 60 20 Q90 -5 80 30 Q110 10 96 50 Q105 70 80 60 L40 60 Q15 70 24 50Z"
          fill="#fff" stroke="#111" strokeWidth="3"
        />
        <circle cx="48" cy="68" r="8" fill="#fff" stroke="#111" strokeWidth="2.5" />
        <circle cx="72" cy="68" r="8" fill="#fff" stroke="#111" strokeWidth="2.5" />
        <circle ref={eyeLRef} cx="48" cy="68" r="3" fill="#111" />
        <circle ref={eyeRRef} cx="72" cy="68" r="3" fill="#111" />
        <path d="M48 88 Q60 96 72 88" stroke="#111" strokeWidth="2.5" fill="none" />
        <path d="M30 58 L40 50 M90 58 L80 50" stroke="#111" strokeWidth="2.5" />
      </svg>
    </div>
  );
}

// ---------- Drift-partiklar bakom hero ----------

function DriftParticles() {
  const [particles] = useState(() => {
    const arr: { top: number; left: number; dx: number; dy: number; dur: number }[] = [];
    for (let i = 0; i < 18; i++) {
      arr.push({
        top: Math.random() * 100,
        left: Math.random() * 100,
        dx: (Math.random() - 0.5) * 120,
        dy: (Math.random() - 0.5) * 120,
        dur: 6 + Math.random() * 8,
      });
    }
    return arr;
  });
  return (
    <div className="absolute inset-0 overflow-hidden pointer-events-none z-0" aria-hidden="true">
      {particles.map((p, i) => (
        <span
          key={i}
          className="particle drifting"
          style={{
            top: `${p.top}%`,
            left: `${p.left}%`,
            ["--dx" as never]: `${p.dx}px`,
            ["--dy" as never]: `${p.dy}px`,
            ["--dur" as never]: `${p.dur}s`,
          }}
        />
      ))}
    </div>
  );
}

// ---------- Funktioner-sektion (9 mini-celler) ----------

type Feature = { chip: string; chipColor: CellColor; title: string; body: string };

const FEATURES: Feature[] = [
  { chip: "Pf", chipColor: "special", title: "Unik elev-profil",
    body: "Varje elev får slumpat yrke, lön, stad och livssituation. Ingen i klassen har samma utgångsläge." },
  { chip: "Ku", chipColor: "konto", title: "Riktiga PDF:er",
    body: "Läraren genererar kontoutdrag, lönespec, lånebesked och kreditkortsfakturor som eleverna själva importerar." },
  { chip: "Bu", chipColor: "grund", title: "Budget mot verklighet",
    body: "Eleven sätter månadsbudget från Konsumentverkets 2026-siffror — sedan jämförs den mot faktiska köp." },
  { chip: "Bl", chipColor: "fordj", title: "Bolåne-beslut",
    body: "Historiska räntor från Riksbanken. Eleven väljer rörlig eller bunden — systemet visar facit efter horisonten." },
  { chip: "Ov", chipColor: "risk", title: "Livet händer",
    body: "Diskmaskin går sönder. Sjukdagar sänker lönen. Julshopping exploderar. Eleverna övar på det oväntade." },
  { chip: "Hu", chipColor: "grund", title: "Familjer",
    body: "Två elever kan dela ekonomi — sambo-hushåll med gemensam budget, räkningar och sparmål." },
  { chip: "Rp", chipColor: "special", title: "Lärarens översikt",
    body: "Översiktsmatris med status per elev/barn och uppdrag. Facit för varje kategorisering — grönt eller rött på en blick." },
  { chip: "AI", chipColor: "special", title: "Fråga Ekon (AI)",
    body: "Multi-turn coach på Claude Sonnet. Anpassar språket till elevens mastery — mer Socrates där grunden saknas." },
  { chip: "Sp", chipColor: "fordj", title: "Sparmål & uppdrag",
    body: "Tydliga uppdrag: 'spara 2 000 kr', 'balansera månaden', 'kategorisera alla köp'. Status uppdateras live." },
];

function Features() {
  return (
    <section id="funktioner" className="border-t border-rule">
      <div className="max-w-7xl mx-auto px-4 md:px-6 py-14 md:py-20">
        <div className="section-divider mb-10">Funktionerna</div>
        <div className="max-w-3xl mb-12">
          <h2 className="serif text-4xl md:text-5xl leading-[1.05]">
            Allt en lärare eller förälder behöver för att göra ekonomi
            begripligt.
          </h2>
          <p className="mt-4 lead">
            Från första lönen till bolåne-beslut. Varje funktion är ett
            element i kursplanen — den unga övar genom att göra, inte genom
            att läsa om det.
          </p>
        </div>
        <ul className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {FEATURES.map((f) => (
            <li key={f.title} className="feature-card">
              <div className="flex items-start gap-4">
                <span className={`feature-chip ${f.chipColor}`} aria-hidden="true">
                  {f.chip}
                </span>
                <div>
                  <h3 className="serif text-xl leading-snug">{f.title}</h3>
                  <p className="mt-2 body-prose text-sm">{f.body}</p>
                </div>
              </div>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

// ---------- Flow-sektionen (5 numrerade steg) ----------

function Flow() {
  return (
    <section id="flow" className="border-t border-rule bg-white">
      <div className="max-w-7xl mx-auto px-4 md:px-6 py-14 md:py-20">
        <div className="section-divider mb-10">Så funkar det</div>
        <div className="max-w-3xl mb-14">
          <h2 className="serif text-4xl md:text-5xl leading-[1.05]">Fem nyckelmoment.</h2>
          <p className="mt-4 lead">
            Det här är vad den unga och den vuxna faktiskt gör — i ordning,
            månad för månad. Samma flöde i klassrummet som hemma.
          </p>
        </div>

        <div className="space-y-16">
          <FlowStep
            num={1}
            title="Den unga får en egen vardag."
            body="Yrke, lön, bostad, lån — allt slumpas unikt per användare. Dashboarden visar nettolön, utgifter, sparande och budget mot verkligheten i realtid."
            mock={<MockDashboard />}
          />
          <FlowStep
            num={2}
            reverse
            title="Riktiga dokument att jobba med."
            body="Du trycker 'generera' — den unga får kontoutdrag, lönespec, lånebesked och kortfakturor som PDF:er och importerar själv."
            mock={<MockPdfList />}
          />
          <FlowStep
            num={3}
            title="Budget möter verklighet."
            body="Den unga sätter månadsbudget enligt Konsumentverkets 2026-siffror. När en trasig diskmaskin slår till syns följderna direkt."
            mock={<MockBudget />}
          />
          <FlowStep
            num={4}
            reverse
            title="Verkliga ekonomiska val."
            body="Bolåne-beslut baserat på Riksbankens historiska räntor. Användaren binder eller kör rörlig — systemet visar facit efter perioden. Konsekvenser görs synliga."
            mock={<MockMortgage />}
          />
          <FlowStep
            num={5}
            title="Du ser hela bilden."
            body="Matris över alla användare och uppdrag. Kategoriseringsfacit per transaktion. Chatt för feedback. Samma översikt vare sig du följer en klass eller dina barn."
            mock={<MockClassMatrix />}
          />
        </div>
      </div>
    </section>
  );
}

function FlowStep({
  num, title, body, mock, reverse,
}: {
  num: number; title: string; body: string; mock: React.ReactNode; reverse?: boolean;
}) {
  return (
    <div className="grid md:grid-cols-2 gap-6 md:gap-10 items-center">
      <div className={reverse ? "md:order-2" : ""}>
        <div className="flow-num mb-5">{num}</div>
        <h3 className="serif text-3xl leading-tight">{title}</h3>
        <p className="mt-3 body-prose">{body}</p>
      </div>
      <div className={reverse ? "md:order-1" : ""}>{mock}</div>
    </div>
  );
}

function MockDashboard() {
  return (
    <div className="mock">
      <div className="eyebrow mb-3">Anna · barista · Stockholm</div>
      <div className="mock-row"><span>Nettolön nov</span><span className="mock-num">23 450 kr</span></div>
      <div className="mock-row"><span>Hyra</span><span className="mock-num">−9 200 kr</span></div>
      <div className="mock-row"><span>Mat &amp; dryck</span><span className="mock-num">−3 870 kr</span></div>
      <div className="mock-row"><span>Sparande</span><span className="mock-num">+1 500 kr</span></div>
      <div className="mock-row"><span className="font-semibold">Saldo idag</span><span className="mock-num">8 880 kr</span></div>
    </div>
  );
}

function MockPdfList() {
  const docs = [
    { sym: "Ku", color: "konto" as CellColor, label: "Kontoutdrag · 23 transaktioner" },
    { sym: "Lö", color: "grund" as CellColor, label: "Lönespec · november" },
    { sym: "Bl", color: "fordj" as CellColor, label: "Lånebesked · 18,4 kvkm" },
    { sym: "Kk", color: "risk" as CellColor, label: "Kortfaktura · −2 340 kr" },
  ];
  return (
    <div className="mock">
      <div className="eyebrow mb-3">Generering 2026-11</div>
      <ul className="space-y-2">
        {docs.map((d) => (
          <li key={d.sym} className="flex items-center gap-3">
            <span
              className={`feature-chip ${d.color}`}
              style={{ width: 32, height: 32, fontSize: 13 }}
              aria-hidden="true"
            >
              {d.sym}
            </span>
            <span className="flex-1">{d.label}</span>
            <span className="mock-pill ok">PDF</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function MockBudget() {
  return (
    <div className="mock">
      <div className="eyebrow mb-3">Budget vs faktiskt · november</div>
      <div className="space-y-3">
        <div>
          <div className="flex justify-between text-xs mb-1"><span>Mat (planerat 4 000)</span><span className="mock-num">3 870 kr</span></div>
          <div className="mock-bar"><span style={{ width: "97%" }} /></div>
        </div>
        <div>
          <div className="flex justify-between text-xs mb-1"><span>Nöje (planerat 1 500)</span><span className="mock-num">2 410 kr</span></div>
          <div className="mock-bar"><span style={{ width: "100%", background: "#eb5757" }} /></div>
        </div>
        <div>
          <div className="flex justify-between text-xs mb-1"><span>Hushåll (planerat 800)</span><span className="mock-num">3 200 kr</span></div>
          <div className="mock-bar"><span style={{ width: "100%", background: "#eb5757" }} /></div>
        </div>
      </div>
      <p className="mt-3 text-xs text-[#777] serif-italic">
        Diskmaskinen sa upp sig den 14:e.
      </p>
    </div>
  );
}

function MockMortgage() {
  return (
    <div className="mock">
      <div className="eyebrow mb-3">Bolåne-uppdrag · 36 mån horisont</div>
      <div className="grid grid-cols-2 gap-3 text-xs">
        <div className="border border-rule p-3">
          <div className="text-[#888]">Rörlig (eleven valde)</div>
          <div className="mock-num text-2xl mt-1">3,25 %</div>
          <div className="mt-2 text-[#666]">Snitt över perioden: 3,8 %</div>
        </div>
        <div className="border border-rule p-3">
          <div className="text-[#888]">3 år bunden</div>
          <div className="mock-num text-2xl mt-1">3,90 %</div>
          <div className="mt-2 text-[#666]">Fixerad hela perioden</div>
        </div>
      </div>
      <div className="mt-3 mock-pill ok">Rörlig vann: −18 240 kr</div>
    </div>
  );
}

function MockClassMatrix() {
  const rows: { name: string; budget: "ok" | "no" | ""; mortg: "ok" | "no" | ""; mastery: string }[] = [
    { name: "Anna", budget: "ok", mortg: "ok", mastery: "82 %" },
    { name: "Bahar", budget: "ok", mortg: "no", mastery: "71 %" },
    { name: "Carl", budget: "no", mortg: "", mastery: "54 %" },
    { name: "Disa", budget: "ok", mortg: "ok", mastery: "90 %" },
    { name: "Erik", budget: "no", mortg: "no", mastery: "63 %" },
  ];
  function pillClass(s: "ok" | "no" | "") {
    return s === "ok" ? "mock-pill ok" : s === "no" ? "mock-pill no" : "mock-pill";
  }
  function pillText(s: "ok" | "no" | "") {
    return s === "ok" ? "klar" : s === "no" ? "pågår" : "väntar";
  }
  return (
    <div className="mock">
      <div className="eyebrow mb-3">Klass NA22 · 5 elever</div>
      <table className="w-full text-xs">
        <thead>
          <tr className="text-[#888]">
            <th className="text-left font-normal py-1">Elev</th>
            <th className="text-left font-normal">Budget</th>
            <th className="text-left font-normal">Bolån</th>
            <th className="text-left font-normal">Mastery</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.name} className="border-t border-rule">
              <td className="py-1.5">{r.name}</td>
              <td><span className={pillClass(r.budget)}>{pillText(r.budget)}</span></td>
              <td><span className={pillClass(r.mortg)}>{pillText(r.mortg)}</span></td>
              <td className="mock-num">{r.mastery}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ---------- Stats-ticker (live från /public/stats, count-up) ----------

type Stats = {
  teachers: number;
  students: number;
  modules_completed: number;
  reflections_written: number;
};

function Stats() {
  const [stats, setStats] = useState<Stats | null>(null);

  useEffect(() => {
    let cancelled = false;
    api<Stats>("/public/stats")
      .then((d) => { if (!cancelled) setStats(d); })
      .catch(() => { /* tysta — sektionen visar '—' */ });
    return () => { cancelled = true; };
  }, []);

  const items: { key: keyof Stats; label: string }[] = [
    { key: "teachers", label: "Lärare" },
    { key: "students", label: "Elever" },
    { key: "modules_completed", label: "Avklarade moduler" },
    { key: "reflections_written", label: "Reflektioner" },
  ];

  return (
    <section id="stats" className="border-t border-rule bg-white">
      <div className="max-w-7xl mx-auto px-4 md:px-6 py-12 md:py-14">
        <div className="section-divider mb-10">I produktion just nu</div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-x-8 gap-y-8">
          {items.map((it) => (
            <div key={it.key} className="text-center">
              <div className="serif text-4xl md:text-5xl">
                {stats ? <CountUp target={stats[it.key]} /> : "—"}
              </div>
              <div className="eyebrow mt-2">{it.label}</div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

// ---------- Logiken-strip + Why-section ----------

function Logiken() {
  const items = [
    {
      n: "01",
      title: "En cell, en kompetens.",
      body: "Varje element är kopplat till en eller flera moduler. När den unga klarar stegen fylls cellen — precis som MasteryChart redan gör.",
    },
    {
      n: "02",
      title: "Du rättar i rader.",
      body: "Reflektioner batchas per kolumn. Claude föreslår rubric-betyg; du skriver under eller ändrar på två klick — som lärare eller förälder.",
    },
    {
      n: "03",
      title: "Hela gruppen i en bild.",
      body: "Översikten lägger användarnas mastery som ett värmekarta-lager ovanpå systemet — toggla i hero-vyn ovan. Funkar för en klass eller ett syskonpar.",
    },
  ];
  return (
    <section className="border-t border-rule bg-white">
      <div className="max-w-7xl mx-auto px-4 md:px-6 py-14 md:py-20">
        <div className="section-divider mb-12">Logiken</div>
        <div className="grid md:grid-cols-3 gap-x-8 md:gap-x-12 gap-y-8 md:gap-y-10">
          {items.map((it) => (
            <div key={it.n}>
              <div className="eyebrow mb-2">{it.n}</div>
              <h3 className="serif text-2xl leading-[1.15]">{it.title}</h3>
              <p className="mt-3 body-prose">{it.body}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function Why() {
  return (
    <section id="why" className="border-t border-rule">
      <div className="max-w-7xl mx-auto px-4 md:px-6 py-14 md:py-20">
        <div className="section-divider mb-10">Problemet</div>
        <div className="grid md:grid-cols-[1.1fr_1fr] gap-8 md:gap-12 items-start">
          <div>
            <h2 className="serif text-4xl md:text-5xl leading-[1.05]">
              Ekonomi är ett livskunskaps­ämne.<br />
              Och det saknas — både i skolan och hemma.
            </h2>
            <p className="mt-5 lead max-w-md">
              Svenska unga lämnar gymnasiet utan grund­läggande kunskaper om
              skatt, sparande, lån och budget. Verkligheten möter dem först
              när de flyttar hemifrån — ofta för sent. Skolan har sällan
              tid, och föräldrar har sällan ett verktyg att lära ut med.
            </p>
            <div className="mt-8 border-l-[3px] border-ink pl-5 py-1 max-w-md">
              <div className="serif-italic text-lg leading-snug">
                Lär genom att göra — inte genom att läsa om det.
              </div>
              <p className="mt-2 text-sm body-prose">
                Den unga får egen simulerad inkomst, egna räkningar, egen
                lön varje månad. Varje val har konsekvenser som syns direkt
                i budgeten.
              </p>
            </div>
          </div>

          <ul className="grid gap-3">
            <li className="border-[1.5px] border-ink bg-white p-5 flex items-baseline gap-5">
              <span className="serif text-5xl leading-none shrink-0">4 av 10</span>
              <span className="body-prose">unga klarar inte en oväntad räkning på 2 000 kr.</span>
            </li>
            <li className="border-[1.5px] border-ink bg-white p-5 flex items-baseline gap-5">
              <span className="serif text-5xl leading-none shrink-0">60 %</span>
              <span className="body-prose">av unga har aldrig läst en lönespecifikation.</span>
            </li>
            <li className="border-[1.5px] border-ink bg-white p-5 flex items-baseline gap-5">
              <span className="serif text-5xl leading-none shrink-0">1 h</span>
              <span className="body-prose">räcker för att prova grunderna i Ekonomilabbet.</span>
            </li>
          </ul>
        </div>
      </div>
    </section>
  );
}


// ---------- Två målgrupper: skola + hemma ----------

function Audiences() {
  return (
    <section id="malgrupper" className="border-t border-rule bg-white">
      <div className="max-w-7xl mx-auto px-4 md:px-6 py-14 md:py-20">
        <div className="section-divider mb-10">Två sätt att använda</div>
        <div className="max-w-3xl mb-12">
          <h2 className="serif text-4xl md:text-5xl leading-[1.05]">
            Samma plattform — i klassrummet eller vid köksbordet.
          </h2>
          <p className="mt-4 lead">
            Ekonomilabbet är byggt så att en lärare kan följa en hel klass
            och en förälder kan följa sina egna barn — i samma verktyg,
            med samma moduler och samma trygga sandlåda.
          </p>
        </div>
        <div className="grid md:grid-cols-2 gap-5">
          <article className="border-[2.5px] border-ink bg-paper p-7">
            <div className="eyebrow mb-3">För skolan</div>
            <h3 className="serif text-2xl leading-tight">
              Ett labb i klassrummet.
            </h3>
            <ul className="mt-5 space-y-2.5 text-sm body-prose">
              <li className="flex gap-2">
                <span className="text-ink shrink-0">→</span>
                <span>
                  Bjud in en hel klass via 6-teckens-koder — ingen
                  e-post per elev krävs.
                </span>
              </li>
              <li className="flex gap-2">
                <span className="text-ink shrink-0">→</span>
                <span>
                  Tilldela samma modul till alla, eller skräddarsy per
                  elev. Mastery-grafen visar var klassen fastnar.
                </span>
              </li>
              <li className="flex gap-2">
                <span className="text-ink shrink-0">→</span>
                <span>
                  Portfolio-PDF per elev eller hela klassen som ZIP —
                  perfekt som bedömningsunderlag.
                </span>
              </li>
              <li className="flex gap-2">
                <span className="text-ink shrink-0">→</span>
                <span>
                  AI-coachen anpassar sig efter elevens nivå utan att
                  läraren behöver konfigurera något.
                </span>
              </li>
            </ul>
            <Link
              to="/signup/teacher"
              className="mt-7 inline-block btn-dark px-5 py-2.5 rounded-md text-sm"
            >
              Skapa lärarkonto →
            </Link>
          </article>

          <article className="border-[2.5px] border-ink bg-paper p-7">
            <div className="eyebrow mb-3">För hemmet</div>
            <h3 className="serif text-2xl leading-tight">
              Samtalet om pengar — i lugnt format.
            </h3>
            <ul className="mt-5 space-y-2.5 text-sm body-prose">
              <li className="flex gap-2">
                <span className="text-ink shrink-0">→</span>
                <span>
                  Skapa konton för dina barn på två minuter. Varje
                  barn får en egen sandlåda — riktiga pengar är aldrig
                  inblandade.
                </span>
              </li>
              <li className="flex gap-2">
                <span className="text-ink shrink-0">→</span>
                <span>
                  Du följer med i samma vy som läraren har: vad har
                  barnet gjort, vad har det fastnat på, vad har det
                  frågat AI:n.
                </span>
              </li>
              <li className="flex gap-2">
                <span className="text-ink shrink-0">→</span>
                <span>
                  Modulerna täcker kontoutdrag, bolån, kreditkort,
                  sparande och familjeekonomi — bygg upp ett gemensamt
                  språk hemma.
                </span>
              </li>
              <li className="flex gap-2">
                <span className="text-ink shrink-0">→</span>
                <span>
                  AI-coachen svarar på "varför betalar man skatt?"
                  utan att vänta på er nästa middag.
                </span>
              </li>
            </ul>
            <Link
              to="/signup/parent"
              className="mt-7 inline-block btn-dark px-5 py-2.5 rounded-md text-sm"
            >
              Skapa familjekonto →
            </Link>
          </article>
        </div>
        <p className="mt-8 text-sm text-[#666] serif-italic max-w-2xl">
          Tekniskt är skola och hemma samma admin-konto under huven —
          du följer dem du är ansvarig för. Ingen samkörning av data
          mellan familjer eller skolor sker någonsin.
        </p>
      </div>
    </section>
  );
}


// ---------- Social proof + Vyer-galleri ----------

// SocialProof: pilotskole-listan är utkommenterad tills vi har riktiga
// pilotkunder att namnge. Återanvänd komponenten genom att lägga
// tillbaka <SocialProof /> i render-trädet ovan när det är dags.
// function SocialProof() {
//   const schools = [
//     "Exempelskolan",
//     "Ekonomilinjen Malmö",
//     "Linnéskolan",
//     "Musikgymnasiet",
//     "Fjällgymnasiet",
//   ];
//   return (
//     <section id="social" className="border-t border-rule bg-white">
//       <div className="max-w-7xl mx-auto px-4 md:px-6 py-12 md:py-14">
//         <div className="section-divider mb-8">
//           I pilotprojekt tillsammans med
//         </div>
//         <ul className="grid grid-cols-2 md:grid-cols-5 gap-x-6 gap-y-4 text-center">
//           {schools.map((s) => (
//             <li key={s} className="serif text-lg text-[#555]">{s}</li>
//           ))}
//         </ul>
//         <p className="mt-6 text-xs text-[#999] text-center serif-italic">
//           Riktiga logotyper läggs till efter pilotfasen.
//         </p>
//       </div>
//     </section>
//   );
// }

type GalleryAsset = {
  id: number;
  slot: string;
  title: string;
  body: string;
  chip: string;
  chip_color: string;
  sort_order: number;
  has_image: boolean;
  image_url: string | null;
};

const FALLBACK_SHOTS: Array<{
  chip: string; chipColor: CellColor; title: string; body: string;
}> = [
  { chip: "Lä", chipColor: "special", title: "Lärarens dashboard",
    body: "Alla elever, inbox, uppdrag och AI-lägesbilder på en skärm." },
  { chip: "Mo", chipColor: "grund", title: "Elevens kursplan",
    body: "Moduler steg för steg: läs, reflektera, quiz och uppdrag." },
  { chip: "Ms", chipColor: "fordj", title: "Mastery-grafen",
    body: "Per-kompetens mastery, milstolpar och nästa-steg-hint." },
  { chip: "Pf", chipColor: "special", title: "Portfolio-PDF",
    body: "Exporteras per elev eller som ZIP för hela klassen." },
  { chip: "AI", chipColor: "special", title: "Fråga Ekon",
    body: "Multi-turn AI-coach som anpassar svaren till elevens nivå." },
  { chip: "Tt", chipColor: "risk", title: "Time on task",
    body: "Se vilka steg som fastnar för eleverna i din klass." },
];

// ---------- Lönesamtal + arbetsplats-dynamik ----------

function SalaryNegotiation() {
  return (
    <section id="lonesamtal" className="border-t border-rule bg-white">
      <div className="max-w-7xl mx-auto px-4 md:px-6 py-14 md:py-20">
        <div className="section-divider mb-10">
          Det enda samtalet på året
        </div>
        <div className="grid md:grid-cols-[1.2fr_1fr] gap-10 md:gap-14 items-start">
          <div>
            <h2 className="serif text-4xl md:text-5xl leading-[1.05]">
              Lönesamtal du faktiskt vågar gå in i.
            </h2>
            <p className="mt-5 lead max-w-md">
              Din arbetsgivare har ett kollektivavtal, en revisionsnorm,
              och ett begränsat utrymme. Eleven får 5 ronder mot
              AI-chefen Maria — som balanserar avtalet, satisfaction-
              faktorn och bolagets budget.
            </p>
            <div className="mt-8 border-l-[3px] border-ink pl-5 py-1 max-w-md">
              <div className="serif-italic text-lg leading-snug">
                Lönen kommer nästa månad — inte på en gång.
              </div>
              <p className="mt-2 text-sm body-prose">
                När samtalet är klart sätts ett <em>pending salary</em>{" "}
                med startdatum 1:a nästa månad. Lönespecen som genereras
                speglar den nya lönen — exakt som i verkligheten.
              </p>
            </div>
          </div>

          <div className="border-[1.5px] border-ink bg-paper p-5 space-y-3 text-sm">
            <div className="text-[10px] uppercase tracking-wider text-slate-500">
              Rond 2 av 5 · avtals-norm 3,0 %
            </div>
            <div className="border-l-2 border-slate-300 pl-3 py-1 bg-white">
              <div className="text-[10px] uppercase text-slate-500 mb-1">
                Eleven
              </div>
              <p className="body-prose">
                Marknadslönen för min roll ligger på 39 500 kr enligt
                Akavia 2026. Jag ligger 1 500 kr under. Jag vill upp
                till 39 500 kr — det är 4,5 %.
              </p>
            </div>
            <div className="border-l-2 border-ink pl-3 py-1 bg-white">
              <div className="text-[10px] uppercase text-slate-700 mb-1">
                Maria (HR) — bud 3,5 %
              </div>
              <p className="body-prose">
                Jag uppskattar att du tagit lead-rollen. Men det var
                inget du valde — du hoppade in när Erik slutade. Det är
                ett skäl för 4 %, inte 4,5.
              </p>
            </div>
            <div className="text-[11px] text-slate-500 italic pt-1">
              Eleven ser inte detta. Maria balanserar avtal, satisfaction
              och budget — utgår från det.
            </div>
          </div>
        </div>

        {/* Workplace-frågor underrad */}
        <div className="mt-12 pt-8 border-t border-rule grid md:grid-cols-3 gap-4">
          <div className="border-[1.5px] border-ink p-4 bg-white">
            <div className="text-[10px] uppercase tracking-wider text-slate-500 mb-2">
              Slumpad arbetsplats-fråga
            </div>
            <h3 className="serif text-lg leading-snug">
              Kollegan glömmer pass — täcker du?
            </h3>
            <p className="mt-2 text-sm body-prose">
              Din kollega Maria har glömt sitt passerkort hemma och
              ringer kl 06.45 — kan du köra och hämta henne? Ert pass
              startar 07.00.
            </p>
          </div>
          <div className="border-[1.5px] border-ink p-4 bg-white">
            <div className="text-[10px] uppercase tracking-wider text-slate-500 mb-2">
              Arbetsgivar-nöjdhet
            </div>
            <h3 className="serif text-lg leading-snug">
              Hur hanterar du missnöjd kund?
            </h3>
            <p className="mt-2 text-sm body-prose">
              Varje val flyttar elevens satisfaction-score 0–100. Låg
              score → mindre löneutrymme. Hög score → mer förhandlings-
              utrymme i samtalet.
            </p>
          </div>
          <div className="border-[1.5px] border-ink p-4 bg-white">
            <div className="text-[10px] uppercase tracking-wider text-slate-500 mb-2">
              Avtal som faktiskt finns
            </div>
            <h3 className="serif text-lg leading-snug">
              11 kollektivavtal · 17 yrken
            </h3>
            <p className="mt-2 text-sm body-prose">
              HÖK Kommunal, Tjänstemanna IT, Byggavtalet, Detaljhandel
              med flera. Varje yrke är mappat — eller markerat
              <em> småföretag, fri lönesättning</em>.
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}

// ---------- Banken-sektion ----------

function BankSimulation() {
  return (
    <section id="banken" className="border-t border-rule">
      <div className="max-w-7xl mx-auto px-4 md:px-6 py-14 md:py-20">
        <div className="section-divider mb-10">
          Banken är inte bokföringen
        </div>
        <div className="grid md:grid-cols-[1fr_1.2fr] gap-10 md:gap-14 items-start">
          <div>
            <h2 className="serif text-4xl md:text-5xl leading-[1.05]">
              Bank, redovisning, konsekvens.
              <br />
              Tre system — som i verkligheten.
            </h2>
            <p className="mt-5 lead max-w-md">
              Eleven loggar in i banken med simulerat BankID, exporterar
              kontoutdrag till sina dokument, och importerar sedan till
              bokföringssystemet. Tre steg, exakt som hemma. Bank-saker
              hör inte hemma i bokföringen — de möts på vägen.
            </p>
            <div className="mt-8 grid grid-cols-3 gap-3 max-w-md">
              <div className="border-[1.5px] border-ink p-3 bg-white">
                <div className="text-[10px] uppercase tracking-wider text-slate-500">
                  Steg 1
                </div>
                <div className="serif text-base mt-1">Banken</div>
                <div className="text-xs body-prose mt-1">
                  Logga in med BankID
                </div>
              </div>
              <div className="border-[1.5px] border-ink p-3 bg-white">
                <div className="text-[10px] uppercase tracking-wider text-slate-500">
                  Steg 2
                </div>
                <div className="serif text-base mt-1">Dokument</div>
                <div className="text-xs body-prose mt-1">
                  Exportera PDF:er
                </div>
              </div>
              <div className="border-[1.5px] border-ink p-3 bg-white">
                <div className="text-[10px] uppercase tracking-wider text-slate-500">
                  Steg 3
                </div>
                <div className="serif text-base mt-1">Bokför</div>
                <div className="text-xs body-prose mt-1">
                  Importera till systemet
                </div>
              </div>
            </div>
          </div>

          <div className="space-y-4">
            <div className="border-[1.5px] border-ink p-5 bg-paper">
              <div className="text-[10px] uppercase tracking-wider text-slate-500 mb-2">
                BankID-simulering
              </div>
              <h3 className="serif text-2xl leading-snug">
                Något du har — något du vet.
              </h3>
              <p className="mt-2 text-sm body-prose">
                QR-flöde + 4-siffrig PIN. Pedagogisk metafor: telefonen
                (något du har) + PIN (något du vet). Eleven förstår
                varför man aldrig delar PIN — banken ringer aldrig och
                frågar.
              </p>
            </div>
            <div className="border-[1.5px] border-ink p-5 bg-paper">
              <div className="text-[10px] uppercase tracking-wider text-slate-500 mb-2">
                Signera betalningar
              </div>
              <h3 className="serif text-2xl leading-snug">
                Saldot räknar — i realtid.
              </h3>
              <p className="mt-2 text-sm body-prose">
                Eleven signerar fakturor i banken. På förfallodagen
                körs betalningen <em>om</em> saldot räcker. Räcker det
                inte triggas påminnelse-flödet: 60 → 120 → 180 kr →
                Kronofogden. Pedagogiskt skarpt.
              </p>
            </div>
            <div className="border-[1.5px] border-ink p-5 bg-paper">
              <div className="flex items-baseline justify-between mb-2">
                <div className="text-[10px] uppercase tracking-wider text-slate-500">
                  EkonomiSkalan — kreditbetyg
                </div>
                <div className="serif text-3xl font-semibold">724</div>
              </div>
              <h3 className="serif text-2xl leading-snug">
                Varje sen betalning syns.
              </h3>
              <p className="mt-2 text-sm body-prose">
                300–850 skala (likt UC). Sena betalningar, skuldkvot,
                buffert och arbetsgivar-nöjdhet räknas in — varje faktor
                med transparent delta. Eleven kan räkna efter.
              </p>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}


function StockEmotion() { return null; }
function EntreprenorSneak() { return null; }


function Gallery() {
  const [assets, setAssets] = useState<GalleryAsset[] | null>(null);

  useEffect(() => {
    api<GalleryAsset[]>("/landing/gallery")
      .then((rows) => setAssets(rows.length ? rows : null))
      .catch(() => setAssets(null));
  }, []);

  // Tom server-respons eller fel → fall tillbaka på placeholder-kort
  // så landningssidan aldrig är blank för en första-besökare.
  const items = assets
    ? assets.map((a) => ({
        key: `${a.id}`,
        chip: a.chip || "·",
        chipColor: (a.chip_color || "grund") as CellColor,
        title: a.title,
        body: a.body,
        imageUrl: a.has_image && a.image_url
          ? `${getApiBase()}${a.image_url}`
          : null,
      }))
    : FALLBACK_SHOTS.map((s) => ({
        key: s.title,
        chip: s.chip,
        chipColor: s.chipColor,
        title: s.title,
        body: s.body,
        imageUrl: null,
      }));

  return (
    <section id="vyer" className="border-t border-rule">
      <div className="max-w-7xl mx-auto px-4 md:px-6 py-14 md:py-20">
        <div className="section-divider mb-10">Vyerna</div>
        <div className="max-w-3xl mb-10">
          <h2 className="serif text-4xl md:text-5xl leading-[1.05]">
            Sex skärmar lärare och elever rör sig i.
          </h2>
          <p className="mt-4 lead">
            {assets && assets.some((a) => a.has_image)
              ? "Skärmdumpar från det riktiga systemet."
              : "Konceptbilder — riktiga skärmdumpar laddas upp av super-admin."}
          </p>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {items.map((s) => (
            <article
              key={s.key}
              className={
                "feature-card overflow-hidden flex flex-col " +
                (s.imageUrl ? "p-0" : "aspect-[4/3] justify-between")
              }
            >
              {s.imageUrl ? (
                <>
                  <div className="relative bg-paper">
                    <span
                      className={`feature-chip ${s.chipColor} absolute top-3 left-3 z-10`}
                      aria-hidden="true"
                    >
                      {s.chip}
                    </span>
                    <img
                      src={s.imageUrl}
                      alt={s.title}
                      className="block w-full h-auto"
                      loading="lazy"
                    />
                  </div>
                  <div className="p-5">
                    <h3 className="serif text-xl leading-snug">{s.title}</h3>
                    <p className="mt-2 body-prose text-sm">{s.body}</p>
                  </div>
                </>
              ) : (
                <>
                  <span
                    className={`feature-chip ${s.chipColor}`}
                    aria-hidden="true"
                  >
                    {s.chip}
                  </span>
                  <div>
                    <h3 className="serif text-xl leading-snug">{s.title}</h3>
                    <p className="mt-2 body-prose text-sm">{s.body}</p>
                  </div>
                </>
              )}
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}

// ---------- Pricing + FAQ ----------

function Pricing() {
  return (
    <section id="pricing" className="border-t border-rule bg-white">
      <div className="max-w-7xl mx-auto px-4 md:px-6 py-14 md:py-20">
        <div className="section-divider mb-10">Pris</div>
        <div className="max-w-3xl mb-12">
          <h2 className="serif text-4xl md:text-5xl leading-[1.05]">Enkel prismodell.</h2>
          <p className="mt-4 lead">
            Gratis under pilotåret 2026 — för skolor och familjer. Ingen
            bindningstid, inga dolda kostnader. Från 2027 sätts en avgift
            per användare i dialog med pilotkunderna.
          </p>
        </div>

        <div className="grid md:grid-cols-2 gap-5 max-w-3xl">
          <article className="border-[2.5px] border-ink bg-paper p-7 relative">
            <span className="absolute -top-3 left-5 px-2 py-0.5 bg-ink text-white text-xs uppercase tracking-eyebrow">
              Pilot 2026
            </span>
            <div className="serif text-5xl mt-3 leading-none">0 kr</div>
            <p className="mt-2 text-sm text-[#555]">Hela plattformen, utan tak.</p>
            <ul className="mt-5 space-y-2 text-sm body-prose">
              <li className="flex items-start gap-2"><span className="serif">·</span>Obegränsat antal elever/barn</li>
              <li className="flex items-start gap-2"><span className="serif">·</span>AI-funktioner (Claude Sonnet)</li>
              <li className="flex items-start gap-2"><span className="serif">·</span>Portfolio-PDF + ZIP-export</li>
              <li className="flex items-start gap-2"><span className="serif">·</span>Support via mail</li>
            </ul>
          </article>

          <article className="border-[1.5px] border-rule bg-white p-7">
            <span className="eyebrow">Från 2027</span>
            <div className="serif text-5xl mt-3 leading-none">Per-användare</div>
            <p className="mt-2 text-sm text-[#555]">
              Nivå sätts tillsammans med pilotkunderna — troligen
              50–150 kr/användare/år. Familjer får ett enklare paketpris.
            </p>
            <ul className="mt-5 space-y-2 text-sm body-prose">
              <li className="flex items-start gap-2"><span className="serif">·</span>Samma plattform, ingen funktionsnedskärning</li>
              <li className="flex items-start gap-2"><span className="serif">·</span>Tak för AI-användning</li>
              <li className="flex items-start gap-2"><span className="serif">·</span>Dedikerad support</li>
            </ul>
          </article>
        </div>
      </div>
    </section>
  );
}

const FAQ_ITEMS: { q: string; a: string }[] = [
  {
    q: "Vad kostar Ekonomilabbet?",
    a: "Gratis under pilotåret 2026 — både för skolor och föräldrar. Inga dolda kostnader. Från 2027 sätts en avgift per användare i dialog med pilotkunderna.",
  },
  {
    q: "Är det GDPR-säkert?",
    a: "Ja. All användardata sparas i svensk molntjänst (Google Cloud Run, europe-north1). Vi delar inga personuppgifter med tredje part. AI-anropen anonymiseras — Claude ser aldrig namn eller personnummer.",
  },
  {
    q: "Vad behöver vi installera?",
    a: "Inget. Ekonomilabbet är en webbapp. Den vuxna (lärare eller förälder) skapar konto, lägger in elever/barn och de loggar in med en 6-teckenskod eller QR-kod. Ingen installation, ingen app-store.",
  },
  {
    q: "Kan föräldrar använda detta hemma?",
    a: "Ja, det är ett av två huvudspår. Som förälder skapar du ett familjekonto, lägger till dina barn (varje barn får en egen kod) och följer deras arbete i samma admin-vy som en lärare. Modulerna täcker allt från kontoutdrag och sparande till bolån och kreditkort.",
  },
  {
    q: "Går det att använda utan AI?",
    a: "Absolut. Alla pedagogiska flöden (moduler, reflektioner, quiz, rubric, portfolio) fungerar utan AI. AI är en ren extra-funktion som kan aktiveras per konto.",
  },
  {
    q: "Kan elever eller barn komma åt varandras data?",
    a: "Nej. Varje elev/barn har en egen SQLite-DB på servern, ingen cross-access även om de råkar i samma klass eller familj. Den vuxna ser bara sina egna användare — aldrig någon annan lärares eller förälders.",
  },
  {
    q: "Vad händer med elevernas data när året är slut?",
    a: "Ingenting tvångsmässigt — datan är kvar tills läraren tar bort kontot. Vi exporterar gärna hela klassen till ZIP så du har en kopia innan du raderar.",
  },
  {
    q: "Vilken AI-modell används?",
    a: "Claude Haiku 4.5 för snabba uppgifter (kategori-check, feedback-förslag) och Claude Sonnet 4.6 för djupare uppgifter (rubric, elev-Q&A, modul-generering). Prompt-caching används för kostnadskontroll.",
  },
  {
    q: "Kan jag importera befintliga moduler från andra system?",
    a: "Inte som automatisk import än. Moduler skapas i plattformen eller klonas från systemmallar/andra lärares delade moduler. Säg till oss vad ni använder — vi bygger importen om det finns efterfrågan.",
  },
];

function Faq() {
  return (
    <section id="faq" className="border-t border-rule">
      <div className="max-w-3xl mx-auto px-4 md:px-6 py-14 md:py-20">
        <div className="section-divider mb-10">FAQ</div>
        <h2 className="serif text-4xl md:text-5xl leading-[1.05] mb-10">
          Vanliga frågor.
        </h2>
        {FAQ_ITEMS.map((it, i) => (
          <details key={i} className="faq">
            <summary>
              {it.q}
              <span className="arrow" />
            </summary>
            <div className="answer">{it.a}</div>
          </details>
        ))}
      </div>
    </section>
  );
}

// ---------- Founder + CTA + Kontakt + Footer ----------

function FounderQuote() {
  return (
    <section className="border-t border-rule">
      <div className="max-w-3xl mx-auto px-4 md:px-6 py-14 md:py-20 text-center">
        <div className="serif text-7xl leading-none text-ink/15 select-none">
          &ldquo;
        </div>
        <blockquote className="serif-italic text-2xl md:text-[28px] leading-snug mt-2 text-[#222]">
          Ekonomilabbet började som ett verktyg för min egen ekonomi. Nu
          kan det också hjälpa unga att förstå pengar, beslut och vardags­
          ekonomi på riktigt — på ett sätt som känns konkret och användbart.
        </blockquote>
        <div className="mt-6 eyebrow">— Grundaren</div>
      </div>
    </section>
  );
}

function Cta() {
  return (
    <section className="max-w-7xl mx-auto px-4 md:px-6 py-16 md:py-24 text-center">
      <div className="eyebrow mb-4">Kom igång</div>
      <h2 className="serif text-4xl md:text-5xl leading-[1.05]">
        Det vuxenlivs­ämne som varken skolan eller köksbordet
        riktigt hann med.
      </h2>
      <p className="mt-5 lead max-w-xl mx-auto">
        Gratis under pilotåret. Ingen bindningstid. Du väljer själv om du
        kör med en klass eller med dina egna barn.
      </p>
      <div className="mt-7 flex justify-center gap-3 flex-wrap">
        <Link to="/signup/teacher" className="btn-dark px-6 py-3.5 rounded-md">
          Starta som lärare
        </Link>
        <Link to="/signup/parent" className="btn-dark px-6 py-3.5 rounded-md">
          Starta som förälder
        </Link>
        <a
          href="mailto:info@ekonomilabbet.org?subject=Boka%20introduktion"
          className="btn-outline px-6 py-3.5 rounded-md"
        >
          Boka introduktion
        </a>
      </div>
    </section>
  );
}

function Contact() {
  return (
    <section id="kontakt" className="border-t border-rule bg-white">
      <div className="max-w-3xl mx-auto px-4 md:px-6 py-12 md:py-16 text-center">
        <div className="section-divider mb-8">Kontakt</div>
        <h2 className="serif text-3xl md:text-4xl leading-[1.05]">
          Frågor, förslag eller samarbeten?
        </h2>
        <p className="mt-4 lead">
          Vi hjälper gärna till om du vill komma igång i din klass eller
          med dina egna barn, har önskemål om nya funktioner, eller vill
          utforska samarbeten med skolor, kommuner, föreningar eller
          lärarorganisationer.
        </p>
        <a
          href="mailto:info@ekonomilabbet.org"
          className="btn-dark inline-block mt-7 px-6 py-3.5 rounded-md font-mono text-sm"
        >
          info@ekonomilabbet.org
        </a>
        <p className="text-xs text-[#888] mt-4 serif-italic">
          Vi svarar oftast inom ett par arbetsdagar.
        </p>
      </div>
    </section>
  );
}

function Footer() {
  return (
    <footer className="border-t border-rule">
      <div className="max-w-7xl mx-auto px-4 md:px-6 py-10 md:py-12 grid md:grid-cols-3 gap-6 md:gap-10 text-sm">
        <div>
          <div className="flex items-center gap-2 mb-3">
            <svg width="22" height="22" viewBox="0 0 40 40" aria-hidden="true">
              <circle cx="20" cy="20" r="18" fill="none" stroke="#111217" strokeWidth="2" />
              <text x="20" y="26" textAnchor="middle" fontFamily="Spectral" fontWeight="800" fontSize="18">Ek</text>
            </svg>
            <span className="serif text-lg">Ekonomilabbet</span>
          </div>
          <p className="text-[#666] body-prose">
            En öppen utbildningsplattform för privatekonomi — i
            klassrummet och vid köksbordet.
          </p>
        </div>
        <div>
          <div className="eyebrow mb-3">Sidan</div>
          <ul className="space-y-1.5">
            <li><a href="#funktioner" className="nav-link">Funktioner</a></li>
            <li><a href="#flow" className="nav-link">Så funkar det</a></li>
            <li><a href="#pricing" className="nav-link">Pris</a></li>
            <li><a href="#faq" className="nav-link">FAQ</a></li>
          </ul>
        </div>
        <div>
          <div className="eyebrow mb-3">Kontakt &amp; juridik</div>
          <ul className="space-y-1.5">
            <li><a href="mailto:info@ekonomilabbet.org" className="nav-link">info@ekonomilabbet.org</a></li>
            <li><Link to="/docs" className="nav-link">Dokumentation</Link></li>
            <li><a href="#faq" className="nav-link">FAQ</a></li>
          </ul>
        </div>
      </div>
      <div className="border-t border-rule">
        <div className="max-w-7xl mx-auto px-4 md:px-6 py-5 text-xs text-[#888] flex flex-wrap justify-between gap-3">
          <div>© {new Date().getFullYear()} Ekonomilabbet · För skolan och hemmet</div>
          <div className="serif-italic">Prototyp — utgåva 2026</div>
        </div>
      </div>
    </footer>
  );
}

function CountUp({ target }: { target: number }) {
  const [val, setVal] = useState(0);
  useEffect(() => {
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduce || target === 0) {
      setVal(target);
      return;
    }
    const start = performance.now();
    const dur = 800;
    let raf = 0;
    const step = (now: number) => {
      const t = Math.min(1, (now - start) / dur);
      const eased = 1 - Math.pow(1 - t, 3);
      setVal(Math.round(target * eased));
      if (t < 1) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [target]);
  return <>{val.toLocaleString("sv-SE")}</>;
}
