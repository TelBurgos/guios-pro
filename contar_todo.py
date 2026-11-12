import time
from evaluacion.models import Subfactor
from importancia_sugerida.services import generar_consulta, contar_openalex

for s in Subfactor.objects.order_by("id"):
    q = generar_consulta(s)
    try:
        n = contar_openalex(q)
    except Exception as e:
        n = f"ERROR: {e}"
    print(f"{s.id} | {n} | {q}")
    time.sleep(0.5)