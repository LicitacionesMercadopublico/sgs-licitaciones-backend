"""
SGS EHS Chile – Backend API
Conecta Mercado Público + Claude IA para identificar licitaciones relevantes
"""

from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
import httpx
import anthropic
import os
from datetime import datetime, timedelta
from typing import Optional
import json

# ─────────────────────────────────────────────
#  CONFIGURACIÓN
# ─────────────────────────────────────────────
TICKET_MP = os.getenv("TICKET_MP", "F8537A18-6766-4DEF-9E59-426B4FEE2844")  # ticket de prueba
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")  # tu API key de Anthropic
MP_BASE = "https://api.mercadopublico.cl/servicios/v1/publico"

# ─────────────────────────────────────────────
#  PORTAFOLIO SGS EHS CHILE
# ─────────────────────────────────────────────
SGS_PORTFOLIO = """
PORTAFOLIO SGS EHS CHILE – 5 FASES DEL PROYECTO:

FASE 1 – Prefactibilidad y Planificación:
  - Due Diligence Ambiental
  - Líneas Base (Aire, Agua, Biodiversidad)
  - Consultas de Pertinencia
  - Análisis de Brechas ESG

FASE 2 – Evaluación Ambiental:
  - Estudios de Biodiversidad y Patrimonio Cultural
  - Modelación Numérica (Aire, Ruido, Agua)
  - Permisos Ambientales y Sectoriales
  - Relacionamiento Comunitario

FASE 3 – Construcción:
  - ITO Ambiental, HSE y SSO
  - Matriz de Cumplimiento Post RCA
  - Monitoreo de Aire y Ruido
  - Higiene y Seguridad Industrial (DS 594)

FASE 4 – Operación:
  - Monitoreo y Seguimiento de Cumplimiento
  - Laboratorio Ambiental Acreditado
  - Auditorías de Tercera Parte
  - Verificación Huella Carbono e Hídrica
  - Evaluación de Proveedores
  - Zero Waste to Landfill

FASE 5 – Cierre y Post-Cierre:
  - Economía Circular y Valorización de Subproductos
  - Auditorías Técnicas de Cierre
  - Bonos de Carbono
  - Reporte ESG y Sostenibilidad

PALABRAS CLAVE RELEVANTES: monitoreo ambiental, calidad aire, calidad agua, ruido,
biodiversidad, flora fauna, EIA, SEIA, RCA, auditoría ambiental, ISO 14001, ISO 45001,
HSE, SSO, seguridad industrial, DS 594, higiene industrial, laboratorio ambiental,
análisis agua, análisis suelo, huella carbono, GEI, carbono neutro, ESG, sostenibilidad,
residuos peligrosos, RESPEL, RILES, RISES, due diligence, línea base, prefactibilidad,
permisos ambientales, DGA, CONAF, patrimonio cultural, modelación, dispersión, economía circular,
remediación suelos, cierre minero, plan cierre, bonos carbono, reporte sustentabilidad.
"""

# ─────────────────────────────────────────────
#  APP FASTAPI
# ─────────────────────────────────────────────
app = FastAPI(
    title="SGS EHS Chile – API Licitaciones",
    description="Backend que conecta Mercado Público + Claude IA para SGS EHS Chile",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # En producción: especifica tu dominio
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────────
#  HELPERS – MERCADO PÚBLICO
# ─────────────────────────────────────────────
def fecha_str(offset_dias: int = 0) -> str:
    """Retorna fecha en formato ddmmaaaa para la API de MP"""
    d = datetime.now() - timedelta(days=offset_dias)
    return d.strftime("%d%m%Y")


async def fetch_licitaciones_mp(fecha: str, estado: str = "activas") -> dict:
    """Consulta la API de Mercado Público y retorna el JSON crudo"""
    url = f"{MP_BASE}/licitaciones.json"
    params = {
        "fecha": fecha,
        "ticket": TICKET_MP,
        "estado": estado
    }
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(url, params=params)
        r.raise_for_status()
        return r.json()


async def fetch_detalle_licitacion(codigo: str) -> dict:
    """Obtiene el detalle completo de una licitación por código"""
    url = f"{MP_BASE}/licitaciones.json"
    params = {"codigo": codigo, "ticket": TICKET_MP}
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(url, params=params)
        r.raise_for_status()
        return r.json()


# ─────────────────────────────────────────────
#  HELPERS – ANÁLISIS IA
# ─────────────────────────────────────────────
def construir_resumen_licitaciones(listado: list) -> str:
    """Convierte el listado de MP a texto plano para el prompt de Claude"""
    lines = []
    for i, l in enumerate(listado[:100], 1):   # máx 100 para el contexto
        nombre = l.get("Nombre", "Sin nombre")
        codigo = l.get("CodigoExterno", l.get("Codigo", "N/A"))
        organismo = l.get("NombreOrganismo", "N/A")
        estado = l.get("CodigoEstado", "N/A")
        fecha_cierre = l.get("FechaCierre", "N/A")
        monto = l.get("MontoEstimado", "N/A")
        tipo = l.get("Tipo", "N/A")
        lines.append(
            f"{i}. [{codigo}] {nombre} | Organismo: {organismo} | "
            f"Estado: {estado} | Cierre: {fecha_cierre} | Monto: {monto} | Tipo: {tipo}"
        )
    return "\n".join(lines)


async def analizar_con_ia(listado_texto: str, consulta_usuario: str, total: int) -> str:
    """Envía las licitaciones a Claude para análisis y cruce con portafolio SGS"""
    if not ANTHROPIC_API_KEY:
        return "⚠️ Configura la variable de entorno ANTHROPIC_API_KEY para habilitar el análisis IA."

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    system_prompt = f"""Eres el asistente comercial de SGS EHS Chile.
Tu misión es analizar licitaciones de Mercado Público y determinar cuáles son oportunidades de negocio para SGS EHS Chile.

{SGS_PORTFOLIO}

INSTRUCCIONES:
1. Analiza cada licitación por su nombre y descripción.
2. Calcula un % de compatibilidad (0-100) con los servicios SGS EHS.
3. Muestra SOLO licitaciones con compatibilidad >= 30%, ordenadas de mayor a menor.
4. Para cada oportunidad presenta:
   - Título de la licitación
   - Organismo comprador
   - Código (para construir el link a MP)
   - % compatibilidad
   - Servicios SGS aplicables (lista concisa)
   - Por qué es una oportunidad (1-2 oraciones)
   - Link: https://www.mercadopublico.cl/Procurement/Modules/RFB/DetailsAcquisition.aspx?idLicitacion=CODIGO
5. Si no hay compatibles, indícalo claramente.
6. Termina con resumen: licitaciones analizadas vs oportunidades encontradas.
Responde en español profesional y conciso."""

    user_content = f"""Consulta del equipo comercial: "{consulta_usuario}"

Total licitaciones en Mercado Público hoy: {total}
Licitaciones a analizar ({min(total,100)} primeras):

{listado_texto}"""

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        system=system_prompt,
        messages=[{"role": "user", "content": user_content}]
    )
    return message.content[0].text


# ─────────────────────────────────────────────
#  ENDPOINTS
# ─────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def root():
    return """
    <h2>SGS EHS Chile – API Licitaciones ✅</h2>
    <p>Backend operativo. Endpoints disponibles:</p>
    <ul>
      <li><a href="/docs">📖 Documentación interactiva (Swagger)</a></li>
      <li><code>GET /licitaciones/hoy</code> – Licitaciones del día + análisis IA</li>
      <li><code>GET /licitaciones/buscar?consulta=monitoreo ambiental</code> – Búsqueda inteligente</li>
      <li><code>GET /licitaciones/detalle/{codigo}</code> – Detalle de una licitación</li>
      <li><code>GET /status</code> – Estado de la conexión con Mercado Público</li>
    </ul>
    """


@app.get("/status")
async def status():
    """Verifica la conexión con la API de Mercado Público"""
    try:
        fecha = fecha_str()
        data = await fetch_licitaciones_mp(fecha)
        return {
            "mercado_publico": "✅ conectado",
            "fecha_consultada": fecha,
            "licitaciones_hoy": data.get("Cantidad", 0),
            "ticket_activo": TICKET_MP[:8] + "...",
            "ia_configurada": bool(ANTHROPIC_API_KEY),
        }
    except Exception as e:
        return {"mercado_publico": "❌ error", "detalle": str(e)}


@app.get("/licitaciones/hoy")
async def licitaciones_hoy(
    analizar: bool = Query(True, description="Analizar con IA contra portafolio SGS"),
    estado: str = Query("activas", description="Estado: activas | cerradas | todas"),
    offset_dias: int = Query(0, description="0=hoy, 1=ayer, etc.")
):
    """
    Trae las licitaciones del día desde Mercado Público.
    Si analizar=True, usa Claude para identificar oportunidades SGS EHS.
    """
    try:
        fecha = fecha_str(offset_dias)
        data = await fetch_licitaciones_mp(fecha, estado)
    except httpx.HTTPError as e:
        raise HTTPException(502, f"Error consultando Mercado Público: {e}")

    listado = data.get("Listado", [])
    total = data.get("Cantidad", 0)

    result = {
        "fecha": fecha,
        "total_licitaciones": total,
        "estado_filtro": estado,
        "licitaciones_raw": listado[:50],  # máx 50 en raw
    }

    if analizar and listado:
        resumen = construir_resumen_licitaciones(listado)
        analisis = await analizar_con_ia(
            resumen,
            "Dame un análisis completo de todas las licitaciones de hoy para SGS EHS Chile",
            total
        )
        result["analisis_sgs"] = analisis

    return result


@app.get("/licitaciones/buscar")
async def buscar_licitaciones(
    consulta: str = Query(..., description="Qué tipo de licitaciones buscar. Ej: 'monitoreo ambiental Antofagasta'"),
    offset_dias: int = Query(0, description="0=hoy, 1=ayer, etc."),
    estado: str = Query("activas", description="Estado: activas | cerradas | todas")
):
    """
    Busca licitaciones del día en Mercado Público y las analiza con IA
    según la consulta del usuario, cruzando con el portafolio SGS EHS Chile.
    """
    try:
        fecha = fecha_str(offset_dias)
        data = await fetch_licitaciones_mp(fecha, estado)
    except httpx.HTTPError as e:
        raise HTTPException(502, f"Error consultando Mercado Público: {e}")

    listado = data.get("Listado", [])
    total = data.get("Cantidad", 0)

    if not listado:
        return {
            "consulta": consulta,
            "fecha": fecha,
            "total_licitaciones": total,
            "mensaje": "No hay licitaciones disponibles para esta fecha.",
            "analisis_sgs": None
        }

    resumen = construir_resumen_licitaciones(listado)
    analisis = await analizar_con_ia(resumen, consulta, total)

    return {
        "consulta": consulta,
        "fecha": fecha,
        "total_licitaciones": total,
        "analisis_sgs": analisis
    }


@app.get("/licitaciones/detalle/{codigo}")
async def detalle_licitacion(codigo: str):
    """Obtiene el detalle completo de una licitación específica por código"""
    try:
        data = await fetch_detalle_licitacion(codigo)
        return data
    except httpx.HTTPError as e:
        raise HTTPException(502, f"Error obteniendo detalle: {e}")


@app.get("/licitaciones/chat")
async def chat_licitaciones(
    mensaje: str = Query(..., description="Mensaje del usuario"),
    fecha: Optional[str] = Query(None, description="Fecha ddmmaaaa (default: hoy)")
):
    """
    Endpoint conversacional: recibe un mensaje y retorna análisis IA.
    Ideal para integrar con un chatbot o frontend de chat.
    """
    fecha_consulta = fecha or fecha_str()

    try:
        data = await fetch_licitaciones_mp(fecha_consulta)
    except httpx.HTTPError as e:
        raise HTTPException(502, f"Error consultando Mercado Público: {e}")

    listado = data.get("Listado", [])
    total = data.get("Cantidad", 0)
    resumen = construir_resumen_licitaciones(listado) if listado else "Sin licitaciones disponibles para esta fecha."

    respuesta = await analizar_con_ia(resumen, mensaje, total)

    return {
        "mensaje_usuario": mensaje,
        "fecha_consultada": fecha_consulta,
        "total_licitaciones_analizadas": total,
        "respuesta_ia": respuesta
    }
