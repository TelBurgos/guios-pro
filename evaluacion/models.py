from decimal import Decimal

from django.contrib.auth.models import User
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q

from .logic import RECO_TITULOS  # fuente única de los títulos A/B/C

ESCALA_1_4 = [MinValueValidator(1), MaxValueValidator(4)]


class Organizacion(models.Model):
    usuario = models.ForeignKey(User, on_delete=models.CASCADE, related_name="organizaciones")
    nombre = models.CharField(max_length=100)
    tipo = models.CharField(max_length=50, blank=True)
    descripcion = models.TextField(blank=True)

    class Meta:
        verbose_name = "Organización"
        verbose_name_plural = "Organizaciones"
        ordering = ["nombre"]
        constraints = [
            models.UniqueConstraint(fields=["usuario", "nombre"], name="uq_org_usuario_nombre"),
        ]

    def __str__(self):
        return self.nombre


class Categoria(models.Model):
    nombre = models.CharField(max_length=100, unique=True)

    class Meta:
        verbose_name = "Categoría"
        verbose_name_plural = "Categorías"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


# ==========================================
# CATÁLOGO: DIMENSIÓN, FACTOR Y SUBFACTOR
# ==========================================

class Dimension(models.Model):
    nombre = models.CharField(max_length=100, unique=True)

    class Meta:
        verbose_name = "Dimensión"
        verbose_name_plural = "Dimensiones"

    def __str__(self):
        return self.nombre


class Factor(models.Model):
    ALCANCES = [("Interno", "Interno"), ("Externo", "Externo"), ("Ambos", "Ambos")]

    dimension = models.ForeignKey(Dimension, on_delete=models.PROTECT, related_name="factores")
    nombre = models.CharField(max_length=100, unique=True)
    importancia_is = models.SmallIntegerField(default=1, validators=ESCALA_1_4)        # IS vigente
    importancia_experta = models.SmallIntegerField(default=1, validators=ESCALA_1_4)   # IE
    alcance_base = models.CharField(max_length=10, choices=ALCANCES, default="Ambos")

    class Meta:
        verbose_name_plural = "Factores"

    def __str__(self):
        return self.nombre


class Subfactor(models.Model):
    factor = models.ForeignKey(Factor, on_delete=models.CASCADE, related_name="subfactores")
    nombre = models.CharField(max_length=255)
    terminos_busqueda = models.CharField(
        max_length=300, blank=True,
        help_text="Términos en inglés separados por coma. Ej: cloud infrastructure, cloud hosting",
    )

    def __str__(self):
        return self.nombre


# ==========================================
# EVALUACIÓN
# ==========================================

class Evaluacion(models.Model):
    TIPOS = [("primera", "Primera"), ("segunda", "Segunda")]
    PROGRESOS = [("en_progreso", "En progreso"), ("completada", "Completada")]
    CODIGOS = [("A", "A"), ("B", "B"), ("C", "C")]
    CLASES = {"A": "res-a", "B": "res-b", "C": "res-c"}

    usuario = models.ForeignKey(User, on_delete=models.CASCADE, related_name="evaluaciones")
    organizacion = models.ForeignKey(Organizacion, on_delete=models.PROTECT, related_name="evaluaciones")
    software = models.CharField(max_length=150)
    categoria = models.ForeignKey(Categoria, on_delete=models.PROTECT, related_name="evaluaciones")
    descripcion = models.TextField(blank=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    # Informe: tipo, evaluacion_padre, paso_actual, estado, recomendacion, actualizacion
    tipo = models.CharField(max_length=10, choices=TIPOS, default="primera")
    evaluacion_padre = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.CASCADE, related_name="segundas",
    )
    actualizacion = models.ForeignKey(
        "importancia_sugerida.ActualizacionIS", null=True, blank=True,
        on_delete=models.PROTECT, related_name="evaluaciones",
    )
    paso_actual = models.PositiveSmallIntegerField(default=1, validators=[MinValueValidator(1), MaxValueValidator(6)])
    progreso = models.CharField(max_length=15, choices=PROGRESOS, default="en_progreso")
    recomendacion = models.CharField(max_length=1, choices=CODIGOS, blank=True)  # A, B o C
    recomendacion_texto = models.TextField(blank=True)

    class Meta:
        verbose_name = "Evaluación"
        verbose_name_plural = "Evaluaciones"
        ordering = ["-fecha_creacion"]

    def __str__(self):
        return f"{self.software} - {self.organizacion.nombre}"

    # --- Datos derivados de EvaluacionFactor (ya no se duplican en la tabla) ---
    def _contar(self, foda):
        return sum(1 for v in self.valoraciones_factor.all() if v.foda == foda)

    @property
    def fortalezas(self):
        return self._contar("Fortaleza")

    @property
    def oportunidades(self):
        return self._contar("Oportunidad")

    @property
    def debilidades(self):
        return self._contar("Debilidad")

    @property
    def amenazas(self):
        return self._contar("Amenaza")

    @property
    def ponderacion_media(self):
        # Promedio de pesos ya redondeados: puede diferir en 0.01 del promedio sin redondear
        pesos = [v.peso_global for v in self.valoraciones_factor.all() if v.peso_global is not None]
        if not pesos:
            return None
        return (sum(pesos) / len(pesos)).quantize(Decimal("0.01"))

    @property
    def etiqueta(self):
        return RECO_TITULOS.get(self.recomendacion, "Sin resultado")

    @property
    def clase_etiqueta(self):
        return self.CLASES.get(self.recomendacion, "res-none")


class EvaluacionFactor(models.Model):
    """HU-07 / HU-08: valoración, ponderación media y FODA de un factor dentro de una evaluación."""

    ALCANCES = [("Interno", "Interno"), ("Externo", "Externo")]
    FODA = [("Fortaleza", "Fortaleza"), ("Oportunidad", "Oportunidad"),
            ("Debilidad", "Debilidad"), ("Amenaza", "Amenaza")]

    evaluacion = models.ForeignKey(Evaluacion, on_delete=models.CASCADE, related_name="valoraciones_factor")
    factor = models.ForeignKey(Factor, on_delete=models.PROTECT, related_name="valoraciones")
    importancia_decisor = models.PositiveSmallIntegerField(validators=ESCALA_1_4)
    importancia_relativa = models.PositiveSmallIntegerField(validators=ESCALA_1_4)
    relevante = models.BooleanField(default=False)
    peso_global = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    alcance_evaluado = models.CharField(max_length=10, choices=ALCANCES)
    foda = models.CharField(max_length=20, choices=FODA, blank=True)

    class Meta:
        verbose_name = "Valoración de factor"
        verbose_name_plural = "Valoraciones de factores"
        constraints = [
            models.UniqueConstraint(fields=["evaluacion", "factor"], name="uq_evalfactor_eval_factor"),
            models.CheckConstraint(
                condition=Q(importancia_decisor__range=(1, 4)) & Q(importancia_relativa__range=(1, 4)),
                name="ck_evalfactor_escala_1_4",
            ),
        ]

    def __str__(self):
        return f"Eval. {self.evaluacion_id} · factor {self.factor_id}"


class EvaluacionSubfactor(models.Model):
    """Valoración (1 a 4) de un subfactor dentro de una evaluación. Su existencia indica 'guardado'."""

    evaluacion = models.ForeignKey(Evaluacion, on_delete=models.CASCADE, related_name="valoraciones_subfactor")
    subfactor = models.ForeignKey(Subfactor, on_delete=models.PROTECT, related_name="valoraciones")
    importancia = models.PositiveSmallIntegerField(validators=ESCALA_1_4)

    class Meta:
        verbose_name = "Valoración de subfactor"
        verbose_name_plural = "Valoraciones de subfactores"
        constraints = [
            models.UniqueConstraint(fields=["evaluacion", "subfactor"], name="uq_evalsub_eval_subfactor"),
            models.CheckConstraint(condition=Q(importancia__range=(1, 4)), name="ck_evalsub_escala_1_4"),
        ]

    def __str__(self):
        return f"Eval. {self.evaluacion_id} · subfactor {self.subfactor_id}"