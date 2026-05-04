/**
 * Interaktiva guider — speglar prototypens GUIDES-konfig.
 *
 * Varje guide har en lista av steg, varje steg har:
 * - selector: CSS-selector för elementet som ska spotligheras
 * - route: vilken URL eleven måste vara på (vi navigerar dit)
 * - eye: kort header-text "Guide · X / Y"
 * - h: rubrik (kan ha <em>)
 * - prose: brödtext (kan ha <em>/<strong>)
 * - placement: var tip-cardet ska placeras
 *
 * Intro-guiden startar auto på Hub efter onboarding. Övriga 10
 * guider startas via header-knappen.
 */

export type GuidePlacement = "bottom" | "top" | "right" | "bottom-left" | "left";

export type GuideStep = {
  selector: string;
  route: string; // URL-path
  eye: string;
  h: string;
  prose: string;
  placement: GuidePlacement;
};

export type GuideDef = {
  key: string;
  label: string;
  icon: string;
  time: string; // "8 steg · 3 min"
  sub: string;
  steps: GuideStep[];
};

const INTRO_STEPS: GuideStep[] = [
  {
    selector: "[data-guide='hub-pentagon']",
    route: "/v2/hub",
    eye: "Guide · 1 / 7",
    h: "Pentagonen är ditt <em>hjärta</em>.",
    prose:
      "Fem axlar (ekonomi, hälsa, social, fritid, safety). När något händer — som tandläkaren ringer — tippar pentagonen <em>direkt</em>. Inget val är gratis.",
    placement: "right",
  },
  {
    selector: "[data-guide='hub-compass']",
    route: "/v2/hub",
    eye: "Guide · 2 / 7 · kompassen",
    h: "Här är dina <em>aktörer</em>.",
    prose:
      "9 aktörer (Banken, Arbetsgivaren, Skatteverket, Lånegivaren, Avanza, Försäkringar, Förbrukning, Hyresvärden, Pension) plus Postlådan. <em>Aktörer ser ut som världen</em>.",
    placement: "top",
  },
  {
    selector: "[data-guide='hub-tools']",
    route: "/v2/hub",
    eye: "Guide · 3 / 7 · verktyg",
    h: "Verktyg och <em>skola</em>.",
    prose:
      "Bokföring, budget, mål, simulator, lånekalkylator + skol-noder för moduler, portfolio, meddelanden, feedback. Klicka för att utforska.",
    placement: "top",
  },
  {
    selector: "[data-guide='echo-button']",
    route: "/v2/hub",
    eye: "Guide · 4 / 7 · Echo",
    h: "Echo är alltid <em>tillgänglig</em>.",
    prose:
      "Echo-knappen i nedre högra hörnet öppnar en chatt-drawer. Echo vet vad du tittar på och ställer <em>frågor</em> — inte råd. Du fattar besluten själv.",
    placement: "left",
  },
  {
    selector: "[data-guide='postladan-link']",
    route: "/v2/hub",
    eye: "Guide · 5 / 7 · postlådan",
    h: "Postlådan är <em>källan</em>.",
    prose:
      "Räkningar, lönespecar och myndighetspost landar här först. Du måste granska — sen exportera till banken eller bokföra.",
    placement: "bottom",
  },
  {
    selector: "[data-guide='hub-banner']",
    route: "/v2/hub",
    eye: "Guide · 6 / 7 · banner",
    h: "V2-bannern visar <em>din roll</em>.",
    prose:
      "Du loggar in som elev — bannern visar det och om du är i en utvecklingsmiljö. Lärar-vyer har samma banner men i lärar-färg.",
    placement: "bottom",
  },
  {
    selector: "[data-guide='hub-pentagon']",
    route: "/v2/hub",
    eye: "Guide · 7 / 7 · klar",
    h: "Du är <em>laddad</em>.",
    prose:
      "Dags att börja. Tandläkaren väntar i postlådan. Anders Lind har skickat ett uppdrag. Lycka till.",
    placement: "right",
  },
];

const POSTLADAN_STEPS: GuideStep[] = [
  {
    selector: "[data-guide='postladan-list']",
    route: "/v2/postladan",
    eye: "Postlådan · 1 / 4",
    h: "Postlådan är <em>källan</em>.",
    prose:
      "Alla räkningar, lönespecar, myndighetspost landar här. Ingen bokföring förrän du <em>granskat</em>.",
    placement: "right",
  },
  {
    selector: "[data-guide='postladan-tabs']",
    route: "/v2/postladan",
    eye: "Postlådan · 2 / 4 · filter",
    h: "Filtrera efter <em>typ</em>.",
    prose:
      "Klicka på flikar för att se bara fakturor, lönespecar eller myndighetspost. Ohanterade visas som standard.",
    placement: "bottom",
  },
  {
    selector: "[data-guide='postladan-list']",
    route: "/v2/postladan",
    eye: "Postlådan · 3 / 4 · klick",
    h: "Klicka på ett <em>brev</em>.",
    prose:
      "Kreditkortsfakturor och lönespecar öppnas i detalj-vy med transaktioner respektive brutto/netto-breakdown.",
    placement: "right",
  },
  {
    selector: "[data-guide='postladan-list']",
    route: "/v2/postladan",
    eye: "Postlådan · 4 / 4 · åtgärd",
    h: "<em>Granska</em> sen <em>agera</em>.",
    prose:
      "Markera som granskad, exportera till banken, eller diskutera med Echo. Pedagogisk friktion bevarad.",
    placement: "right",
  },
];

const BANKEN_STEPS: GuideStep[] = [
  {
    selector: "[data-guide='bank-accounts']",
    route: "/v2/banken",
    eye: "Banken · 1 / 4",
    h: "Banken är <em>infrastruktur</em>.",
    prose:
      "Lönekonto, sparkonto, ISK, kreditkort. Tillgängligt saldo är inte hela bilden — kommande dragningar äter upp det.",
    placement: "bottom",
  },
  {
    selector: "[data-guide='bank-accounts']",
    route: "/v2/banken",
    eye: "Banken · 2 / 4 · konton",
    h: "Klicka för <em>detaljer</em>.",
    prose:
      "Varje konto-card visar saldo, kommande och senaste transaktioner. Kreditkort visar dessutom kreditgräns och nästa faktura.",
    placement: "bottom",
  },
  {
    selector: "[data-guide='bank-accounts']",
    route: "/v2/banken",
    eye: "Banken · 3 / 4 · BankID",
    h: "Signera fakturor via <em>BankID</em>.",
    prose:
      "När fakturor från postlådan importerats kan du signera dem alla på en gång via BankID-simulatorn — friktion bevarad i 6 steg.",
    placement: "bottom",
  },
  {
    selector: "[data-guide='bank-accounts']",
    route: "/v2/banken",
    eye: "Banken · 4 / 4 · klar",
    h: "Bank = <em>flöde</em>.",
    prose:
      "Pengar in (lön), pengar ut (autogiro). Banken är där det blir konkret. Resten av appen är <em>medvetenhet</em>.",
    placement: "bottom",
  },
];

const PENTAGON_STEPS: GuideStep[] = [
  {
    selector: "[data-guide='hub-pentagon']",
    route: "/v2/hub",
    eye: "Pentagon · 1 / 3",
    h: "Pentagon = <em>balans</em>.",
    prose:
      "Fem axlar mäter ditt liv. Varje aktion (signera faktura, klassa transaktion, sluta lönesamtal) tippar någon axel.",
    placement: "right",
  },
  {
    selector: "[data-guide='hub-pentagon']",
    route: "/v2/hub",
    eye: "Pentagon · 2 / 3 · faktorer",
    h: "Faktorerna är <em>spårbara</em>.",
    prose:
      "Varje förändring kommer från en konkret beräkning — t.ex. förstahandskontrakt = +5 safety, ISK > 0 = +2 economy. Hela listan visas under pentagonen.",
    placement: "right",
  },
  {
    selector: "[data-guide='hub-pentagon']",
    route: "/v2/hub",
    eye: "Pentagon · 3 / 3 · pedagogik",
    h: "Pentagon är <em>spegel</em>.",
    prose:
      "Inget rätt svar. Du jagar inte 100 % på alla axlar — du ser tradeoffs. Hög ekonomi-axel kan kosta i fritid.",
    placement: "right",
  },
];

const MARIA_STEPS: GuideStep[] = [
  {
    selector: "[data-guide='maria-chat']",
    route: "/v2/maria",
    eye: "Maria · 1 / 3",
    h: "Maria är AI · <em>spelar realistiskt</em>.",
    prose:
      "5 ronder. Du anchorar med marknadsdata, hänvisar till kollektivavtal. Maria har dold smärtgräns — du anar den.",
    placement: "left",
  },
  {
    selector: "[data-guide='maria-chat']",
    route: "/v2/maria",
    eye: "Maria · 2 / 3 · BATNA",
    h: "BATNA = <em>din styrka</em>.",
    prose:
      "Best Alternative To Negotiated Agreement. Stark BATNA = stark position. Tänk: vad gör du om Maria säger nej?",
    placement: "left",
  },
  {
    selector: "[data-guide='maria-chat']",
    route: "/v2/maria",
    eye: "Maria · 3 / 3 · tystnad",
    h: "Tystnad är <em>din vän</em>.",
    prose:
      "80 % av framgångsrika förhandlare gör tystnaden till sin allierade. Sänk inte i panik.",
    placement: "left",
  },
];

const BANKID_STEPS: GuideStep[] = [
  {
    selector: "[data-guide='bankid-qr']",
    route: "/v2/banken",
    eye: "BankID · 1 / 3",
    h: "BankID är <em>med flit</em> i 6 steg.",
    prose:
      "Friktionen är meningen. Du måste se vad du signerar — fingret ska få veta. Aldrig signera utan att läsa.",
    placement: "right",
  },
  {
    selector: "[data-guide='bankid-qr']",
    route: "/v2/banken",
    eye: "BankID · 2 / 3 · QR",
    h: "QR-koden är <em>specifik</em>.",
    prose:
      "Bunden till denna signering. Aldrig återanvändbar. Skanna med Ekonomilabbet-ID eller skriv personnumret.",
    placement: "right",
  },
  {
    selector: "[data-guide='bankid-qr']",
    route: "/v2/banken",
    eye: "BankID · 3 / 3 · pedagogik",
    h: "Du <em>signerar</em> inte bara — du <em>förstår</em>.",
    prose:
      "23 fakturor binder dig till leverantörer i 30 dagar. Det är inte trivialt. Tiden i flödet tränar muskeln.",
    placement: "right",
  },
];

const BOKFORING_STEPS: GuideStep[] = [
  {
    selector: "[data-guide='bokforing-summary']",
    route: "/v2/bokforing",
    eye: "Bokföring · 1 / 4",
    h: "Klassa = <em>se</em>.",
    prose:
      "Att klassa en transaktion = du bestämmer vad det betyder. Spegeln av dina vanor.",
    placement: "bottom",
  },
  {
    selector: "[data-guide='bokforing-filters']",
    route: "/v2/bokforing",
    eye: "Bokföring · 2 / 4 · filter",
    h: "Filtrera per <em>period och status</em>.",
    prose:
      "Innevarande månad / hela perioden · ovettade / auto-klassade / manuella · per konto. Sök på beskrivning eller kategori.",
    placement: "bottom",
  },
  {
    selector: "[data-guide='bokforing-summary']",
    route: "/v2/bokforing",
    eye: "Bokföring · 3 / 4 · regelmotor",
    h: "AI-knappen kör <em>regelmotor</em>.",
    prose:
      "Klicka 'Klassa alla X (AI)' så kör backend regelmotor + history-match + Claude-fallback. Snabbar upp 70-80 % av jobbet.",
    placement: "bottom",
  },
  {
    selector: "[data-guide='bokforing-summary']",
    route: "/v2/bokforing",
    eye: "Bokföring · 4 / 4 · klar",
    h: "Klassningsgrad <em>räknas</em>.",
    prose:
      "≥ 80 % på senaste 30 dgr → +2 economy i wellbeing. < 40 % → -1 economy ('svårare att lära dig vanor').",
    placement: "bottom",
  },
];

const BUDGET_STEPS: GuideStep[] = [
  {
    selector: "[data-guide='budget-categories']",
    route: "/v2/budget",
    eye: "Budget · 1 / 2",
    h: "Budget är <em>kärlek</em>.",
    prose:
      "Sätt en restaurang-budget = lovord till framtida-dig som vill ha buffert. Det är inte begränsning, det är prioritering.",
    placement: "right",
  },
  {
    selector: "[data-guide='budget-categories']",
    route: "/v2/budget",
    eye: "Budget · 2 / 2 · jämförelse",
    h: "Plan vs <em>utfall</em>.",
    prose:
      "Konsumentverkets schablon vs din budget vs ditt faktiska utfall. Tre tal som tillsammans säger mer än ett.",
    placement: "right",
  },
];

const AVANZA_STEPS: GuideStep[] = [
  {
    selector: "[data-guide='avanza-funds']",
    route: "/v2/avanza",
    eye: "Avanza · 1 / 3",
    h: "ISK gör <em>tiden</em> till din vän.",
    prose:
      "Schablonskatt 0,89 % på kapitalunderlaget. Spara 600 kr/mån i 40 år vid 7 % real avk = 1,47 Mkr.",
    placement: "bottom",
  },
  {
    selector: "[data-guide='avanza-funds']",
    route: "/v2/avanza",
    eye: "Avanza · 2 / 3 · fonder",
    h: "Fonder är <em>bredd</em>.",
    prose:
      "Ett klick = exponering mot 100-tals bolag. Indexfonder med < 0,5 % avgift slår 80 % aktivt förvaltade på 10 år.",
    placement: "bottom",
  },
  {
    selector: "[data-guide='avanza-funds']",
    route: "/v2/avanza",
    eye: "Avanza · 3 / 3 · aktier",
    h: "Aktier är <em>fokus</em>.",
    prose:
      "Klicka 'Öppna aktiemarknaden' för att handla enskilda OMXS30 + USA-large-caps. Mini-courtage 1 kr · 0,25 % över 400.",
    placement: "bottom",
  },
];

const SKATT_STEPS: GuideStep[] = [
  {
    selector: "[data-guide='skatten-summary']",
    route: "/v2/skatten",
    eye: "Skatt · 1 / 2",
    h: "Skatten är <em>förhandlingsbar</em>.",
    prose:
      "Det förifyllda är ett förslag. Avdrag är dina pengar. ROT/RUT, ränteavdrag, jobbskatteavdrag — allt kan justeras.",
    placement: "bottom",
  },
  {
    selector: "[data-guide='skatten-summary']",
    route: "/v2/skatten",
    eye: "Skatt · 2 / 2 · pedagogik",
    h: "Skatt = <em>samhällskontrakt</em>.",
    prose:
      "Du betalar för välfärd, infrastruktur, utbildning. Men du har också rätt till varenda krona du har laglig rätt till.",
    placement: "bottom",
  },
];

const UPPDRAG_STEPS: GuideStep[] = [
  {
    selector: "[data-guide='uppdrag-list']",
    route: "/v2/uppdrag",
    eye: "Uppdrag · 1 / 3",
    h: "Uppdrag är <em>verklighetsförankring</em>.",
    prose:
      "Specifika lärar-uppgifter med deadline. \"Räkna KALP för 2,4 Mkr i Hökarängen\" — du måste hämta data från flera aktörer i appen.",
    placement: "right",
  },
  {
    selector: "[data-guide='uppdrag-list']",
    route: "/v2/uppdrag",
    eye: "Uppdrag · 2 / 3 · status",
    h: "Status räknas <em>live</em>.",
    prose:
      "De flesta uppdrag bedöms automatiskt — gör jobbet i rätt verktyg så uppdateras status. Reflektioner markerar du själv klara.",
    placement: "right",
  },
  {
    selector: "[data-guide='uppdrag-list']",
    route: "/v2/uppdrag",
    eye: "Uppdrag · 3 / 3 · feedback",
    h: "Lärare kan be om <em>retry</em>.",
    prose:
      "Om läraren ger feedback med 'request_retry' får uppdraget aktiv-status igen. Du kan då revidera och markera klart på nytt.",
    placement: "right",
  },
];

const KOMPETENS_STEPS: GuideStep[] = [
  {
    selector: "[data-guide='kompetens-detail']",
    route: "/v2/portfolio",
    eye: "Kompetens · 1 / 3",
    h: "Klicka på en <em>kompetens</em>.",
    prose:
      "Varje rad i portfolio öppnar en detalj-vy. Du ser resa B → G → F, mastery, timeline med vad du gjort.",
    placement: "bottom",
  },
  {
    selector: "[data-guide='kompetens-detail']",
    route: "/v2/portfolio",
    eye: "Kompetens · 2 / 3 · krav",
    h: "Krav är <em>transparenta</em>.",
    prose:
      "För nästa nivå listas mastery, antal kopplade moduler klara, och totalt klarade steg — med live-progress.",
    placement: "bottom",
  },
  {
    selector: "[data-guide='kompetens-detail']",
    route: "/v2/portfolio",
    eye: "Kompetens · 3 / 3 · pedagogik",
    h: "Spårbarhet är <em>respekt</em>.",
    prose:
      "Inga svarta lådor. Du kan visa portfolio + kompetens-resa för en arbetsgivare om 5 år. Ekonomilabbet följer dig.",
    placement: "bottom",
  },
];

const MODUL_STEPS: GuideStep[] = [
  {
    selector: "[data-guide='moduler-list']",
    route: "/v2/moduler",
    eye: "Moduler · 1 / 2",
    h: "Moduler är <em>scaffolding</em>.",
    prose:
      "Stegen leder genom appen. Kompetenser höjs när du gör steg klara. Läraren bedömer manuellt — inte algoritm.",
    placement: "bottom",
  },
  {
    selector: "[data-guide='moduler-list']",
    route: "/v2/moduler",
    eye: "Moduler · 2 / 2 · adaptiv",
    h: "Olika moduler för <em>olika elever</em>.",
    prose:
      "Läraren tilldelar moduler baserat på var du står. System-mallar (Bolån, ISK, Pension) finns för alla — egna moduler är klass-specifika.",
    placement: "bottom",
  },
];

// Bug #3 · Lärar-guide · för läraren när hen kommer in i v2-läget
const TEACHER_INTRO_STEPS: GuideStep[] = [
  {
    selector: ".larare-head",
    route: "/teacher/v2",
    eye: "Lärare · 1 / 6",
    h: "Välkommen till <em>lärar-dashboarden</em>.",
    prose:
      "Här ser du klassens pentagon i realtid, alla elevers status och senaste händelser. Vi börjar från toppen.",
    placement: "bottom",
  },
  {
    selector: ".larare-actions",
    route: "/teacher/v2",
    eye: "Lärare · 2 / 6",
    h: "Action-bar · <em>din verktygslåda</em>.",
    prose:
      "Skapa elev (eller hela klasser via Klasser-knappen), öppna modulbiblioteket, hantera postlådor, läs reflektioner. Time-on-task och Rubrics finns också.",
    placement: "bottom",
  },
  {
    selector: ".class-stage",
    route: "/teacher/v2",
    eye: "Lärare · 3 / 6",
    h: "Klassens <em>pentagon</em>.",
    prose:
      "Snittvärden över klassen per axel. Klicka för att flippa kortet och se topp/botten-elever per dimension. Pilar visar trend senaste veckan.",
    placement: "right",
  },
  {
    selector: ".attn-list",
    route: "/teacher/v2",
    eye: "Lärare · 4 / 6",
    h: "Action-bar · <em>vad behöver din uppmärksamhet</em>.",
    prose:
      "Olästa reflektioner, väntande lönesamtal, elever som behöver feedback. Klicka för att öppna direkt.",
    placement: "left",
  },
  {
    selector: ".mini-grid",
    route: "/teacher/v2",
    eye: "Lärare · 5 / 6",
    h: "Klassens <em>elever</em>.",
    prose:
      "Lista över alla elever med snabb-info: pentagonsnitt, level, senaste aktivitet. Klicka in för fulldetaljer + spelmotor-historik.",
    placement: "top",
  },
  {
    selector: ".v2-topbar",
    route: "/teacher/v2",
    eye: "Lärare · 6 / 6",
    h: "Topbar · <em>dina vardagsfunktioner</em>.",
    prose:
      "Notiser, AI-chatt (med dagskvot), guider, logga ut. Allt du behöver är här uppe.",
    placement: "bottom",
  },
];

export const GUIDES: Record<string, GuideDef> = {
  teacher_intro: {
    key: "teacher_intro",
    label: "Lärar-intro · v2",
    icon: "T",
    time: "6 steg · 3 min",
    sub: "Pentagon, action-bar, klass-listan, topbar",
    steps: TEACHER_INTRO_STEPS,
  },
  intro: {
    key: "intro",
    label: "Intro till plattformen",
    icon: "1",
    time: "7 steg · 3 min",
    sub: "Pentagonen, kompassen, Echo, postlådan",
    steps: INTRO_STEPS,
  },
  postladan: {
    key: "postladan",
    label: "Postlådan",
    icon: "✉",
    time: "4 steg · 2 min",
    sub: "Hur du läser, klassar, exporterar brev",
    steps: POSTLADAN_STEPS,
  },
  banken: {
    key: "banken",
    label: "Banken",
    icon: "B",
    time: "4 steg · 3 min",
    sub: "Konton, kontoutdrag, kommande fakturor, BankID",
    steps: BANKEN_STEPS,
  },
  pentagon: {
    key: "pentagon",
    label: "Pentagonen i detalj",
    icon: "▲",
    time: "3 steg · 2 min",
    sub: "Klicka på axlar, se vad som påverkar",
    steps: PENTAGON_STEPS,
  },
  maria: {
    key: "maria",
    label: "Lönesamtalet · Maria",
    icon: "M",
    time: "3 steg · 2 min",
    sub: "Förhandlingsstrategi, BATNA, smärtgräns",
    steps: MARIA_STEPS,
  },
  bankid: {
    key: "bankid",
    label: "BankID-signering",
    icon: "B",
    time: "3 steg · 3 min",
    sub: "Hur du signerar fakturor",
    steps: BANKID_STEPS,
  },
  bokforing: {
    key: "bokforing",
    label: "Bokföring · klassa",
    icon: "≡",
    time: "4 steg · 2 min",
    sub: "Regelmotor, AI-förslag, manuella val",
    steps: BOKFORING_STEPS,
  },
  budget: {
    key: "budget",
    label: "Budget · sätt din",
    icon: "▦",
    time: "2 steg · 2 min",
    sub: "Plan vs utfall, Konsumentverket",
    steps: BUDGET_STEPS,
  },
  avanza: {
    key: "avanza",
    label: "Avanza · ISK + aktier",
    icon: "$",
    time: "3 steg · 3 min",
    sub: "Fonder, schablonskatt, ränta-på-ränta",
    steps: AVANZA_STEPS,
  },
  skatt: {
    key: "skatt",
    label: "Skatteverket · deklaration",
    icon: "§",
    time: "2 steg · 2 min",
    sub: "Förifyllt, avdrag, ISK-schablon",
    steps: SKATT_STEPS,
  },
  modul: {
    key: "modul",
    label: "Moduler · pedagogik",
    icon: "✦",
    time: "2 steg · 2 min",
    sub: "Steg, kompetenshöjning, lärar-feedback",
    steps: MODUL_STEPS,
  },
  uppdrag: {
    key: "uppdrag",
    label: "Mina uppdrag",
    icon: "▷",
    time: "3 steg · 2 min",
    sub: "Lärar-tilldelade uppgifter med deadline",
    steps: UPPDRAG_STEPS,
  },
  kompetens: {
    key: "kompetens",
    label: "Kompetens-detalj",
    icon: "★",
    time: "3 steg · 2 min",
    sub: "Resa B → G → F · spårbar progression",
    steps: KOMPETENS_STEPS,
  },
};

export const GUIDE_KEYS = Object.keys(GUIDES);
