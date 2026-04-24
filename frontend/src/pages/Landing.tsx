import { Link } from "react-router-dom";
import {
  AlertTriangle, GraduationCap, Lightbulb, Sparkles,
} from "lucide-react";

export default function Landing() {
  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-white to-brand-50">
      <Header />
      <Hero />
      <WhySection />
      <FeaturesSection />
      <FlowSection />
      <CtaSection />
      <Footer />
    </div>
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
          <a href="#sa-funkar-det" className="text-slate-700 hover:text-brand-600">
            Så funkar det
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
    <section className="max-w-6xl mx-auto px-6 py-16 md:py-24 text-center">
      <div className="inline-flex items-center gap-2 bg-brand-100 text-brand-700 rounded-full px-4 py-1 text-sm mb-6 animate-fadein">
        <GraduationCap className="w-4 h-4" />
        Privatekonomi för skolan
      </div>
      <h1 className="text-4xl md:text-6xl font-bold text-slate-900 leading-tight animate-fadeup">
        Lär eleverna hantera sin
        <span className="text-brand-600"> riktiga ekonomi</span>
        <br />– innan de möter den på riktigt.
      </h1>
      <p className="mt-6 text-lg text-slate-600 max-w-2xl mx-auto animate-fadeup delay-100">
        Ekonomilabbet är en interaktiv simulator där varje elev får en egen
        simulerad vardag — yrke, lön, skatt, hyra, lån, räkningar. De lär sig
        budgetera, spara och förstå vad som händer när livet inte går som
        planerat.
      </p>
      <div className="mt-8 flex flex-wrap justify-center gap-3 animate-fadeup delay-200">
        <Link
          to="/login"
          className="bg-brand-600 hover:bg-brand-700 text-white rounded-lg px-6 py-3 font-medium shadow-lg hover:shadow-xl transition-all"
        >
          Kom igång som lärare
        </Link>
        <Link
          to="/login"
          className="bg-white border-2 border-slate-300 hover:border-brand-500 text-slate-700 rounded-lg px-6 py-3 font-medium"
        >
          Jag är elev
        </Link>
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
function FeaturesSection() { return null; }
function FlowSection() { return null; }
function CtaSection() { return null; }

function Footer() {
  return (
    <footer className="border-t border-slate-200 bg-white py-8 mt-16">
      <div className="max-w-6xl mx-auto px-6 text-center text-sm text-slate-500">
        <div className="font-semibold text-slate-700 mb-1">Ekonomilabbet</div>
        <div>
          En öppen utbildningsplattform för privatekonomi. Byggd med ❤ för
          svenska skolor.
        </div>
      </div>
    </footer>
  );
}
