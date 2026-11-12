import csv
import re

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import NoReverseMatch, reverse
from django.views.decorators.http import require_http_methods

from .forms import EvaluacionForm
from .logic import catalogue, init_state, derive, recommendation, LEVELS, SUB_LEVELS
from .models import Evaluacion, Organizacion


# ==========================================
# EVALUACIÓN ORIGINAL DE GUIOSPRO
# ==========================================

@login_required
@require_http_methods(["GET", "POST"])
def inicio(request):
    cat = catalogue()
    state = request.session.get("guiospro_state")
    if not isinstance(state, dict) or set(state) != {str(i) for i in range(len(cat))}:
        state = init_state(cat)

    tab = "factores"
    error = ""
    show_recommendation = False

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "reset":
            state = init_state(cat)

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
                values = [
                    parse_rating(request.POST.get(f"weight_{i}_{j}"))
                    for j in range(len(cat[i]["subfactors"]))
                ]
                state[str(i)]["weights"] = values
                state[str(i)]["saved"] = True
            except (ValueError, TypeError):
                error = "Revise las valoraciones de los subfactores."

        elif action == "recommendation":
            tab = "resultados"
            show_recommendation = True

        request.session["guiospro_state"] = state

    rows = derive(cat, state)

    # Respaldo para agrupar por dimensión (pasos 1, 2, 3 y 4)
    for r in rows:
        r.setdefault("dimension", cat[r["id"]].get("dimension", "Factores"))

    con_score = [r for r in rows if r["score"] is not None]

    # La recomendación se calcula siempre (para mostrarla en el paso 4);
    # solo se guarda en el historial cuando se pulsa "Guardar en historial".
    reco_text = (recommendation(rows) or "") if con_score else ""
    texto_recomendacion = reco_text if show_recommendation else None

    if show_recommendation:
        guardar_resultado(request, rows, state, texto_recomendacion)

    # ---------- Paso 2: factor seleccionado y navegación ----------
    relevant = [r for r in rows if r["relevant"]]
    ids = [r["id"] for r in relevant]

    selected_id = request.POST.get("factor_id") if request.method == "POST" else request.GET.get("factor_id")
    try:
        selected_id = int(selected_id)
    except (ValueError, TypeError):
        selected_id = ids[0] if ids else None
    if selected_id not in ids:
        selected_id = ids[0] if ids else None

    # "Siguiente factor": tras guardar, pasa al siguiente factor relevante
    if (
        request.method == "POST"
        and request.POST.get("action") == "subfactors"
        and request.POST.get("nav") == "next"
        and not error
        and selected_id in ids
    ):
        pos = ids.index(selected_id)
        if pos + 1 < len(ids):
            selected_id = ids[pos + 1]

    selected = rows[selected_id] if selected_id is not None else None

    # Subfactores con su valoración actual (para los botones 1-4)
    sub_rows = []
    if selected:
        weights = selected.get("weights") or []
        sub_rows = [
            (name, weights[j] if j < len(weights) else None)
            for j, name in enumerate(selected["subfactors"])
        ]

    # Columna lateral: factores relevantes con su avance
    factor_nav = []
    for r in relevant:
        total = len(r["subfactors"])
        guardado = bool(state[str(r["id"])].get("saved"))
        factor_nav.append({
            "id": r["id"],
            "name": r["name"],
            "total": total,
            "done": total if guardado else 0,
            "active": r["id"] == selected_id,
        })
    missing = sum(f["total"] - f["done"] for f in factor_nav)

    pos = ids.index(selected_id) if selected_id in ids else None
    prev_id = ids[pos - 1] if pos is not None and pos > 0 else None
    next_id = ids[pos + 1] if pos is not None and pos + 1 < len(ids) else None

    is_label = ""
    if selected:
        try:
            is_label = LEVELS[int(selected["suggested"]) - 1]
        except (ValueError, TypeError, IndexError, KeyError):
            is_label = ""

    # ---------- Paso 3: ponderación ----------
    escala = 4

    def tono(pct):
        if pct >= 60:
            return "high"
        if pct >= 40:
            return "mid"
        return "low"

    pond_rows = []
    for r in sorted(con_score, key=lambda x: x["score"], reverse=True):
        pct = int(round(r["score"] / escala * 100))
        pond_rows.append({
            "name": r["name"],
            "score": r["score"],
            "pct": pct,
            "tone": tono(pct),
        })

    pond_media = None
    pond_pct = 0
    pond_nivel = ""
    pond_dim = []

    if con_score:
        pond_media = round(sum(r["score"] for r in con_score) / len(con_score), 2)
        pond_pct = int(round(pond_media / escala * 100))

        if pond_pct >= 75:
            pond_nivel = "Nivel favorable"
        elif pond_pct >= 50:
            pond_nivel = "Nivel moderado"
        else:
            pond_nivel = "Nivel bajo"

        por_dim = {}
        for r in con_score:
            por_dim.setdefault(r["dimension"], []).append(r["score"])

        for nombre, valores in por_dim.items():
            media = round(sum(valores) / len(valores), 2)
            pond_dim.append({
                "name": nombre,
                "score": media,
                "pct": int(round(media / escala * 100)),
            })

    # ---------- Paso 4: FODA y recomendación ----------
    foda_cfg = [
        ("Fortaleza", "Fortalezas", "F", "f"),
        ("Oportunidad", "Oportunidades", "O", "o"),
        ("Debilidad", "Debilidades", "D", "d"),
        ("Amenaza", "Amenazas", "A", "a"),
    ]

    foda_groups = []
    for clave, titulo, letra, css in foda_cfg:
        nombres = [r["name"] for r in con_score if r["foda"] == clave]
        foda_groups.append({
            "title": titulo,
            "letter": letra,
            "css": css,
            "count": len(nombres),
            "names": nombres,
        })

    match = re.search(r"Recomendación ([ABC]):\s*(.*)", reco_text, re.S)
    reco_code = match.group(1) if match else ""
    reco_body = match.group(2).strip() if match else reco_text
    reco_title = {
        "A": "Adopción recomendada",
        "B": "Adopción con plan de mitigación",
        "C": "Adopción no recomendada",
    }.get(reco_code, "Recomendación")

    riesgos = [r["name"] for r in con_score if r["foda"] in ("Debilidad", "Amenaza")]
    reco_actions = [f"Mitigar: {nombre}" for nombre in riesgos[:3]]

    # ---------- Evaluación en curso (encabezado) ----------
    evaluacion = None
    eval_id = request.session.get("evaluacion_actual_id")
    if eval_id:
        evaluacion = (
            Evaluacion.objects.filter(pk=eval_id, usuario=request.user)
            .select_related("organizacion")
            .first()
        )

    informe_url = None
    if evaluacion:
        try:
            informe_url = reverse("evaluacion:exportar_evaluacion", args=[evaluacion.pk])
        except NoReverseMatch:
            informe_url = None

    return render(request, "evaluacion/historial.html", {
        "rows": rows,
        "relevant": relevant,
        "selected": selected,
        "sub_rows": sub_rows,
        "factor_nav": factor_nav,
        "missing": missing,
        "prev_id": prev_id,
        "next_id": next_id,
        "is_label": is_label,
        "pond_rows": pond_rows,
        "pond_media": pond_media,
        "pond_pct": pond_pct,
        "pond_nivel": pond_nivel,
        "pond_dim": pond_dim,
        "escala": escala,
        "foda_groups": foda_groups,
        "foda_total": len(con_score),
        "reco_text": reco_text,
        "reco_code": reco_code,
        "reco_title": reco_title,
        "reco_body": reco_body,
        "reco_actions": reco_actions,
        "informe_url": informe_url,
        "evaluacion": evaluacion,
        "levels": list(enumerate(LEVELS, 1)),
        "sublevels": list(enumerate(SUB_LEVELS, 1)),
        "tab": tab,
        "error": error,
    })


def parse_rating(value):
    value = int(value)
    if value not in (1, 2, 3, 4):
        raise ValueError("Fuera de rango")
    return value


def guardar_resultado(request, rows, state, texto):
    """Guarda en la BD el resultado de la evaluación actual."""
    eval_id = request.session.get("evaluacion_actual_id")
    if not eval_id:
        return
    ev = Evaluacion.objects.filter(pk=eval_id, usuario=request.user).first()
    if not ev:
        return

    con_score = [r for r in rows if r["score"] is not None]

    def conteo(nombre):
        return sum(1 for r in con_score if r["foda"] == nombre)

    codigo = re.search(r"Recomendación ([ABC]):", texto or "")
    ev.estado_guiospro = state
    ev.recomendacion = codigo.group(1) if codigo else ""
    ev.recomendacion_texto = texto or ""
    ev.ponderacion_media = (
        round(sum(r["score"] for r in con_score) / len(con_score), 2) if con_score else None
    )
    ev.fortalezas = conteo("Fortaleza")
    ev.oportunidades = conteo("Oportunidad")
    ev.debilidades = conteo("Debilidad")
    ev.amenazas = conteo("Amenaza")
    ev.progreso = "completada" if ev.recomendacion else "en_progreso"
    ev.save()


# ==========================================
# NUEVA EVALUACIÓN Y PANEL
# ==========================================

@login_required
def nueva_evaluacion(request):
    if request.method == "POST":
        form = EvaluacionForm(request.POST)

        if form.is_valid():
            evaluacion = form.save(commit=False)

            # Asociar la evaluación al usuario autenticado
            evaluacion.usuario = request.user

            # Guardar los datos en PostgreSQL
            evaluacion.save()

            # Guardar el identificador de la evaluación actual
            request.session["evaluacion_actual_id"] = evaluacion.id

            # Inicializar las valoraciones para la nueva evaluación
            request.session["guiospro_state"] = init_state(catalogue())

            # Abrir la evaluación de GUIOSPRO
            return redirect("evaluacion:inicio")
    else:
        form = EvaluacionForm()

    return render(request, "evaluacion/nueva_evaluacion.html", {"form": form})


@login_required
def panel(request):
    cat = catalogue()
    qs = (
        Evaluacion.objects.filter(usuario=request.user)
        .select_related("organizacion")
        .order_by("-fecha_creacion")
    )

    evaluaciones = []
    for ev in qs:
        completada = ev.progreso == "completada"

        if completada:
            pct, paso = 100, "Resultado listo"
        else:
            state = ev.estado_guiospro or init_state(cat)
            relevantes = [r for r in derive(cat, state) if r["relevant"]]
            guardados = sum(
                1 for r in relevantes if state[str(r["id"])].get("saved")
            )
            pct = int(guardados / len(relevantes) * 100) if relevantes else 0
            paso = "Subfactores"

        try:
            url = reverse("evaluacion:abrir_evaluacion", args=[ev.pk])
        except NoReverseMatch:
            url = "#"

        evaluaciones.append({
            "nombre": ev.software,
            "organizacion": ev.organizacion.nombre,
            "estado": "Completada" if completada else "En progreso",
            "estado_slug": "completada" if completada else "en-progreso",
            "paso": paso,
            "progreso": pct,
            "fecha": ev.fecha_creacion,
            "url": url,
        })

    completadas = sum(1 for e in evaluaciones if e["estado_slug"] == "completada")

    return render(request, "evaluacion/panel.html", {
        "evaluaciones": evaluaciones,
        "total": len(evaluaciones),
        "completadas": completadas,
        "en_progreso": len(evaluaciones) - completadas,
    })
# ==========================================
# HISTORIAL
# ==========================================

@login_required
def historial(request):
    qs = (
        Evaluacion.objects.filter(usuario=request.user)
        .select_related("organizacion", "categoria")
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
        "evaluaciones": qs,
        "q": q,
        "resultado": resultado,
        "anio": anio,
        "org": org,
        "anios": base.dates("fecha_creacion", "year", order="DESC"),
        "organizaciones": Organizacion.objects.filter(
            evaluaciones__usuario=request.user
        ).distinct(),
    })


@login_required
def abrir_evaluacion(request, pk):
    """Carga una evaluación guardada en la sesión y abre sus resultados."""
    ev = get_object_or_404(Evaluacion, pk=pk, usuario=request.user)
    request.session["evaluacion_actual_id"] = ev.id
    request.session["guiospro_state"] = ev.estado_guiospro or init_state(catalogue())
    return redirect(reverse("evaluacion:inicio") + "#resultados")


@login_required
def exportar_evaluacion(request, pk):
    ev = get_object_or_404(Evaluacion, pk=pk, usuario=request.user)
    cat = catalogue()
    state = ev.estado_guiospro or init_state(cat)

    resp = HttpResponse(content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="evaluacion_{ev.pk}.csv"'
    resp.write("\ufeff")  # para que Excel lea bien las tildes
    w = csv.writer(resp)
    w.writerow(["Software", ev.software, "Organización", ev.organizacion.nombre])
    w.writerow(["Recomendación", ev.recomendacion_texto])
    w.writerow([])
    w.writerow(["Factor", "Ponderación media", "Alcance", "FODA"])
    for r in derive(cat, state):
        if r["score"] is not None:
            w.writerow([r["name"], f'{r["score"]:.1f}', r["scope_selected"], r["foda"]])
    return resp


@login_required
def exportar_todo(request):
    resp = HttpResponse(content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = 'attachment; filename="historial_guios.csv"'
    resp.write("\ufeff")
    w = csv.writer(resp)
    w.writerow([
        "Fecha", "Software", "Organización", "Categoría", "Resultado",
        "Ponderación media", "F", "O", "D", "A",
    ])
    evaluaciones = (
        Evaluacion.objects.filter(usuario=request.user)
        .select_related("organizacion", "categoria")
    )
    for e in evaluaciones:
        w.writerow([
            e.fecha_creacion.date(), e.software, e.organizacion.nombre,
            e.categoria.nombre, e.etiqueta, e.ponderacion_media or "",
            e.fortalezas, e.oportunidades, e.debilidades, e.amenazas,
        ])
    return resp


@login_required
def ver_evaluacion(request, pk):
    ev = get_object_or_404(Evaluacion, pk=pk, usuario=request.user)
    cat = catalogue()
    state = ev.estado_guiospro or init_state(cat)
    rows = derive(cat, state)
    for r in rows:
        r.setdefault("dimension", cat[r["id"]].get("dimension", "Factores"))
    con_score = [r for r in rows if r["score"] is not None]
    escala = 4

    def tono(pct):
        return "high" if pct >= 60 else "mid" if pct >= 40 else "low"

    pond_rows = [
        {
            "name": r["name"],
            "score": r["score"],
            "pct": int(round(r["score"] / escala * 100)),
            "tone": tono(int(round(r["score"] / escala * 100))),
        }
        for r in sorted(con_score, key=lambda x: x["score"], reverse=True)
    ]

    pond_media, pond_pct, pond_nivel = None, 0, ""
    if con_score:
        pond_media = round(sum(r["score"] for r in con_score) / len(con_score), 2)
        pond_pct = int(round(pond_media / escala * 100))
        pond_nivel = (
            "Nivel favorable" if pond_pct >= 75
            else "Nivel moderado" if pond_pct >= 50
            else "Nivel bajo"
        )

    foda_cfg = [
        ("Fortaleza", "Fortalezas", "F", "f"),
        ("Oportunidad", "Oportunidades", "O", "o"),
        ("Debilidad", "Debilidades", "D", "d"),
        ("Amenaza", "Amenazas", "A", "a"),
    ]
    foda_groups = []
    for clave, titulo, letra, css in foda_cfg:
        nombres = [r["name"] for r in con_score if r["foda"] == clave]
        foda_groups.append({
            "title": titulo, "letter": letra, "css": css,
            "count": len(nombres), "names": nombres,
        })

    reco_text = ev.recomendacion_texto or ""
    match = re.search(r"Recomendación ([ABC]):\s*(.*)", reco_text, re.S)
    reco_code = match.group(1) if match else ev.recomendacion
    reco_body = match.group(2).strip() if match else reco_text
    reco_title = {
        "A": "Adopción recomendada",
        "B": "Adopción con plan de mitigación",
        "C": "Adopción no recomendada",
    }.get(reco_code, "Recomendación")

    riesgos = [r["name"] for r in con_score if r["foda"] in ("Debilidad", "Amenaza")]

    return render(request, "evaluacion/ver_evaluacion.html", {
        "ev": ev,
        "pond_rows": pond_rows,
        "pond_media": pond_media,
        "pond_pct": pond_pct,
        "pond_nivel": pond_nivel,
        "escala": escala,
        "foda_groups": foda_groups,
        "reco_title": reco_title,
        "reco_body": reco_body,
        "reco_actions": [f"Mitigar: {n}" for n in riesgos[:3]],
    })