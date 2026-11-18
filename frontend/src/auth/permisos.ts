/**
 * Qué puede hacer cada rol en las pantallas compartidas (refleja app/core/permisos.py).
 * Solo oculta botones: el backend vuelve a validar cada acción y responde 403.
 */
import { useCurrentUser } from './AuthContext'

export function permisosDe(rol: string | null) {
  const admin = rol === 'admin'
  return {
    /** Configuración, borrados irreversibles y contabilidad: solo el administrador. */
    eliminarProductos: admin,
    eliminarProveedores: admin,
    marcarPagos: admin,
    anularVentas: admin,
    borrarFacturas: admin,
    editarCategorias: admin,
    /** Base para las rutas de las pantallas (accesos directos del panel). */
    base: admin ? '/admin' : rol === 'gestor' ? '/gestor' : '/cajero',
  }
}

export function usePermisos() {
  return permisosDe(useCurrentUser().rol)
}
