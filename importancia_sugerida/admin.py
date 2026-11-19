from django.contrib import admin
from .models import ActualizacionIS, ConsultaIS, DetalleActualizacionIS


class SoloLecturaAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(ActualizacionIS)
class ActualizacionISAdmin(SoloLecturaAdmin):
    list_display = ("id", "fecha", "fuente", "version_calculo")


@admin.register(ConsultaIS)
class ConsultaISAdmin(SoloLecturaAdmin):
    list_display = ("actualizacion", "subfactor", "articulos_encontrados")
    list_filter = ("actualizacion",)


@admin.register(DetalleActualizacionIS)
class DetalleActualizacionISAdmin(SoloLecturaAdmin):
    list_display = ("actualizacion", "factor", "importancia_literaria",
                    "importancia_experta", "importancia_sugerida")
    list_filter = ("actualizacion",)