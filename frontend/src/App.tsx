import React from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { BarChart2, LayoutDashboard, Package, ShieldCheck, ShoppingCart, Tags, Truck, Users } from 'lucide-react'
import { homeFor, useAuth } from '@/auth/AuthContext'
import LoginPage from '@/auth/LoginPage'
import RecuperarPage from '@/auth/RecuperarPage'
import RequireRole from '@/auth/RequireRole'
import { CartProvider } from '@/cajero/CartContext'
import AppLayout, { type NavItem } from '@/shared/components/AppLayout'
import { Spinner } from '@/shared/components/ui'

// Cada pantalla se descarga al abrirla (los gráficos y PDF pesan bastante).
const Dashboard = React.lazy(() => import('@/admin/pages/Dashboard'))
const Usuarios = React.lazy(() => import('@/admin/pages/Usuarios'))
const AdminInventario = React.lazy(() => import('@/admin/pages/Inventario'))
const Reportes = React.lazy(() => import('@/admin/pages/Reportes'))
const Proveedores = React.lazy(() => import('@/admin/pages/Proveedores'))
const Catalogo = React.lazy(() => import('@/admin/pages/Catalogo'))
const Auditoria = React.lazy(() => import('@/admin/pages/Auditoria'))
const PuntoVenta = React.lazy(() => import('@/cajero/pages/PuntoVenta'))
const CajeroInventario = React.lazy(() => import('@/cajero/pages/Inventario'))
const MisVentas = React.lazy(() => import('@/cajero/pages/MisVentas'))
const AcercaDe = React.lazy(() => import('@/shared/pages/AcercaDe'))

const ADMIN_NAV: NavItem[] = [
  { to: '', label: 'Inicio', icon: LayoutDashboard },
  { to: 'usuarios', label: 'Usuarios', icon: Users },
  { to: 'inventario', label: 'Inventario', icon: Package },
  { to: 'catalogo', label: 'Catálogo', icon: Tags },
  { to: 'reportes', label: 'Reportes', icon: BarChart2 },
  { to: 'proveedores', label: 'Proveedores', icon: Truck },
  { to: 'auditoria', label: 'Auditoría', icon: ShieldCheck },
]

const CAJERO_NAV: NavItem[] = [
  { to: '', label: 'Punto de venta', icon: ShoppingCart },
  { to: 'inventario', label: 'Inventario', icon: Package },
  { to: 'ventas', label: 'Mis ventas', icon: BarChart2 },
]

function Home() {
  const { user, checking } = useAuth()
  if (checking) return <Spinner label="Verificando sesión..." className="h-screen" />
  return <Navigate to={user ? homeFor(user.rol) : '/login'} replace />
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/recuperar" element={<RecuperarPage />} />
      <Route element={<RequireRole rol="admin" />}>
        <Route path="/admin" element={<AppLayout items={ADMIN_NAV} base="/admin" subtitle="Panel de administración" />}>
          <Route index element={<Dashboard />} />
          <Route path="usuarios" element={<Usuarios />} />
          <Route path="inventario" element={<AdminInventario />} />
          <Route path="catalogo" element={<Catalogo />} />
          <Route path="reportes" element={<Reportes />} />
          <Route path="proveedores" element={<Proveedores />} />
          <Route path="auditoria" element={<Auditoria />} />
          <Route path="acerca" element={<AcercaDe />} />
        </Route>
      </Route>
      <Route element={<RequireRole rol="cashier" />}>
        <Route path="/cajero" element={<CartProvider><AppLayout items={CAJERO_NAV} base="/cajero" subtitle="Panel de cajero" /></CartProvider>}>
          <Route index element={<PuntoVenta />} />
          <Route path="inventario" element={<CajeroInventario />} />
          <Route path="ventas" element={<MisVentas />} />
          <Route path="acerca" element={<AcercaDe />} />
        </Route>
      </Route>
      <Route path="*" element={<Home />} />
    </Routes>
  )
}
