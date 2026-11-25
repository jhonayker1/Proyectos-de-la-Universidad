import { saveBlob } from './downloads'

type CsvValue = string | number | null | undefined

function celdaCsv(value: CsvValue): string {
  let text = value == null ? '' : String(value)
  if (/^[=+\-@]/.test(text)) text = `'${text}`
  return `"${text.replace(/"/g, '""')}"`
}

export async function descargarCsv(filename: string, headers: string[], rows: CsvValue[][]): Promise<void> {
  const contents = [headers, ...rows].map(row => row.map(celdaCsv).join(';')).join('\r\n')
  const blob = new Blob([`\uFEFF${contents}`], { type: 'text/csv;charset=utf-8' })
  await saveBlob(blob, filename)
}
