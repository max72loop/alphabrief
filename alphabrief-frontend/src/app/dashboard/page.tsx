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
    <div className="min-h-screen bg-gray-950 text-white p-8">
      <div className="max-w-4xl mx-auto">
        <div className="flex justify-between items-center mb-8">
          <h1 className="text-3xl font-bold">AlphaBrief</h1>
          <button
            onClick={handleLogout}
            className="px-4 py-2 bg-gray-800 rounded-lg hover:bg-gray-700"
          >
            Déconnexion
          </button>
        </div>
        <p className="text-gray-400">Connecté en tant que {user.email}</p>
        <p className="text-gray-500 mt-4">Dashboard à venir...</p>
      </div>
    </div>
  )
}
