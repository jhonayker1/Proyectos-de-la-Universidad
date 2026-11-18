import { saveBlob } from '@/api/client'

/** CSV separado por ";" con BOM (Excel en español abre bien los acentos). Ningún texto
 * se interpreta como fórmula al abrirlo. */
export function descargarCsv(nombre: string, encabezados: string[], filas: (string | number | null | undefined)[][]) {
  const celda = (v: string | number | null | undefined) => {
    let t = v === null || v === undefined ? '' : String(v)
    if (/^[=+\-@]/.test(t) && typeof v === 'string') t = `'${t}`
    return /[";\n]/.test(t) ? `"${t.replace(/"/g, '""')}"` : t
  }
  const texto = [encabezados, ...filas].map(f => f.map(celda).join(';')).join('\r\n')
  saveBlob(new Blob(['﻿' + texto], { type: 'text/csv;charset=utf-8' }), nombre)
}
