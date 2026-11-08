import React from 'react'
import { Database, FileText, Settings, UserRound } from 'lucide-react'

function Card({ icon, iconBg, title, children }: { icon: React.ReactNode; iconBg: string; title: string; children: React.ReactNode }) {
  return (
    <div className="card flex flex-col gap-3.5 !rounded-[14px] p-6">
      <div className="flex items-center gap-3.5">
        <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl" style={{ background: iconBg }}>{icon}</div>
        <h3 className="m-0 text-[17px] font-bold">{title}</h3>
      </div>
      {children}
    </div>
  )
}

const ReactLogo = () => (
  <svg viewBox="-11.5 -10.232 23 20.463" width={36} height={36} aria-hidden>
    <circle r="2.05" fill="#61dafb" />
    <g fill="none" stroke="#61dafb" strokeWidth="1">
      <ellipse rx="11" ry="4.2" /><ellipse rx="11" ry="4.2" transform="rotate(60)" /><ellipse rx="11" ry="4.2" transform="rotate(120)" />
    </g>
  </svg>
)

const PythonLogo = () => (
  <svg viewBox="0 0 48 48" width={36} height={36} aria-hidden>
    <path d="M24 3.5c-5 0-8.5 1-10 3.5-1 1.5-1 3-1 4.5v3h11v2H9.5c-3 0-6 1.8-7 6.5-.8 4.5-.8 7 0 11.5C3.5 37.5 5 40 8 40h4v-5.5c0-3.5 3-6.5 6.5-6.5h11c3 0 5.5-2.5 5.5-5.5V12c0-3-2.5-5.5-5.5-5.5H24zm-6.5 3.5c1 0 2 .9 2 2s-.9 2-2 2-2-.9-2-2 .9-2 2-2z" fill="#3776ab" />
    <path d="M37.5 8h-4v5.5c0 3.5-3 6.5-6.5 6.5h-11c-3 0-5.5 2.5-5.5 5.5V36c0 3 2.5 5.5 5.5 5.5H24c5 0 8.5-1 10-3.5 1-1.5 1-3 1-4.5v-3H24v-2h14.5c3 0 6-1.8 7-6.5.8-4.5.8-7 0-11.5C44.5 10.5 43 8 40 8h-2.5zm-6.5 29.5c-1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2z" fill="#ffd43b" />
  </svg>
)

export default function AcercaDe() {
  return (
    <div className="grid grid-cols-1 gap-5 pb-6 lg:grid-cols-2">
      <Card icon={<Settings size={26} className="text-gray-700" />} iconBg="#f0f0f0" title="Información del Software">
        <div>
          <p className="m-0 mb-1.5 font-display text-sm font-bold">Representaciones July Cauchos Rey – Sistema de Gestión</p>
          <p className="m-0 mb-2.5 text-[13px] leading-relaxed text-muted-foreground">
            Sistema de gestión en tiempo real para un establecimiento comercial único, basado en una plataforma web desacoplada y auditable.
          </p>
          <p className="m-0 text-[13px] text-muted-foreground"><span className="font-semibold text-foreground">Versión:</span> v1.0.0</p>
        </div>
        <div className="flex items-center gap-6">
          {[['React.js', <ReactLogo key="r" />], ['Python · FastAPI', <PythonLogo key="p" />], ['PostgreSQL', <Database key="d" size={34} className="text-[#336791]" />]].map(([label, logo]) => (
            <div key={String(label)} className="flex flex-col items-center gap-1.5">
              {logo}
              <span className="text-[11px] font-medium text-muted-foreground">{label}</span>
            </div>
          ))}
        </div>
      </Card>

      <div className="card flex flex-row gap-5 !rounded-[14px] p-6">
        <div className="flex flex-1 flex-col gap-3.5">
          <div className="flex items-center gap-3.5">
            <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-[#e0e7ff]"><UserRound size={26} className="text-primary" /></div>
            <h3 className="m-0 text-[17px] font-bold">Créditos de Desarrollo</h3>
          </div>
          <div className="flex flex-col gap-2 text-[13px]">
            <div><span className="font-bold">Desarrolladores: </span><span className="text-muted-foreground">David Gamboa · Jhonayker Parra</span></div>
            <div><span className="font-bold">Proyecto de Grado</span><span className="text-muted-foreground"> – Instituto Universitario de Tecnología (IUT) del Táchira, Venezuela</span></div>
            <div><span className="font-bold">Año de Finalización: </span><span className="text-muted-foreground">2026</span></div>
          </div>
        </div>
        <div className="flex h-20 w-20 shrink-0 items-center justify-center self-center rounded-full border-[3px] border-secondary bg-secondary text-center">
          <div>
            <div className="font-display text-[13px] leading-tight font-extrabold text-white">IUT</div>
            <div className="mt-0.5 font-display text-[8px] leading-tight text-secondary-foreground">TÁCHIRA</div>
          </div>
        </div>
      </div>

      <Card icon={<FileText size={26} className="text-success" />} iconBg="#d1fae5" title="Recursos y Soporte">
        <button className="btn-primary w-full !py-3" disabled title="El manual de usuario aún no está disponible">
          Descargar Manual de Usuario (PDF) · próximamente
        </button>
        <div className="text-[13px] text-muted-foreground">
          <span className="font-semibold text-foreground">Correo de Soporte: </span>soporte@tesiscauchosrey.com.ve
        </div>
      </Card>
    </div>
  )
}
