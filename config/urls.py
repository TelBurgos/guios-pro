from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path("admin/", admin.site.urls),

    # Registro, login y recuperación de contraseña
    path("accounts/", include("allauth.urls")),

    # Importancia sugerida (IS): literatura científica y trazabilidad
    # Va ANTES de la ruta "" para que no sea capturada por evaluacion.urls
    path("importancia-sugerida/", include("importancia_sugerida.urls")),

    # Sistema GUIOSPRO
    path("", include("evaluacion.urls")),



]