import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  AlertTriangle, ArrowRight, BarChart3, Briefcase, Check, ChevronDown,
  GraduationCap, Home, Lightbulb, MessageCircle, PiggyBank, Quote,
  Receipt, School, Sparkles, TrendingUp, Users, Zap,
} from "lucide-react";
import { api } from "@/api/client";
import DashboardPreview from "@/components/landing/DashboardPreview";
import BudgetDemo from "@/components/landing/BudgetDemo";
import PdfImportDemo from "@/components/landing/PdfImportDemo";
import TeacherDemo from "@/components/landing/TeacherDemo";
import MortgageDemo from "@/components/landing/MortgageDemo";
import { useReveal } from "@/hooks/useReveal";

export default function Landing() {
  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-white to-brand-50">
      <Header />
      <Hero />
      <StatsTicker />
      <SocialProof />
      <WhySection />
      <FeaturesSection />
      <ScreenshotGallery />
      <DemoSection />
      <FlowSection />
      <PricingSection />
      <FaqSection />
      <FounderNote />
      <CtaSection />
      <ContactSection />
      <Footer />
    </div>
  );
}

function DemoSection() {
  return (
    <section className="py-16">
      <div className="max-w-5xl mx-auto px-6">
        <div className="relative bg-gradient-to-br from-amber-400 via-orange-400 to-rose-400 rounded-3xl p-10 md:p-14 shadow-xl overflow-hidden">
          {/* Dekorativa cirklar */}
          <div className="absolute -top-20 -right-20 w-64 h-64 bg-white/10 rounded-full blur-3xl" />
          <div className="absolute -bottom-20 -left-20 w-72 h-72 bg-white/10 rounded-full blur-3xl" />

          <div className="relative grid md:grid-cols-[1fr_auto] gap-8 items-center">
            <div>
              <div className="inline-flex items-center gap-2 bg-white/20 backdrop-blur text-white rounded-full px-3 py-1 text-xs font-medium mb-4">
                <Zap className="w-3.5 h-3.5" /> Ingen registrering krävs
              </div>
              <h2 className="text-3xl md:text-4xl font-bold text-white mb-3">
                Prova plattformen direkt
              </h2>
              <p className="text-white/90 max-w-xl">
                En färdig klass med 5 elever väntar i demo-miljön. Logga in
                som lärare och utforska flödena, eller testa som elev och
                se hur dashboard och budget funkar. Datan återställs var
                10:e minut — spring-fri sandlåda.
              </p>
              <ul className="mt-5 text-white/90 text-sm space-y-1.5">
                <li className="flex items-center gap-2">
                  <span className="w-1.5 h-1.5 bg-white rounded-full" />
                  3 månaders genererad data redan importerad
                </li>
                <li className="flex items-center gap-2">
                  <span className="w-1.5 h-1.5 bg-white rounded-full" />
                  Olika elev-profiler: sparsam, blandad, slösaktig
                </li>
                <li className="flex items-center gap-2">
                  <span className="w-1.5 h-1.5 bg-white rounded-full" />
                  Pågående uppdrag och en levande meddelandetråd
                </li>
              </ul>
            </div>
            <Link
              to="/demo"
              className="group bg-white hover:bg-slate-50 text-orange-600 rounded-2xl px-8 py-5 font-semibold shadow-xl hover:shadow-2xl transition-all inline-flex items-center gap-3 whitespace-nowrap"
            >
              <Zap className="w-5 h-5" />
              Starta demo
              <ArrowRight className="w-4 h-4 group-hover:translate-x-1 transition-transform" />
            </Link>
          </div>
        </div>
      </div>
    </section>
  );
}

function Header() {
  return (
    <header className="sticky top-0 z-30 bg-white/80 backdrop-blur border-b border-slate-200">
      <div className="max-w-6xl mx-auto px-6 py-3 flex items-center justify-between">
        <div className="flex items-center gap-2 text-brand-600 font-bold text-lg">
          <Sparkles className="w-5 h-5" />
          Ekonomilabbet
        </div>
        <nav className="flex items-center gap-3 text-sm">
          <a href="#funktioner" className="text-slate-700 hover:text-brand-600">
            Funktioner
          </a>
          <a href="#sa-funkar-det" className="text-slate-700 hover:text-brand-600 hidden md:inline">
            Så funkar det
          </a>
          <a href="#pricing" className="text-slate-700 hover:text-brand-600 hidden md:inline">
            Pris
          </a>
          <a href="#faq" className="text-slate-700 hover:text-brand-600 hidden md:inline">
            FAQ
          </a>
          <Link to="/docs" className="text-slate-700 hover:text-brand-600 hidden md:inline">
            Dokumentation
          </Link>
          <a href="#kontakt" className="text-slate-700 hover:text-brand-600 hidden md:inline">
            Kontakt
          </a>
          <Link
            to="/login"
            className="bg-brand-600 hover:bg-brand-700 text-white rounded-lg px-4 py-2"
          >
            Logga in
          </Link>
        </nav>
      </div>
    </header>
  );
}

function Hero() {
  return (
    <section className="max-w-6xl mx-auto px-6 py-16 md:py-20 grid md:grid-cols-2 gap-10 items-center">
      <div>
        <div className="inline-flex items-center gap-2 bg-brand-100 text-brand-700 rounded-full px-4 py-1 text-sm mb-6 animate-fadein">
          <GraduationCap className="w-4 h-4" />
          Privatekonomi för skolan
        </div>
        <h1 className="text-4xl md:text-5xl font-bold text-slate-900 leading-tight animate-fadeup">
          Lär eleverna hantera sin
          <span className="text-brand-600"> riktiga ekonomi</span>
          <br />– innan de möter den på riktigt.
        </h1>
        <p className="mt-6 text-lg text-slate-600 animate-fadeup delay-100">
          Ekonomilabbet är en interaktiv simulator där varje elev får en egen
          simulerad vardag — yrke, lön, skatt, hyra, lån, räkningar. De lär
          sig budgetera, spara och förstå när livet inte går som planerat.
        </p>
        <div className="mt-8 flex flex-wrap gap-3 animate-fadeup delay-200">
          <Link
            to="/login/teacher"
            className="bg-brand-600 hover:bg-brand-700 text-white rounded-lg px-6 py-3 font-medium shadow-lg hover:shadow-xl transition-all"
          >
            Kom igång som lärare
          </Link>
          <Link
            to="/login/student"
            className="bg-white border-2 border-slate-300 hover:border-brand-500 text-slate-700 rounded-lg px-6 py-3 font-medium"
          >
            Jag är elev
          </Link>
        </div>
      </div>
      <div className="animate-fadeup delay-300">
        <DashboardPreview />
      </div>
    </section>
  );
}

function WhySection() {
  const stats = [
    { num: "4 av 10", label: "unga klarar inte en oväntad räkning på 2 000 kr" },
    { num: "60%", label: "av elever har aldrig läst en lönespecifikation" },
    { num: "1 timme", label: "räcker för att prova grunderna i Ekonomilabbet" },
  ];
  return (
    <section className="bg-white border-y border-slate-200 py-16">
      <div className="max-w-6xl mx-auto px-6">
        <div className="text-center mb-10">
          <div className="inline-flex items-center gap-2 text-brand-600 text-sm font-medium mb-2">
            <AlertTriangle className="w-4 h-4" /> Problem
          </div>
          <h2 className="text-3xl md:text-4xl font-bold text-slate-900">
            Ekonomi är ett livskunskapsämne.<br />Och det saknas i skolan.
          </h2>
          <p className="mt-4 text-slate-600 max-w-2xl mx-auto">
            Svenska unga lämnar skolan utan grundläggande kunskaper om skatt,
            sparande, lån och budget. Först när de flyttar hemifrån möter de
            verkligheten — ofta för sent.
          </p>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {stats.map((s, i) => (
            <div
              key={i}
              className="bg-gradient-to-br from-brand-50 to-white border border-brand-100 rounded-xl p-6 text-center hover:shadow-md transition-shadow"
            >
              <div className="text-4xl font-bold text-brand-600 mb-2">
                {s.num}
              </div>
              <div className="text-sm text-slate-700">{s.label}</div>
            </div>
          ))}
        </div>
        <div className="mt-10 bg-emerald-50 border-l-4 border-emerald-500 rounded p-5 flex gap-4">
          <Lightbulb className="w-8 h-8 text-emerald-600 shrink-0" />
          <div>
            <h3 className="font-semibold text-emerald-900 mb-1">
              Lär genom att göra — inte genom att läsa om det
            </h3>
            <p className="text-sm text-emerald-900">
              Eleven får egen simulerad inkomst, egna räkningar, egen lön varje
              månad. Precis som i livet utanför klassrummet. Varje val har
              konsekvenser som syns i deras budget.
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}
type Feat = {
  icon: React.ReactNode;
  title: string;
  body: string;
  color: string;
  anim: "bounce" | "wiggle" | "spin";
  pulse?: boolean;
};

function FeaturesSection() {
  const features: Feat[] = [
    { icon: <Briefcase className="w-6 h-6" />, title: "Unik elev-profil",
      body: "Varje elev får ett slumpat yrke, arbetsgivare, lön, stad och livssituation. Ingen annan i klassen har samma.",
      color: "brand", anim: "bounce" },
    { icon: <Receipt className="w-6 h-6" />, title: "Riktiga PDF:er",
      body: "Läraren genererar kontoutdrag, lönespec, lån och kreditkortsfakturor som eleverna själva importerar.",
      color: "emerald", anim: "wiggle" },
    { icon: <PiggyBank className="w-6 h-6" />, title: "Budget mot verklighet",
      body: "Eleven sätter sin egen månadsbudget baserat på Konsumentverkets 2026-siffror — sedan jämförs den mot faktiska köp.",
      color: "amber", anim: "bounce" },
    { icon: <Home className="w-6 h-6" />, title: "Bolåne-beslut",
      body: "Historiska räntor från Riksbanken. Eleven väljer rörlig eller bunden — systemet visar facit efter horisonten.",
      color: "rose", anim: "wiggle", pulse: true },
    { icon: <AlertTriangle className="w-6 h-6" />, title: "Livet händer",
      body: "Diskmaskin går sönder. Sjukdagar sänker lönen. Julshopping exploderar. Eleverna får öva på att hantera oväntat.",
      color: "purple", anim: "wiggle" },
    { icon: <Users className="w-6 h-6" />, title: "Familjer",
      body: "Två elever kan dela ekonomi — sambo-hushåll med gemensam budget, räkningar och sparmål.",
      color: "sky", anim: "bounce" },
    { icon: <BarChart3 className="w-6 h-6" />, title: "Lärarens översikt",
      body: "Klassöversikt med status per elev och uppdrag. Facit för varje kategorisering — grönt/rött på en blick.",
      color: "brand", anim: "spin" },
    { icon: <MessageCircle className="w-6 h-6" />, title: "Feedback-chat",
      body: "Eleven kan ställa frågor direkt till läraren. Läraren svarar + ger feedback på enskilda transaktioner.",
      color: "emerald", anim: "wiggle", pulse: true },
    { icon: <TrendingUp className="w-6 h-6" />, title: "Sparmål & uppdrag",
      body: "Läraren sätter tydliga uppdrag: 'spara 2 000 kr', 'balansera månaden', 'kategorisera alla köp'. Statusen uppdateras automatiskt.",
      color: "amber", anim: "bounce" },
  ];

  return (
    <section id="funktioner" className="max-w-6xl mx-auto px-6 py-20">
      <div className="text-center mb-12">
        <div className="inline-flex items-center gap-2 text-brand-600 text-sm font-medium mb-2">
          <Sparkles className="w-4 h-4" /> Funktioner
        </div>
        <h2 className="text-3xl md:text-4xl font-bold text-slate-900">
          Allt du behöver för att göra ekonomi begripligt
        </h2>
        <p className="mt-4 text-slate-600 max-w-2xl mx-auto">
          Från första lönen till komplexa bolåneval — varje funktion är byggd
          för att eleven ska lära genom handling.
        </p>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
        {features.map((f, i) => (
          <FeatureCard key={i} index={i} {...f} />
        ))}
      </div>
    </section>
  );
}

function FeatureCard({
  icon, title, body, color, anim, pulse, index,
}: {
  icon: React.ReactNode;
  title: string;
  body: string;
  color: string;
  anim?: "bounce" | "wiggle" | "spin";
  pulse?: boolean;
  index: number;
}) {
  const ref = useReveal<HTMLDivElement>();
  const colorMap: Record<string, string> = {
    brand: "bg-brand-100 text-brand-600",
    emerald: "bg-emerald-100 text-emerald-600",
    amber: "bg-amber-100 text-amber-600",
    rose: "bg-rose-100 text-rose-600",
    purple: "bg-purple-100 text-purple-600",
    sky: "bg-sky-100 text-sky-600",
  };
  const animClass =
    anim === "bounce" ? "animate-hover-bounce" :
    anim === "wiggle" ? "animate-hover-wiggle" :
    anim === "spin" ? "animate-hover-spin" : "";
  return (
    <div
      ref={ref}
      className="reveal group bg-white border border-slate-200 rounded-xl p-5 hover:border-brand-400 hover:shadow-xl hover:-translate-y-1 transition-all duration-300"
      style={{ transitionDelay: `${(index % 3) * 60}ms` }}
    >
      <div
        className={`relative inline-flex w-12 h-12 rounded-lg items-center justify-center mb-3 ${
          colorMap[color] ?? "bg-brand-100 text-brand-600"
        } group-hover:scale-110 transition-transform ${pulse ? "pulse-ring" : ""}`}
      >
        <span className={animClass}>{icon}</span>
      </div>
      <h3 className="font-semibold text-slate-900 mb-1">{title}</h3>
      <p className="text-sm text-slate-600 leading-relaxed">{body}</p>
    </div>
  );
}
function FlowSection() {
  const blocks = [
    {
      num: "01",
      title: "Eleven får en egen vardag",
      body: "Yrke, lön, bostad, lån — allt slumpas unikt per elev. Dashboarden visar nettolön, utgifter, sparande och budget mot verkligheten i realtid.",
      color: "bg-brand-500",
      demo: <DashboardPreview />,
    },
    {
      num: "02",
      title: "Verkliga dokument att jobba med",
      body: "Läraren trycker 'generera' — eleven får kontoutdrag, lönespec, lånebesked och kortfakturor som PDF:er och importerar själv.",
      color: "bg-emerald-500",
      demo: <PdfImportDemo />,
    },
    {
      num: "03",
      title: "Budget möter verklighet",
      body: "Eleven sätter en månadsbudget enligt Konsumentverkets 2026-siffror. När en trasig diskmaskin slår till syns följderna direkt.",
      color: "bg-amber-500",
      demo: <BudgetDemo />,
    },
    {
      num: "04",
      title: "Verklig fostring i ekonomiska val",
      body: "Bolåne-beslut baserat på Riksbankens historiska räntor. Eleven binder eller kör rörlig — systemet visar facit efter perioden. Konsekvenser gjort synliga.",
      color: "bg-purple-500",
      demo: <MortgageDemo />,
    },
    {
      num: "05",
      title: "Läraren ser hela klassen",
      body: "Matris över alla elever och uppdrag. Kategoriseringsfacit per tx. Chatt för feedback. Allt du behöver för att följa upp.",
      color: "bg-rose-500",
      demo: <TeacherDemo />,
    },
  ];

  return (
    <section id="sa-funkar-det" className="bg-slate-900 text-white py-20">
      <div className="max-w-6xl mx-auto px-6">
        <div className="text-center mb-16">
          <div className="inline-flex items-center gap-2 text-brand-300 text-sm font-medium mb-2">
            <Sparkles className="w-4 h-4" /> Så funkar det
          </div>
          <h2 className="text-3xl md:text-4xl font-bold">
            Se plattformen i rörelse
          </h2>
          <p className="text-slate-400 mt-3 max-w-xl mx-auto">
            Fyra nyckel-ögonblick i Ekonomilabbet — precis så elever och
            lärare faktiskt använder det.
          </p>
        </div>

        <div className="space-y-20">
          {blocks.map((b, i) => (
            <div
              key={b.num}
              className={`grid md:grid-cols-2 gap-10 items-center ${
                i % 2 === 1 ? "md:[&>div:first-child]:order-2" : ""
              }`}
            >
              <div>
                <div
                  className={`${b.color} inline-flex w-14 h-14 rounded-full items-center justify-center text-xl font-bold mb-4 shadow-lg`}
                >
                  {b.num}
                </div>
                <h3 className="text-2xl font-bold mb-3">{b.title}</h3>
                <p className="text-slate-300 leading-relaxed">{b.body}</p>
              </div>
              <div>{b.demo}</div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
function FounderNote() {
  return (
    <section className="max-w-3xl mx-auto px-6 py-16">
      <div className="relative bg-white border border-slate-200 rounded-2xl p-8 md:p-10 shadow-sm">
        <Quote className="absolute -top-3 -left-3 w-8 h-8 text-brand-500 bg-white p-1 rounded-full border border-slate-200" />
        <p className="text-lg md:text-xl text-slate-800 leading-relaxed italic">
          Ekonomilabbet började som ett verktyg för min egen ekonomi. Nu kan
          det också hjälpa unga att förstå pengar, beslut och vardagsekonomi
          på riktigt — på ett sätt som känns konkret och användbart.
        </p>
        <div className="mt-4 text-sm text-slate-500">— Grundaren</div>
      </div>
    </section>
  );
}

function CtaSection() {
  return (
    <section className="max-w-4xl mx-auto px-6 py-20 text-center">
      <div className="bg-gradient-to-br from-brand-500 to-brand-700 rounded-3xl p-10 md:p-14 shadow-2xl text-white">
        <GraduationCap className="w-12 h-12 mx-auto mb-4 text-brand-100" />
        <h2 className="text-3xl md:text-4xl font-bold mb-3">
          Kom igång på under en minut
        </h2>
        <p className="text-brand-100 max-w-xl mx-auto mb-8">
          Skapa ditt lärarkonto, lägg till din första klass och testa flödet
          själv. Helt gratis under beta-perioden.
        </p>
        <div className="flex flex-wrap justify-center gap-3">
          <Link
            to="/login/teacher"
            className="bg-white hover:bg-slate-50 text-brand-700 rounded-lg px-8 py-3 font-semibold shadow-lg hover:shadow-xl transition-all"
          >
            Skapa lärarkonto
          </Link>
          <Link
            to="/login/student"
            className="bg-brand-800 hover:bg-brand-900 text-white rounded-lg px-8 py-3 font-semibold border-2 border-brand-400"
          >
            Elev-inloggning
          </Link>
        </div>
      </div>
    </section>
  );
}

function ContactSection() {
  return (
    <section id="kontakt" className="bg-slate-50 border-y border-slate-200 py-16">
      <div className="max-w-3xl mx-auto px-6 text-center">
        <div className="inline-flex items-center gap-2 text-brand-600 text-sm font-medium mb-2">
          <MessageCircle className="w-4 h-4" /> Kontakta oss
        </div>
        <h2 className="text-3xl md:text-4xl font-bold text-slate-900 mb-4">
          Frågor, förslag eller samarbeten?
        </h2>
        <p className="text-slate-600 mb-6">
          Vi hjälper gärna till om du vill komma igång i din klass, har
          önskemål om nya funktioner, eller vill utforska samarbeten med
          skolor, kommuner eller lärarorganisationer.
        </p>
        <a
          href="mailto:info@ekonomilabbet.org"
          className="inline-flex items-center gap-2 bg-brand-600 hover:bg-brand-700 text-white rounded-lg px-6 py-3 font-medium shadow-lg hover:shadow-xl transition-all"
        >
          <MessageCircle className="w-5 h-5" />
          info@ekonomilabbet.org
        </a>
        <p className="text-xs text-slate-500 mt-4">
          Vi svarar oftast inom ett par arbetsdagar.
        </p>
      </div>
    </section>
  );
}


function StatsTicker() {
  const [stats, setStats] = useState<{
    teachers: number; students: number;
    modules_completed: number; reflections_written: number;
  } | null>(null);
  useEffect(() => {
    api<typeof stats>("/public/stats")
      .then(setStats)
      .catch(() => setStats(null));
  }, []);
  if (!stats) return null;
  const items = [
    { label: "Lärare", value: stats.teachers },
    { label: "Elever", value: stats.students },
    { label: "Avklarade moduler", value: stats.modules_completed },
    { label: "Reflektioner skickade", value: stats.reflections_written },
  ];
  return (
    <section className="bg-white border-y border-slate-200 py-8">
      <div className="max-w-6xl mx-auto px-6 grid grid-cols-2 md:grid-cols-4 gap-6">
        {items.map((x) => (
          <div key={x.label} className="text-center">
            <div className="text-3xl md:text-4xl font-bold text-brand-700">
              {x.value.toLocaleString("sv-SE")}
            </div>
            <div className="text-xs uppercase tracking-wider text-slate-500 mt-1">
              {x.label}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function SocialProof() {
  // Pilotprojekt — bara platshållare tills vi har riktiga skolor att
  // visa upp. Tona ned med opacitet så det inte upplevs oärligt.
  const schools = [
    "Exempelskolan", "Ekonomilinjen Malmö",
    "Linnéskolan", "Musikgymnasiet", "Fjällgymnasiet",
  ];
  return (
    <section className="py-10 bg-slate-50">
      <div className="max-w-6xl mx-auto px-6 text-center">
        <p className="text-xs uppercase tracking-widest text-slate-500 mb-4">
          I pilotprojekt tillsammans med
        </p>
        <ul className="flex flex-wrap justify-center gap-x-8 gap-y-3 opacity-50">
          {schools.map((s) => (
            <li
              key={s}
              className="text-slate-700 font-serif text-lg flex items-center gap-2"
            >
              <School className="w-4 h-4" /> {s}
            </li>
          ))}
        </ul>
        <p className="text-xs text-slate-400 mt-3">
          Vi lägger till riktiga logotyper när pilotfasen är klar.
        </p>
      </div>
    </section>
  );
}

function ScreenshotGallery() {
  const shots = [
    {
      title: "Lärarens dashboard",
      body: "Alla elever, inbox, uppdrag och AI-lägesbilder på en skärm.",
      icon: <Users className="w-5 h-5" />,
      tint: "from-brand-100 to-sky-100",
    },
    {
      title: "Elevens kursplan",
      body: "Moduler med steg för steg: läs, reflektera, quiz och uppdrag.",
      icon: <GraduationCap className="w-5 h-5" />,
      tint: "from-emerald-100 to-teal-100",
    },
    {
      title: "Mastery-grafen",
      body: "Per-kompetens mastery, milstolpar och nästa-steg-hint.",
      icon: <BarChart3 className="w-5 h-5" />,
      tint: "from-amber-100 to-orange-100",
    },
    {
      title: "Portfolio-PDF",
      body: "Exporteras per elev eller som ZIP för hela klassen.",
      icon: <Receipt className="w-5 h-5" />,
      tint: "from-rose-100 to-pink-100",
    },
    {
      title: "Fråga Ekon",
      body: "Multi-turn AI-coach som anpassar svaren till elevens nivå.",
      icon: <Sparkles className="w-5 h-5" />,
      tint: "from-purple-100 to-fuchsia-100",
    },
    {
      title: "Time-on-task",
      body: "Se vilka steg som fastnar för eleverna i din klass.",
      icon: <TrendingUp className="w-5 h-5" />,
      tint: "from-indigo-100 to-blue-100",
    },
  ];
  return (
    <section className="py-16 bg-white">
      <div className="max-w-6xl mx-auto px-6">
        <div className="text-center mb-10">
          <h2 className="text-3xl md:text-4xl font-bold text-slate-900 mb-2">
            Se plattformen i bruk
          </h2>
          <p className="text-slate-600">
            Sex vyer som täcker det mesta lärare och elever rör sig i dagligen.
          </p>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {shots.map((s) => (
            <div
              key={s.title}
              className={`rounded-xl bg-gradient-to-br ${s.tint} border border-white aspect-[4/3] p-5 flex flex-col justify-between shadow-sm hover:shadow-md transition-shadow`}
            >
              <div className="inline-flex items-center justify-center w-9 h-9 bg-white/80 rounded-lg text-slate-700">
                {s.icon}
              </div>
              <div>
                <div className="font-semibold text-slate-900">{s.title}</div>
                <p className="text-sm text-slate-700 mt-1">{s.body}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function PricingSection() {
  return (
    <section id="pricing" className="py-20 bg-slate-50 border-y border-slate-200">
      <div className="max-w-4xl mx-auto px-6 text-center">
        <h2 className="text-3xl md:text-4xl font-bold text-slate-900 mb-2">
          Enkel prismodell
        </h2>
        <p className="text-slate-600 max-w-xl mx-auto">
          Gratis under pilotåret 2026. Ingen bindningstid, inga dolda kostnader.
          Från 2027 blir det en enkel per-elev-kostnad — beslut tas i
          dialog med pilotskolorna.
        </p>
        <div className="mt-10 grid md:grid-cols-2 gap-4 max-w-2xl mx-auto">
          <div className="bg-white border-2 border-brand-600 rounded-2xl p-6 text-left shadow-sm">
            <div className="inline-flex items-center gap-1 bg-brand-600 text-white text-xs font-medium rounded-full px-2.5 py-0.5">
              Pilot 2026
            </div>
            <div className="text-3xl font-bold text-slate-900 mt-3">0 kr</div>
            <div className="text-sm text-slate-600 mb-4">
              Hela plattformen, utan tak.
            </div>
            <ul className="text-sm space-y-2">
              {[
                "Obegränsat antal elever",
                "AI-funktioner (Claude Sonnet)",
                "Portfolio-PDF + ZIP-export",
                "Support via mail",
              ].map((x) => (
                <li key={x} className="flex items-start gap-2">
                  <Check className="w-4 h-4 text-emerald-600 mt-0.5" /> {x}
                </li>
              ))}
            </ul>
          </div>
          <div className="bg-white border border-slate-200 rounded-2xl p-6 text-left">
            <div className="text-xs uppercase tracking-wide text-slate-500">
              Från 2027
            </div>
            <div className="text-3xl font-bold text-slate-900 mt-3">
              Per-elev
            </div>
            <div className="text-sm text-slate-600 mb-4">
              Exakt nivå sätts tillsammans med pilotskolorna — troligen
              mellan 50–150 kr/elev/läsår.
            </div>
            <ul className="text-sm space-y-2">
              {[
                "Samma plattform, ingen funktionsnedskärning",
                "Tak för AI-användning",
                "Dedikerad support",
              ].map((x) => (
                <li key={x} className="flex items-start gap-2">
                  <Check className="w-4 h-4 text-emerald-600 mt-0.5" /> {x}
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>
    </section>
  );
}

function FaqSection() {
  const items = [
    {
      q: "Vad kostar Ekonomilabbet?",
      a:
        "Gratis under pilotåret 2026. Inga dolda kostnader. Från 2027 tas en " +
        "per-elev-avgift ut, nivån bestäms tillsammans med pilotskolorna.",
    },
    {
      q: "Är det GDPR-säkert?",
      a:
        "Ja. All elevdata sparas i svensk molntjänst (Google Cloud Run, " +
        "europe-north1). Vi delar inga personuppgifter med tredje part. " +
        "AI-anropen anonymiseras — Claude ser aldrig elevers namn eller " +
        "personnummer.",
    },
    {
      q: "Vad behöver vi installera?",
      a:
        "Inget. Ekonomilabbet är en webbapp. Läraren skapar konto, lägger " +
        "in eleverna och eleverna loggar in med en 6-teckenskod eller QR-" +
        "kod. Ingen installation, ingen app-store.",
    },
    {
      q: "Går det att använda utan AI?",
      a:
        "Absolut. Alla pedagogiska flöden (moduler, reflektioner, quiz, " +
        "rubric, portfolio) fungerar utan AI. AI är en ren extra-funktion " +
        "som kan aktiveras per lärare.",
    },
    {
      q: "Kan elever komma åt varandras data?",
      a:
        "Nej. Varje elev har en egen krypterad SQLite-DB på servern, " +
        "ingen cross-access även om de råkar i samma klass. Läraren ser " +
        "alla sina elever men aldrig någon annan lärares.",
    },
    {
      q: "Vad händer med elevernas data när året är slut?",
      a:
        "Ingenting tvångsmässigt — datan är kvar tills läraren tar bort " +
        "kontot. Vi exporterar gärna hela klassen till ZIP så du har en " +
        "kopia innan du raderar.",
    },
    {
      q: "Vilken AI-modell används?",
      a:
        "Claude Haiku 4.5 för snabba uppgifter (kategori-check, feedback-" +
        "förslag) och Claude Sonnet 4.6 för djupare uppgifter (rubric, " +
        "elev-Q&A, modul-generering). Prompt-caching används för " +
        "kostnadskontroll.",
    },
    {
      q: "Kan jag importera befintliga moduler från andra system?",
      a:
        "Inte som automatisk import än. Moduler skapas i plattformen " +
        "eller klonas från systemmallar/andra lärares delade moduler. " +
        "Säg till oss vad ni använder — vi bygger importen om det finns " +
        "efterfrågan.",
    },
  ];
  return (
    <section id="faq" className="py-20">
      <div className="max-w-3xl mx-auto px-6">
        <h2 className="text-3xl md:text-4xl font-bold text-slate-900 text-center mb-10">
          Vanliga frågor
        </h2>
        <ul className="space-y-2">
          {items.map((it, i) => (
            <FaqItem key={i} q={it.q} a={it.a} />
          ))}
        </ul>
      </div>
    </section>
  );
}

function FaqItem({ q, a }: { q: string; a: string }) {
  const [open, setOpen] = useState(false);
  return (
    <li className="bg-white border border-slate-200 rounded-xl overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="w-full flex items-center justify-between text-left px-4 py-3 hover:bg-slate-50"
      >
        <span className="font-medium text-slate-900">{q}</span>
        <ChevronDown
          className={`w-5 h-5 text-slate-500 transition-transform ${
            open ? "rotate-180" : ""
          }`}
        />
      </button>
      {open && (
        <div className="px-4 pb-4 text-slate-700 text-sm leading-relaxed">
          {a}
        </div>
      )}
    </li>
  );
}

function Footer() {
  return (
    <footer className="border-t border-slate-200 bg-white py-10 mt-0">
      <div className="max-w-6xl mx-auto px-6 grid md:grid-cols-3 gap-8 text-sm">
        <div>
          <div className="flex items-center gap-2 text-brand-600 font-bold mb-2">
            <Sparkles className="w-5 h-5" /> Ekonomilabbet
          </div>
          <p className="text-slate-600">
            En öppen utbildningsplattform för privatekonomi. Byggd med ❤
            för svenska skolor.
          </p>
        </div>
        <div>
          <div className="font-semibold text-slate-700 mb-2">Länkar</div>
          <ul className="space-y-1 text-slate-600">
            <li>
              <Link to="/docs" className="hover:text-brand-600">
                Dokumentation
              </Link>
            </li>
            <li>
              <Link to="/demo" className="hover:text-brand-600">
                Prova demo
              </Link>
            </li>
            <li>
              <a href="#kontakt" className="hover:text-brand-600">
                Kontakt
              </a>
            </li>
            <li>
              <a
                href="https://github.com/robinandreeklund-collab/Hembudget"
                target="_blank" rel="noreferrer"
                className="hover:text-brand-600"
              >
                GitHub
              </a>
            </li>
          </ul>
        </div>
        <div>
          <div className="font-semibold text-slate-700 mb-2">Kontakt</div>
          <ul className="space-y-1 text-slate-600">
            <li>
              <a
                href="mailto:info@ekonomilabbet.org"
                className="hover:text-brand-600"
              >
                info@ekonomilabbet.org
              </a>
            </li>
            <li className="text-slate-500">
              ekonomilabbet.org
            </li>
          </ul>
        </div>
      </div>
      <div className="max-w-6xl mx-auto px-6 mt-8 pt-6 border-t border-slate-200 text-xs text-slate-500 text-center">
        © {new Date().getFullYear()} Ekonomilabbet · Öppen källkod
      </div>
    </footer>
  );
}
