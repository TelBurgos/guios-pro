import json
import logging
import os
import time

from dotenv import load_dotenv
from google import genai
from google.genai import types

from evaluacion.models import Subfactor

load_dotenv()
logger = logging.getLogger(__name__)

MODELO = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
LOTE = 10          # subfactores por llamada
PAUSA = 5          # segundos entre llamadas (15 por minuto = 1 cada 4 s)
REINTENTOS = 4
ESPERA_REINTENTO = 40  # segundos ante 429 (límite) o 503 (alta demanda)

MIN_PALABRAS, MAX_PALABRAS = 2, 2   # largo permitido de cada término

PROMPT = (
    "Para cada criterio de adopción de software libre de la lista, devuelve 5 "
    "términos de búsqueda académica en inglés, separados por coma, sin comillas. "
    "Reglas:\n"
    "- Cada término tiene EXACTAMENTE 2 palabras, y son palabras clave que "
    "aparecen de verdad en títulos y resúmenes de artículos científicos "
    "(por ejemplo 'vendor lock-in', 'user training', 'code quality').\n"
    "- No inventes combinaciones ni parafrasees el criterio. Si dudas de que "
    "un término exista en la literatura, usa uno más común.\n"
    "- Incluye términos amplios del tema (por ejemplo 'technical support') y "
    "sinónimos habituales.\n"
    "- No uses nombres de productos o marcas, ni palabras sueltas.\n"
    "- NO incluyas 'open source', 'free software', 'FLOSS' ni 'software' solos "
    "(ya se agregan aparte).\n"
    "Responde SOLO un objeto JSON cuya clave sea el id y cuyo valor sea el texto "
    "con los términos. Ejemplo: {{\"12\": \"standards compliance, software "
    "certification, quality assurance, regulatory compliance, compliance testing\"}}."
    "\n\nCriterios:\n{lista}"
)

def _limpiar(texto):
    """Normaliza los términos y descarta los de una sola palabra o de más de 3."""
    texto = (texto or "").replace("\n", ",")
    terminos = [
        " ".join(t.replace('"', " ").replace("|", " ").replace("*", " ").split())
        for t in texto.split(",")
    ]
    terminos = [t for t in terminos if MIN_PALABRAS <= len(t.split()) <= MAX_PALABRAS]
    return ", ".join(terminos)[:300]


def _es_temporal(error):
    """429 (límite por minuto) y 503 (alta demanda) se resuelven esperando."""
    msg = str(error)
    return any(c in msg for c in ("429", "503", "UNAVAILABLE", "RESOURCE_EXHAUSTED"))


def _llamar(client, lote):
    lista = "\n".join(f"{s.pk}: {s.nombre} (factor: {s.factor.nombre})" for s in lote)
    for intento in range(REINTENTOS):
        try:
            r = client.models.generate_content(
                model=MODELO,
                contents=PROMPT.format(lista=lista),
                config=types.GenerateContentConfig(
                    response_mime_type="application/json"),
            )
            datos = json.loads(r.text)
            if not isinstance(datos, dict):
                raise ValueError("La IA no devolvió un objeto JSON")
            return datos
        except Exception as e:
            ultimo = intento == REINTENTOS - 1
            if (_es_temporal(e) or isinstance(e, (json.JSONDecodeError, ValueError))) \
                    and not ultimo:
                logger.warning("Gemini: %s. Reintentando en %s s (intento %s/%s)",
                               type(e).__name__, ESPERA_REINTENTO, intento + 1, REINTENTOS)
                time.sleep(ESPERA_REINTENTO)
                continue
            raise


def completar_terminos():
    """Genera con IA los términos de los subfactores que no tienen.
    Nunca rompe la actualización (RNF-08)."""
    if not os.getenv("GEMINI_API_KEY"):
        logger.warning("Falta GEMINI_API_KEY: no se generan términos con IA.")
        return 0

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    pendientes = list(
        Subfactor.objects.filter(terminos_busqueda="").select_related("factor"))
    n = 0
    for i in range(0, len(pendientes), LOTE):
        lote = pendientes[i:i + LOTE]
        try:
            respuesta = _llamar(client, lote)
        except Exception:
            logger.exception("La IA falló en el lote que empieza en %s", lote[0].pk)
            continue
        for s in lote:
            terminos = _limpiar(respuesta.get(str(s.pk), ""))
            if terminos:
                s.terminos_busqueda = terminos
                s.save(update_fields=["terminos_busqueda"])
                n += 1
        time.sleep(PAUSA)
    return n