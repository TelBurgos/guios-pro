from pathlib import Path
import os

import dj_database_url
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


# CONFIGURACIÓN GENERAL
_CLAVE_DESARROLLO = "development-only-insecure-key-change-me"

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", _CLAVE_DESARROLLO)

DEBUG = os.getenv("DJANGO_DEBUG", "True").lower() == "true"

# En producción no se permite la clave de desarrollo
if not DEBUG and SECRET_KEY == _CLAVE_DESARROLLO:
    raise ImproperlyConfigured(
        "Defina DJANGO_SECRET_KEY en el .env antes de usar DEBUG=False."
    )

# Hosts permitidos: por defecto local; se pueden añadir más desde el .env
# (ejemplo: DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,miapp.onrender.com)
ALLOWED_HOSTS = [
    host.strip()
    for host in os.getenv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if host.strip()
]


# BASE DE DATOS (Neon, PostgreSQL en la nube)
# DB_DIRECTA=1 usa la conexión directa (para migrate y loaddata)
_clave_url = (
    "DATABASE_URL_UNPOOLED"
    if os.getenv("DB_DIRECTA") == "1"
    else "DATABASE_URL"
)
_url = os.getenv(_clave_url)

if not _url:
    raise ImproperlyConfigured(
        f"Falta {_clave_url}. Copie .env.example a .env y complete las credenciales."
    )

DATABASES = {
    "default": dj_database_url.parse(
        _url,
        conn_max_age=0,
        disable_server_side_cursors=True,
    )
}


# APLICACIONES
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    "allauth",
    "allauth.account",

    "evaluacion",
    "importancia_sugerida",
]


# MIDDLEWARE
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "allauth.account.middleware.AccountMiddleware",
]


# SESIONES
SESSION_ENGINE = "django.contrib.sessions.backends.signed_cookies"


# URLS
ROOT_URLCONF = "config.urls"


# PLANTILLAS
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]


# ARCHIVOS ESTÁTICOS
STATIC_URL = "static/"

# Solo se registra la carpeta si existe (Git no sube carpetas vacías)
STATICFILES_DIRS = [
    ruta for ruta in [BASE_DIR / "static"] if ruta.exists()
]


# CONFIGURACIÓN DE DJANGO
WSGI_APPLICATION = "config.wsgi.application"

LANGUAGE_CODE = "es"
TIME_ZONE = "America/Guayaquil"

USE_I18N = True
USE_TZ = True

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# AUTENTICACIÓN
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]


# REDIRECCIONES
LOGIN_URL = "account_login"
LOGIN_REDIRECT_URL = "evaluacion:panel"
LOGOUT_REDIRECT_URL = "account_login"


# CONFIGURACIÓN DE DJANGO-ALLAUTH

# Iniciar sesión con correo electrónico
ACCOUNT_LOGIN_METHODS = {"email"}

# Campos obligatorios para el registro
ACCOUNT_SIGNUP_FIELDS = [
    "email*",
    "password1*",
    "password2*",
]

# Evitar correos duplicados
ACCOUNT_UNIQUE_EMAIL = True

# No exigir verificación de correo
ACCOUNT_EMAIL_VERIFICATION = "none"

# Formulario personalizado para nombres y apellidos
ACCOUNT_SIGNUP_FORM_CLASS = (
    "evaluacion.allauth_forms.RegistroAdicionalForm"
)


# CORREO LOCAL (SIN BREVO)
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"


SESSION_COOKIE_AGE = 30 * 60          # 30 minutos de inactividad
SESSION_SAVE_EVERY_REQUEST = True     # renueva el plazo con cada petición