import csv

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import ProtectedError, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import NoReverseMatch, reverse
from django.views.decorators.http import require_http_methods, require_POST
from .forms import CategoriaForm, EvaluacionForm, OrganizacionForm
from importancia_sugerida.models import ActualizacionIS

from .logic import (
    LEVELS, SUB_LEVELS, comparar_evaluaciones, derive, detalle_recomendacion,
    factores_a_reevaluar, init_state, resumen_resultados, subfactores_pendientes,
)
from .models import Evaluacion, Organizacion
from .services import cargar_estado, catalogue, crear_segunda_evaluacion, guardar_avance

TAB_PASO = {"factores": 1, "subfactores": 3, "resultados": 6}
PASO_TAB = {1: "factores", 2: "factores", 3: "subfactores", 4: "resultados", 5: "resultados", 6: "resultados"}


def parse_rating(value):
    value = int(value)
    if value not in (1, 2, 3, 4):
        raise ValueError("Fuera de rango")
    return value


def _evaluacion_actual(request):
    eval_id = request.session.get("evaluacion_actual_id")
    if not eval_id:
        return None
    return (
        Evaluacion.objects.filter(pk=eval_id, usuario=request.user)
        .select_related("organizacion", "actualizacion")
        .prefetch_related("valoraciones_factor", "valoraciones_subfactor")
        .first()
    )


# ==========================================
# EVALUACIÓN GUIOS (pasos 1 a 6)
# ==========================================

@login_required
@require_http_methods(["GET", "POST"])
def inicio(request):
    ev = _evaluacion_actual(request)
    if ev is None:
        return redirect("evaluacion:nueva_evaluacion")

    cat = catalogue(ev.actualizacion)
    state = cargar_estado(ev, cat)       # la BD es la fuente de verdad
    tab = PASO_TAB.get(ev.paso_actual, "factores")
    error = ""

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "reset":
            state = init_state(cat)
            tab = "factores"

        elif action == "factors":
            try:
                for i, f in enumerate(cat):
                    state[str(i)]["decisor"] = parse_rating(request.POST.get(f"decisor_{i}"))
                    scope = request.POST.get(f"scope_{i}") if f["scope"] == "Ambos" else f["scope"]
                    if scope not in ("Interno", "Externo"):
                        raise ValueError("El alcance es inválido")
                    state[str(i)]["scope"] = scope
                tab = "subfactores"
            except (ValueError, TypeError):
                error = "Revise las valoraciones de los factores."

        elif action == "subfactors":
            tab = "subfactores"
            try:
                i = int(request.POST.get("factor_id", "-1"))
                if i < 0 or i >= len(cat):
                    raise ValueError("Factor desconocido")
                state[str(i)]["weights"] = [
                    parse_rating(request.POST.get(f"weight_{i}_{j}"))
                    for j in range(len(cat[i]["subfactors"]))
                ]
                state[str(i)]["saved"] = True
            except (ValueError, TypeError):
                error = "Revise las valoraciones de los subfactores."

        elif action == "recommendation":
            # HU-06: el servidor impide avanzar con subfactores sin valorar
            rows_chk = derive(cat, state)
            pendientes = subfactores_pendientes(rows_chk)
            if pendientes:
                tab = "subfactores"
                error = f"Faltan {pendientes} subfactores por valorar. Complete todos antes de continuar."
            elif not any(r["relevant"] for r in rows_chk):
                tab = "factores"
                error = "Ningún factor resulta relevante. Revise las valoraciones de importancia."
            else:
                guardar_avance(ev, cat, state, TAB_PASO["resultados"], completar=True)
                return redirect("evaluacion:ver_evaluacion", pk=ev.pk)

        if error:
            state = cargar_estado(ev, cat)          # descarta cambios parciales
        else:
            guardar_avance(ev, cat, state, TAB_PASO[tab])

    rows = derive(cat, state)

    # ---------- Paso 3: factor seleccionado y navegación ----------
    relevant = [r for r in rows if r["relevant"]]
    ids = [r["id"] for r in relevant]

    selected_id = request.POST.get("factor_id") if request.method == "POST" else request.GET.get("factor_id")
    try:
        selected_id = int(selected_id)
    except (ValueError, TypeError):
        selected_id = ids[0] if ids else None
    if selected_id not in ids:
        selected_id = ids[0] if ids else None

    if (request.method == "POST" and request.POST.get("action") == "subfactors"
            and request.POST.get("nav") == "next" and not error and selected_id in ids):
        pos = ids.index(selected_id)
        if pos + 1 < len(ids):
            selected_id = ids[pos + 1]

    selected = rows[selected_id] if selected_id is not None else None
    sub_rows = []
    if selected:
        # Solo se muestran valoradas si ya se guardaron (no hay 1 preseleccionado)
        weights = selected["weights"] if selected["saved"] else []
        sub_rows = [(name, weights[j] if j < len(weights) else None)
                    for j, name in enumerate(selected["subfactors"])]

    factor_nav = [{
        "id": r["id"], "name": r["name"], "total": len(r["subfactors"]),
        "done": len(r["subfactors"]) if r["saved"] else 0,
        "active": r["id"] == selected_id,
    } for r in relevant]

    pos = ids.index(selected_id) if selected_id in ids else None
    prev_id = ids[pos - 1] if pos is not None and pos > 0 else None
    next_id = ids[pos + 1] if pos is not None and pos + 1 < len(ids) else None

    is_label = ""
    if selected:
        try:
            is_label = LEVELS[int(selected["suggested"]) - 1]
        except (ValueError, TypeError, IndexError, KeyError):
            is_label = ""

    try:
        informe_url = reverse("evaluacion:exportar_evaluacion", args=[ev.pk])
    except NoReverseMatch:
        informe_url = None

    ctx = {
        "rows": rows, "relevant": relevant, "selected": selected, "sub_rows": sub_rows,
        "factor_nav": factor_nav, "missing": subfactores_pendientes(rows),
        "prev_id": prev_id, "next_id": next_id, "is_label": is_label,
        "a_reevaluar": [r["name"] for r in factores_a_reevaluar(rows)],
        "informe_url": informe_url, "evaluacion": ev,
        "levels": list(enumerate(LEVELS, 1)), "sublevels": list(enumerate(SUB_LEVELS, 1)),
        "tab": tab, "error": error,
        "is_fecha": ev.actualizacion.fecha if ev.actualizacion else None,
    }
    ctx.update(resumen_resultados(rows))   # pond_*, foda_*, reco_*
    return render(request, "evaluacion/inicio.html", ctx)


# ==========================================
# ORGANIZACIÓN Y NUEVA EVALUACIÓN
# ==========================================

@login_required
@require_POST
def crear_organizacion(request):
    form = OrganizacionForm(request.POST, user=request.user)
    if form.is_valid():
        form.save()
        messages.success(request, "Organización registrada.")
    else:
        messages.error(request, " ".join(e for errs in form.errors.values() for e in errs))
    return redirect("evaluacion:nueva_evaluacion")


@login_required
def nueva_evaluacion(request):
    if request.method == "POST":
        form = EvaluacionForm(request.POST, user=request.user)
        if form.is_valid():
            evaluacion = form.save(commit=False)
            evaluacion.usuario = request.user
            # La evaluación recuerda con qué IS se calculó (reproducibilidad)
            evaluacion.actualizacion = ActualizacionIS.objects.order_by("-fecha").first()
            evaluacion.save()
            request.session["evaluacion_actual_id"] = evaluacion.id
            return redirect("evaluacion:inicio")
    else:
        # Preselecciona lo recién creado en los modales
        initial = {}
        for campo in ("organizacion", "categoria"):
            valor = request.GET.get(campo, "")
            if valor.isdigit():
                initial[campo] = int(valor)
        form = EvaluacionForm(user=request.user, initial=initial)

    return render(request, "evaluacion/nueva_evaluacion.html", {
        "form": form,
        "org_form": OrganizacionForm(user=request.user),
        "cat_form": CategoriaForm(),
    })

@login_required
def panel(request):
    cat = catalogue()
    qs = (
        Evaluacion.objects.filter(usuario=request.user)
        .select_related("organizacion")
        .prefetch_related("valoraciones_factor", "valoraciones_subfactor")
        .order_by("-fecha_creacion")
    )

    evaluaciones = []
    for ev in qs:
        completada = ev.progreso == "completada"
        if completada:
            pct, paso = 100, "Resultado listo"
        else:
            rows = derive(cat, cargar_estado(ev, cat))   # aprox. con la IS vigente
            relevantes = [r for r in rows if r["relevant"]]
            pct = int(sum(1 for r in relevantes if r["saved"]) / len(relevantes) * 100) if relevantes else 0
            paso = f"Paso {ev.paso_actual} de 6"

        try:
            url = reverse("evaluacion:abrir_evaluacion", args=[ev.pk])
        except NoReverseMatch:
            url = "#"

        evaluaciones.append({
            "nombre": ev.software, "organizacion": ev.organizacion.nombre,
            "tipo": ev.get_tipo_display(),
            "estado": "Completada" if completada else "En progreso",
            "estado_slug": "completada" if completada else "en-progreso",
            "paso": paso, "progreso": pct, "fecha": ev.fecha_creacion, "url": url,
        })

    completadas = sum(1 for e in evaluaciones if e["estado_slug"] == "completada")
    return render(request, "evaluacion/panel.html", {
        "evaluaciones": evaluaciones, "total": len(evaluaciones),
        "completadas": completadas, "en_progreso": len(evaluaciones) - completadas,
    })


# ==========================================
# HISTORIAL, DETALLE Y SEGUNDA EVALUACIÓN
# ==========================================

@login_required
def historial(request):
    qs = (
        Evaluacion.objects.filter(usuario=request.user)
        .select_related("organizacion", "categoria")
        .prefetch_related("valoraciones_factor")
    )

    q = request.GET.get("q", "").strip()
    resultado = request.GET.get("resultado", "")
    anio = request.GET.get("anio", "")
    org = request.GET.get("org", "")

    if q:
        qs = qs.filter(Q(software__icontains=q) | Q(organizacion__nombre__icontains=q))
    if resultado in ("A", "B", "C"):
        qs = qs.filter(recomendacion=resultado)
    elif resultado == "pendiente":
        qs = qs.filter(recomendacion="")
    if anio.isdigit():
        qs = qs.filter(fecha_creacion__year=int(anio))
    if org.isdigit():
        qs = qs.filter(organizacion_id=int(org))

    base = Evaluacion.objects.filter(usuario=request.user)
    return render(request, "evaluacion/historial.html", {
        "evaluaciones": qs, "q": q, "resultado": resultado, "anio": anio, "org": org,
        "anios": base.dates("fecha_creacion", "year", order="DESC"),
        "organizaciones": Organizacion.objects.filter(evaluaciones__usuario=request.user).distinct(),
    })


@login_required
def abrir_evaluacion(request, pk):
    ev = get_object_or_404(Evaluacion, pk=pk, usuario=request.user)
    request.session["evaluacion_actual_id"] = ev.id
    destino = reverse("evaluacion:inicio")
    return redirect(destino + ("#resultados" if ev.progreso == "completada" else ""))


@login_required
def ver_evaluacion(request, pk):
    ev = get_object_or_404(
        Evaluacion.objects.select_related("organizacion", "categoria", "actualizacion", "evaluacion_padre")
        .prefetch_related("valoraciones_factor", "valoraciones_subfactor"),
        pk=pk, usuario=request.user,
    )
    cat = catalogue(ev.actualizacion)
    rows = derive(cat, cargar_estado(ev, cat))
    _, reco_title, reco_body = detalle_recomendacion(ev.recomendacion_texto)

    a_reevaluar, segunda, comparacion = [], None, []
    if ev.tipo == "primera" and ev.progreso == "completada":
        a_reevaluar = [r["name"] for r in factores_a_reevaluar(rows)]
        segunda = ev.segundas.first()
    elif ev.tipo == "segunda" and ev.evaluacion_padre:
        padre = ev.evaluacion_padre
        cat_p = catalogue(padre.actualizacion)
        comparacion = comparar_evaluaciones(derive(cat_p, cargar_estado(padre, cat_p)), rows)

    ctx = {
        "ev": ev, "a_reevaluar": a_reevaluar, "segunda": segunda, "comparacion": comparacion,
        "puede_segunda": bool(a_reevaluar) and segunda is None,
    }
    ctx.update(resumen_resultados(rows))
    ctx.update({"reco_title": reco_title, "reco_body": reco_body})   # usa lo guardado
    return render(request, "evaluacion/ver_evaluacion.html", ctx)


@login_required
@require_POST
def eliminar_evaluacion(request, pk):
    """Elimina una evaluación del usuario y vuelve al historial."""
    ev = Evaluacion.objects.filter(pk=pk, usuario=request.user).first()

    if ev is None:
        messages.info(request, "Esa evaluación ya no existe o fue eliminada.")
        return redirect("evaluacion:historial")

    nombre = ev.software
    ev_id = ev.pk

    try:
        ev.delete()
    except ProtectedError:
        messages.error(
            request,
            "No se puede eliminar: tiene una segunda evaluación asociada. Elimine primero la segunda.",
        )
        return redirect("evaluacion:historial")

    # Si era la evaluación en curso, se limpia la sesión
    if request.session.get("evaluacion_actual_id") == ev_id:
        del request.session["evaluacion_actual_id"]

    messages.success(request, f"Evaluación de «{nombre}» eliminada.")
    return redirect("evaluacion:historial")


@login_required
@require_POST
def crear_segunda(request, pk):
    """HU-09: inicia (o retoma) la segunda evaluación de una evaluación completada."""
    padre = get_object_or_404(Evaluacion, pk=pk, usuario=request.user)
    if padre.tipo != "primera" or padre.progreso != "completada":
        messages.error(request, "Solo se puede hacer una segunda evaluación de una primera completada.")
        return redirect("evaluacion:ver_evaluacion", pk=padre.pk)

    hija = padre.segundas.first()
    if hija is None:
        cat = catalogue(padre.actualizacion)
        if not factores_a_reevaluar(derive(cat, cargar_estado(padre, cat))):
            messages.info(request, "No hay debilidades ni amenazas: no se sugiere segunda evaluación.")
            return redirect("evaluacion:ver_evaluacion", pk=padre.pk)
        hija = crear_segunda_evaluacion(padre)

    request.session["evaluacion_actual_id"] = hija.id
    return redirect("evaluacion:inicio")


# ==========================================
# EXPORTACIÓN
# ==========================================

@login_required
def exportar_evaluacion(request, pk):
    ev = get_object_or_404(Evaluacion.objects.select_related("organizacion"), pk=pk, usuario=request.user)

    resp = HttpResponse(content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="evaluacion_{ev.pk}.csv"'
    resp.write("\ufeff")  # para que Excel lea bien las tildes
    w = csv.writer(resp)
    w.writerow(["Software", ev.software, "Organización", ev.organizacion.nombre])
    w.writerow(["Tipo", ev.get_tipo_display()])
    w.writerow(["Recomendación", ev.recomendacion_texto])
    w.writerow([])
    w.writerow(["Factor", "Ponderación media", "Alcance", "FODA"])
    valoraciones = (ev.valoraciones_factor.filter(peso_global__isnull=False)
                    .select_related("factor").order_by("factor_id"))
    for v in valoraciones:
        w.writerow([v.factor.nombre, f"{v.peso_global:.2f}", v.alcance_evaluado, v.foda])
    return resp


@login_required
def exportar_todo(request):
    resp = HttpResponse(content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = 'attachment; filename="historial_guios.csv"'
    resp.write("\ufeff")
    w = csv.writer(resp)
    w.writerow(["Fecha", "Software", "Organización", "Categoría", "Tipo", "Resultado",
                "Ponderación media", "F", "O", "D", "A"])
    evaluaciones = (
        Evaluacion.objects.filter(usuario=request.user)
        .select_related("organizacion", "categoria")
        .prefetch_related("valoraciones_factor")
    )
    for e in evaluaciones:
        w.writerow([
            e.fecha_creacion.date(), e.software, e.organizacion.nombre, e.categoria.nombre,
            e.get_tipo_display(), e.etiqueta, e.ponderacion_media or "",
            e.fortalezas, e.oportunidades, e.debilidades, e.amenazas,
        ])
    return resp

@login_required
@require_POST
def crear_categoria(request):
    form = CategoriaForm(request.POST)
    if form.is_valid():
        categoria = form.save()
        messages.success(request, "Categoría registrada.")
        return redirect(f"{reverse('evaluacion:nueva_evaluacion')}?categoria={categoria.pk}")
    messages.error(request, " ".join(e for errs in form.errors.values() for e in errs))
    return redirect("evaluacion:nueva_evaluacion")