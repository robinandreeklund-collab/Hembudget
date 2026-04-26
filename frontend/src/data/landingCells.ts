// Delad celldata för Variant C — tip/long/example/trains per cell.
// Konsumeras av LandingVariantC.tsx för hover-tooltip och modal.

export type CellCat = "grund" | "fordj" | "expert" | "konto" | "risk" | "prof";

export type CellInfo = {
  n: number;
  sym: string;
  name: string;
  desc: string;
  cat: CellCat;
  tip: string;
  long: string;
  example: string;
  trains: string;
};

export const CELL_INFO: CellInfo[] = [
  { n: 1, sym: "Lö", name: "Lön", desc: "brutto", cat: "grund",
    tip: "Lön = bruttolön minus skatt = det du faktiskt får",
    long: "Bruttolön är vad du tjänar på pappret. Nettolön är vad som landar på kontot efter att skatten dragits. Skillnaden är ofta 25–35 % beroende på kommun och inkomstnivå.",
    example: "Anna har en bruttolön på 32 000 kr. Efter ~28 % skatt får hon ut 23 040 kr i handen den 25:e varje månad.",
    trains: "Steg 2 i Din första månad — eleven läser sin egen lönespec." },
  { n: 2, sym: "Sk", name: "Skatt", desc: "netto", cat: "grund",
    tip: "Skatt = din andel av samhället",
    long: "Inkomstskatt består av kommunalskatt (~30 %) och statlig skatt (på inkomster över ~615 000 kr/år). Den dras direkt från lönen och betalar för skola, vård, vägar och allt offentligt.",
    example: "Av Annas 32 000 kr går ~9 000 kr till kommunal- och statsskatt — varav merparten till hennes hemkommun.",
    trains: "Steg 3 i Din första månad — eleven jämför kommun-skattesatser." },
  { n: 3, sym: "Bu", name: "Budget", desc: "månad", cat: "grund",
    tip: "Budget = planen innan pengarna försvinner",
    long: "En budget är en plan över vad pengarna SKA gå till. Inkomster minus utgifter ska gå plus. Konsumentverkets siffror är ett bra startläge.",
    example: "Anna budgeterar 4 000 kr för mat, 1 500 kr för nöje, 800 kr för hygien. Totalt 6 300 kr — verkligheten avgör om det räcker.",
    trains: "Steg 5–6 i Din första månad — eleven sätter sin egen budget och jämför mot Konsumentverkets riktvärden." },
  { n: 4, sym: "Ku", name: "Kontoutdr.", desc: "läsa", cat: "fordj",
    tip: "Kontoutdrag = bankens dagbok över dig",
    long: "Kontoutdraget visar varje krona in och ut. Det är facit för månaden — där ser du om du höll budgeten eller inte. Att läsa ett kontoutdrag är en grundläggande färdighet som många unga aldrig övat på.",
    example: "Annas november-utdrag har 47 rader. Lön +23 040, hyra −9 200, ICA Maxi 14 ggr för totalt 4 120 kr.",
    trains: "Steg 4 i Din första månad — eleven importerar PDF:en läraren genererat." },
  { n: 5, sym: "Ka", name: "Kalkyl", desc: "verklig.", cat: "fordj",
    tip: "Kalkyl = budget möter verklighet",
    long: "Att räkna efter månaden — vad blev det egentligen? Skillnaden mellan budget och utfall visar var planen håller och var den behöver justeras inför nästa månad.",
    example: "Anna budgeterade 4 000 kr för mat. Faktiskt: 4 870 kr. +870 kr över. Nästa månad: höj budgeten eller skär i restaurangbesök.",
    trains: "Modulen Budget möter verklighet — eleven kalkylerar månads-diff." },
  { n: 6, sym: "Sa", name: "Saldo", desc: "koll", cat: "expert",
    tip: "Saldo = sanningen just nu",
    long: "Saldot är vad som faktiskt finns på kontot — inte vad du \"tror\" du har. Att kolla saldot innan ett köp är en grundvana som hindrar övertrasseringar.",
    example: "På Annas konto den 15:e: 8 880 kr. Hyran nästa månad är 9 200. Hon behöver vänta med Black Friday.",
    trains: "Visas live i Dashboard — eleven ser saldot uppdateras vid varje import." },
  { n: 7, sym: "Sp", name: "Sparande", desc: "mål", cat: "konto",
    tip: "Sparande = framtida du tackar nuvarande du",
    long: "Att sätta undan pengar regelbundet är skillnaden mellan ekonomisk frihet och stress. Tumregeln 10 % av inkomsten är en bra start — bygg först en buffert på 2–3 månadslöner, sedan långsiktigt.",
    example: "Anna sparar 1 500 kr/mån. På ett år har hon 18 000 kr — räcker för en oväntad räkning eller en bilreparation.",
    trains: "Modulen Buffert & sparmål — eleven sätter ett konkret mål och spårar månadsvis." },
  { n: 8, sym: "Hu", name: "Hushåll", desc: "delat", cat: "risk",
    tip: "Hushållskostnader = vad det faktiskt kostar att leva",
    long: "Konsumentverket räknar varje år ut vad det kostar att leva med rimlig levnadsstandard — mat, kläder, hygien, fritid. För en ensamboende vuxen 2026: ~5 700 kr/mån (utan boendekostnad).",
    example: "Anna får ut 23 040 kr. Konsumentverket säger 5 700 kr. Hon har 17 340 kr till hyra, sparande och nöje.",
    trains: "Steg 6 i Din första månad — eleven jämför sin egen budget mot Konsumentverkets nivå." },
];
