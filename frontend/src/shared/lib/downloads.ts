const BASE_DATOS = 'cauchos-rey-descargas'
const ALMACEN = 'carpetas'
const CLAVE_CARPETA = 'destino'

type PermisoCarpeta = 'granted' | 'denied' | 'prompt'
type ArchivoEscribible = {
  write: (contenido: Blob) => Promise<void>
  close: () => Promise<void>
  abort?: () => Promise<void>
}
type ArchivoHandle = { createWritable: () => Promise<ArchivoEscribible> }
type CarpetaHandle = {
  name: string
  getFileHandle: (nombre: string, opciones?: { create?: boolean }) => Promise<ArchivoHandle>
  queryPermission: (opciones: { mode: 'readwrite' }) => Promise<PermisoCarpeta>
  requestPermission: (opciones: { mode: 'readwrite' }) => Promise<PermisoCarpeta>
}
type VentanaConSelector = Window & {
  showDirectoryPicker?: (opciones: { id: string; mode: 'readwrite'; startIn: 'desktop' }) => Promise<CarpetaHandle>
}

function notificarDescarga(mensaje: string) {
  window.dispatchEvent(new CustomEvent('app-download-complete', { detail: mensaje }))
}

function descargarConNavegador(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const enlace = document.createElement('a')
  enlace.href = url
  enlace.download = filename
  enlace.style.display = 'none'
  document.body.append(enlace)
  enlace.click()
  enlace.remove()
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
  notificarDescarga(`Se solicitó la descarga de ${filename}. Revisa la lista de descargas del navegador.`)
}

function abrirBaseDatos(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const solicitud = indexedDB.open(BASE_DATOS, 1)
    solicitud.onupgradeneeded = () => solicitud.result.createObjectStore(ALMACEN)
    solicitud.onsuccess = () => resolve(solicitud.result)
    solicitud.onerror = () => reject(solicitud.error ?? new Error('No se pudo abrir el almacenamiento de descargas.'))
  })
}

async function leerCarpeta(): Promise<CarpetaHandle | null> {
  const db = await abrirBaseDatos()
  try {
    return await new Promise((resolve, reject) => {
      const tx = db.transaction(ALMACEN, 'readonly')
      const solicitud = tx.objectStore(ALMACEN).get(CLAVE_CARPETA)
      solicitud.onsuccess = () => resolve((solicitud.result as CarpetaHandle | undefined) ?? null)
      solicitud.onerror = () => reject(solicitud.error ?? new Error('No se pudo leer la carpeta de descargas.'))
    })
  } finally {
    db.close()
  }
}

async function guardarCarpeta(carpeta: CarpetaHandle): Promise<void> {
  const db = await abrirBaseDatos()
  try {
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction(ALMACEN, 'readwrite')
      tx.objectStore(ALMACEN).put(carpeta, CLAVE_CARPETA)
      tx.oncomplete = () => resolve()
      tx.onerror = () => reject(tx.error ?? new Error('No se pudo guardar la carpeta de descargas.'))
      tx.onabort = () => reject(tx.error ?? new Error('Se canceló el guardado de la carpeta de descargas.'))
    })
  } finally {
    db.close()
  }
}

export async function configurarCarpetaDescargas(): Promise<string> {
  if (!window.isSecureContext) {
    throw new Error('La selección de carpetas requiere una conexión segura (HTTPS o localhost).')
  }
  const browser = window as VentanaConSelector
  if (!browser.showDirectoryPicker) {
    throw new Error('Este navegador o vista previa no permite elegir carpetas. Abre la aplicación en Edge o Chrome actualizado.')
  }

  let carpeta: CarpetaHandle
  try {
    carpeta = await browser.showDirectoryPicker({
      id: 'cauchos-rey-descargas',
      mode: 'readwrite',
      startIn: 'desktop',
    })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new Error('No se seleccionó una carpeta de destino.')
    }
    throw error
  }

  const permiso = await carpeta.requestPermission({ mode: 'readwrite' })
  if (permiso !== 'granted') {
    throw new Error('No se concedió permiso para guardar archivos en la carpeta seleccionada.')
  }
  await guardarCarpeta(carpeta)
  return carpeta.name
}

function limpiarNombre(nombre: string) {
  const seguro = nombre.replace(/[<>:"/\\|?*\u0000-\u001f]/g, '_').trim()
  return seguro && seguro !== '.' && seguro !== '..' ? seguro : 'descarga'
}

async function crearArchivoSinReemplazar(carpeta: CarpetaHandle, nombre: string): Promise<ArchivoHandle> {
  const punto = nombre.lastIndexOf('.')
  const base = punto > 0 ? nombre.slice(0, punto) : nombre
  const extension = punto > 0 ? nombre.slice(punto) : ''
  let candidato = nombre
  let sufijo = 1
  while (true) {
    try {
      await carpeta.getFileHandle(candidato)
      candidato = `${base} (${sufijo++})${extension}`
    } catch (error) {
      if (error instanceof DOMException && error.name === 'NotFoundError') {
        return carpeta.getFileHandle(candidato, { create: true })
      }
      throw error
    }
  }
}

export async function saveBlob(blob: Blob, filename: string): Promise<void> {
  const nombre = limpiarNombre(filename)
  const browser = window as VentanaConSelector
  if (!window.isSecureContext || !browser.showDirectoryPicker) {
    descargarConNavegador(blob, nombre)
    return
  }

  const carpetaGuardada = await leerCarpeta()
  if (!carpetaGuardada) {
    descargarConNavegador(blob, nombre)
    return
  }
  if (await carpetaGuardada.queryPermission({ mode: 'readwrite' }) !== 'granted') {
    throw new Error('La carpeta requiere autorización. Vuelve a elegirla desde el menú lateral.')
  }
  const archivo = await crearArchivoSinReemplazar(carpetaGuardada, nombre)
  const escritura = await archivo.createWritable()
  try {
    await escritura.write(blob)
    await escritura.close()
    notificarDescarga(`Archivo guardado: ${nombre} en «${carpetaGuardada.name}».`)
  } catch (error) {
    try {
      await escritura.abort?.()
    } catch (errorAbortar) {
      throw new AggregateError([error, errorAbortar], 'No se pudo completar ni cancelar la escritura del archivo.')
    }
    throw error
  }
}
