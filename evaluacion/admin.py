from django.contrib import admin

from .models import Categoria, Dimension, Evaluacion, Factor, Organizacion, Subfactor


@admin.register(Organizacion)
class OrganizacionAdmin(admin.ModelAdmin):
    list_display = ("id", "nombre", "usuario")
    search_fields = ("nombre",)


@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    list_display = ("id", "nombre")
    search_fields = ("nombre",)


@admin.register(Dimension)
class DimensionAdmin(admin.ModelAdmin):
    list_display = ("id", "nombre")


@admin.register(Factor)
class FactorAdmin(admin.ModelAdmin):
    list_display = ("id", "nombre", "dimension", "importancia_is",
                    "importancia_experta", "alcance_base")
    list_filter = ("dimension",)
    search_fields = ("nombre",)


@admin.register(Subfactor)
class SubfactorAdmin(admin.ModelAdmin):
    # Permite revisar qué términos de búsqueda generó la IA para cada subfactor
    list_display = ("id", "nombre", "factor", "terminos_busqueda")
    list_filter = ("factor",)
    search_fields = ("nombre", "terminos_busqueda")


@admin.register(Evaluacion)
class EvaluacionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "software",
        "organizacion",
        "categoria",
        "usuario",
        "tipo",
        "progreso",
        "fecha_creacion",
    )

    list_filter = ("categoria", "organizacion", "tipo", "progreso", "fecha_creacion")
    search_fields = ("software", "organizacion__nombre")