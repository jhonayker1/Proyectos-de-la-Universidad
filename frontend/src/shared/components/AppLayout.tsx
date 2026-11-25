/** Barra lateral + barra superior comunes a los dos paneles (diseño de Figma). */
import React from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { Folder, Info, LogOut, Menu, X, type LucideIcon } from 'lucide-react'
import logoImg from '@/assets/logo.jpeg'
import { useAuth, useCurrentUser } from '@/auth/AuthContext'
import { Spinner, cx, errorText, useToast } from './ui'
import { configurarCarpetaDescargas } from '@/shared/lib/downloads'

export type NavItem = { to: string; label: string; icon: LucideIcon }

export default function AppLayout({ items, base, subtitle }: { items: NavItem[]; base: string; subtitle: string }) {
  const [open, setOpen] = React.useState(() => typeof window === 'undefined' || window.innerWidth >= 768)
  const user = useCurrentUser()
  const { logout } = useAuth()
  const toast = useToast()
  const { pathname } = useLocation()
  const [configurandoCarpeta, setConfigurandoCarpeta] = React.useState(false)
  const all = [...items, { to: 'acerca', label: 'Acerca de', icon: Info }]
  const current = all.find(i => pathname === `${base}/${i.to}` || (i.to === '' && pathname === base)) ?? items[0]

  React.useEffect(() => {
    const media = window.matchMedia('(min-width: 768px)')
    const ajustarMenu = (event: MediaQueryList | MediaQueryListEvent) => setOpen(event.matches)
    ajustarMenu(media)
    media.addEventListener('change', ajustarMenu)
    return () => media.removeEventListener('change', ajustarMenu)
  }, [])

  React.useEffect(() => {
    const alDescargar = (event: Event) => {
      if (event instanceof CustomEvent && typeof event.detail === 'string') toast(event.detail)
    }
    window.addEventListener('app-download-complete', alDescargar)
    return () => window.removeEventListener('app-download-complete', alDescargar)
  }, [toast])

  const elegirCarpetaDescargas = async () => {
    setConfigurandoCarpeta(true)
    try {
      const nombre = await configurarCarpetaDescargas()
      toast(`Las descargas de esta aplicación se guardarán en «${nombre}».`)
    } catch (e) {
      toast(errorText(e), 'error')
    } finally {
      setConfigurandoCarpeta(false)
    }
  }

  const link = ({ to, label, icon: Icon }: NavItem) => (
    <NavLink key={to} to={to} end={to === ''} title={label}
      className={({ isActive }) => cx(
        'flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-sm no-underline transition-colors',
        isActive ? 'bg-primary font-semibold text-white' : 'text-secondary-foreground/70 hover:bg-white/10',
      )}>
      {({ isActive }) => <>
        <Icon size={18} strokeWidth={isActive ? 2.5 : 1.8} className="shrink-0" />
        {open && <span className="whitespace-nowrap">{label}</span>}
      </>}
    </NavLink>
  )

  return (
    <div className="flex h-dvh min-h-[320px] overflow-hidden bg-background">
      {open && <button aria-label="Cerrar menú" onClick={() => setOpen(false)} className="fixed inset-0 z-30 cursor-default border-none bg-black/40 md:hidden" />}
      <aside className={cx(
        'fixed inset-y-0 left-0 z-40 flex w-60 shrink-0 flex-col bg-secondary text-secondary-foreground transition-all duration-300 md:relative md:inset-auto md:z-auto',
        open ? 'translate-x-0 md:w-60' : '-translate-x-full md:w-[72px]',
      )}>
        <div className="flex items-center gap-3 border-b border-white/10 px-4 py-5">
          <img src={logoImg} alt="Cauchos Rey" className="h-9 w-9 shrink-0 rounded-xl bg-black object-cover" />
          {open && <span className="font-display text-xs leading-snug font-semibold">Representaciones July<br />Cauchos Rey</span>}
        </div>
        <nav className="flex flex-1 flex-col gap-1 px-2 py-4">{items.map(link)}</nav>
        <div className="flex flex-col gap-1 px-2 pb-2">
          {link(all[all.length - 1])}
          <button onClick={elegirCarpetaDescargas} disabled={configurandoCarpeta}
            title="Elige cualquier carpeta existente para guardar las descargas de esta aplicación."
            className="flex w-full cursor-pointer items-center gap-3 rounded-lg border-none bg-transparent px-3 py-2.5 text-left text-sm text-secondary-foreground/70 hover:bg-white/10 disabled:opacity-50">
            <Folder size={18} strokeWidth={1.8} className="shrink-0" />
            {open && <span>{configurandoCarpeta ? 'Configurando…' : 'Carpeta de descargas'}</span>}
          </button>
          <button onClick={() => logout()} title="Cerrar sesión"
            className="flex w-full cursor-pointer items-center gap-3 rounded-lg border-none bg-transparent px-3 py-2.5 text-left text-sm text-secondary-foreground/70 hover:bg-white/10">
            <LogOut size={18} strokeWidth={1.8} className="shrink-0" />
            {open && <span>Cerrar sesión</span>}
          </button>
        </div>
        {open && <div className="border-t border-white/5 px-4 py-4 text-xs text-secondary-foreground/35">v1.0.0</div>}
      </aside>

      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <header className="flex shrink-0 items-center justify-between gap-2 border-b border-border bg-card px-3 py-3 sm:px-6">
          <div className="flex min-w-0 items-center gap-2 sm:gap-4">
            <button aria-label={open ? 'Contraer menú' : 'Expandir menú'} onClick={() => setOpen(o => !o)}
              className="shrink-0 cursor-pointer rounded-lg border-none bg-transparent p-2 text-muted-foreground hover:bg-muted">
              {open ? <X size={20} /> : <Menu size={20} />}
            </button>
            <div className="min-w-0">
              <h1 className="m-0 text-lg font-bold">{current.label}</h1>
              <p className="m-0 truncate text-xs text-muted-foreground">{subtitle}</p>
            </div>
          </div>
          <div className="flex min-w-0 shrink-0 items-center gap-2 rounded-xl bg-muted px-2 py-1.5 sm:px-3">
            <div className="flex h-[30px] w-[30px] items-center justify-center rounded-full bg-primary font-display text-[13px] font-bold text-white">
              {user.nombre_completo.charAt(0).toUpperCase()}
            </div>
            <div className="hidden min-w-0 sm:block">
              <div className="max-w-40 truncate font-display text-[13px] font-semibold">{user.nombre_completo}</div>
              <div className="max-w-40 truncate text-[11px] text-muted-foreground">{user.correo}</div>
            </div>
          </div>
        </header>
        <main className="flex min-w-0 flex-1 flex-col items-center overflow-y-auto px-3 py-4 sm:p-6">
          <div className="flex min-h-0 w-full max-w-[1440px] min-w-0 flex-1 flex-col">
            <React.Suspense fallback={<Spinner />}>
              <Outlet />
            </React.Suspense>
          </div>
        </main>
      </div>
    </div>
  )
}
