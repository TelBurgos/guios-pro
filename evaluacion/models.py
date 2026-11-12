
from django.db import models
from django.contrib.auth.models import User


# ==========================================
# MODELO: ORGANIZACIÓN
# ==========================================

class Organizacion(models.Model):
    nombre = models.CharField(max_length=150, unique=True)

    class Meta:
        verbose_name = "Organización"
        verbose_name_plural = "Organizaciones"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


# ==========================================
# MODELO: CATEGORÍA DE SOFTWARE
# ==========================================

class Categoria(models.Model):
    nombre = models.CharField(max_length=100, unique=True)

    class Meta:
        verbose_name = "Categoría"
        verbose_name_plural = "Categorías"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


# ==========================================
# MODELO: EVALUACIÓN
# ==========================================

class Evaluacion(models.Model):
    usuario = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="evaluaciones"
    )

    organizacion = models.ForeignKey(
        Organizacion,
        on_delete=models.PROTECT,
        related_name="evaluaciones"
    )

    software = models.CharField(max_length=150)

    categoria = models.ForeignKey(
        Categoria,
        on_delete=models.PROTECT,
        related_name="evaluaciones"
    )

    descripcion = models.TextField(
        blank=True
    )

    fecha_creacion = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        verbose_name = "Evaluación"
        verbose_name_plural = "Evaluaciones"
        ordering = ["-fecha_creacion"]

    def __str__(self):
        return f"{self.software} - {self.organizacion.nombre}"

    progreso = models.CharField(
        max_length=15,
        choices=[("en_progreso", "En progreso"), ("completada", "Completada")],
        default="en_progreso",
    )
    estado_guiospro = models.JSONField(null=True, blank=True)  # copia de la sesión
    recomendacion = models.CharField(max_length=1, blank=True)  # A, B o C
    recomendacion_texto = models.TextField(blank=True)
    ponderacion_media = models.DecimalField(
        max_digits=3, decimal_places=2, null=True, blank=True
    )
    fortalezas = models.PositiveSmallIntegerField(default=0)
    oportunidades = models.PositiveSmallIntegerField(default=0)
    debilidades = models.PositiveSmallIntegerField(default=0)
    amenazas = models.PositiveSmallIntegerField(default=0)

    # Texto y estilo de la etiqueta de resultado
    ETIQUETAS = {
        "A": ("Adopción recomendada", "res-a"),
        "B": ("Adopción con reservas", "res-b"),
        "C": ("Adopción no recomendada", "res-c"),
    }

    @property
    def etiqueta(self):
        return self.ETIQUETAS.get(self.recomendacion, ("Sin resultado", "res-none"))[0]

    @property
    def clase_etiqueta(self):
        return self.ETIQUETAS.get(self.recomendacion, ("", "res-none"))[1]


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

    dimension = models.ForeignKey(Dimension, on_delete=models.PROTECT,
                                  related_name="factores")
    nombre = models.CharField(max_length=100, unique=True)
    importancia_is = models.SmallIntegerField(default=1)        # IS vigente (1 a 4)
    importancia_experta = models.SmallIntegerField(default=1)   # IE (1 a 4)
    alcance_base = models.CharField(max_length=10, choices=ALCANCES, blank=True)

    class Meta:
        verbose_name_plural = "Factores"

    def __str__(self):
        return self.nombre


class Subfactor(models.Model):
    factor = models.ForeignKey(Factor, on_delete=models.CASCADE,
                               related_name="subfactores")
    nombre = models.CharField(max_length=255)
    terminos_busqueda = models.CharField(
        max_length=300, blank=True,
        help_text="Términos en inglés separados por coma. Ej: cloud infrastructure, cloud hosting",
    )

    def __str__(self):
        return self.nombre