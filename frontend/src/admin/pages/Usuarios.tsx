import React from 'react'
import { useQuery } from '@tanstack/react-query'
import { Download, KeyRound, Pencil, Plus, PowerOff, Trash2 } from 'lucide-react'
import { ApiError } from '@/api/client'
import { categoriasApi, finanzasApi, usuariosApi, ventasApi } from '@/api/endpoints'
import { keys, useApiMutation, useCategorias } from '@/api/queries'
import type { Usuario } from '@/api/types'
import { useCurrentUser } from '@/auth/AuthContext'
import { useTasas } from '@/shared/components/productos'
import { Badge, ConfirmDialog, EmptyState, ErrorBanner, Field, Modal, PasswordInput, QueryState, Spinner, errorText, useToast } from '@/shared/components/ui'
import { fmtHora, todayIso } from '@/shared/lib/dates'
import { fmtTasa, num, parseDecimal, usd } from '@/shared/lib/money'
import { pdfHistorialDia } from '@/shared/lib/pdf'

const COLORS = ['#4f46e5', '#06b6d4', '#10b981', '#f59e0b', '#f43f5e', '#8b5cf6']
const colorDe = (id: number) => COLORS[id % COLORS.length]

/** Tarjeta editable de una tasa (Bs./USD o COP/USD); al guardar crea una tasa nueva. */
function TasaCard({ codigo, titulo }: { codigo: 'VES' | 'COP'; titulo: string }) {
  const toast = useToast()
  const { tasas, ves, cop } = useTasas()
  const query = codigo === 'VES' ? ves : cop
  const actual = tasas[codigo]
  const [edit, setEdit] = React.useState(false)
  const [tmp, setTmp] = React.useState('')
  const guardar = useApiMutation((v: string) => finanzasApi.setTasa(codigo, v), [keys.tasas, keys.productos], () => {
    setEdit(false)
    toast(`Tasa ${codigo} actualizada.`)
  })
  const submit = () => {
    const v = parseDecimal(tmp)
    if (!(v > 0)) return toast('Ingrese una tasa mayor que 0.', 'error')
    guardar.mutate(String(v), { onError: e => toast(errorText(e), 'error') })
  }
  return (
    <div className="card !rounded-[14px] px-4 py-3">
      <div className="mb-2 text-[11px] font-semibold text-muted-foreground">{titulo}</div>
      <div className="flex items-center gap-2.5">
        {edit ? (
          <input autoFocus aria-label={`Nueva tasa ${codigo}`} className="input !w-32 !border-primary !bg-card !py-1 font-display !text-xl font-bold"
            value={tmp} onChange={e => setTmp(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') submit(); if (e.key === 'Escape') setEdit(false) }} />
        ) : (
          <span className="font-display text-2xl font-extrabold">
            {query.isLoading ? '…' : actual === null ? 'Sin tasa' : `${codigo === 'VES' ? 'Bs.' : 'COP'} ${fmtTasa(actual, codigo)}`}
          </span>
        )}
        <button aria-label="Editar tasa" className="btn-icon" onClick={() => { setTmp(actual ? String(actual) : ''); setEdit(e => !e) }}><Pencil size={12} /></button>
        {edit && <button className="btn-success !px-3 !py-1 text-[11px]" onClick={submit} disabled={guardar.isPending}>Guardar</button>}
      </div>
    </div>
  )
}

/** Porcentaje de ganancia por categoría (recalcula precios de productos sin margen propio). */
function MargenCard() {
  const toast = useToast()
  const categorias = useCategorias()
  const [sel, setSel] = React.useState<number | null>(null)
  const [edit, setEdit] = React.useState(false)
  const [tmp, setTmp] = React.useState('')
  const cat = categorias.data?.find(c => c.id_categoria === sel) ?? categorias.data?.[0]
  const guardar = useApiMutation((v: string) => categoriasApi.update(cat!.id_categoria, { margen_ganancia: v }),
    [keys.categorias, keys.productos], () => { setEdit(false); toast(`Margen de ${cat?.nombre} actualizado; precios recalculados.`) })
  const valor = parseDecimal(tmp)
  const excesivo = tmp.trim() !== '' && valor >= 100
  const submit = () => {
    if (!(valor >= 0) || valor > 999.99) return toast('Ingrese un porcentaje entre 0 y 999.99.', 'error')
    guardar.mutate(String(valor), { onError: e => toast(errorText(e), 'error') })
  }
  return (
    <div className="card flex min-w-[250px] flex-col overflow-hidden !rounded-[14px]">
      <div className="flex items-center gap-2.5 border-b border-border px-4 py-2.5">
        <span className="text-[11px] font-semibold text-muted-foreground">Categoría</span>
        <select aria-label="Categoría del margen" className="input flex-1 !py-1 font-display font-bold" value={cat?.id_categoria ?? ''}
          onChange={e => { setSel(Number(e.target.value)); setEdit(false) }}>
          {categorias.data?.map(c => <option key={c.id_categoria} value={c.id_categoria}>{c.nombre}</option>)}
        </select>
      </div>
      <div className="flex items-center gap-2.5 px-4 py-2.5">
        {edit ? (
          <input autoFocus aria-label="Nuevo margen" className={`input !w-20 !bg-card !py-1 font-display !text-xl font-bold ${excesivo ? '!border-red-600' : '!border-primary'}`}
            value={tmp} onChange={e => setTmp(e.target.value)} onKeyDown={e => { if (e.key === 'Enter') submit(); if (e.key === 'Escape') setEdit(false) }} />
        ) : (
          <span className="font-display text-2xl font-extrabold">{cat ? `${num(cat.margen_ganancia)}%` : '…'}</span>
        )}
        <button aria-label="Editar margen" className="btn-icon" disabled={!cat} onClick={() => { setTmp(cat ? String(num(cat.margen_ganancia)) : ''); setEdit(e => !e) }}><Pencil size={12} /></button>
        {edit && <button className="btn-success ml-auto !px-3 !py-1 text-[11px]" onClick={submit} disabled={guardar.isPending}>Guardar</button>}
      </div>
      {edit && (
        <div className={`px-4 pb-2.5 text-[11px] ${excesivo ? 'text-red-600' : 'text-muted-foreground'}`}>
          {excesivo ? 'Advertencia: el porcentaje ingresado representa una cantidad desproporcionada.' : '0% = precios manuales (no se recalculan).'}
        </div>
      )}
    </div>
  )
}

function VentasHoy() {
  const hoy = todayIso()
  const toast = useToast()
  const { tasas } = useTasas()
  const ventas = useQuery({ queryKey: [...keys.ventas, 'dia', hoy], queryFn: () => ventasApi.list({ dia: hoy, limite: 1000 }) })
  const [pdf, setPdf] = React.useState(false)
  const lineas = (ventas.data ?? []).filter(v => v.estado !== 'Anulada').flatMap(v => v.detalles.map(d => ({ v, d })))
  const descargar = async () => {
    setPdf(true)
    try { await pdfHistorialDia(ventas.data ?? [], tasas.VES) } catch (e) { toast(errorText(e), 'error') } finally { setPdf(false) }
  }
  return (
    <div className="card flex min-h-[360px] flex-col overflow-hidden">
      <div className="flex shrink-0 items-center justify-between gap-3 border-b border-border px-[18px] py-3.5">
        <div>
          <h3 className="m-0 text-sm font-bold">Productos vendidos hoy</h3>
          <p className="mt-0.5 mb-0 text-[11px] text-muted-foreground">Registro de ventas por cajero</p>
        </div>
        <button className="btn-primary !px-3 !py-1.5 text-xs" onClick={descargar} disabled={pdf || lineas.length === 0}>
          <Download size={13} /> {pdf ? 'Generando...' : 'Descargar PDF'}
        </button>
      </div>
      <div className="flex-1 overflow-y-auto">
        <QueryState query={ventas}>
          {() => lineas.length === 0 ? <EmptyState title="Aún no hay ventas hoy." /> : lineas.map(({ v, d }, i) => (
            <div key={`${v.id_venta}-${d.id_detalle}`} className={`flex flex-col gap-1 border-b border-border px-[18px] py-3 ${i % 2 ? 'bg-muted' : 'bg-card'}`}>
              <div className="flex items-center justify-between gap-2">
                <span className="text-[13px] font-bold">
                  <span className="mr-2 rounded-md border border-border bg-muted px-1.5 py-0.5 font-mono text-[10px] font-bold text-primary">{v.numero_factura}</span>
                  {d.nombre_producto_snapshot}
                </span>
                <span className="font-display text-[13px] font-extrabold text-primary">{usd(d.subtotal_usd)}</span>
              </div>
              <span className="text-[11px] text-muted-foreground">Cant. {d.cantidad} · {usd(d.precio_unitario_usd)} c/u · pago en {v.codigo_moneda_pago}</span>
              <div className="mt-0.5 flex items-center justify-between">
                <div className="flex items-center gap-1.5">
                  <div className="flex h-5 w-5 items-center justify-center rounded-full text-[10px] font-bold text-white" style={{ background: colorDe(v.id_usuario) }}>
                    {(v.nombre_usuario ?? '?').charAt(0)}
                  </div>
                  <span className="text-[11px] font-semibold" style={{ color: colorDe(v.id_usuario) }}>Vendido por {v.nombre_usuario}</span>
                </div>
                <span className="text-[10px] text-muted-foreground">Hoy {fmtHora(v.fecha_venta)}</span>
              </div>
            </div>
          ))}
        </QueryState>
      </div>
    </div>
  )
}

type FormUsuario = { nombre_completo: string; correo: string; password: string; telefono: string; permisos: string }

function UsuarioModal({ editar, onClose }: { editar: Usuario | null; onClose: () => void }) {
  const toast = useToast()
  const [form, setForm] = React.useState<FormUsuario>({
    nombre_completo: editar?.nombre_completo ?? '', correo: editar?.correo ?? '', password: '',
    telefono: editar?.telefono ?? '', permisos: editar?.permisos ?? '',
  })
  const set = (k: keyof FormUsuario) => (e: React.ChangeEvent<HTMLInputElement>) => setForm(f => ({ ...f, [k]: e.target.value }))
  const guardar = useApiMutation(async () => {
    const base = {
      nombre_completo: form.nombre_completo.trim(), correo: form.correo.trim(),
      telefono: form.telefono.trim() || null, permisos: form.permisos.trim() || null,
    }
    return editar ? usuariosApi.update(editar.id_usuario, base) : usuariosApi.create({ ...base, password: form.password, rol: 'cashier' })
  }, [keys.usuarios], () => { toast(editar ? 'Usuario actualizado.' : 'Cajero creado.'); onClose() })
  const invalido = form.nombre_completo.trim().length < 3 || !form.correo.includes('@') || (!editar && form.password.length < 8)
  return (
    <Modal title={editar ? 'Editar usuario' : 'Nuevo cajero'} onClose={onClose} footer={<>
      <button className="btn-muted" onClick={onClose}>Cancelar</button>
      <button className="btn-primary" disabled={invalido || guardar.isPending} onClick={() => guardar.mutate(undefined)}>
        {guardar.isPending ? 'Guardando...' : 'Guardar'}
      </button>
    </>}>
      <div className="flex flex-col gap-3.5">
        <Field label="Nombre completo"><input className="input" value={form.nombre_completo} onChange={set('nombre_completo')} autoFocus /></Field>
        <Field label="Correo"><input className="input" type="email" value={form.correo} onChange={set('correo')} /></Field>
        {/* La contraseña no se muestra al editar (plans/ocultar-contrasena-al-editar-usuario.md). */}
        {!editar && (
          <Field label="Contraseña" hint="Mínimo 8 caracteres.">
            <PasswordInput autoComplete="new-password" value={form.password} onChange={set('password')} />
          </Field>
        )}
        <Field label="Teléfono"><input className="input" value={form.telefono} onChange={set('telefono')} /></Field>
        <Field label="Permisos (descripción)"><input className="input" placeholder="Ventas, apertura de caja..." value={form.permisos} onChange={set('permisos')} /></Field>
        {/* Solo se crean cajeros (plans/limitar-creacion-usuarios-a-cajeros.md). */}
        <Field label="Rol">
          <select className="input" disabled value={editar?.rol ?? 'cashier'}>
            <option value="cashier">Cajero</option>
            <option value="admin">Administrador</option>
          </select>
        </Field>
        {guardar.error && <ErrorBanner error={guardar.error} />}
      </div>
    </Modal>
  )
}

function PasswordModal({ usuario, onClose }: { usuario: Usuario; onClose: () => void }) {
  const toast = useToast()
  const [pw, setPw] = React.useState('')
  const [pw2, setPw2] = React.useState('')
  const [err, setErr] = React.useState('')
  const guardar = useApiMutation((p: string) => usuariosApi.resetPassword(usuario.id_usuario, p), [], () => {
    toast(`Contraseña de ${usuario.nombre_completo} actualizada.`); onClose()
  })
  const submit = () => {
    if (pw.length < 8) return setErr('La contraseña debe tener al menos 8 caracteres.')
    if (pw !== pw2) return setErr('Las contraseñas no coinciden.')
    guardar.mutate(pw, { onError: e => setErr(errorText(e)) })
  }
  return (
    <Modal title="Restablecer contraseña" subtitle={`Define una nueva contraseña para ${usuario.nombre_completo}.`} onClose={onClose} footer={<>
      <button className="btn-muted" onClick={onClose}>Cancelar</button>
      <button className="btn-primary" onClick={submit} disabled={guardar.isPending}>Actualizar contraseña</button>
    </>}>
      <div className="flex flex-col gap-3.5">
        <Field label="Nueva contraseña"><PasswordInput autoFocus autoComplete="new-password" placeholder="Mínimo 8 caracteres" value={pw} onChange={e => { setPw(e.target.value); setErr('') }} /></Field>
        <Field label="Confirmar contraseña"><PasswordInput className={err ? '!border-danger' : undefined} autoComplete="new-password" value={pw2}
          onChange={e => { setPw2(e.target.value); setErr('') }} onKeyDown={e => { if (e.key === 'Enter') submit() }} /></Field>
        {err && <p className="m-0 text-[11px] text-danger">{err}</p>}
      </div>
    </Modal>
  )
}

function UserCard({ u, esYo, onEdit, onReset, onToggle, onDelete }: {
  u: Usuario; esYo: boolean; onEdit: () => void; onReset: () => void; onToggle: () => void; onDelete: () => void
}) {
  const activo = u.estado === 1
  const rol = u.rol === 'admin' ? 'Administrador' : 'Cajero'
  const color = colorDe(u.id_usuario)
  return (
    <div className="card flex flex-col gap-3.5 p-5">
      <div className="flex items-center justify-between">
        <span className="font-display text-sm font-bold">{rol}{esYo && ' · Tú'}</span>
        <Badge tone={activo ? 'Activo' : 'Inactivo'}>{activo ? 'Activo' : 'Inactivo'}</Badge>
      </div>
      <div className="flex items-center gap-3">
        <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full font-display text-xl font-extrabold text-white" style={{ background: color }}>
          {u.nombre_completo.charAt(0).toUpperCase()}
        </div>
        <div className="min-w-0">
          <div className="font-display text-[15px] font-bold">{u.nombre_completo}</div>
          <div className="mt-0.5 truncate text-xs text-muted-foreground">{u.correo}{u.telefono && ` · ${u.telefono}`}</div>
          {u.permisos && <div className="mt-0.5 text-[11px] text-muted-foreground">{u.permisos}</div>}
        </div>
      </div>
      <div className="flex flex-wrap gap-2">
        <button className="btn-primary !px-3.5 !py-1.5 text-xs" onClick={onEdit}><Pencil size={12} /> Editar</button>
        <button className="btn-muted !px-3.5 !py-1.5 text-xs" onClick={onReset}><KeyRound size={12} /> Restablecer contraseña</button>
        {!esYo && (
          <button className={`${activo ? 'btn-danger' : 'btn-success'} !px-3.5 !py-1.5 text-xs`} onClick={onToggle}>
            <PowerOff size={12} /> {activo ? 'Desactivar' : 'Activar'}
          </button>
        )}
        {!esYo && (
          <button className="btn ml-auto border border-danger/25 bg-danger/10 !px-3.5 !py-1.5 text-xs text-danger" onClick={onDelete}>
            <Trash2 size={12} /> Eliminar
          </button>
        )}
      </div>
    </div>
  )
}

export default function Usuarios() {
  const yo = useCurrentUser()
  const toast = useToast()
  const usuarios = useQuery({ queryKey: keys.usuarios, queryFn: usuariosApi.list })
  const [modal, setModal] = React.useState<{ editar: Usuario | null } | null>(null)
  const [reset, setReset] = React.useState<Usuario | null>(null)
  const [borrar, setBorrar] = React.useState<Usuario | null>(null)
  const toggle = useApiMutation((u: Usuario) => usuariosApi.setActivo(u.id_usuario, u.estado !== 1), [keys.usuarios],
    u => toast(`${u.nombre_completo} ${u.estado === 1 ? 'activado' : 'desactivado'}.`))
  const eliminar = useApiMutation((u: Usuario) => usuariosApi.remove(u.id_usuario), [keys.usuarios], () => {
    toast('Usuario eliminado.'); setBorrar(null)
  })

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-3">
        <TasaCard codigo="VES" titulo="Bolívares por Dólar" />
        <TasaCard codigo="COP" titulo="Pesos por Dólar" />
        <MargenCard />
        <button className="btn-primary ml-auto !px-[18px] !py-2.5 shadow-md" onClick={() => setModal({ editar: null })}>
          <Plus size={15} /> Nuevo Cajero
        </button>
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <VentasHoy />
        <div className="card flex flex-col overflow-hidden">
          <div className="shrink-0 border-b border-border px-[18px] py-3.5">
            <h3 className="m-0 text-sm font-bold">Usuarios</h3>
            <p className="mt-0.5 mb-0 text-[11px] text-muted-foreground">{usuarios.data?.length ?? 0} miembros registrados</p>
          </div>
          <div className="flex max-h-[640px] flex-col gap-2.5 overflow-y-auto p-3">
            {usuarios.isLoading ? <Spinner /> : usuarios.error ? <ErrorBanner error={usuarios.error} onRetry={() => usuarios.refetch()} /> :
              usuarios.data?.map(u => (
                <UserCard key={u.id_usuario} u={u} esYo={u.id_usuario === yo.id_usuario}
                  onEdit={() => setModal({ editar: u })} onReset={() => setReset(u)}
                  onToggle={() => toggle.mutate(u, { onError: e => toast(errorText(e), 'error') })}
                  onDelete={() => setBorrar(u)} />
              ))}
          </div>
        </div>
      </div>

      {modal && <UsuarioModal editar={modal.editar} onClose={() => setModal(null)} />}
      {reset && <PasswordModal usuario={reset} onClose={() => setReset(null)} />}
      {borrar && (
        <ConfirmDialog danger title="Eliminar usuario" confirmText="Eliminar" busy={eliminar.isPending}
          message={<>
            ¿Eliminar a <b>{borrar.nombre_completo}</b>? Solo se puede eliminar si no tiene ventas ni compras registradas.
            {eliminar.error instanceof ApiError && eliminar.error.status === 409 && (
              <div className="mt-3 flex flex-col gap-2">
                <ErrorBanner error={eliminar.error} />
                {borrar.estado === 1 && (
                  <button className="btn-danger self-start" onClick={() => { toggle.mutate(borrar); setBorrar(null) }}>Desactivarlo en su lugar</button>
                )}
              </div>
            )}
            {eliminar.error && !(eliminar.error instanceof ApiError && eliminar.error.status === 409) && <div className="mt-3"><ErrorBanner error={eliminar.error} /></div>}
          </>}
          onConfirm={() => eliminar.mutate(borrar)} onClose={() => { setBorrar(null); eliminar.reset() }} />
      )}
    </div>
  )
}
