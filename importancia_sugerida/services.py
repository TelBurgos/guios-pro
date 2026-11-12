import os
import statistics
import time
from decimal import Decimal

import requests
from django.db import transaction

from evaluacion.models import Factor, Subfactor
from .models import ActualizacionIS, ConsultaIS, DetalleActualizacionIS

VERSION = "v1.0"
ANIO_DESDE, ANIO_HASTA = 2020, 2025
API_KEY = os.environ.get("OPENALEX_API_KEY", "")

# clave = (IL, IE) -> IS   (Rea Sánchez, 2022, Fig. 5.10)
MATRIZ_IS = {
    (1, 1): 1, (2, 1): 1, (3, 1): 2, (4, 1): 2,
    (1, 2): 1, (2, 2): 2, (3, 2): 2, (4, 2): 3,
    (1, 3): 2, (2, 3): 2, (3, 3): 3, (4, 3): 3,
    (1, 4): 2, (2, 4): 3, (3, 4): 3, (4, 4): 4,
}

BLOQUE_FLOSS = '(FLOSS OR FOSS OR "free software" OR "open source")'
BLOQUE_ADOPCION = '(adoption OR adopt OR migration OR deployment)'

def generar_consulta(subfactor):
    terminos = [t.strip() for t in subfactor.terminos_busqueda.split(",") if t.strip()]
    if terminos:
        bloque = " OR ".join(f'"{t}"' for t in terminos)
    else:
        bloque = f'"{subfactor.nombre}"'
    return f'({bloque}) AND {BLOQUE_FLOSS} AND {BLOQUE_ADOPCION}'

def contar_openalex(consulta, reintentos=4):
    params = {
        "filter": f"title_and_abstract.search:{consulta},"
                  f"from_publication_date:{ANIO_DESDE}-01-01,"
                  f"to_publication_date:{ANIO_HASTA}-12-31",
        "per-page": 1,
        "api_key": API_KEY,
    }
    for intento in range(reintentos):
        r = requests.get("https://api.openalex.org/works", params=params, timeout=20)
        if r.status_code == 429:
            espera = float(r.headers.get("Retry-After", 2 ** (intento + 1)))
            if espera > 30:
                raise RuntimeError(f"Presupuesto diario de OpenAlex agotado: {r.text[:200]}")
            time.sleep(espera)
            continue
        r.raise_for_status()
        return r.json()["meta"]["count"]
    raise RuntimeError("OpenAlex sigue devolviendo 429")


def cuartiles(valores):
    if len(valores) < 4:
        raise ValueError("Se necesitan al menos 4 factores con subfactores para calcular cuartiles.")
    v = sorted(valores)
    q1, q2, q3 = statistics.quantiles(v, n=4, method="inclusive")
    return q1, q2, q3, v[-1]


def calcular_il(r, rq):
    if r <= rq[0]:
        return 1
    if r <= rq[1]:
        return 2
    if r <= rq[2]:
        return 3
    return 4


@transaction.atomic
def actualizar_is():
    act = ActualizacionIS.objects.create(fuente="OpenAlex", version_calculo=VERSION)
    datos = {}  # factor_id -> (c_i, n)

    for f in Factor.objects.all():
        subs = Subfactor.objects.filter(factor=f)
        total = 0
        for s in subs:
            q = generar_consulta(s)
            n_art = contar_openalex(q)
            ConsultaIS.objects.create(
                actualizacion=act, subfactor=s, consulta=q,
                anio_desde=ANIO_DESDE, anio_hasta=ANIO_HASTA,
                articulos_encontrados=n_art,
            )
            total += n_art
            time.sleep(0.3)  # evita el 429 de OpenAlex
        datos[f.id] = (total, subs.count())

    rs = {fid: Decimal(c) / Decimal(n) for fid, (c, n) in datos.items() if n}
    rq = cuartiles([float(x) for x in rs.values()])

    for f in Factor.objects.all():
        if f.id not in rs:
            continue
        il = calcular_il(float(rs[f.id]), rq)
        ie = f.importancia_experta
        if not ie:
            raise ValueError(f"El factor '{f.nombre}' no tiene importancia_experta")
        is_ = MATRIZ_IS[(il, ie)]
        DetalleActualizacionIS.objects.create(
            actualizacion=act, factor=f, total_articulos=datos[f.id][0],
            promedio_r=rs[f.id].quantize(Decimal("0.01")),
            importancia_literaria=il, importancia_experta=ie,
            importancia_sugerida=is_,
        )
        f.importancia_is = is_
        f.save(update_fields=["importancia_is"])
    return act


def actualizar_is_seguro():
    """RNF-08: si falla API/IA, se conserva la última IS y se avisa."""
    try:
        return actualizar_is(), None
    except Exception as e:
        ultima = ActualizacionIS.objects.order_by("-fecha").first()
        return ultima, f"Falló la actualización: {e}. Se usa la última IS almacenada."