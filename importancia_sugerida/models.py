from django.db import models


class ActualizacionIS(models.Model):
    fecha = models.DateTimeField(auto_now_add=True)
    fuente = models.CharField(max_length=150, blank=True)
    version_calculo = models.CharField(max_length=50, blank=True)

    class Meta:
        db_table = "actualizacionis"
        ordering = ["-fecha"]


class ConsultaIS(models.Model):
    actualizacion = models.ForeignKey(ActualizacionIS, on_delete=models.CASCADE,
                                      related_name="consultas")
    subfactor = models.ForeignKey("evaluacion.Subfactor", on_delete=models.CASCADE)
    consulta = models.TextField()
    anio_desde = models.SmallIntegerField(default=2020)
    anio_hasta = models.SmallIntegerField(default=2025)
    articulos_encontrados = models.IntegerField(default=0)

    class Meta:
        db_table = "consultais"


class DetalleActualizacionIS(models.Model):
    actualizacion = models.ForeignKey(ActualizacionIS, on_delete=models.CASCADE,
                                      related_name="detalles")
    factor = models.ForeignKey("evaluacion.Factor", on_delete=models.CASCADE)
    total_articulos = models.IntegerField()
    promedio_r = models.DecimalField(max_digits=10, decimal_places=2)
    importancia_literaria = models.SmallIntegerField()
    importancia_experta = models.SmallIntegerField()
    importancia_sugerida = models.SmallIntegerField()

    class Meta:
        db_table = "detalleactualizacionis"
        unique_together = ("actualizacion", "factor")
