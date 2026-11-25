import logging
import os
import re
import time
from decimal import ROUND_HALF_UP, Decimal

import requests
from django.db import transaction
from dotenv import load_dotenv

from evaluacion.logic import MATRIZ_IMPORTANCIA
from evaluacion.models import Factor
from .ia import completar_terminos
from .models import ActualizacionIS, ConsultaIS, DetalleActualizacionIS

load_dotenv()
logger = logging.getLogger(__name__)

# ==========================================
# CONFIGURACIÓN
# ==========================================

VERSION = "v1.0"
FUENTE = "OpenAlex"
ANIO_DESDE, ANIO_HASTA = 2020, 2025

API_URL = "https://api.openalex.org/works"
TIMEOUT = 20          # segundos por petición
# Las búsquedas con más de 5 operadores booleanos admiten solo 2 por segundo
PAUSA = 0.6
MAX_ESPERA = 60       # tope de espera ante un 429/5xx temporal

BLOQUE_FLOSS = '(FLOSS OR FOSS OR "free software" OR "open source")'
BLOQUE_ADOPCION = "(adoption OR adopt OR migration OR deployment)"

SESION = requests.Session()


# ==========================================
# 1. GENERACIÓN DE CONSULTAS
# ==========================================

def _limpiar(texto):
    """Quita caracteres que rompen el filtro de OpenAlex (coma, barra vertical, comillas)."""
    for caracter in (",", "|", '"'):
        texto = texto.replace(caracter, " ")
    return " ".join(texto.split())


def generar_consulta(subfactor):
    """Consulta en inglés para un subfactor: sus términos + bloque FLOSS + bloque adopción."""
    terminos = [_limpiar(t) for t in subfactor.terminos_busqueda.split(",")]
    terminos = [t for t in terminos if t]
    if terminos:
        bloque = " OR ".join(f'"{t}"' for t in terminos)
    else:
        bloque = f'"{_limpiar(subfactor.nombre)}"'
    return f"({bloque}) AND {BLOQUE_FLOSS} AND {BLOQUE_ADOPCION}"


# ==========================================
# 2. CONSULTA A OPENALEX
# ==========================================

def _espera(respuesta, intento):
    """Segundos a esperar: Retry-After, o el aviso 'retry in Ns' del cuerpo, o espera exponencial."""
    try:
        return float(respuesta.headers["Retry-After"])
    except (KeyError, ValueError):
        pass
    m = re.search(r"retry in (\d+(?:\.\d+)?)\s*s", respuesta.text, re.IGNORECASE)
    if m:
        return float(m.group(1))
    return 2 ** (intento + 1)


def contar_openalex(consulta, reintentos=5):
    """Devuelve el número de trabajos que cumplen la consulta en el rango de años."""
    api_key = os.getenv("OPENALEX_API_KEY", "")
    correo = os.getenv("OPENALEX_EMAIL", "")

    params = {
        "filter": f"title_and_abstract.search:{consulta},"
                  f"from_publication_date:{ANIO_DESDE}-01-01,"
                  f"to_publication_date:{ANIO_HASTA}-12-31",
        "per-page": 1,
    }
    if api_key:
        params["api_key"] = api_key
    if correo:
        params["mailto"] = correo

    for intento in range(reintentos):
        try:
            r = SESION.get(API_URL, params=params, timeout=TIMEOUT)
        except (requests.Timeout, requests.ConnectionError):
            if intento == reintentos - 1:
                raise
            time.sleep(2 ** (intento + 1))
            continue

        if r.status_code == 429 or r.status_code >= 500:
            # Presupuesto agotado: esperar no sirve, se aborta
            if r.status_code == 429 and "insufficient budget" in r.text.lower():
                raise RuntimeError(f"Presupuesto diario de OpenAlex agotado: {r.text[:200]}")
            if intento == reintentos - 1:
                break
            espera = min(_espera(r, intento), MAX_ESPERA)
            logger.warning("OpenAlex respondió %s; reintentando en %.0f s", r.status_code, espera)
            time.sleep(espera)
            continue

        r.raise_for_status()
        return r.json()["meta"]["count"]

    raise RuntimeError("OpenAlex no respondió correctamente tras varios reintentos")


# ==========================================
# 3. CÁLCULO DE IL E IS (reglas de la tesis)
# ==========================================

def _percentil_inc(v, p):
    """Percentil con interpolación inclusiva (equivale a QUARTILE.INC de Excel)."""
    pos = Decimal(len(v) - 1) * p
    j = int(pos)
    if j + 1 >= len(v):
        return v[-1]
    return v[j] + (v[j + 1] - v[j]) * (pos - j)


def cuartiles(valores):
    """Devuelve (rq1, rq2, rq3, rq4); rq4 es el máximo, como en la Ecuación 2."""
    if len(valores) < 4:
        raise ValueError("Se necesitan al menos 4 factores con subfactores para calcular cuartiles.")
    v = sorted(Decimal(x) for x in valores)
    return (
        _percentil_inc(v, Decimal("0.25")),
        _percentil_inc(v, Decimal("0.50")),
        _percentil_inc(v, Decimal("0.75")),
        v[-1],
    )


def calcular_il(r, rq):
    """Importancia de la literatura (1 a 4) según el cuartil de rᵢ."""
    if r <= rq[0]:
        return 1
    if r <= rq[1]:
        return 2
    if r <= rq[2]:
        return 3
    return 4


# ==========================================
# 4. FLUJO DE ACTUALIZACIÓN
# ==========================================

def consultar_literatura(factores):
    """Fase externa (sin transacción abierta): ejecuta las consultas y cuenta artículos.

    Devuelve (consultas, datos):
      consultas = [(subfactor, texto_consulta, n_articulos), ...]
      datos     = {factor_id: (cᵢ, n_subfactores)}
    """
    consultas, datos = [], {}
    for f in factores:
        subs = list(f.subfactores.all())
        total = 0
        for s in subs:
            q = generar_consulta(s)
            n_art = contar_openalex(q)
            consultas.append((s, q, n_art))
            total += n_art
            time.sleep(PAUSA)
        datos[f.id] = (total, len(subs))
    return consultas, datos


def calcular_resultados(factores, datos):
    """Calcula rᵢ, IL e IS por factor. Devuelve (resultados, cuartiles). Sin acceso a BD ni red."""
    if sum(c for c, _ in datos.values()) == 0:
        # Con 0 artículos en todo, todos los factores quedarían con IL = 1 y
        # la IS se degradaría sin base real: mejor conservar la última IS.
        raise RuntimeError(
            "OpenAlex no devolvió artículos para ninguna consulta; "
            "revisa los términos de búsqueda y la API key.")

    rs = {fid: Decimal(c) / Decimal(n) for fid, (c, n) in datos.items() if n}
    rq = cuartiles(list(rs.values()))

    resultados = []
    for f in factores:
        if f.id not in rs:          # factor sin subfactores: conserva su IS actual
            continue
        ie = f.importancia_experta
        if ie not in (1, 2, 3, 4):
            raise ValueError(f"El factor '{f.nombre}' no tiene importancia_experta válida (1 a 4)")
        il = calcular_il(rs[f.id], rq)
        resultados.append((f, datos[f.id][0], rs[f.id], il, ie, MATRIZ_IMPORTANCIA[(il, ie)]))
    return resultados, rq


@transaction.atomic
def guardar_actualizacion(consultas, resultados, rq):
    """Fase de persistencia: todo o nada, y rápida (sin llamadas externas)."""
    act = ActualizacionIS.objects.create(
        fuente=FUENTE, version_calculo=VERSION,
        cuartiles={f"rq{i}": str(v) for i, v in enumerate(rq, 1)},
    )

    ConsultaIS.objects.bulk_create([
        ConsultaIS(
            actualizacion=act, subfactor=s, consulta=q,
            anio_desde=ANIO_DESDE, anio_hasta=ANIO_HASTA,
            articulos_encontrados=n,
        )
        for s, q, n in consultas
    ])

    detalles, modificados = [], []
    for f, total, r, il, ie, is_ in resultados:
        detalles.append(DetalleActualizacionIS(
            actualizacion=act, factor=f, total_articulos=total,
            promedio_r=r.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            importancia_literaria=il, importancia_experta=ie,
            importancia_sugerida=is_,
        ))
        f.importancia_is = is_
        modificados.append(f)

    DetalleActualizacionIS.objects.bulk_create(detalles)
    Factor.objects.bulk_update(modificados, ["importancia_is"])
    return act


def actualizar_is():
    """RF-05 / HU-11: consulta la literatura, calcula IL e IS y guarda la trazabilidad."""
    if not os.getenv("OPENALEX_API_KEY"):
        raise RuntimeError(
            "Falta OPENALEX_API_KEY en el .env (sin key, OpenAlex limita a 0,01 USD/día).")

    completar_terminos()  # si la IA falla, se usan los términos que ya existen
    factores = list(Factor.objects.prefetch_related("subfactores").order_by("id"))
    consultas, datos = consultar_literatura(factores)
    resultados, rq = calcular_resultados(factores, datos)
    return guardar_actualizacion(consultas, resultados, rq)


def actualizar_is_seguro():
    """RNF-08: si falla la API o el cálculo, se conserva la última IS y se avisa."""
    try:
        return actualizar_is(), None
    except Exception as e:
        logger.exception("Falló la actualización de la IS")
        ultima = ActualizacionIS.objects.order_by("-fecha").first()
        return ultima, f"Falló la actualización: {e}. Se usa la última IS almacenada."