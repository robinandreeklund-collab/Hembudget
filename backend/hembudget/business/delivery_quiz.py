"""Leverans-quiz · 3 situationsfrågor istället för slider-spam.

Pedagogisk motivering: en quality_score-slider där eleven själv väljer
0-100 lär ut "ljug på enkäten". Här svarar eleven istället på 3
situationsfrågor (kvalitet/kommunikation/tid/etik/teknik) med 3
alternativ vardera. Backend räknar quality_score från svaren — eleven
kan inte fuska sig till 100 %.

Frågedesign:
  · option_good   → 100p (bra svar enligt branschpraxis)
  · option_mid    →  60p (mediocre — fungerar men sub-optimalt)
  · option_bad    →  20p (dåligt — kortsiktigt eller oetiskt)

quality_score = clamp(0, 100, mean(points) ± slump(7))

Anti-repetition: senast använda 10 question_ids per Company sparas
i Company.recent_quiz_question_ids (JSON). pick_questions() filtrerar
bort dem så eleven inte får samma fråga 2 leveranser i rad.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Optional


# === Question library · global, inga DB-rader, inga migrationer ====
#
# Schema: dict med id/category/industry/text/options/explanation.
# `industry` = None → universell. Annars match mot Company.industry_key.
# Lägg till frågor genom att appenda i listan; ID:n måste vara unika.
# Kategorier: "kvalitet" / "kommunikation" / "tid" / "etik" / "teknik".

@dataclass(frozen=True)
class QuizQuestion:
    id: int
    category: str
    industry: Optional[str]  # None = universell
    text: str
    option_good: str
    option_mid: str
    option_bad: str
    explanation: str  # Visas EFTER svar · pedagogiken


# Universella frågor (id 1-40)
_UNIVERSAL: list[QuizQuestion] = [
    QuizQuestion(
        id=1, category="kvalitet", industry=None,
        text=(
            "Du upptäcker en mindre miss precis innan leverans. "
            "Deadline är imorgon. Vad gör du?"
        ),
        option_good=(
            "Säger till kunden, levererar fix-version dagen efter "
            "deadline."
        ),
        option_mid=(
            "Levererar med missen i — det är trots allt mindre."
        ),
        option_bad=(
            "Döljer missen och hoppas kunden inte märker."
        ),
        explanation=(
            "Transparens > deadline. En kund som upptäcker dolda fel "
            "själv blir 10x argare än om du hade flaggat dem. "
            "Konsumentköplagens reklamationsrätt är 3 år för tjänster."
        ),
    ),
    QuizQuestion(
        id=2, category="kommunikation", industry=None,
        text=(
            "Kunden ber om 'en liten extra sak gratis' efter "
            "att offerten är godkänd. Vad svarar du?"
        ),
        option_good=(
            "'Det är utanför scope — jag offerera det separat.'"
        ),
        option_mid=(
            "'OK den här gången' — men man markerar att framtida "
            "ändringar kostar."
        ),
        option_bad=(
            "Säger ja på allt som beställs · scope-creep utan tillägg."
        ),
        explanation=(
            "Scope-creep är den vanligaste orsaken till att frilansare "
            "förlorar pengar. Ja-på-allt sätter precedens — kunden "
            "förväntar sig det igen, och du jobbar gratis."
        ),
    ),
    QuizQuestion(
        id=3, category="tid", industry=None,
        text=(
            "Du ser i mitten av jobbet att det tar 3 dagar längre "
            "än kalkylerat. Vad gör du?"
        ),
        option_good=(
            "Mailar kunden direkt · ny tidsplan + förklaring."
        ),
        option_mid=(
            "Knäcker över helgen så det går i tid (men du bränner ut)."
        ),
        option_bad=(
            "Säger inget — levererar 3 dgr sent + 'oväntade buggar'."
        ),
        explanation=(
            "Förseningar kostar förtroende. Tidigt-flaggat = "
            "förhandlingsläge. Sent-flaggat = klagomål. Branschens "
            "tumregel: kommunikation > deadline."
        ),
    ),
    QuizQuestion(
        id=4, category="etik", industry=None,
        text=(
            "En leverantör erbjuder 5 % kickback om du väljer deras "
            "lösning till kunden. Vad gör du?"
        ),
        option_good=(
            "Tackar nej — väljer det som är bäst för kunden."
        ),
        option_mid=(
            "Tar kickback men berättar för kunden i fakturan."
        ),
        option_bad=(
            "Tar kickback i tysthet — kunden behöver inte veta."
        ),
        explanation=(
            "Kickback utan transparens är muta enligt brottsbalken "
            "10 kap. För konsulter: en kund som upptäcker dolda "
            "kickbacks slutar omedelbart att lita på dig — och "
            "berättar för kollegor."
        ),
    ),
    QuizQuestion(
        id=5, category="kvalitet", industry=None,
        text=(
            "Kunden har inte testat det du levererat — säger 'det "
            "ser bra ut'. Vad gör du?"
        ),
        option_good=(
            "Insisterar på en gemensam genomgång där vi testar."
        ),
        option_mid=(
            "Skickar checklista de kan följa själva."
        ),
        option_bad=(
            "Tar 'ser bra ut' som godkännande — fakturerar."
        ),
        explanation=(
            "Otestade leveranser blir tvister 6 mån senare. "
            "Faktiskt godkännande > nominellt godkännande. "
            "Använd skriftlig acceptance test där det är möjligt."
        ),
    ),
    QuizQuestion(
        id=6, category="kommunikation", industry=None,
        text=(
            "Kunden mailar med en panik-fråga klockan 22:00 en lördag. "
            "Vad gör du?"
        ),
        option_good=(
            "Svarar måndag morgon med en kort bekräftelse på söndag."
        ),
        option_mid=(
            "Svarar direkt så kunden känner sig prioriterad."
        ),
        option_bad=(
            "Ignorerar tills nästa vardag, säger inget."
        ),
        explanation=(
            "Direkt-svar 22:00 sätter precedens · kunden förväntar "
            "sig det igen. Lägg in arbetstider i avtalet. Tystnad "
            "skapar oro — en kort bekräftelse räcker."
        ),
    ),
    QuizQuestion(
        id=7, category="tid", industry=None,
        text=(
            "Du har 3 jobb parallellt. Det viktigaste är försenat. "
            "Hur prioriterar du?"
        ),
        option_good=(
            "Pausa 1 jobb temporärt med tydlig kund-kommunikation."
        ),
        option_mid=(
            "Jobba 12h-dagar · ta dem alla i mål."
        ),
        option_bad=(
            "Försena alla 3 lika · ingen blir extra missnöjd."
        ),
        explanation=(
            "Parallell-deadline-stress sänker kvalitet på allt. "
            "Hellre 1 förlorad kund än 3 missnöjda. Studier visar "
            "context-switching kostar 23 min återhämtning per byte."
        ),
    ),
    QuizQuestion(
        id=8, category="etik", industry=None,
        text=(
            "Kunden ber dig kopiera material från en konkurrent: "
            "'gör likadant fast med vår logo'. Vad gör du?"
        ),
        option_good=(
            "Förklarar att copyright finns · föreslår originalarbete."
        ),
        option_mid=(
            "Inspireras av men gör tillräckligt olikt."
        ),
        option_bad=(
            "Kopierar 1:1 — kunden bär ansvaret."
        ),
        explanation=(
            "Upphovsrätt skyddar uttryck (lag 1960:729). Du som "
            "utförare är solidariskt ansvarig — inte bara kunden. "
            "Skadestånd kan landa på 10× materialets värde."
        ),
    ),
    QuizQuestion(
        id=9, category="kvalitet", industry=None,
        text=(
            "En testperson hittar en bugg du själv aldrig hittat. "
            "Vad gör du?"
        ),
        option_good=(
            "Tackar, fixar, lägger till deras case i din test-suite."
        ),
        option_mid=(
            "Fixar den enskilda buggen och går vidare."
        ),
        option_bad=(
            "Säger 'edge case' och låter den vara — sällsynt scenario."
        ),
        explanation=(
            "En upptäckt edge-case betyder att din testning missar "
            "något. Lägg till test-fallet permanent — annars dyker "
            "samma typ av bugg upp igen om 6 mån."
        ),
    ),
    QuizQuestion(
        id=10, category="kommunikation", industry=None,
        text=(
            "Kunden missförstod offerten. De trodde funktion X ingick. "
            "Vad gör du?"
        ),
        option_good=(
            "Genomgång av offerten · erbjud X som tillägg + uppdatera "
            "offert-mall så det blir tydligare framöver."
        ),
        option_mid=(
            "Inkluderar X gratis för att rädda kund-relationen."
        ),
        option_bad=(
            "Bemöter 'står inte i offerten' utan dialog."
        ),
        explanation=(
            "Missförstånd är OFTA otydlig offert · inte kund-fel. "
            "Lär av dem — uppdatera mallen. Att skylla på kunden "
            "vinner argumentet men förlorar relationen."
        ),
    ),
    QuizQuestion(
        id=11, category="tid", industry=None,
        text=(
            "Kunden vill ha veckovis status-möten. Vad gör du?"
        ),
        option_good=(
            "Skriftlig veckorapport (15 min att skriva) + möte vid "
            "behov · ingår i offerten."
        ),
        option_mid=(
            "Möten på 30 min varje fredag · ingen extra kostnad."
        ),
        option_bad=(
            "Tackar nej — tar tid från det egentliga jobbet."
        ),
        explanation=(
            "Status-möten kostar utförare 1-2h/vecka (möte + "
            "förberedelse). 1h/vecka × 12 v = 12h gratis arbete. "
            "Skriftliga rapporter skalar bättre."
        ),
    ),
    QuizQuestion(
        id=12, category="etik", industry=None,
        text=(
            "Du har jobbat klart och ser att kunden satt felaktig "
            "moms-procent på fakturamallen du skickade. Vad gör du?"
        ),
        option_good=(
            "Säger till — momslagen kräver rätt rate (25/12/6 %)."
        ),
        option_mid=(
            "Skickar fakturan ändå · kunden ansvarar för sin moms."
        ),
        option_bad=(
            "Höjer momsen så fakturan ser större ut · ingen märker."
        ),
        explanation=(
            "Felaktig moms är skattefel — Skatteverket kan kräva "
            "rätt belopp 5 år bakåt. Felaktigt höjd moms är "
            "bedrägeri. Som leverantör har du ingen moms-redovisnings"
            "ansvar för KUNDEN, men korrekt fakturering är ditt ansvar."
        ),
    ),
    QuizQuestion(
        id=13, category="kvalitet", industry=None,
        text=(
            "Kunden vill ha 'snabbast möjligt' istället för "
            "kvalitet. Vad gör du?"
        ),
        option_good=(
            "Tydligt avtal · kvalitets-trade-offs dokumenterade."
        ),
        option_mid=(
            "Levererar snabb prototyp · markerar 'beta'."
        ),
        option_bad=(
            "Slänger ihop något funktionellt utan trade-off-dialog."
        ),
        explanation=(
            "Eleven måste OFTA välja mellan snabbt/billigt/bra. "
            "Eleven kan välja 2 av 3, inte alla 3. Dokumentera "
            "valet så kunden inte 6 mån senare säger 'det här "
            "håller ju inte'."
        ),
    ),
    QuizQuestion(
        id=14, category="kommunikation", industry=None,
        text=(
            "Du måste säga nej till en kunds önskemål. Vad gör du?"
        ),
        option_good=(
            "Konkret nej + alternativt förslag som tillgodoser "
            "behovet."
        ),
        option_mid=(
            "Vagt 'det är svårt' · hoppas kunden förstår signalen."
        ),
        option_bad=(
            "Säger ja och försöker — misslyckas, levererar något "
            "halvdant."
        ),
        explanation=(
            "Vagt nej blir uppfattat som ja. Hellre tydligt nej + "
            "alternativ. 'Vi kan inte X, men Y löser samma sak' "
            "är professionell. 'Det är svårt' är amatör."
        ),
    ),
    QuizQuestion(
        id=15, category="tid", industry=None,
        text=(
            "Ett akutjobb dyker upp · kund-A är akut. Aktuella "
            "kund-B är på spår. Vad gör du?"
        ),
        option_good=(
            "Ringer B · 'akut hos annan kund · 2 dgr senare?' "
            "Förhandla."
        ),
        option_mid=(
            "Tar A på sidan · jobbar 12h-dagar."
        ),
        option_bad=(
            "Försena B utan att säga något · A först."
        ),
        explanation=(
            "Tystnad är värsta. B föredrar 2 dgr senare med "
            "förvarning över 0 dgr senare med tystnad. Kommunikation "
            "är gratis · överraskningar kostar."
        ),
    ),
    QuizQuestion(
        id=16, category="etik", industry=None,
        text=(
            "Kunden ber dig fakturera privatpersonens jobb på "
            "deras företagsfaktura så de kan dra moms. Vad gör du?"
        ),
        option_good=(
            "Nej — det är skattefusk. Förklarar att privata köp "
            "ska faktureras till privatperson."
        ),
        option_mid=(
            "Säger 'inte mitt problem' och ställer ut den."
        ),
        option_bad=(
            "Gör som kunden ber · ingen kommer märka."
        ),
        explanation=(
            "Felaktig momsavlyftning är skattebrott (skattebrottslagen "
            "§ 2). Du som utfärdare är solidariskt ansvarig. "
            "Skatteverket gör stickprov på 10 % av småbolags-fakturor."
        ),
    ),
    QuizQuestion(
        id=17, category="kvalitet", industry=None,
        text=(
            "Kunden testar din leverans · säger 'det här är inte "
            "vad jag tänkte mig'. Vad gör du?"
        ),
        option_good=(
            "Bjud in till 30 min videosamtal · skissar nytt utgångs"
            "läge."
        ),
        option_mid=(
            "Gör en revision baserat på deras skriftliga feedback."
        ),
        option_bad=(
            "'Det här är vad du beställde · läs offerten igen.'"
        ),
        explanation=(
            "Vagt missnöje är dialogen som behövs. Att möta det med "
            "offerthänvisning vinner argumentet men förlorar kunden. "
            "Levande dialog reder ut missförstånd snabbare än mejlpingpong."
        ),
    ),
    QuizQuestion(
        id=18, category="kommunikation", industry=None,
        text=(
            "Du har dåliga nyheter att berätta · kostnaden ökar "
            "20 %. Hur kommunicerar du?"
        ),
        option_good=(
            "Ring · förklara orsak · konkret nytt belopp · skriftligt "
            "samma dag."
        ),
        option_mid=(
            "Mejlar med utförlig förklaring · väntar på svar."
        ),
        option_bad=(
            "Bara ny faktura med utan förklaring · kunden får fråga."
        ),
        explanation=(
            "Dåliga nyheter via röst > text. Mejl ger kund tid att "
            "spinna upp ilska innan dialog. Ring först + skriftlig "
            "uppföljning. Aldrig 'överraskningsfaktura'."
        ),
    ),
    QuizQuestion(
        id=19, category="tid", industry=None,
        text=(
            "En kund frågar 'när är du klar?' två gånger i veckan. "
            "Vad gör du?"
        ),
        option_good=(
            "Sätter upp veckovis statusrapport så de slipper fråga."
        ),
        option_mid=(
            "Svara varje gång · det är inte mycket jobb."
        ),
        option_bad=(
            "Ignorerar för att slippa avbrott."
        ),
        explanation=(
            "Upprepade frågor signalerar oro · inte ointresse. "
            "Proaktiv status (1× per vecka) släcker oron permanent. "
            "Reaktiv = ständigt läge."
        ),
    ),
    QuizQuestion(
        id=20, category="etik", industry=None,
        text=(
            "Du upptäcker att din fakturamall har räknat fel — "
            "kunden har betalat 2 000 kr för mycket. Vad gör du?"
        ),
        option_good=(
            "Ringer · återbetalar omedelbart · kreditfaktura."
        ),
        option_mid=(
            "Räkna av nästa faktura."
        ),
        option_bad=(
            "Säger inget · det var deras kontroll-ansvar."
        ),
        explanation=(
            "Att hålla på pengar du fått av misstag = obehörig "
            "vinst (BrB 9:7). Spårbarhet finns alltid via "
            "bokföringen. Att 'glömma' nämna är förseningsräntan "
            "värd och förstör relationen."
        ),
    ),
    QuizQuestion(
        id=21, category="kvalitet", industry=None,
        text=(
            "Du har gjort jobbet · kunden vill ha en testperiod på "
            "2 veckor innan godkännande. Vad gör du?"
        ),
        option_good=(
            "Skriftligt avtal: vad räknas som 'godkänt' · testperiod "
            "OK med specifika kriterier."
        ),
        option_mid=(
            "Acceptera men sätt deadline för respons (annars auto-"
            "godkänt)."
        ),
        option_bad=(
            "Acceptera utan villkor · vänta passivt."
        ),
        explanation=(
            "Öppen testperiod utan kriterier = öppet betalningsslut. "
            "Konkreta kriterier ('alla 5 specade flöden funkar') = "
            "stängt slut. 'Auto-godkänt efter 14 dgr utan respons' "
            "är vanligt klausul."
        ),
    ),
    QuizQuestion(
        id=22, category="kommunikation", industry=None,
        text=(
            "Kunden CC:ar sin chef i alla mejl. Vad gör du?"
        ),
        option_good=(
            "Behåller proffstonen · undviker pinsamheter du inte "
            "vill att chefen ska se."
        ),
        option_mid=(
            "Frågar varför · 'är det något specifikt jag missat?'"
        ),
        option_bad=(
            "Skickar separata mejl till kunden privat · skugg-tråd."
        ),
        explanation=(
            "CC är ofta en signal om att kunden vill ha skriftlig "
            "spårbarhet · ofta för att internt visa progress. Skugg-"
            "trådar förstör tilliten när de upptäcks (och de gör de)."
        ),
    ),
    QuizQuestion(
        id=23, category="tid", industry=None,
        text=(
            "Ett jobb tar mindre tid än kalkylerat. Vad gör du?"
        ),
        option_good=(
            "Levererar i tid till samma pris · använd extratiden "
            "till kvalitetshöjning eller nästa kund."
        ),
        option_mid=(
            "Levererar tidigt · överraska kunden positivt."
        ),
        option_bad=(
            "Drar ut på det · 'det är trots allt vad de betalar för'."
        ),
        explanation=(
            "Du säljer värde · inte timmar. Att dra ut är oärligt "
            "och du tappar marginal. Tidig leverans imponerar men "
            "sätter precedens · gör det max 1 av 3 gånger."
        ),
    ),
    QuizQuestion(
        id=24, category="etik", industry=None,
        text=(
            "Du har avtal med Kund-A om exklusivitet i deras "
            "bransch i 6 mån. Kund-B (konkurrent) frågar dig direkt. "
            "Vad gör du?"
        ),
        option_good=(
            "Säger nej till B · respekterar avtalet."
        ),
        option_mid=(
            "Tar B men 'sär-håller information' · A vet inget."
        ),
        option_bad=(
            "Tar B parallellt · pengar är pengar."
        ),
        explanation=(
            "Brott mot exklusivitetsavtal är avtalsbrott · A kan "
            "kräva skadestånd. Mer praktiskt: branschen är liten · "
            "A kommer få veta. Förtroende-kapital tar 5 år att bygga, "
            "10 sek att förstöra."
        ),
    ),
    QuizQuestion(
        id=25, category="kvalitet", industry=None,
        text=(
            "Kunden ber dig 'göra det själv där det funkar bäst' · "
            "ger inga specifikationer. Vad gör du?"
        ),
        option_good=(
            "Skickar mockup/skiss FÖRE arbetet · få godkänt på "
            "inriktning."
        ),
        option_mid=(
            "Levererar din bästa gissning."
        ),
        option_bad=(
            "Hoppar på det · justerar i flera revisions-rundor."
        ),
        explanation=(
            "'Gör vad du tycker' är fälla. Eleven gör något · kunden "
            "säger 'inte så jag tänkte' · revisionsmaraton börjar. "
            "1 timme mockup-godkännande sparar 10 timmar revisions."
        ),
    ),
    QuizQuestion(
        id=26, category="kommunikation", industry=None,
        text=(
            "Du har levererat. Det går 3 veckor utan respons. "
            "Vad gör du?"
        ),
        option_good=(
            "Mejlar uppföljning · 'levererat 1 mars · finns det "
            "frågor innan jag fakturerar?'"
        ),
        option_mid=(
            "Skickar fakturan direkt · 30 dgr betal-period."
        ),
        option_bad=(
            "Väntar passivt · de hör av sig om de behöver något."
        ),
        explanation=(
            "Kund-tystnad efter leverans betyder oftast att de inte "
            "kollat. Faktura utan godkännande blir tvist. "
            "Uppföljning aktiverar ansvarstagande."
        ),
    ),
    QuizQuestion(
        id=27, category="tid", industry=None,
        text=(
            "Du blev sjuk · 2 dagars förlust. Hur kommunicerar du?"
        ),
        option_good=(
            "Mejlar samma dag · ny tidsplan + ber inte om ursäkt "
            "förlamande utan konstaterar."
        ),
        option_mid=(
            "Försöker ta igen tiden · säger inget."
        ),
        option_bad=(
            "Säger inget · hoppas det hinns ifatt."
        ),
        explanation=(
            "Sjukdom är normalt · acceptabelt. Tystnad är inte. "
            "Kunder är förstående om de informeras tidigt; sura om "
            "de upptäcker det själva när deadline missas."
        ),
    ),
    QuizQuestion(
        id=28, category="etik", industry=None,
        text=(
            "Kunden bad dig signera NDA. Senare ber en annan kund "
            "om 'reference cases'. Vad gör du?"
        ),
        option_good=(
            "Ber NDA-kunden om uttryckligt skriftligt OK INNAN du "
            "nämner dem."
        ),
        option_mid=(
            "Säger 'jobbat med en stor svensk aktör' · ingen "
            "namnger."
        ),
        option_bad=(
            "Nämner namnet · NDA gäller inte 'allmän marknadsföring'."
        ),
        explanation=(
            "NDA gäller även för marknadsföring om det inte uttryckligen "
            "tillåts. Brott mot NDA = skadestånd som kan landa på "
            "10× kontraktsvärde. Skriftligt OK är gratis."
        ),
    ),
    QuizQuestion(
        id=29, category="kvalitet", industry=None,
        text=(
            "Du levererar på tid. Kunden säger nästa dag: 'något är fel'. "
            "Vad gör du?"
        ),
        option_good=(
            "Frågar konkret vad · vill ha repro/exempel innan du "
            "fixar."
        ),
        option_mid=(
            "Frågar 'vad är fel?' · repar generellt."
        ),
        option_bad=(
            "Försöker återge själv · gissar sig till lösning."
        ),
        explanation=(
            "'Något är fel' utan konkretion är inte ett bug-report. "
            "Frågande tillbaka är professionellt och utbildande. "
            "Eleven blir bättre på att rapportera, ni båda sparar tid."
        ),
    ),
    QuizQuestion(
        id=30, category="kommunikation", industry=None,
        text=(
            "Kunden vill ha alla möten på Teams. Du föredrar Zoom. "
            "Vad gör du?"
        ),
        option_good=(
            "Använder Teams · kunden är gäst hos dig."
        ),
        option_mid=(
            "Förslår Zoom denna gång · Teams nästa."
        ),
        option_bad=(
            "Insisterar på Zoom · 'mitt verktyg, mina villkor'."
        ),
        explanation=(
            "Plattform-stridigheter är inte värda det. Kunden "
            "betalar · kunden väljer mötesverktyg. Ditt val av "
            "verktyg är frihet du har som leverantör · kund-möten "
            "är inte rätta forumet."
        ),
    ),
    QuizQuestion(
        id=31, category="tid", industry=None,
        text=(
            "Slut-spurten. Du upptäcker att det du gjort hittills "
            "går att förenkla 30 %. Vad gör du?"
        ),
        option_good=(
            "Slutför som det är · bokför insikten för nästa kund."
        ),
        option_mid=(
            "Bygger om · levererar i tid · äter förseningen."
        ),
        option_bad=(
            "Bygger om · försenar med 1 vecka."
        ),
        explanation=(
            "Sent-i-projektet refactoring kostar mer än det smakar. "
            "Levereras-version vinner. Insikten är värdefull · spara "
            "den för nästa gång."
        ),
    ),
    QuizQuestion(
        id=32, category="etik", industry=None,
        text=(
            "Kund-A säger att kund-B (deras konkurrent) hade 'samma "
            "problem' och frågar hur du löste det. Vad gör du?"
        ),
        option_good=(
            "Säger inte vilken approach · 'jag delar inte enskilda "
            "kund-lösningar'."
        ),
        option_mid=(
            "Beskriver problemet allmänt · ingen lösning."
        ),
        option_bad=(
            "Berättar exakt hur · sparar A tid."
        ),
        explanation=(
            "Indirekt brott mot tystnadsplikt. Även utan NDA är "
            "branschpraxis att inte dela konkurrenters lösningar. "
            "A skulle ha samma policy om B frågat."
        ),
    ),
    QuizQuestion(
        id=33, category="kvalitet", industry=None,
        text=(
            "Du måste välja mellan 'snabbt och fult' eller 'långsamt "
            "och vackert'. Vad gör du?"
        ),
        option_good=(
            "Frågar kunden · matar med trade-offs · de väljer."
        ),
        option_mid=(
            "Tar mellanvägen · 'OK och OK' utan att fråga."
        ),
        option_bad=(
            "Antar 'snabbt och fult' · det är vad de bad om."
        ),
        explanation=(
            "Trade-offs är kund-beslut · inte ditt. Men det betyder "
            "INTE 'fråga om allt'. Fråga om det som faktiskt har "
            "konsekvens. Kunden känner sig involverad och du är "
            "blameless."
        ),
    ),
    QuizQuestion(
        id=34, category="kommunikation", industry=None,
        text=(
            "Kunden skickar ett otydligt mejl med 7 frågor. "
            "Vad gör du?"
        ),
        option_good=(
            "Numrerar frågorna · svarar 1, 2, 3 ordnat."
        ),
        option_mid=(
            "Svarar i flytande prosa · pratar runt allt."
        ),
        option_bad=(
            "Svarar bara på 2-3 frågor · ignorerar resten."
        ),
        explanation=(
            "Numrerade svar är skanbara. Prosa-svar leder till "
            "uppföljnings-mejl ('du svarade aldrig på X'). Spar "
            "tid både dig och kunden."
        ),
    ),
    QuizQuestion(
        id=35, category="tid", industry=None,
        text=(
            "Helgen kommer · kunden mejlar 16:30 fredag · väntar "
            "svar 'snart'. Vad gör du?"
        ),
        option_good=(
            "Auto-svar · 'läser måndag · akut? Ring 070-xxx'."
        ),
        option_mid=(
            "Svarar måndag morgon utan förvarning."
        ),
        option_bad=(
            "Svarar 23:00 fredag · sätter 'jag jobbar alltid'-"
            "förväntan."
        ),
        explanation=(
            "Auto-svar kommunicerar respekt mot dig själv och "
            "förväntningar mot kunden. 24/7-tillgänglighet är inte "
            "marknadsföringsfördel · det är utbrändhets-risk."
        ),
    ),
    QuizQuestion(
        id=36, category="etik", industry=None,
        text=(
            "Du levererar och kunden ger dig en kontant tip på "
            "1 000 kr. Vad gör du?"
        ),
        option_good=(
            "Tackar · noterar i bokföringen som intäkt · skattar."
        ),
        option_mid=(
            "Tackar · skattar inte (under tabellen)."
        ),
        option_bad=(
            "Tackar · använder för privat utan att bokföra."
        ),
        explanation=(
            "All intäkt ska bokföras (Bokföringslagen). Kontant-tip "
            "är intäkt · inte gåva. Ej-bokfört = svart inkomst = "
            "skattebrott. 'Ingen kommer märka' tills bokföringen "
            "saknar källa."
        ),
    ),
    QuizQuestion(
        id=37, category="kvalitet", industry=None,
        text=(
            "Du arbetar i ett område du inte är expert på. "
            "Kunden tror du är. Vad gör du?"
        ),
        option_good=(
            "Säger ärligt · 'detta är inte min kärnkompetens · "
            "vill du ändå att jag ska försöka?'"
        ),
        option_mid=(
            "Försöker · googlar · hoppas det går."
        ),
        option_bad=(
            "Spelar expert · ingen kommer veta."
        ),
        explanation=(
            "Honesty om kompetens-gap är karriär-uppbyggande. "
            "Kunden uppskattar transparensen oftare än 'falsk "
            "expertis' som upptäcks när problem uppstår. Långsiktigt "
            "förtroende > kortvinst på det enskilda jobbet."
        ),
    ),
    QuizQuestion(
        id=38, category="kommunikation", industry=None,
        text=(
            "Kunden använder ett facktermsord du inte känner till. "
            "Vad gör du?"
        ),
        option_good=(
            "Frågar direkt · 'vad menar ni med X?'"
        ),
        option_mid=(
            "Googlar i smyg under samtalet."
        ),
        option_bad=(
            "Låtsas förstå · gissar mig fram."
        ),
        explanation=(
            "Falsk-förstå är högrisksport. Eleven slutsats blir baserad "
            "på fel grund. Att fråga signalerar engagemang · ingen "
            "tappar respekt. 'Jag vill säkerställa att vi pratar samma "
            "språk · vad menar ni med X?'"
        ),
    ),
    QuizQuestion(
        id=39, category="tid", industry=None,
        text=(
            "Du har 4 timmar kvar på dagen. 2 jobb behöver lika "
            "mycket. Hur prioriterar du?"
        ),
        option_good=(
            "Sätter timer 2h per jobb · stoppar oavsett."
        ),
        option_mid=(
            "Slutför ett · börjar nästa imorgon."
        ),
        option_bad=(
            "Hoppar mellan båda · 'multitasking'."
        ),
        explanation=(
            "Time-boxing håller WIP låg. Multitasking kostar 23 min "
            "context-switching per byte (forskning). Klart-ett-i-taget "
            "ger 2 levererade jobb istället för 2 halvfärdiga."
        ),
    ),
    QuizQuestion(
        id=40, category="etik", industry=None,
        text=(
            "En kund-anställd ber dig 'fixa något snabbt' utanför "
            "deras chefens kännedom. Vad gör du?"
        ),
        option_good=(
            "Fråga om chefen är OK med det · kommunicerar uppåt."
        ),
        option_mid=(
            "Gör det · litar på den anställdas auktoritet."
        ),
        option_bad=(
            "Gör det · skickar separat faktura till den anställda "
            "privat."
        ),
        explanation=(
            "Skugg-jobb runt chefen är riskfyllt. Om det går snett "
            "är det DU som hade ansvar att kommunicera uppåt. "
            "Kontaktperson på operativ nivå behöver godkänna med "
            "deras chef · inte du."
        ),
    ),
]


# IT-frågor (id 1001-1030)
_IT: list[QuizQuestion] = [
    QuizQuestion(
        id=1001, category="teknik", industry="webshop_it_konsult",
        text=(
            "Kunden vill ha 'enkel' inloggning · 'bara lösenord'. "
            "Vad gör du?"
        ),
        option_good=(
            "Förklara MFA · implementerar TOTP/passkeys · 5 min mer "
            "för kund."
        ),
        option_mid=(
            "Implementerar 'bara lösenord' med stark hashing."
        ),
        option_bad=(
            "Implementerar utan MFA · plain text-lösenord i DB."
        ),
        explanation=(
            "GDPR Art. 32 kräver 'lämpliga säkerhetsåtgärder' = MFA "
            "för personuppgifter. Plain text-lösen = sanktioner upp "
            "till 4 % av omsättning. 'Enkelt' är inte ett laga "
            "argument."
        ),
    ),
    QuizQuestion(
        id=1002, category="teknik", industry="webshop_it_konsult",
        text=(
            "Du upptäcker en SQL injection-bug i kundens system "
            "INNAN deploy. Vad gör du?"
        ),
        option_good=(
            "Fixa direkt · prepared statements överallt · skriv "
            "regression-test."
        ),
        option_mid=(
            "Fixa den enskilda buggen · markera 'TODO audit övriga'."
        ),
        option_bad=(
            "Deploy · fixar i nästa version."
        ),
        explanation=(
            "SQL injection = en av OWASP Top-10 sedan 2003. ALDRIG "
            "shippa med kända SQLi. Och om du hittade en finns det "
            "garanterat fler · audit hela kodbasen."
        ),
    ),
    QuizQuestion(
        id=1003, category="kvalitet", industry="webshop_it_konsult",
        text=(
            "Tester saknas i kundens kodbas. Vad gör du?"
        ),
        option_good=(
            "Skriver tester för det DU rör · markerar resten som "
            "tech-debt med kund."
        ),
        option_mid=(
            "Skriver tester för det du rör · säger inget om resten."
        ),
        option_bad=(
            "Skippar tester · 'inte mitt ansvar'."
        ),
        explanation=(
            "Du ärver INTE kundens tech-debt · men du täcker det DU "
            "lämnar. Att inte täcka det egna är slarv. Att flagga "
            "den befintliga är kund-värde · de kanske vill ha en "
            "test-uppgradering nästa."
        ),
    ),
    QuizQuestion(
        id=1004, category="teknik", industry="webshop_it_konsult",
        text=(
            "Kunden vill köra på production direkt utan staging. "
            "Vad gör du?"
        ),
        option_good=(
            "Kräver minst en staging-deploy först · sätter upp om "
            "den saknas."
        ),
        option_mid=(
            "Kör med feature-flag · går att rulla tillbaka snabbt."
        ),
        option_bad=(
            "Kör · 'kunden vet bäst'."
        ),
        explanation=(
            "Direkt-prod är amatör-deploy. Down-time eller data-"
            "förlust drabbar slutkunder, inte din uppdragsgivare. "
            "Du har ansvar att skydda mot det · ofta måste leverantör "
            "säga nej till dåliga arbetssätt."
        ),
    ),
    QuizQuestion(
        id=1005, category="etik", industry="webshop_it_konsult",
        text=(
            "Kunden ber dig kopiera 1000 e-postadresser från "
            "deras CRM och 'maila erbjudande'. Vad gör du?"
        ),
        option_good=(
            "Kontroll: GDPR-samtycke per kontakt · annars nej."
        ),
        option_mid=(
            "Mailar med opt-out i botten."
        ),
        option_bad=(
            "Mailar · 'kunden bär ansvaret'."
        ),
        explanation=(
            "GDPR § 6 kräver legal grund för marknadsföring. "
            "'Hade ditt mejl i CRM:et' är inte samtycke. Du som "
            "utförare är personuppgiftsbiträde · sanktion 4 % av "
            "omsättning gäller även dig."
        ),
    ),
    QuizQuestion(
        id=1006, category="teknik", industry="webshop_it_konsult",
        text=(
            "API-nycklar finns hårdkodade i kundens kod. Vad gör du?"
        ),
        option_good=(
            "Flytta till env-vars/secret manager · rotera nycklarna."
        ),
        option_mid=(
            "Flytta till .env · säg åt kunden att rotera."
        ),
        option_bad=(
            "Lämnar · 'inte mitt jobb'."
        ),
        explanation=(
            "Hårdkodade nycklar i git-history är permanenta. Även "
            "efter borttagning lever de i historik · måste roteras. "
            "GitHub scannar publika repos · ditt API-konto kan "
            "låsas på 5 min om läckta."
        ),
    ),
    QuizQuestion(
        id=1007, category="kommunikation", industry="webshop_it_konsult",
        text=(
            "Kunden förstår inte tekniska termer. Vad gör du?"
        ),
        option_good=(
            "Översätter till affärsspråk · 'X betyder för er Y kr/mån'."
        ),
        option_mid=(
            "Förenklar tekniskt · 'tänk på det som...'"
        ),
        option_bad=(
            "Pratar tekniskt · 'de får lära sig'."
        ),
        explanation=(
            "Affärs-impact > teknik-detaljer för kunder. Översätt "
            "alltid: 'denna refactor sparar 5h support per månad' "
            "eller 'denna säkerhetsfix förebygger en incident som "
            "skulle kosta 100k att städa'."
        ),
    ),
    QuizQuestion(
        id=1008, category="kvalitet", industry="webshop_it_konsult",
        text=(
            "Din nya kod fungerar lokalt men inte i prod. Vad gör du?"
        ),
        option_good=(
            "Reproducerar i staging · diffar miljöer · fixar root "
            "cause."
        ),
        option_mid=(
            "Lägger till felsökning-loggar · ser vad som händer."
        ),
        option_bad=(
            "Trial-and-error i prod · push push push."
        ),
        explanation=(
            "'Funkar i min maskin' = okänd dependency mellan miljöer. "
            "Trial-and-error i prod är destruktivt. Reproducera "
            "lokalt, sedan staging, sedan prod. Annars hittar du "
            "aldrig root cause."
        ),
    ),
    QuizQuestion(
        id=1009, category="teknik", industry="webshop_it_konsult",
        text=(
            "Kunden ska skicka kreditkortsuppgifter via mejl. "
            "Vad gör du?"
        ),
        option_good=(
            "STOPP · PCI-DSS förbjuder · skickar säker länk istället."
        ),
        option_mid=(
            "Säg åt dem att kryptera mejlet."
        ),
        option_bad=(
            "Tar emot · raderar efter användning."
        ),
        explanation=(
            "PCI-DSS § 4 förbjuder okrypterad transmission av kort-"
            "data. Mejl är okrypterat. Att TA EMOT är brott · även "
            "om kunden skickade. Säker portal/Stripe Links är 5 min "
            "att sätta upp."
        ),
    ),
    QuizQuestion(
        id=1010, category="kommunikation", industry="webshop_it_konsult",
        text=(
            "Kunden eskalerar 'sajten är nere!' när det är en "
            "småfix. Vad gör du?"
        ),
        option_good=(
            "Bekräftar lugnt · 'jag tittar nu' · återkopplar inom 15 "
            "min med status."
        ),
        option_mid=(
            "Förklarar att det inte är så stort."
        ),
        option_bad=(
            "Reagerar med samma panik · stress-fixar."
        ),
        explanation=(
            "Lugn vs panik signalerar professionalism. Statusupp"
            "datering var 15:e min släcker oro även om fixen tar "
            "längre. Att möta panik med panik fördubblar stressen."
        ),
    ),
    QuizQuestion(
        id=1011, category="kvalitet", industry="webshop_it_konsult",
        text=(
            "Du upptäcker en bättre arkitektur halvvägs in. Vad gör du?"
        ),
        option_good=(
            "Slutför som det är · bokför 'arkitektur-uppgradering "
            "v2' som potentiellt nästa-jobb."
        ),
        option_mid=(
            "Bygger om · eat the cost."
        ),
        option_bad=(
            "Bygger om · försenar."
        ),
        explanation=(
            "Halv-vägs-omarkitektur kostar mer än ger. Slutleverans "
            "med dokumenterade insikter är värdefulla artefakter "
            "för framtida jobb. Lärande till nästa kund · inte denna."
        ),
    ),
    QuizQuestion(
        id=1012, category="teknik", industry="webshop_it_konsult",
        text=(
            "Logfilen i prod är 50 GB. Kunden frågar 'kan vi ta "
            "bort det?'. Vad gör du?"
        ),
        option_good=(
            "Sätter upp log-rotation · sparar 30 dgr · raderar äldre."
        ),
        option_mid=(
            "Manuell rensning denna gång."
        ),
        option_bad=(
            "rm -rf · klart."
        ),
        explanation=(
            "Loggar är audit-trail · GDPR + bokföringslag kräver "
            "spårbarhet. Också: senaste 30 dgr av loggar är debug-"
            "guld vid incident. Raderar du allt blir nästa bug "
            "100× svårare. Log-rotation är standard."
        ),
    ),
    QuizQuestion(
        id=1013, category="etik", industry="webshop_it_konsult",
        text=(
            "Kunden ber dig 'lägga till en backdoor admin-konto "
            "ifall vi behöver det'. Vad gör du?"
        ),
        option_good=(
            "Nej · backdoors är säkerhetsproblem. Sätt upp riktig "
            "break-glass-procedur via deras IT."
        ),
        option_mid=(
            "Skapa konto med tidsbegränsning."
        ),
        option_bad=(
            "Skapa · de är trots allt ägaren."
        ),
        explanation=(
            "Backdoors blir attack-vektorer. Om dina inloggnings"
            "uppgifter läcker har angripare en väg in. Auditerade "
            "break-glass-konton via riktiga IAM-system är rätt sätt. "
            "Backdoors är amatör-praktik och bryter mot SOC-2/ISO27001."
        ),
    ),
    QuizQuestion(
        id=1014, category="tid", industry="webshop_it_konsult",
        text=(
            "Du har en bug-fix som kräver 2h. Kunden vill ha "
            "förklaring varför. Vad gör du?"
        ),
        option_good=(
            "Skriftlig kort förklaring + tidslog · 5 min."
        ),
        option_mid=(
            "30-min videosamtal."
        ),
        option_bad=(
            "Vagt 'det är komplext'."
        ),
        explanation=(
            "Skriftlig förklaring är arkiverbar referens · video är "
            "engångskonsumtion. 'Komplext' är bortförklaring. Ärlig "
            "kort förklaring bygger förtroende långsiktigt."
        ),
    ),
    QuizQuestion(
        id=1015, category="teknik", industry="webshop_it_konsult",
        text=(
            "Kunden sparar GDPR-känslig data utan kryptering. "
            "Vad gör du?"
        ),
        option_good=(
            "Implementerar kryptering at-rest · uppdaterar Personuppg"
            "iftspolicy · informerar."
        ),
        option_mid=(
            "Säger åt kunden att åtgärda."
        ),
        option_bad=(
            "Lämnar · 'inte mitt ansvar'."
        ),
        explanation=(
            "Personuppgiftsbiträdes-ansvaret innebär aktiv plikt att "
            "påtala. Tystnad om GDPR-läckor är medverkan. "
            "Sanktionsavgift kan landa på dig som biträde."
        ),
    ),
    QuizQuestion(
        id=1016, category="kvalitet", industry="webshop_it_konsult",
        text=(
            "Du ska skriva docs. Vad är 'tillräckligt'?"
        ),
        option_good=(
            "Setup + 3 vanliga felsökningar + arkitekturskiss."
        ),
        option_mid=(
            "README med en setup-paragraph."
        ),
        option_bad=(
            "Inline kommentarer i kod räcker."
        ),
        explanation=(
            "Docs ska klara av 'utvecklare i 2027 som aldrig sett "
            "koden'. Setup + felsökning + skiss = de 3 sakerna man "
            "ALDRIG hittar i koden själv. Inline-kommentarer är "
            "supplement, inte ersättning."
        ),
    ),
    QuizQuestion(
        id=1017, category="kommunikation", industry="webshop_it_konsult",
        text=(
            "Kunden vill ha statusrapport · vad ska du inkludera?"
        ),
        option_good=(
            "Klart sedan sist · pågår nu · risker · nästa vecka."
        ),
        option_mid=(
            "'Allt går bra · är nästan klar.'"
        ),
        option_bad=(
            "Lång loggbok med all detaljer · 'läs själv'."
        ),
        explanation=(
            "Klart-pågår-risker-nästa är industristandard (ATC). "
            "Vag positivism döljer problem · överdetaljerad logg "
            "läser ingen. 4 punkter, en sida, varje vecka."
        ),
    ),
    QuizQuestion(
        id=1018, category="teknik", industry="webshop_it_konsult",
        text=(
            "Du behöver göra en migration på en levande databas. "
            "Vad gör du?"
        ),
        option_good=(
            "Backup först · testa migration på kopia · kör live "
            "med transaktion + rollback-plan."
        ),
        option_mid=(
            "Backup · kör direkt."
        ),
        option_bad=(
            "Kör direkt · backup tar tid."
        ),
        explanation=(
            "Live-migration utan backup är karriärs-slut om något "
            "går snett. Test på kopia avslöjar 90 % av problemen. "
            "Transaktion + rollback-plan = kunde rulla tillbaka på "
            "60 sek. Branschnorm."
        ),
    ),
    QuizQuestion(
        id=1019, category="etik", industry="webshop_it_konsult",
        text=(
            "Kund-anställd har sagt upp sig · ber dig 'kopiera "
            "deras kod' till sin privata GitHub. Vad gör du?"
        ),
        option_good=(
            "Nej · kod tillhör arbetsgivaren · LAS § 38."
        ),
        option_mid=(
            "Bara open source-delarna."
        ),
        option_bad=(
            "Hjälper till · 'eleven har skrivit den, eleven äger'."
        ),
        explanation=(
            "I Sverige tillhör arbets-resultat arbetsgivaren (LAS "
            "§ 38, oklar för rena uppfinningar men kod är arbets-"
            "resultat). Hjälpa anställd kopiera är medverkan till "
            "stöld. Risk för skadestånd från ex-arbetsgivaren."
        ),
    ),
    QuizQuestion(
        id=1020, category="teknik", industry="webshop_it_konsult",
        text=(
            "Kunden ber dig integrera mot en deprecated API. "
            "Vad gör du?"
        ),
        option_good=(
            "Föreslå nyare API · om kund kvarstår skriftligt risk."
        ),
        option_mid=(
            "Bygg på deprecated · markera 'TODO migrate'."
        ),
        option_bad=(
            "Bygg utan att nämna · de märker när det slutar funka."
        ),
        explanation=(
            "Deprecated APIs slutar funka 6-18 mån efter deprecation. "
            "Skriftligt 'jag avråder · ni accepterar risken' är "
            "din försäkring. Tystnad gör DIG ansvarig när det "
            "slutar funka."
        ),
    ),
    QuizQuestion(
        id=1021, category="kvalitet", industry="webshop_it_konsult",
        text=(
            "Du levererar och kunden vill ha 'kommentarer på "
            "varje rad'. Vad gör du?"
        ),
        option_good=(
            "Förklara att det är anti-pattern · självförklarande "
            "namn istället · skriv 'why' inte 'what'."
        ),
        option_mid=(
            "Lägger till kommentarer · slösar tid."
        ),
        option_bad=(
            "Vägrar · 'jag gör som jag vill'."
        ),
        explanation=(
            "Branschstandard sedan 2010-talet: kommentera 'why' "
            "inte 'what'. Variabel-namn ska förklara what. För-"
            "många-kommentarer åldras snabbare än kod och blir "
            "felaktiga. Utbilda kunden · ändra inte din kvalitet."
        ),
    ),
    QuizQuestion(
        id=1022, category="kommunikation", industry="webshop_it_konsult",
        text=(
            "Kunden ber dig joina deras Slack permanent. Vad gör du?"
        ),
        option_good=(
            "Joina som gäst · checkar 1× per dag · sätter förväntan."
        ),
        option_mid=(
            "Joinar · är reaktiv på allt."
        ),
        option_bad=(
            "Joinar inte · 'mejl är bättre'."
        ),
        explanation=(
            "Slack-närvaro är förväntning på real-time-svar. Sätt "
            "förväntan tidigt: 'jag kollar 1× per dag, akut = ring'. "
            "Annars blir du DERAS support-resurs gratis. Att inte "
            "joina alls är ofta inte realistiskt."
        ),
    ),
    QuizQuestion(
        id=1023, category="teknik", industry="webshop_it_konsult",
        text=(
            "Kunden vill att du utvecklar i deras Microsoft Office-"
            "miljö men du föredrar VS Code/Linux. Vad gör du?"
        ),
        option_good=(
            "Använd vad som ger bästa output · meddela vilka verktyg "
            "du jobbar i (öppen för deras stack om motiverat)."
        ),
        option_mid=(
            "Lär dig deras verktyg · även om långsammare."
        ),
        option_bad=(
            "Insisterar på dina verktyg · ignorerar deras frågor."
        ),
        explanation=(
            "Verktygsval är leverantörsfrihet · output är vad som "
            "betalas. Men kommunikation om varför du valt en stack "
            "är värd att ge · ofta finns deras motiv (säkerhet) som "
            "du behöver respektera."
        ),
    ),
    QuizQuestion(
        id=1024, category="etik", industry="webshop_it_konsult",
        text=(
            "Kunden ber dig 'skrapa data från konkurrentens sajt "
            "varje natt'. Vad gör du?"
        ),
        option_good=(
            "Kontroll: ToS + GDPR + databasdirektivet · ofta nej."
        ),
        option_mid=(
            "Använder publika API · säkrare väg."
        ),
        option_bad=(
            "Skrapar · 'allmän information'."
        ),
        explanation=(
            "Web-scraping mot ToS = avtalsbrott + databasdirektivet "
            "(96/9/EG) skyddar systematisk insamling. Konkurrenten "
            "kan stämma DIG som utförare · inte bara kunden. Risk-"
            "ekvation är obalanserad."
        ),
    ),
    QuizQuestion(
        id=1025, category="kvalitet", industry="webshop_it_konsult",
        text=(
            "Du ska deploy:a fredag 16:00. Vad gör du?"
        ),
        option_good=(
            "Senare-flytt till måndag · 'no friday deploys' är "
            "branschvisdom."
        ),
        option_mid=(
            "Deploya 14:00 · ha tid att fixa innan 17:00."
        ),
        option_bad=(
            "Deploya 16:30 · ut från jobbet 17."
        ),
        explanation=(
            "Friday-deploys = on-call hela helgen om något brister. "
            "Branschstandard sedan 2015: deploy mån-tor förmiddag. "
            "Kund som kräver fredag visar omogen process · push back."
        ),
    ),
    QuizQuestion(
        id=1026, category="teknik", industry="webshop_it_konsult",
        text=(
            "Du upptäcker att kundens app:s lösenord är hashade "
            "med MD5. Vad gör du?"
        ),
        option_good=(
            "Migrera till bcrypt/argon2 · informera om risk + "
            "kostnad. Kanske obligatorisk uppdatering."
        ),
        option_mid=(
            "Föreslå migration men gör inget aktivt."
        ),
        option_bad=(
            "Lämnar · 'fungerar ju'."
        ),
        explanation=(
            "MD5 är cryptobruten sedan 2004 · NIST har deprecated "
            "den för password storage. GDPR Art. 32 kan tolkas som "
            "att MD5 = otillräcklig säkerhet. Påtala är din skyldighet."
        ),
    ),
    QuizQuestion(
        id=1027, category="kommunikation", industry="webshop_it_konsult",
        text=(
            "Kunden frågar 'kan AI göra det här jobbet?'. Vad gör du?"
        ),
        option_good=(
            "Ärligt: 'AI kan förbereda 60 % · jag verifierar/anpassar "
            "40 % · netto 30-50 % billigare'."
        ),
        option_mid=(
            "'Nej, AI klarar inte det' (för att skydda jobbet)."
        ),
        option_bad=(
            "'Ja det löser AI helt' (oärlig hype)."
        ),
        explanation=(
            "AI-frågan är 2025-realiteten. Ärlighet om vad AI "
            "ersätter och vad du tillför bygger förtroende. Skydda-"
            "jobbet-genom-att-ljuga är kortsiktigt. Anpassad samar"
            "betsmodell (du + AI) är den vinnande affärsmodellen."
        ),
    ),
    QuizQuestion(
        id=1028, category="tid", industry="webshop_it_konsult",
        text=(
            "Kunden vill att du sitter på deras kontor. Vad gör du?"
        ),
        option_good=(
            "Förhandla hybrid · 1 dag/v hos dem + 4 dagar fjärr · "
            "tillägg om alla 5 dagar krävs."
        ),
        option_mid=(
            "Sittar där · samma timpris."
        ),
        option_bad=(
            "Vägrar · 'jag jobbar fjärr alltid'."
        ),
        explanation=(
            "On-site = restid + lägre fokus + svårare flow-state. "
            "Branschpraxis: tillägg ~20 % för on-site. Om kunden "
            "kräver 100 % on-site är det egentligen tjänst (an"
            "ställning) inte konsultupp drag."
        ),
    ),
    QuizQuestion(
        id=1029, category="etik", industry="webshop_it_konsult",
        text=(
            "Du har skrivit cool kod för kund-A. Kund-B (i annan "
            "bransch) skulle gynnas av samma. Vad gör du?"
        ),
        option_good=(
            "Återanvänd MED kund-A:s OK · annars skriv om eller "
            "köp licens."
        ),
        option_mid=(
            "Skriv om så det 'är lite olikt'."
        ),
        option_bad=(
            "Använd 1:1 · 'jag skrev den, jag äger'."
        ),
        explanation=(
            "Default i svenska konsultkontrakt: kunden äger arbets-"
            "resultatet. Att återanvända utan OK är upphovsrättsbrott. "
            "Vissa kontrakt ger dig 'rights to reuse' · läs alltid "
            "innan du återanvänder."
        ),
    ),
    QuizQuestion(
        id=1030, category="teknik", industry="webshop_it_konsult",
        text=(
            "Kunden kör databas-backup varje vecka. Vad föreslår du?"
        ),
        option_good=(
            "Daily backup + restore-test 1× per kvartal · annars "
            "vet ni inte om de funkar."
        ),
        option_mid=(
            "Daily backup."
        ),
        option_bad=(
            "Veckovis funkar · 'minskar lagring'."
        ),
        explanation=(
            "Branschstandard: daily backup + dokumenterat restore-"
            "test. Otestade backuper är skroppe. Vid kris upptäcker "
            "du att backup:erna är korrupta · 1 vecka data borta. "
            "Storage är billigt · datadöd är dyrt."
        ),
    ),
]


_ALL_QUESTIONS: list[QuizQuestion] = _UNIVERSAL + _IT
_BY_ID: dict[int, QuizQuestion] = {q.id: q for q in _ALL_QUESTIONS}


# === Selection + scoring ============================================


def pick_questions(
    *,
    industry_key: Optional[str],
    recent_ids: list[int],
    rng: Optional[random.Random] = None,
) -> list[QuizQuestion]:
    """Plocka 3 unika frågor för en leverans.

    Logik:
    1. Filtrera ut frågor som finns i recent_ids (anti-repetition)
    2. Vikta industry-matchande frågor 2× mot universella
    3. Slumpa 3 från olika kategorier om möjligt (för variation)

    `recent_ids`: senaste 10 fråge-id eleven sett. Hjälpsamt för att
    undvika "jag svarade på exakt denna fråga senaste leveransen".
    Skickas typiskt från Company.recent_quiz_question_ids.
    """
    rng = rng or random.Random()
    candidates = [q for q in _ALL_QUESTIONS if q.id not in set(recent_ids)]

    # Säkerhet om recent_ids täcker hela biblioteket — då återställer vi
    if len(candidates) < 3:
        candidates = list(_ALL_QUESTIONS)

    # Industry-bias: matchande frågor får 2× vikt, universella 1×
    def _weight(q: QuizQuestion) -> float:
        if industry_key and q.industry == industry_key:
            return 2.0
        if q.industry is None:
            return 1.0
        return 0.3  # andra industries · liten chans men inte noll

    # Försök få variation över kategorier · plocka 3 från olika
    chosen: list[QuizQuestion] = []
    used_categories: set[str] = set()
    pool = list(candidates)

    while len(chosen) < 3 and pool:
        # Vikta poolen
        weights = [_weight(q) for q in pool]
        # Boosta okategoriserade kategorier ×1.5 så vi blandar
        for i, q in enumerate(pool):
            if q.category not in used_categories:
                weights[i] *= 1.5

        total = sum(weights)
        if total <= 0:
            break
        pick = rng.random() * total
        running = 0.0
        for i, w in enumerate(weights):
            running += w
            if pick <= running:
                chosen.append(pool[i])
                used_categories.add(pool[i].category)
                pool.pop(i)
                break

    return chosen[:3]


def score_answers(answers: list[str]) -> int:
    """Räkna ut quality_score (0-100) från en lista svar.

    `answers`: list med exakt 3 strängar, var och en "good"/"mid"/"bad".
    Mappning per-svar:
        good → 100, mid → 60, bad → 20
    Slutscore = mean ± slump(±7) · clampad till 0-100.

    Mean av (good, good, good) = 100 → ~93-100
    Mean av (good, mid, bad)   = 60  → ~53-67
    Mean av (bad, bad, bad)    = 20  → ~13-27
    """
    if len(answers) != 3:
        raise ValueError("score_answers kräver exakt 3 svar")
    points_map = {"good": 100, "mid": 60, "bad": 20}
    points = []
    for a in answers:
        if a not in points_map:
            raise ValueError(
                f"Okänt svar '{a}' · måste vara good/mid/bad",
            )
        points.append(points_map[a])
    base = sum(points) / 3
    jitter = random.randint(-7, 7)
    return max(0, min(100, int(round(base + jitter))))


def get_question(qid: int) -> Optional[QuizQuestion]:
    return _BY_ID.get(qid)


def update_recent_ids(
    existing: Optional[list[int]],
    new_ids: list[int],
    *,
    keep_n: int = 10,
) -> list[int]:
    """Lägg till new_ids först, behåll max keep_n totalt.
    Idempotent — om samma id finns flera gånger dedupliceras.
    """
    combined = list(new_ids)
    for x in (existing or []):
        if x not in combined:
            combined.append(x)
    return combined[:keep_n]
