"""Svenska default-kategorier och basregler för kategorisering."""

DEFAULT_CATEGORIES: list[tuple[str, str | None, str | None]] = [
    # (name, parent_name, icon)
    ("Inkomst", None, "arrow-down"),
    ("Lön", "Inkomst", None),
    ("Swish in", "Inkomst", None),
    ("Återbetalning", "Inkomst", None),
    ("Swish ut", None, "arrow-up-right"),
    ("Boende", None, "home"),
    ("Bolåneränta", "Boende", None),
    ("Amortering", "Boende", None),
    ("Hyra", "Boende", None),
    ("El", "Boende", None),
    ("Internet", "Boende", None),
    ("Hemförsäkring", "Boende", None),
    ("Vatten/Avgift", "Boende", None),
    ("Mat", None, "shopping-cart"),
    ("Livsmedel", "Mat", None),
    ("Restaurang", "Mat", None),
    ("Café", "Mat", None),
    ("Take-away", "Mat", None),
    ("Transport", None, "car"),
    ("Kollektivtrafik", "Transport", None),
    ("Drivmedel", "Transport", None),
    ("Parkering", "Transport", None),
    ("Bilservice", "Transport", None),
    ("Taxi/Uber", "Transport", None),
    ("Nöje", None, "film"),
    ("Streaming", "Nöje", None),
    ("Biograf/Konsert", "Nöje", None),
    ("Spel", "Nöje", None),
    ("Böcker/Media", "Nöje", None),
    ("Hälsa", None, "heart"),
    ("Apotek", "Hälsa", None),
    ("Sjukvård", "Hälsa", None),
    ("Träning/Gym", "Hälsa", None),
    ("Kläder & Skor", None, "shirt"),
    ("Barn", None, "baby"),
    ("Förskola/Skola", "Barn", None),
    ("Leksaker", "Barn", None),
    ("Kläder barn", "Barn", None),
    ("Resor", None, "plane"),
    ("Flyg", "Resor", None),
    ("Hotell", "Resor", None),
    ("Semester", "Resor", None),
    ("Prenumerationer", None, "repeat"),
    ("Mobil", "Prenumerationer", None),
    ("Hemelektronik", None, None),
    ("Hem & Hushåll", None, "package"),
    ("Presenter", None, "gift"),
    ("Sparande/Investering", None, "trending-up"),
    ("ISK-insättning", "Sparande/Investering", None),
    ("Fondköp", "Sparande/Investering", None),
    ("Aktieköp", "Sparande/Investering", None),
    ("Pension", "Sparande/Investering", None),
    ("Överföring", None, "exchange"),
    ("Kontantuttag", None, "dollar-sign"),
    ("Avgifter & Ränta", None, "percent"),
    ("Skatt", None, "clipboard"),
    ("Försäkring", None, "shield"),
    ("Bilförsäkring", "Försäkring", None),
    ("Livförsäkring", "Försäkring", None),
    ("Övrigt", None, "help-circle"),
]


SEED_RULES: list[tuple[str, str, int]] = [
    # (pattern_substring_lowercase, category_name, priority)
    # Livsmedel
    ("ica", "Livsmedel", 100),
    ("coop", "Livsmedel", 100),
    ("willys", "Livsmedel", 100),
    ("lidl", "Livsmedel", 100),
    ("hemköp", "Livsmedel", 100),
    ("city gross", "Livsmedel", 100),
    ("mathem", "Livsmedel", 100),
    ("hjogotten", "Livsmedel", 100),
    ("broderna brandt", "Livsmedel", 100),
    ("bröderna brandt", "Livsmedel", 100),
    ("vete & rag", "Livsmedel", 100),
    ("tempo", "Livsmedel", 100),
    # Restaurang / Café
    ("mcdonald", "Restaurang", 100),
    ("max ", "Restaurang", 100),
    ("burger king", "Restaurang", 100),
    ("sushi", "Restaurang", 100),
    ("pizza", "Restaurang", 100),
    ("espresso house", "Café", 100),
    ("wayne", "Café", 100),
    ("foodora", "Take-away", 100),
    ("wolt", "Take-away", 100),
    # Restaurang/café (lokalt)
    ("korkissebastian", "Restaurang", 100),
    ("jumpyard", "Nöje", 100),

    # Transport
    ("sl ab", "Kollektivtrafik", 100),
    ("storstockholms lokaltrafik", "Kollektivtrafik", 100),
    ("sj ab", "Kollektivtrafik", 100),
    ("västtrafik", "Kollektivtrafik", 100),
    ("skånetrafiken", "Kollektivtrafik", 100),
    ("circle k", "Drivmedel", 100),
    ("okq8", "Drivmedel", 100),
    ("preem", "Drivmedel", 100),
    ("ingo", "Drivmedel", 100),
    ("shell", "Drivmedel", 100),
    ("st1", "Drivmedel", 100),
    ("macken i hjo", "Drivmedel", 100),
    ("macken ", "Drivmedel", 90),
    ("uber", "Taxi/Uber", 100),
    ("bolt.eu", "Taxi/Uber", 100),
    ("taxi stockholm", "Taxi/Uber", 100),
    ("easypark", "Parkering", 100),
    ("parkster", "Parkering", 100),
    # Streaming / Nöje
    ("netflix", "Streaming", 100),
    ("spotify", "Streaming", 100),
    ("hbo max", "Streaming", 100),
    ("viaplay", "Streaming", 100),
    ("disney+", "Streaming", 100),
    ("apple.com/bill", "Streaming", 90),
    ("apple.com", "Streaming", 80),
    ("steamgames", "Spel", 100),
    ("playstation", "Spel", 100),
    # Digitala tjänster/spel via PayPal (vanligt på Nordea-utdrag)
    ("xsolla", "Spel", 100),
    ("epic games", "Spel", 100),
    ("google roblo", "Spel", 100),
    ("google grok", "Streaming", 90),
    ("paypal *microsoft", "Hemelektronik", 90),
    ("paypal *ebay", "Hem & Hushåll", 90),
    ("paypal *google", "Streaming", 70),
    # Hälsa
    ("apotek hjärtat", "Apotek", 100),
    ("apotea", "Apotek", 100),
    ("kronans apotek", "Apotek", 100),
    ("sats", "Träning/Gym", 100),
    ("nordic wellness", "Träning/Gym", 100),
    # Telekom / Internet
    ("telia", "Mobil", 100),
    ("telenor", "Mobil", 100),
    ("hallon", "Mobil", 100),
    ("tre ", "Mobil", 100),
    ("comviq", "Mobil", 100),
    ("bahnhof", "Internet", 100),
    # El
    ("vattenfall", "El", 100),
    ("fortum", "El", 100),
    ("eon ", "El", 100),
    # Försäkring
    ("länsförsäkringar", "Hemförsäkring", 90),
    ("folksam", "Hemförsäkring", 90),
    ("if skadeförsäkring", "Bilförsäkring", 100),
    ("if skadeförs", "Bilförsäkring", 100),
    ("trygg-hansa", "Hemförsäkring", 90),
    ("moderna försäkring", "Hemförsäkring", 90),
    # Swish — specific phrasings so incoming ≠ outgoing
    ("swish inbetalning", "Swish in", 110),
    ("swish betalning", "Swish ut", 110),
    # Lön
    ("lön", "Lön", 80),
    ("salary", "Lön", 80),
    # ISK / Invest
    ("isk", "ISK-insättning", 80),
    ("avanza", "Fondköp", 70),
    ("nordnet", "Fondköp", 70),
    # Kläder
    ("h&m", "Kläder & Skor", 100),
    ("zara", "Kläder & Skor", 100),
    ("lindex", "Kläder & Skor", 100),
    ("kappahl", "Kläder & Skor", 100),
    # Hem
    ("ikea", "Hem & Hushåll", 100),
    ("clas ohlson", "Hem & Hushåll", 100),
    ("jula", "Hem & Hushåll", 100),
    ("byggmax", "Hem & Hushåll", 100),
    ("bauhaus", "Hem & Hushåll", 100),
    # Elektronik
    ("netonnet", "Hemelektronik", 100),
    ("elgiganten", "Hemelektronik", 100),
    ("kjell", "Hemelektronik", 100),
    ("webhallen", "Hemelektronik", 100),
    # Barn
    ("babyshop", "Kläder barn", 100),
    ("lekia", "Leksaker", 100),
    # Resor
    ("sas ", "Flyg", 100),
    ("norwegian", "Flyg", 100),
    ("ryanair", "Flyg", 100),
    ("booking.com", "Hotell", 100),
    ("airbnb", "Hotell", 100),
    # Kontant / avgift
    ("bankomat", "Kontantuttag", 100),
    ("uttagsavgift", "Avgifter & Ränta", 100),
    ("ränta", "Avgifter & Ränta", 60),
    ("avgift extra kort", "Avgifter & Ränta", 100),
    ("årsavgift", "Avgifter & Ränta", 90),
    # Bolåneränta / Amortering
    ("bolåneränta", "Bolåneränta", 100),
    ("amortering", "Amortering", 100),

    # Fler svenska vardagsmönster (från riktig data)
    # A-kassa / fack
    ("a-kassa", "Avgifter & Ränta", 100),
    ("akassa", "Avgifter & Ränta", 100),
    # Kommun & myndigheter
    ("skatteverket", "Skatt", 100),
    ("hjo kommun", "Vatten/Avgift", 100),
    (" kommun", "Vatten/Avgift", 80),
    ("trängselskatt", "Kollektivtrafik", 100),
    # El / energi
    ("telinet", "El", 100),
    ("hjo energi", "El", 100),
    ("göteborg energi", "El", 100),
    # Pension / livförsäkring
    ("nordea liv", "Pension", 90),
    ("amf pension", "Pension", 90),
    ("skandia liv", "Pension", 90),
    # Hem & barn
    ("hem och hobby", "Hem & Hushåll", 100),
    ("soltorget", "Hem & Hushåll", 80),
    ("barnbdr", "Barn", 100),

    # Generiska ord (lägre prio så specifika regler vinner)
    ("pizzeria", "Restaurang", 70),
    ("restaurang", "Restaurang", 60),
    (" rest ", "Restaurang", 50),
    ("café ", "Café", 60),
    ("cafeet", "Café", 60),
    ("hälsocentralen", "Sjukvård", 100),
    ("vårdcentral", "Sjukvård", 100),
    ("tandvård", "Sjukvård", 100),
    ("faktureringsavgift", "Avgifter & Ränta", 100),
    ("klarna", "Avgifter & Ränta", 80),
    ("parkman", "Parkering", 100),
    ("q-park", "Parkering", 100),
    ("p-bolaget", "Parkering", 100),

    # Kedjor — kläder
    ("gina tricot", "Kläder & Skor", 100),
    ("lager 157", "Kläder & Skor", 100),
    ("cubus", "Kläder & Skor", 100),
    ("kids brand", "Kläder barn", 100),
    ("dressmann", "Kläder & Skor", 100),
    ("jack & jones", "Kläder & Skor", 100),

    # Kedjor — hem/diverse
    ("søstrene", "Hem & Hushåll", 100),
    ("sostrene", "Hem & Hushåll", 100),
    ("normal ", "Hem & Hushåll", 90),
    ("dollarstore", "Hem & Hushåll", 100),
    ("rusta", "Hem & Hushåll", 100),
    ("butik", "Hem & Hushåll", 50),     # svag default
    ("temu.com", "Hem & Hushåll", 100),
    ("temu", "Hem & Hushåll", 90),
    ("wish ", "Hem & Hushåll", 90),
    ("ebay", "Hem & Hushåll", 80),

    # Nöje & restaurang kedjor
    ("hemmakväll", "Nöje", 100),
    ("pinchos", "Restaurang", 100),
    ("brane", "Restaurang", 80),
    ("bran's", "Restaurang", 100),
    ("go banana", "Restaurang", 100),
    ("tv4", "Streaming", 90),
    ("openai", "Streaming", 100),
    ("chatgpt", "Streaming", 100),

    # Gym/träning
    ("yogiboost", "Träning/Gym", 100),
    ("crossfit", "Träning/Gym", 90),
    ("friskis", "Träning/Gym", 100),
    ("puls & träning", "Träning/Gym", 100),

    # Bilfinansiering (amortering-relaterat)
    ("volkswagen f", "Amortering", 90),
    ("santander", "Avgifter & Ränta", 80),

    # Lokala mat/livs (Hjo-området i användarens data)
    ("damaskus", "Livsmedel", 100),
    ("minilivs", "Livsmedel", 90),
    ("minibutik", "Livsmedel", 90),
    ("livs ", "Livsmedel", 70),
    ("systembolag", "Livsmedel", 100),
    ("lantkrog", "Restaurang", 100),

    # Programvara / AI-tjänster
    ("cursor", "Streaming", 100),
    ("perplexity", "Streaming", 100),
    ("anthropic", "Streaming", 100),
    ("snusbolag", "Övrigt", 90),
    ("programvar", "Hemelektronik", 70),
    ("domän", "Hemelektronik", 60),

    # Larm/hemförsäkring
    ("verisure", "Hemförsäkring", 100),
    ("sector alarm", "Hemförsäkring", 100),

    # Elektronik
    ("elon", "Hemelektronik", 100),

    # Kläder
    ("vero moda", "Kläder & Skor", 100),
    ("kappahl", "Kläder & Skor", 100),
    ("peak performance", "Kläder & Skor", 100),

    # Hem/hobby
    ("panduro", "Hem & Hushåll", 100),
    ("granngård", "Hem & Hushåll", 100),
    ("granngarden", "Hem & Hushåll", 100),
    ("aliexpress", "Hem & Hushåll", 90),
    ("avfall", "Vatten/Avgift", 80),
    ("färgdesign", "Hem & Hushåll", 80),
    ("klm ", "Flyg", 90),
    ("lufthansa", "Flyg", 100),

    # Försäkringskassan / utbetalningar (inkomst)
    ("försäkringskassan", "Inkomst", 90),
    ("fkassa", "Inkomst", 90),
    ("utlandsinsättning", "Inkomst", 70),

    # Löne-patterns — användaren har arbetsgivaren "Inkab"
    ("inkab", "Lön", 90),
]
