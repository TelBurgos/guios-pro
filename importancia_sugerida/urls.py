from django.urls import path
from . import views

app_name = "importancia_sugerida"

urlpatterns = [
    path("", views.literatura, name="literatura"),
    path("exportar-excel/", views.descargar_excel, name="exportar_excel"),
    path("exportar-excel/<int:act_id>/", views.descargar_excel, name="exportar_excel_id"),
path("descargar/", views.descargar_excel, name="descargar_excel"),
path("descargar/<int:act_id>/", views.descargar_excel, name="descargar_excel_act"),

]