import { useState } from 'react'
import type { ReactNode } from 'react'
import { Sidebar } from './Sidebar'
import { Topbar } from './Topbar'
import { cn } from '../../lib/cn'

interface AppShellProps {
  children: ReactNode
  /** true = la pagina maneja su propio padding/scroll (p.ej. un layout de
   * editor a pantalla completa) -- ver NewMicroVideoProjectPage.tsx. */
  fullBleed?: boolean
}

export function AppShell({ children, fullBleed }: AppShellProps) {
  // Drawer del sidebar (ver RM-20) -- solo relevante por debajo de `lg`,
  // el estado vive aca porque tanto Topbar (boton de hamburguesa) como
  // Sidebar (el drawer en si) lo necesitan.
  const [sidebarOpen, setSidebarOpen] = useState(false)

  return (
    <div className="flex h-screen w-full bg-background">
      <Sidebar open={sidebarOpen} onClose={() => setSidebarOpen(false)} />
      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar onOpenSidebar={() => setSidebarOpen(true)} />
        <main className={cn('flex-1', fullBleed ? 'overflow-hidden' : 'overflow-y-auto p-4 sm:p-6')}>
          {children}
        </main>
      </div>
    </div>
  )
}
