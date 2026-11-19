import csv
import unicodedata
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from evaluacion.models import Dimension, Factor, Subfactor
from importancia_sugerida.models import ActualizacionIS, DetalleActualizacionIS

IE_TESIS = 3  # Tabla 5.3 de la tesis: IE = 3 en los 18 factores


def limpiar(texto):
    return " ".join((texto or "").split())


def norm(texto):
    """Encabezado sin tildes, en minúsculas: 'Dimensión' -> 'dimension'."""
    t = unicodedata.normalize("NFD", texto.strip())
    return "".join(c for c in t if unicodedata.category(c) != "Mn").lower()


def leer_csv(ruta):
    with open(ruta, newline="", encoding="utf-8-sig") as f:
        primera = f.readline()
        f.seek(0)
        delimitador = max(["\t", ";", ","], key=primera.count)
        lector = csv.DictReader(f, delimiter=delimitador)
        return [
            {norm(k): limpiar(v) for k, v in fila.items() if k}
            for fila in lector
        ]


class Command(BaseCommand):
    help = "Carga dimensiones, factores y subfactores y crea la IS inicial."

    def add_arguments(self, parser):
        parser.add_argument("factors_csv")
        parser.add_argument("subfactores_csv")

    @transaction.atomic
    def handle(self, *args, **opts):
        factors = leer_csv(Path(opts["factors_csv"]))
        guios = leer_csv(Path(opts["subfactores_csv"]))

        # Dimensión de cada factor, tomada de guiosad_data.csv
        dimension_de = {}
        for fila in guios:
            dimension_de.setdefault(fila["factor"], fila["dimension"])

        for fila in factors:
            nombre = fila["factor"]
            if nombre not in dimension_de:
                raise CommandError(
                    f"El factor '{nombre}' de factors.csv no aparece "
                    f"en guiosad_data.csv")
            dimension, _ = Dimension.objects.get_or_create(
                nombre=dimension_de[nombre])
            Factor.objects.update_or_create(
                nombre=nombre,
                defaults={
                    "dimension": dimension,
                    "importancia_is": int(fila["sugerida"]),
                    "importancia_experta": IE_TESIS,
                    "alcance_base": fila["alcance"],
                },
            )

        for fila in guios:
            Subfactor.objects.get_or_create(
                factor=Factor.objects.get(nombre=fila["factor"]),
                nombre=fila["subfactor"],
            )

        # IS inicial para que exista la "última IS almacenada" (RNF-08)
        if not ActualizacionIS.objects.exists():
            act = ActualizacionIS.objects.create(
                fuente="Valores base de la tesis", version_calculo="base")
            for f in Factor.objects.all():
                DetalleActualizacionIS.objects.create(
                    actualizacion=act,
                    factor=f,
                    total_articulos=0,
                    promedio_r=0,
                    # La restricción exige 1-4: sin literatura aún, se usa
                    # el valor base de la tesis.
                    importancia_literaria=f.importancia_is,
                    importancia_experta=f.importancia_experta,
                    importancia_sugerida=f.importancia_is,
                )

        self.stdout.write(self.style.SUCCESS(
            f"Dimensiones: {Dimension.objects.count()} | "
            f"Factores: {Factor.objects.count()} | "
            f"Subfactores: {Subfactor.objects.count()}"))