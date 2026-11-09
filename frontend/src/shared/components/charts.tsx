import { Area, AreaChart, CartesianGrid, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

export const PALETTE = ['#4f46e5', '#06b6d4', '#10b981', '#f59e0b', '#f43f5e', '#8b5cf6', '#ec4899']

const tooltipStyle = { background: 'var(--card)', border: '1px solid var(--border)', borderRadius: 8, fontSize: 12 }

export function AreaSerie({ data, color = '#4f46e5', id, unit }: { data: { label: string; value: number }[]; color?: string; id: string; unit?: string }) {
  return (
    <div className="mt-3 h-[150px] w-full">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: -18 }}>
          <defs>
            <linearGradient id={id} x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor={color} stopOpacity={0.25} />
              <stop offset="95%" stopColor={color} stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
          <XAxis dataKey="label" tick={{ fontSize: 10, fill: 'var(--muted-foreground)' }} />
          <YAxis tick={{ fontSize: 10, fill: 'var(--muted-foreground)' }} allowDecimals={false} />
          <Tooltip contentStyle={tooltipStyle} formatter={v => [`${v}${unit ?? ''}`, '']} />
          <Area type="monotone" dataKey="value" stroke={color} strokeWidth={2} fill={`url(#${id})`} dot={false} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}

/** Dona con leyenda a la derecha; `format` da el texto del valor. */
export function Donut({ data, format = v => String(v), size = 140 }: {
  data: { name: string; value: number }[]
  format?: (v: number) => string
  size?: number
}) {
  const total = data.reduce((t, d) => t + d.value, 0)
  return (
    <div className="flex min-h-0 items-center gap-3">
      <div className="shrink-0" style={{ width: size, height: size }}>
        <PieChart width={size} height={size}>
          <Pie data={total > 0 ? data : [{ name: 'Sin datos', value: 1 }]} cx="50%" cy="50%" innerRadius={size * 0.29} outerRadius={size * 0.41} paddingAngle={total > 0 ? 3 : 0} dataKey="value" strokeWidth={0}>
            {(total > 0 ? data : [0]).map((_, i) => <Cell key={i} fill={total > 0 ? PALETTE[i % PALETTE.length] : 'var(--border)'} />)}
          </Pie>
          {total > 0 && <Tooltip contentStyle={tooltipStyle} formatter={v => [format(Number(v)), '']} />}
        </PieChart>
      </div>
      <div className="max-h-[220px] min-w-0 flex-1 overflow-y-auto rounded-xl border border-border bg-muted">
        {data.length === 0 && <div className="p-3 text-xs text-muted-foreground">Sin datos en el período.</div>}
        {data.map((d, i) => (
          <div key={d.name} className="flex items-center justify-between gap-2 border-b border-border px-2.5 py-[7px] last:border-b-0">
            <div className="flex min-w-0 items-center gap-2">
              <span className="h-[9px] w-[9px] shrink-0 rounded-full" style={{ background: PALETTE[i % PALETTE.length] }} />
              <span className="truncate text-[11px] font-medium">{d.name}</span>
            </div>
            <span className="text-[11px] font-bold" style={{ color: PALETTE[i % PALETTE.length] }}>{format(d.value)}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
