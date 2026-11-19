from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import F, Q

# Escala de GUIOS: 1 a 4 (IL, IE e IS)
ESCALA_1_4 = [MinValueValidator(1), MaxValueValidator(4)]


# ==========================================
# ACTUALIZACIÓN DE LA IMPORTANCIA SUGERIDA
# ==========================================

class ActualizacionIS(models.Model):
    """Una ejecución completa del cálculo de la IS (RF-05 / RNF-07)."""

    fecha = models.DateTimeField(auto_now_add=True)
    fuente = models.CharField(max_length=150, blank=True)
    version_calculo = models.CharField(max_length=50, blank=True)

    class Meta:
        db_table = "actualizacionis"
        verbose_name = "Actualización de IS"
        verbose_name_plural = "Actualizaciones de IS"
        ordering = ["-fecha"]

    def __str__(self):
        fecha = f"{self.fecha:%Y-%m-%d %H:%M}" if self.fecha else "sin guardar"
        return f"Actualización #{self.pk} ({self.fuente or 'sin fuente'}, {fecha})"


# ==========================================
# CONSULTA EJECUTADA POR SUBFACTOR
# ==========================================

class ConsultaIS(models.Model):
    """Consulta enviada a la API para un subfactor dentro de una actualización."""

    actualizacion = models.ForeignKey(
        ActualizacionIS,
        on_delete=models.CASCADE,
        related_name="consultas",
    )
    # PROTECT: borrar un subfactor no debe borrar el historial auditable
    subfactor = models.ForeignKey(
        "evaluacion.Subfactor",
        on_delete=models.PROTECT,
        related_name="consultas_is",
    )
    consulta = models.TextField()
    anio_desde = models.PositiveSmallIntegerField(default=2020)
    anio_hasta = models.PositiveSmallIntegerField(default=2025)
    articulos_encontrados = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "consultais"
        verbose_name = "Consulta de IS"
        verbose_name_plural = "Consultas de IS"
        constraints = [
            # Una consulta por subfactor en cada actualización
            models.UniqueConstraint(
                fields=["actualizacion", "subfactor"],
                name="uq_consultais_actualizacion_subfactor",
            ),
            models.CheckConstraint(
                condition=Q(anio_hasta__gte=F("anio_desde")),
                name="ck_consultais_rango_anios",
            ),
        ]

    def __str__(self):
        return f"Act. {self.actualizacion_id} · subfactor {self.subfactor_id}: {self.articulos_encontrados}"


# ==========================================
# RESULTADO POR FACTOR
# ==========================================

class DetalleActualizacionIS(models.Model):
    """Resultado del cálculo (cᵢ, rᵢ, IL, IE, IS) de un factor en una actualización."""

    actualizacion = models.ForeignKey(
        ActualizacionIS,
        on_delete=models.CASCADE,
        related_name="detalles",
    )
    factor = models.ForeignKey(
        "evaluacion.Factor",
        on_delete=models.PROTECT,
        related_name="detalles_is",
    )
    total_articulos = models.PositiveIntegerField()                       # cᵢ
    promedio_r = models.DecimalField(max_digits=10, decimal_places=2)     # rᵢ = cᵢ / nᵢ
    importancia_literaria = models.PositiveSmallIntegerField(validators=ESCALA_1_4)
    importancia_experta = models.PositiveSmallIntegerField(validators=ESCALA_1_4)
    importancia_sugerida = models.PositiveSmallIntegerField(validators=ESCALA_1_4)

    class Meta:
        db_table = "detalleactualizacionis"
        verbose_name = "Detalle de actualización de IS"
        verbose_name_plural = "Detalles de actualización de IS"
        ordering = ["factor_id"]
        constraints = [
            # Equivale a la PK compuesta (id_actualizacion, id_factor) del informe
            models.UniqueConstraint(
                fields=["actualizacion", "factor"],
                name="uq_detalleis_actualizacion_factor",
            ),
            models.CheckConstraint(
                condition=(
                    Q(importancia_literaria__range=(1, 4))
                    & Q(importancia_experta__range=(1, 4))
                    & Q(importancia_sugerida__range=(1, 4))
                ),
                name="ck_detalleis_escala_1_4",
            ),
        ]

    def __str__(self):
        return f"Act. {self.actualizacion_id} · factor {self.factor_id}: IS={self.importancia_sugerida}"

    @property
    def importancia_sugerida_anterior(self):
        """IS que tenía el factor en la actualización previa (para 'IS anterior → nueva', Fig. 17).

        Devuelve None si es la primera actualización. Hace una consulta por fila:
        suficiente para 18 factores.
        """
        return (
            DetalleActualizacionIS.objects
            .filter(factor_id=self.factor_id, actualizacion_id__lt=self.actualizacion_id)
            .order_by("-actualizacion_id")
            .values_list("importancia_sugerida", flat=True)
            .first()
        )