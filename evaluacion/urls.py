from django.urls import path

# Vistas de la app (importadas por nombre)
from .views import (
    inicio,
    nueva_evaluacion,
    panel,
    historial,
    exportar_todo,
    abrir_evaluacion,
    exportar_evaluacion,
    ver_evaluacion
)

# Espacio de nombres: se usa como {% url 'evaluacion:...' %}
app_name = "evaluacion"

urlpatterns = [

    # ----- Rutas principales -----

    # Evaluación GUIOSPRO (pantalla raíz)
    path("", inicio, name="inicio"),

    # Formulario para crear una nueva evaluación
    path("nueva-evaluacion/", nueva_evaluacion, name="nueva_evaluacion"),

    # Panel de bienvenida
    path("panel/", panel, name="panel"),

    # ----- HISTORIAL -----

    # Lista de evaluaciones guardadas (línea de tiempo con filtros)
    path("historial/", historial, name="historial"),

    # Descarga en CSV de todo el historial del usuario
    path("historial/exportar/", exportar_todo, name="exportar_todo"),

    # Carga una evaluación guardada y abre su pestaña de resultados
    path("historial/<int:pk>/", abrir_evaluacion, name="abrir_evaluacion"),

    # Descarga en CSV de una sola evaluación
    path("historial/<int:pk>/exportar/", exportar_evaluacion, name="exportar_evaluacion"),

path("historial/<int:pk>/ver/", ver_evaluacion, name="ver_evaluacion"),
]