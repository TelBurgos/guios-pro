from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.db.models import Count, Sum
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_http_methods

from evaluacion.models import Subfactor

from .exportar import libro_en_bytes, obtener_actualizacion
from .models import ActualizacionIS
from .services import actualizar_is_seguro

# Evita que dos personas lancen la actualización a la vez (cuesta cuota de la API)
LOCK_KEY = "importancia_sugerida:actualizando"
LOCK_TTL = 15 * 60  # segundos

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


# ==========================================
# LITERATURA Y TRAZABILIDAD (RF-05 / HU-11)
# ==========================================

@login_required
@require_http_methods(["GET", "POST"])
def literatura(request):
    if request.method == "POST":
        # Cualquier decisor autenticado puede actualizar la IS (HU-11);
        # el candado evita ejecuciones simultáneas.
        if not cache.add(LOCK_KEY, request.user.pk, LOCK_TTL):
            messages.info(request, "Ya hay una actualización en curso. Intenta de nuevo en unos minutos.")
            return redirect("importancia_sugerida:literatura")

        try:
            act, error = actualizar_is_seguro()
        finally:
            cache.delete(LOCK_KEY)

        if error:
            messages.warning(request, error)  # RNF-08: avisa y conserva la última IS
        else:
            messages.success(
                request,
                f"Importancia sugerida actualizada ({act.detalles.count()} factores).",
            )
        return redirect("importancia_sugerida:literatura")

    act = (
        ActualizacionIS.objects
        .prefetch_related("detalles__factor")
        .order_by("-fecha")
        .first()
    )

    total_articulos = n_subfactores = 0
    if act:
        resumen = act.consultas.aggregate(total=Sum("articulos_encontrados"), n=Count("id"))
        total_articulos = resumen["total"] or 0
        n_subfactores = resumen["n"]

    return render(request, "importancia_sugerida/literatura.html", {
        "act": act,
        "total_articulos": total_articulos,
        "n_subfactores": n_subfactores,
        "puede_actualizar": True,
        # Cuántos subfactores ya tienen términos de búsqueda
        "ia_con_terminos": Subfactor.objects.exclude(terminos_busqueda="").count(),
        "ia_total": Subfactor.objects.count(),
    })


# ==========================================
# DESCARGA DEL EXCEL DE RESULTADOS
# ==========================================

@login_required
@require_GET
def descargar_excel(request, act_id=None):
    act = obtener_actualizacion(act_id)  # lanza Http404 si no existe o no hay ninguna

    resp = HttpResponse(libro_en_bytes(act), content_type=XLSX_MIME)
    resp["Content-Disposition"] = f'attachment; filename="resultados_IS_act{act.id}.xlsx"'
    return resp