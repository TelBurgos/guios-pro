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

PROMPT = (
    "Para cada criterio de adopción de software libre de la lista, devuelve 3 a 4 "
    "términos de búsqueda académica en inglés, separados por coma, sin comillas. "
    "Cada término debe tener de 1 a 3 palabras, ser específico del criterio y NO "
    "contener las palabras 'open source', 'free software' ni 'software' solas "
    "(ya se agregan aparte). Ejemplos: 'documentation quality', 'user manuals', "
    "'vendor lock-in'. "
    "Responde SOLO un objeto JSON cuya clave sea el id y cuyo valor sea el texto "
    "con los términos. Ejemplo: {{\"12\": \"software certification, standards "
    "compliance\"}}.\n\nCriterios:\n{lista}"
)

def _limpiar(texto):
    texto = (texto or "").replace("\n", ",")
    terminos = [
        " ".join(t.replace('"', " ").replace("|", " ").replace("*", " ").split())
        for t in texto.split(",")
    ]
    return ", ".join(t for t in terminos if t)[:300]


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