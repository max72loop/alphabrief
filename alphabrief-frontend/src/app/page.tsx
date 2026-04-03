import Link from "next/link";

export default function Home() {
  return (
    <div className="flex flex-col min-h-screen bg-[#0f0f1a] text-white">
      {/* Nav */}
      <nav className="fixed top-0 left-0 right-0 z-50 flex items-center justify-between px-6 h-14 bg-[#0a0a14]/90 border-b border-white/[0.06] backdrop-blur-xl">
        <span className="text-base font-bold tracking-tight text-white">
          Alpha<span className="text-indigo-400">Brief</span>
        </span>
        <div className="flex items-center gap-2">
          <Link
            href="/login"
            className="px-4 py-1.5 text-sm text-zinc-300 hover:text-white transition-colors"
          >
            Se connecter
          </Link>
          <Link
            href="/login"
            className="px-4 py-1.5 text-sm font-semibold bg-indigo-600 hover:bg-indigo-500 rounded-lg transition-colors"
          >
            Essayer gratuitement
          </Link>
        </div>
      </nav>

      {/* Hero */}
      <section className="flex flex-col items-center justify-center text-center px-6 pt-36 pb-24 flex-1">
        <span className="inline-flex items-center gap-2 text-[0.7rem] font-bold uppercase tracking-widest text-indigo-400 bg-indigo-500/10 border border-indigo-500/25 px-3 py-1 rounded-full mb-6">
          Outil d&apos;analyse quantitative
        </span>
        <h1 className="text-4xl sm:text-6xl font-extrabold leading-tight tracking-tight mb-5 max-w-3xl">
          Investis dans les bonnes boîtes.{" "}
          <span className="bg-gradient-to-r from-indigo-400 to-violet-400 bg-clip-text text-transparent">
            Au bon moment.
          </span>
        </h1>
        <p className="text-lg text-zinc-400 max-w-xl leading-relaxed mb-10">
          AlphaBrief score chaque action de <strong className="text-white">0 à 100</strong> en
          combinant fondamentaux, indicateurs techniques et momentum. Plus besoin de jongler entre
          20 métriques — une seule note pour décider.
        </p>
        <div className="flex flex-col sm:flex-row gap-3">
          <Link
            href="/login"
            className="px-7 py-3 bg-indigo-600 hover:bg-indigo-500 rounded-xl font-semibold text-base transition-colors"
          >
            Commencer gratuitement →
          </Link>
          <a
            href="#comment-ca-marche"
            className="px-7 py-3 border border-white/10 hover:border-white/20 rounded-xl font-semibold text-base text-zinc-300 hover:text-white transition-colors"
          >
            Comment ça marche ?
          </a>
        </div>
        <p className="mt-4 text-xs text-zinc-600">
          5 analyses gratuites par jour · Pas de carte bancaire requise
        </p>
      </section>

      {/* Score demo */}
      <section className="flex justify-center px-6 pb-20">
        <div className="grid grid-cols-3 gap-4 max-w-lg w-full">
          {[
            { ticker: "AAPL", name: "Apple", score: 74, label: "Bon", color: "text-emerald-400", bg: "bg-emerald-500/10 border-emerald-500/20" },
            { ticker: "META", name: "Meta", score: 81, label: "Excellent", color: "text-emerald-400", bg: "bg-emerald-500/10 border-emerald-500/20" },
            { ticker: "NKE", name: "Nike", score: 38, label: "Attention", color: "text-red-400", bg: "bg-red-500/10 border-red-500/20" },
          ].map((s) => (
            <div
              key={s.ticker}
              className="bg-white/[0.03] border border-white/[0.07] rounded-xl p-4 flex flex-col items-center gap-1"
            >
              <span className="text-[0.65rem] font-bold uppercase tracking-wider text-zinc-500">
                {s.ticker}
              </span>
              <span className="text-xs text-zinc-400">{s.name}</span>
              <span className={`text-3xl font-extrabold mt-1 ${s.color}`}>{s.score}</span>
              <span
                className={`text-[0.65rem] font-bold uppercase tracking-wide px-2 py-0.5 rounded-full border ${s.bg} ${s.color}`}
              >
                {s.label}
              </span>
            </div>
          ))}
        </div>
      </section>

      {/* How it works */}
      <section id="comment-ca-marche" className="px-6 pb-24 max-w-4xl mx-auto w-full">
        <h2 className="text-2xl font-bold text-center mb-10">Un score. Trois piliers.</h2>
        <div className="grid sm:grid-cols-3 gap-5">
          {[
            {
              icon: "📊",
              title: "Fondamentaux",
              pct: "50%",
              desc: "Marges, croissance du chiffre d'affaires, dette, retour sur capitaux propres — inspiré de la méthode Brian Feroldi.",
            },
            {
              icon: "📈",
              title: "Techniques",
              pct: "25%",
              desc: "RSI 14 jours, volatilité annuelle, drawdown maximum — pour savoir si le titre est en zone d'achat.",
            },
            {
              icon: "🚀",
              title: "Momentum",
              pct: "25%",
              desc: "Performance relative sur 1, 3, 6 et 12 mois par rapport au marché et au secteur.",
            },
          ].map((p) => (
            <div
              key={p.title}
              className="bg-white/[0.03] border border-white/[0.07] rounded-xl p-5"
            >
              <div className="text-2xl mb-3">{p.icon}</div>
              <div className="flex items-baseline gap-2 mb-2">
                <span className="font-bold text-white">{p.title}</span>
                <span className="text-xs text-indigo-400 font-semibold">{p.pct}</span>
              </div>
              <p className="text-sm text-zinc-400 leading-relaxed">{p.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Score legend */}
      <section className="px-6 pb-24 max-w-2xl mx-auto w-full">
        <h2 className="text-xl font-bold text-center mb-6">Lire un score AlphaBrief</h2>
        <div className="bg-white/[0.03] border border-white/[0.07] rounded-xl overflow-hidden">
          {[
            { range: "75 – 100", label: "Excellent", color: "bg-emerald-500", desc: "Fondamentaux solides, momentum positif, signal fort." },
            { range: "60 – 74", label: "Bon", color: "bg-emerald-400", desc: "Bonne qualité globale, à surveiller de près." },
            { range: "45 – 59", label: "Neutre", color: "bg-amber-400", desc: "Profil mixte — métriques contrastées, pas de signal clair." },
            { range: "30 – 44", label: "Attention", color: "bg-orange-500", desc: "Faiblesses identifiées sur plusieurs piliers." },
            { range: "0 – 29", label: "Risqué", color: "bg-red-500", desc: "Score faible — à éviter ou à revoir en profondeur." },
          ].map((row, i) => (
            <div
              key={row.label}
              className={`flex items-center gap-4 px-5 py-3 ${i < 4 ? "border-b border-white/[0.05]" : ""}`}
            >
              <div className={`w-2.5 h-2.5 rounded-full flex-shrink-0 ${row.color}`} />
              <span className="text-sm font-mono text-zinc-500 w-16 flex-shrink-0">{row.range}</span>
              <span className="text-sm font-semibold text-white w-20 flex-shrink-0">{row.label}</span>
              <span className="text-sm text-zinc-400">{row.desc}</span>
            </div>
          ))}
        </div>
      </section>

      {/* CTA */}
      <section className="px-6 pb-28 text-center">
        <h2 className="text-2xl font-bold mb-4">Prêt à scorer vos premières actions ?</h2>
        <p className="text-zinc-400 mb-6 text-sm">Gratuit jusqu&apos;à 5 analyses par jour.</p>
        <Link
          href="/login"
          className="inline-flex items-center gap-2 px-8 py-3 bg-indigo-600 hover:bg-indigo-500 rounded-xl font-semibold text-base transition-colors"
        >
          Créer un compte gratuit →
        </Link>
      </section>

      {/* Footer */}
      <footer className="border-t border-white/[0.06] px-6 py-6 text-center text-xs text-zinc-600">
        <p>
          © {new Date().getFullYear()} AlphaBrief — Outil d&apos;aide à la décision, pas un conseil en investissement au sens MIF II.
        </p>
        <p className="mt-1">
          <Link href="/login" className="hover:text-zinc-400 transition-colors">Connexion</Link>
          {" · "}
          <a href="mailto:contact@maxloop.ovh" className="hover:text-zinc-400 transition-colors">Contact</a>
        </p>
      </footer>
    </div>
  );
}
