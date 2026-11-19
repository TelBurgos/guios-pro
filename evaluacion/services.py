from decimal import Decimal

from django.db import transaction

from .logic import LEVELS, codigo_recomendacion, derive, init_state, recomendacion
from .models import Evaluacion, EvaluacionFactor, EvaluacionSubfactor, Factor


def catalogue(actualizacion=None):
    """Catálogo desde la BD. Con `actualizacion`, usa la IS que tenía esa evaluación."""
    snapshot = {}
    if actualizacion is not None:
        snapshot = {d.factor_id: d.importancia_sugerida for d in actualizacion.detalles.all()}

    factores = (Factor.objects.select_related("dimension")
                .prefetch_related("subfactores").order_by("id"))
    cat = []
    for f in factores:
        subs = sorted(f.subfactores.all(), key=lambda s: s.id)
        cat.append({
            "factor_id": f.id,            # no se llama "id": derive() lo usa como índice
            "name": f.nombre,
            "dimension": f.dimension.nombre,
            "subfactors": [s.nombre for s in subs],
            "subfactor_ids": [s.id for s in subs],
            "suggested": snapshot.get(f.id, f.importancia_is),
            "expert": f.importancia_experta,
            "scope": f.alcance_base,
        })
    return cat


def cargar_estado(ev, cat):
    """Reconstruye el estado de GUIOS desde las tablas normalizadas."""
    state = init_state(cat)
    factores = {v.factor_id: v for v in ev.valoraciones_factor.all()}
    subs = {v.subfactor_id: v.importancia for v in ev.valoraciones_subfactor.all()}
    for i, f in enumerate(cat):
        s = state[str(i)]
        vf = factores.get(f["factor_id"])
        if vf:
            s["decisor"] = vf.importancia_decisor
            s["scope"] = vf.alcance_evaluado or s["scope"]
        ids = f["subfactor_ids"]
        if ids and all(sid in subs for sid in ids):
            s["weights"] = [subs[sid] for sid in ids]
            s["saved"] = True
    return state


@transaction.atomic
def guardar_avance(ev, cat, state, paso, completar=False):
    """Persiste valoraciones, ponderación y FODA (HU-07, HU-08). Con completar=True cierra con la recomendación (HU-09)."""
    rows = derive(cat, state)
    ev.valoraciones_factor.all().delete()
    ev.valoraciones_subfactor.all().delete()

    factores, subfactores = [], []
    for r in rows:
        score = r["score"]
        factores.append(EvaluacionFactor(
            evaluacion=ev, factor_id=r["factor_id"],
            importancia_decisor=r["decisor"],
            importancia_relativa=LEVELS.index(r["relative"]) + 1,
            relevante=r["relevant"],
            peso_global=Decimal(str(round(score, 2))) if score is not None else None,
            alcance_evaluado=r["scope_selected"],
            foda=r["foda"] or "",
        ))
        if r["saved"]:
            for sid, valor in zip(r["subfactor_ids"], r["weights"]):
                subfactores.append(EvaluacionSubfactor(evaluacion=ev, subfactor_id=sid, importancia=valor))
    EvaluacionFactor.objects.bulk_create(factores)
    EvaluacionSubfactor.objects.bulk_create(subfactores)

    ev.paso_actual = paso
    campos = ["paso_actual"]
    if completar:
        texto = recomendacion(rows)
        ev.recomendacion = codigo_recomendacion(texto)
        ev.recomendacion_texto = texto
        ev.progreso = "completada" if ev.recomendacion else "en_progreso"
        campos += ["recomendacion", "recomendacion_texto", "progreso"]
    elif ev.progreso == "completada":      # se editó una evaluación cerrada: el resultado ya no vale
        ev.progreso, ev.recomendacion, ev.recomendacion_texto = "en_progreso", "", ""
        campos += ["recomendacion", "recomendacion_texto", "progreso"]
    ev.save(update_fields=campos)

    getattr(ev, "_prefetched_objects_cache", {}).clear()   # evita leer valoraciones obsoletas
    return rows


@transaction.atomic
def crear_segunda_evaluacion(padre):
    """HU-09: copia la primera evaluación; deja pendientes los subfactores de los factores con Debilidad/Amenaza."""
    hija = Evaluacion.objects.create(
        usuario=padre.usuario, organizacion=padre.organizacion, software=padre.software,
        categoria=padre.categoria, descripcion=padre.descripcion, tipo="segunda",
        evaluacion_padre=padre, actualizacion=padre.actualizacion, paso_actual=3,
    )
    vfs = list(padre.valoraciones_factor.all())
    a_reevaluar = {v.factor_id for v in vfs if v.foda in ("Debilidad", "Amenaza")}

    EvaluacionFactor.objects.bulk_create([
        EvaluacionFactor(
            evaluacion=hija, factor_id=v.factor_id,
            importancia_decisor=v.importancia_decisor, importancia_relativa=v.importancia_relativa,
            relevante=v.relevante, peso_global=v.peso_global,
            alcance_evaluado=v.alcance_evaluado, foda=v.foda,
        ) for v in vfs
    ])
    EvaluacionSubfactor.objects.bulk_create([
        EvaluacionSubfactor(evaluacion=hija, subfactor_id=v.subfactor_id, importancia=v.importancia)
        for v in padre.valoraciones_subfactor.select_related("subfactor")
        if v.subfactor.factor_id not in a_reevaluar
    ])
    return hija