/** Barra lateral + barra superior comunes a los dos paneles (diseño de Figma). */
import React from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { Info, LogOut, Menu, X, type LucideIcon } from 'lucide-react'
import logoImg from '@/assets/logo.jpeg'
import { useAuth, useCurrentUser } from '@/auth/AuthContext'
import { Spinner, cx } from './ui'

export type NavItem = { to: string; label: string; icon: LucideIcon }

export default function AppLayout({ items, base, subtitle }: { items: NavItem[]; base: string; subtitle: string }) {
  const [open, setOpen] = React.useState(true)
  const user = useCurrentUser()
  const { logout } = useAuth()
  const { pathname } = useLocation()
  const all = [...items, { to: 'acerca', label: 'Acerca de', icon: Info }]
  const current = all.find(i => pathname === `${base}/${i.to}` || (i.to === '' && pathname === base)) ?? items[0]

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
    <div className="flex h-screen overflow-hidden bg-background">
      <aside className={cx('flex shrink-0 flex-col bg-secondary text-secondary-foreground transition-all duration-300', open ? 'w-60' : 'w-[72px]')}>
        <div className="flex items-center gap-3 border-b border-white/10 px-4 py-5">
          <img src={logoImg} alt="Cauchos Rey" className="h-9 w-9 shrink-0 rounded-xl bg-black object-cover" />
          {open && <span className="font-display text-xs leading-snug font-semibold">Representaciones July<br />Cauchos Rey</span>}
        </div>
        <nav className="flex flex-1 flex-col gap-1 px-2 py-4">{items.map(link)}</nav>
        <div className="flex flex-col gap-1 px-2 pb-2">
          {link(all[all.length - 1])}
          <button onClick={() => logout()} title="Cerrar sesión"
            className="flex w-full cursor-pointer items-center gap-3 rounded-lg border-none bg-transparent px-3 py-2.5 text-left text-sm text-secondary-foreground/70 hover:bg-white/10">
            <LogOut size={18} strokeWidth={1.8} className="shrink-0" />
            {open && <span>Cerrar sesión</span>}
          </button>
        </div>
        {open && <div className="border-t border-white/5 px-4 py-4 text-xs text-secondary-foreground/35">v1.0.0</div>}
      </aside>

      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <header className="flex shrink-0 items-center justify-between border-b border-border bg-card px-6 py-3">
          <div className="flex items-center gap-4">
            <button aria-label={open ? 'Contraer menú' : 'Expandir menú'} onClick={() => setOpen(o => !o)}
              className="cursor-pointer rounded-lg border-none bg-transparent p-2 text-muted-foreground hover:bg-muted">
              {open ? <X size={20} /> : <Menu size={20} />}
            </button>
            <div>
              <h1 className="m-0 text-lg font-bold">{current.label}</h1>
              <p className="m-0 text-xs text-muted-foreground">{subtitle}</p>
            </div>
          </div>
          <div className="flex items-center gap-2 rounded-xl bg-muted px-3 py-1.5">
            <div className="flex h-[30px] w-[30px] items-center justify-center rounded-full bg-primary font-display text-[13px] font-bold text-white">
              {user.nombre_completo.charAt(0).toUpperCase()}
            </div>
            <div>
              <div className="font-display text-[13px] font-semibold">{user.nombre_completo}</div>
              <div className="text-[11px] text-muted-foreground">{user.correo}</div>
            </div>
          </div>
        </header>
        <main className="flex min-w-0 flex-1 flex-col overflow-y-auto p-6">
          <React.Suspense fallback={<Spinner />}>
            <Outlet />
          </React.Suspense>
        </main>
      </div>
    </div>
  )
}
