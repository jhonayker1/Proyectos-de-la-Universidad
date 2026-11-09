/** Componentes básicos reutilizados por los paneles de admin y cajero. */
import React from 'react'
import { AlertTriangle, ChevronDown, Loader2, TrendingDown, TrendingUp, X } from 'lucide-react'
import { ApiError } from '@/api/client'

export const cx = (...c: (string | false | null | undefined)[]) => c.filter(Boolean).join(' ')

export function errorText(e: unknown) {
  if (e instanceof ApiError || e instanceof Error) return e.message
  return 'Ocurrió un error inesperado.'
}

export function Spinner({ label = 'Cargando...', className }: { label?: string; className?: string }) {
  return (
    <div className={cx('flex items-center justify-center gap-2 p-8 text-sm text-muted-foreground', className)}>
      <Loader2 size={16} className="animate-spin" /> {label}
    </div>
  )
}

export function ErrorBanner({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  if (!error) return null
  return (
    <div role="alert" className="flex items-center gap-3 rounded-xl border border-danger/30 bg-danger/10 px-4 py-3 text-[13px] text-danger">
      <AlertTriangle size={16} className="shrink-0" />
      <span className="flex-1">{errorText(error)}</span>
      {onRetry && <button className="btn-muted !py-1 text-xs" onClick={onRetry}>Reintentar</button>}
    </div>
  )
}

/** Muestra carga/error de una consulta y, si hay datos, renderiza children. */
export function QueryState<T>({ query, children, label }: {
  query: { data: T | undefined; isLoading: boolean; error: unknown; refetch: () => unknown }
  children: (data: T) => React.ReactNode
  label?: string
}) {
  if (query.isLoading) return <Spinner label={label} />
  if (query.error) return <ErrorBanner error={query.error} onRetry={() => query.refetch()} />
  if (query.data === undefined) return null
  return <>{children(query.data)}</>
}

export function EmptyState({ icon, title, hint }: { icon?: React.ReactNode; title: string; hint?: React.ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 p-8 text-center text-[13px] text-muted-foreground">
      {icon && <div className="opacity-50">{icon}</div>}
      <div className="font-semibold">{title}</div>
      {hint && <div className="text-xs">{hint}</div>}
    </div>
  )
}

export function Modal({ title, subtitle, onClose, children, footer, width = 'max-w-md' }: {
  title: string
  subtitle?: string
  onClose: () => void
  children: React.ReactNode
  footer?: React.ReactNode
  width?: string
}) {
  React.useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/45 p-4" onMouseDown={e => { if (e.target === e.currentTarget) onClose() }}>
      <div role="dialog" aria-modal="true" aria-label={title} className={cx('max-h-[92vh] w-full overflow-y-auto rounded-2xl border border-border bg-card p-7 shadow-2xl', width)}>
        <div className="mb-5 flex items-start justify-between gap-4">
          <div>
            <h3 className="m-0 text-[17px] font-bold">{title}</h3>
            {subtitle && <p className="mt-1 text-xs text-muted-foreground">{subtitle}</p>}
          </div>
          <button aria-label="Cerrar" className="btn-icon border-none" onClick={onClose}><X size={16} /></button>
        </div>
        {children}
        {footer && <div className="mt-5 flex justify-end gap-2.5">{footer}</div>}
      </div>
    </div>
  )
}

export function ConfirmDialog({ title, message, confirmText = 'Confirmar', danger, busy, onConfirm, onClose }: {
  title: string
  message: React.ReactNode
  confirmText?: string
  danger?: boolean
  busy?: boolean
  onConfirm: () => void
  onClose: () => void
}) {
  return (
    <Modal title={title} onClose={onClose} footer={<>
      <button className="btn-muted" onClick={onClose} disabled={busy}>Cancelar</button>
      <button className={danger ? 'btn-danger' : 'btn-primary'} onClick={onConfirm} disabled={busy}>
        {busy ? 'Procesando...' : confirmText}
      </button>
    </>}>
      <div className="text-[13px] text-muted-foreground">{message}</div>
    </Modal>
  )
}

export function Field({ label, children, className, hint }: { label: string; children: React.ReactNode; className?: string; hint?: React.ReactNode }) {
  return (
    <label className={cx('block', className)}>
      <span className="label">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-[11px] text-muted-foreground">{hint}</span>}
    </label>
  )
}

const ESTADO_COLORS: Record<string, string> = {
  Disponible: 'bg-success/15 text-success',
  'Bajo Stock': 'bg-warning/15 text-warning',
  Agotado: 'bg-danger/15 text-danger',
  Inactivo: 'bg-muted text-muted-foreground',
  Completada: 'bg-success/15 text-success',
  Anulada: 'bg-danger/15 text-danger',
  Activo: 'bg-success/15 text-success',
  Pagada: 'bg-success/15 text-success',
  Pendiente: 'bg-danger/15 text-danger',
}

export function Badge({ children, tone }: { children: React.ReactNode; tone?: string }) {
  const key = tone ?? String(children)
  return (
    <span className={cx('inline-block rounded-full px-3 py-0.5 text-[11px] font-bold whitespace-nowrap', ESTADO_COLORS[key] ?? 'bg-primary/10 text-primary')}>
      {children}
    </span>
  )
}

export function KpiCard({ label, value, sub, up, color }: { label: string; value: string; sub?: string; up?: boolean; color: string }) {
  return (
    <div className="card flex flex-col gap-3 p-5">
      <div className="flex items-center justify-between">
        <span className="text-[13px] font-medium text-muted-foreground">{label}</span>
        <div className="rounded-lg p-1.5" style={{ background: `${color}18` }}>
          <TrendingUp size={14} style={{ color }} />
        </div>
      </div>
      <div className="font-display text-[28px] leading-none font-bold">{value}</div>
      {sub && (
        <div className={cx('flex items-center gap-1.5 text-xs font-medium', up === false ? 'text-danger' : up ? 'text-success' : 'text-muted-foreground')}>
          {up === true && <TrendingUp size={13} />}
          {up === false && <TrendingDown size={13} />}
          {sub}
        </div>
      )}
    </div>
  )
}

export function StatBox({ label, value, color, className }: { label: string; value: React.ReactNode; color?: string; className?: string }) {
  return (
    <div className={cx('stat', className)}>
      <div className="mb-1.5 text-xs text-muted-foreground">{label}</div>
      <div className="font-display text-[22px] font-extrabold" style={{ color: color ?? 'var(--foreground)' }}>{value}</div>
    </div>
  )
}

export function Accordion({ title, children, defaultOpen = false, right }: { title: string; children: React.ReactNode; defaultOpen?: boolean; right?: React.ReactNode }) {
  const [open, setOpen] = React.useState(defaultOpen)
  return (
    <div className="overflow-hidden rounded-xl border border-border bg-card">
      <div className="flex items-center">
        <button aria-expanded={open} onClick={() => setOpen(o => !o)} className="flex flex-1 cursor-pointer items-center justify-between border-none bg-transparent px-[18px] py-3.5 text-left font-display text-sm font-bold text-foreground">
          {title}
          <ChevronDown size={18} className={cx('text-muted-foreground transition-transform', open && 'rotate-180')} />
        </button>
        {right && <div className="pr-4">{right}</div>}
      </div>
      {open && <div className="border-t border-border px-[18px] pb-[18px]">{children}</div>}
    </div>
  )
}

export function Tabs<T extends string>({ value, options, onChange, className }: { value: T; options: readonly T[]; onChange: (v: T) => void; className?: string }) {
  return (
    <div className={cx('flex flex-wrap gap-1.5', className)} role="tablist">
      {options.map(o => (
        <button key={o} role="tab" aria-selected={value === o} onClick={() => onChange(o)}
          className={cx('cursor-pointer rounded-lg border-none px-3.5 py-1.5 font-display text-xs font-semibold', value === o ? 'bg-primary text-white' : 'bg-muted text-muted-foreground hover:bg-border')}>
          {o}
        </button>
      ))}
    </div>
  )
}

export function Pagination({ page, total, onChange }: { page: number; total: number; onChange: (p: number) => void }) {
  if (total <= 1) return null
  const pages = Array.from({ length: total }, (_, i) => i + 1).filter(n => n === 1 || n === total || Math.abs(n - page) <= 1)
  return (
    <div className="flex items-center gap-1.5">
      <span className="mr-1 text-[13px] text-muted-foreground">Páginas:</span>
      <button className="btn-muted !px-3 !py-1" disabled={page === 1} onClick={() => onChange(page - 1)}>Anterior</button>
      {pages.map((n, i) => (
        <React.Fragment key={n}>
          {i > 0 && n - pages[i - 1] > 1 && <span className="text-muted-foreground">…</span>}
          <button onClick={() => onChange(n)} aria-current={page === n ? 'page' : undefined}
            className={cx('h-[30px] w-[30px] cursor-pointer rounded-md font-display text-[13px] font-semibold', page === n ? 'border-none bg-primary text-white' : 'border border-border bg-card')}>
            {n}
          </button>
        </React.Fragment>
      ))}
      <button className="btn-muted !px-3 !py-1" disabled={page === total} onClick={() => onChange(page + 1)}>Siguiente</button>
    </div>
  )
}

/** Avisos breves de éxito o error en la esquina de la pantalla. */
type Toast = { id: number; text: string; tone: 'ok' | 'error' }
const ToastContext = React.createContext<(text: string, tone?: Toast['tone']) => void>(() => {})

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = React.useState<Toast[]>([])
  const push = React.useCallback((text: string, tone: Toast['tone'] = 'ok') => {
    const id = Date.now() + Math.random()
    setToasts(t => [...t, { id, text, tone }])
    window.setTimeout(() => setToasts(t => t.filter(x => x.id !== id)), 4500)
  }, [])
  return (
    <ToastContext.Provider value={push}>
      {children}
      <div className="pointer-events-none fixed right-4 bottom-4 z-[60] flex flex-col gap-2" aria-live="polite">
        {toasts.map(t => (
          <div key={t.id} className={cx('rounded-xl px-4 py-3 text-[13px] font-semibold text-white shadow-lg', t.tone === 'ok' ? 'bg-success' : 'bg-danger')}>
            {t.text}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}

export const useToast = () => React.useContext(ToastContext)
