'use client'
import { useEffect, useState } from 'react'
import { supabase } from '@/lib/supabase'
import { useRouter } from 'next/navigation'
import type { User } from '@supabase/supabase-js'

export default function DashboardPage() {
  const [user, setUser] = useState<User | null>(null)
  const router = useRouter()

  useEffect(() => {
    supabase.auth.getUser().then(({ data }) => {
      if (!data.user) router.push('/login')
      else setUser(data.user)
    })
  }, [router])

  const handleLogout = async () => {
    await supabase.auth.signOut()
    router.push('/login')
  }

  if (!user) return null

  return (
    <div className="min-h-screen bg-[#0f0f1a] text-white">
      <nav className="flex items-center justify-between px-6 h-14 border-b border-white/[0.06]">
        <span className="text-base font-bold tracking-tight">
          Alpha<span className="text-indigo-400">Brief</span>
        </span>
        <div className="flex items-center gap-3">
          <span className="text-sm text-zinc-500">{user.email}</span>
          <button
            onClick={handleLogout}
            className="px-3 py-1.5 text-sm bg-white/[0.06] hover:bg-white/[0.1] rounded-lg transition-colors"
          >
            Déconnexion
          </button>
        </div>
      </nav>
      <main className="max-w-3xl mx-auto px-6 py-16 text-center">
        <h1 className="text-3xl font-bold mb-4">Bonjour 👋</h1>
        <p className="text-zinc-400 mb-8 leading-relaxed">
          Votre compte AlphaBrief est actif. L&apos;interface complète (screener, watchlist, portfolio,
          alertes) est disponible sur l&apos;application principale.
        </p>
        <a
          href="http://95.217.239.25:5000"
          className="inline-flex items-center gap-2 px-7 py-3 bg-indigo-600 hover:bg-indigo-500 rounded-xl font-semibold transition-colors"
        >
          Accéder à l&apos;application →
        </a>
        <p className="mt-6 text-xs text-zinc-600">
          {/* TODO: remplacer l'URL par maxloop.ovh une fois le frontend complet déployé */}
        </p>
      </main>
    </div>
  )
}
