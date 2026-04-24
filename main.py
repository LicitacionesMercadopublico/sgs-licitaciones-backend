from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import httpx
import anthropic
import os
from datetime import datetime, timedelta
from typing import Optional

TICKET_MP = os.getenv("TICKET_MP", "F8537A18-6766-4DEF-9E59-426B4FEE2844")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip().replace("\n", "").replace("\r", "").replace(" ", "")
MP_BASE = "https://api.mercadopublico.cl/servicios/v1/publico"

SGS_PORTFOLIO = """
PORTAFOLIO SGS EHS CHILE:
- Fase 1: Due Diligence Ambiental, Lineas Base Aire/Agua/Biodiversidad, Consultas de Pertinencia, Brechas ESG
- Fase 2: Estudios Biodiversidad, Modelacion Numerica Aire/Ruido/Agua, Permisos Ambientales, Relacionamiento Comunitario
- Fase 3: ITO Ambiental HSE SSO, Matriz Cumplimiento Post RCA, Monitoreo Aire y Ruido, Higiene DS 594
- Fase 4: Monitoreo Ambiental, Laboratorio Acreditado, Auditorias Tercera Parte, Huella Carbono, Zero Waste to Landfill
- Fase 5: Economia Circular, Auditorias de Cierre, Bonos de Carbono, Reporte ESG
"""

app = FastAPI(title="SGS EHS Chile API Licitaciones", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def fecha_str(offset_dias: int = 0) -> str:
    from zoneinfo import ZoneInfo
    d = datetime.now(ZoneInfo("America/Santiago")) - timedelta(days=offset_dias)
    return d.strftime("%d%m%Y")

async def fetch_mp(fecha: str) -> dict:
    url = f"{MP_BASE}/licitaciones.json"
    params = {"fecha": fecha, "ticket": TICKET_MP}
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(url, params=params)
        r.raise_for_status()
        return r.json()

async def analizar(listado: list, consulta: str, total: int) -> str:
    if not ANTHROPIC_API_KEY:
        return "Configura ANTHROPIC_API_KEY en Railway Variables."

    resumen = "\n".join([
        f"{i+1}. [{l.get('CodigoExterno','N/A')}] {l.get('Nombre','Sin nombre')} | {l.get('NombreOrganismo','N/A')}"
        for i, l in enumerate(listado[:80])
    ])

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    msg = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=2000,
        system=f"""Eres el asistente comercial de SGS EHS Chile. Analiza licitaciones de Mercado Publico y detecta oportunidades.

{SGS_PORTFOLIO}

Para cada licitacion compatible (>30%):
- Titulo y organismo
- Codigo (para link: https://www.mercadopublico.cl/Procurement/Modules/RFB/DetailsAcquisition.aspx?idLicitacion=CODIGO)
- % compatibilidad con SGS EHS
- Servicios SGS aplicables
- Por que es oportunidad (1 oracion)

Termina con resumen: licitaciones analizadas vs oportunidades SGS encontradas.
Responde en espanol profesional.""",
        messages=[{"role": "user", "content": f'Consulta: "{consulta}"\n\nTotal licitaciones hoy: {total}\n\n{resumen}'}]
    )
    return msg.content[0].text

@app.get("/")
async def root():
    return {"status": "SGS EHS Chile API operativa", "version": "2.0.0"}

@app.get("/status")
async def status():
    try:
        fecha = fecha_str()
        data = await fetch_mp(fecha)
        return {
            "mercado_publico": "✅ conectado",
            "fecha_consultada": fecha,
            "licitaciones_hoy": data.get("Cantidad", 0),
            "ticket_activo": TICKET_MP[:8] + "...",
            "ia_configurada": bool(ANTHROPIC_API_KEY),
        }
    except Exception as e:
        return {"mercado_publico": "❌ error", "detalle": str(e)}

@app.get("/licitaciones/buscar")
async def buscar(
    consulta: str = Query(...),
    offset_dias: int = Query(0)
):
    try:
        fecha = fecha_str(offset_dias)
        data = await fetch_mp(fecha)
    except Exception as e:
        raise HTTPException(502, f"Error Mercado Publico: {str(e)}")

    listado = data.get("Listado", [])
    total = data.get("Cantidad", 0)

    if not listado:
        return {"consulta": consulta, "total": total, "respuesta": "No hay licitaciones para esta fecha."}

    respuesta = await analizar(listado, consulta, total)
    return {"consulta": consulta, "fecha": fecha, "total_licitaciones": total, "analisis_sgs": respuesta}

@app.get("/licitaciones/hoy")
async def hoy(offset_dias: int = Query(0)):
    try:
        fecha = fecha_str(offset_dias)
        data = await fetch_mp(fecha)
    except Exception as e:
        raise HTTPException(502, f"Error Mercado Publico: {str(e)}")

    listado = data.get("Listado", [])
    total = data.get("Cantidad", 0)
    respuesta = await analizar(listado, "Dame todas las oportunidades SGS EHS del dia", total)
    return {"fecha": fecha, "total_licitaciones": total, "analisis_sgs": respuesta}

@app.get("/licitaciones/chat")
async def chat(
    mensaje: str = Query(...),
    fecha: Optional[str] = Query(None)
):
    try:
        fecha_consulta = fecha or fecha_str()
        data = await fetch_mp(fecha_consulta)
    except Exception as e:
        raise HTTPException(502, f"Error Mercado Publico: {str(e)}")

    listado = data.get("Listado", [])
    total = data.get("Cantidad", 0)
    respuesta = await analizar(listado, mensaje, total)
    return {
        "mensaje_usuario": mensaje,
        "fecha_consultada": fecha_consulta,
        "total_licitaciones_analizadas": total,
        "respuesta_ia": respuesta
    }
