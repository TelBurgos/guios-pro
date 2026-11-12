from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import render, redirect
from .models import ActualizacionIS
from .services import actualizar_is_seguro
from django.db.models import Sum

@login_required
def literatura(request):
    error = None
    if request.method == "POST":
        _, error = actualizar_is_seguro()
        (messages.warning if error else messages.success)(
            request, error or "Importancia sugerida actualizada.")
        return redirect("importancia_sugerida:literatura")
    act = ActualizacionIS.objects.prefetch_related("detalles__factor").first()
    total = n_sub = 0
    if act:
        total = act.consultas.aggregate(t=Sum("articulos_encontrados"))["t"] or 0
        n_sub = act.consultas.count()
    return render(request, "importancia_sugerida/literatura.html", {
        "act": act, "error": error, "total_articulos": total, "n_subfactores": n_sub,
    })
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from .exportar import obtener_actualizacion, libro_en_bytes


@login_required
def descargar_excel(request, act_id=None):
    act = obtener_actualizacion(act_id)
    resp = HttpResponse(
        libro_en_bytes(act),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    resp["Content-Disposition"] = f'attachment; filename="resultados_IS_act{act.id}.xlsx"'
    return resp