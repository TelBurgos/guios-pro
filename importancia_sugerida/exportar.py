from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

from .models import ActualizacionIS, ConsultaIS, DetalleActualizacionIS


def _encabezado(ws, columnas, anchos):
    ws.append(columnas)
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="1F3864")
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for i, a in enumerate(anchos, 1):
        ws.column_dimensions[get_column_letter(i)].width = a
    ws.freeze_panes = "A2"


def construir_libro(act):
    wb = Workbook()

    # Hoja 1: resultados por factor
    ws = wb.active
    ws.title = "Resultados por factor"
    _encabezado(ws,
                ["Factor ID", "Factor", "Subfactores", "Total artículos",
                 "Promedio R", "IL", "IE", "IS"],
                [10, 45, 12, 16, 12, 8, 8, 8])
    consultas = ConsultaIS.objects.filter(actualizacion=act).select_related("subfactor__factor")
    n_subs = {}
    for c in consultas:
        n_subs[c.subfactor.factor_id] = n_subs.get(c.subfactor.factor_id, 0) + 1
    detalles = (DetalleActualizacionIS.objects.filter(actualizacion=act)
                .select_related("factor").order_by("factor_id"))
    for d in detalles:
        ws.append([d.factor_id, d.factor.nombre, n_subs.get(d.factor_id, 0),
                   d.total_articulos, float(d.promedio_r),
                   d.importancia_literaria, d.importancia_experta,
                   d.importancia_sugerida])

    # Hoja 2: trazabilidad
    wt = wb.create_sheet("Trazabilidad")
    _encabezado(wt,
                ["Factor ID", "Factor", "Subfactor ID", "Subfactor",
                 "Consulta enviada a OpenAlex", "Año desde", "Año hasta",
                 "Artículos encontrados"],
                [10, 35, 12, 55, 90, 10, 10, 14])
    for c in consultas.order_by("subfactor__factor_id", "subfactor_id"):
        s = c.subfactor
        wt.append([s.factor_id, s.factor.nombre, s.id, s.nombre, c.consulta,
                   c.anio_desde, c.anio_hasta, c.articulos_encontrados])
    for fila in wt.iter_rows(min_row=2):
        fila[4].alignment = Alignment(wrap_text=True, vertical="top")
        fila[3].alignment = Alignment(wrap_text=True, vertical="top")

    # Hoja 3: información de la actualización
    wi = wb.create_sheet("Actualización")
    _encabezado(wi, ["Dato", "Valor"], [28, 50])
    wi.append(["ID de actualización", act.id])
    wi.append(["Fecha", act.fecha.strftime("%Y-%m-%d %H:%M")])
    wi.append(["Fuente", act.fuente])
    wi.append(["Versión de cálculo", act.version_calculo])
    wi.append(["Total de consultas", consultas.count()])
    wi.append(["Total de factores", detalles.count()])
    return wb


def obtener_actualizacion(act_id=None):
    if act_id:
        return ActualizacionIS.objects.get(pk=act_id)
    return ActualizacionIS.objects.order_by("-fecha").first()


def guardar(act_id=None, ruta=None):
    act = obtener_actualizacion(act_id)
    ruta = ruta or f"resultados_IS_act{act.id}.xlsx"
    construir_libro(act).save(ruta)
    print("Guardado:", ruta)


def libro_en_bytes(act):
    buf = BytesIO()
    construir_libro(act).save(buf)
    return buf.getvalue()