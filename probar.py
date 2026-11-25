import time
from types import SimpleNamespace
from importancia_sugerida.services import contar_openalex, generar_consulta

PRUEBAS = [
    (90, "database migration, DBMS"),
    (90, "database compatibility, PostgreSQL, MySQL"),
    (90, "vendor independence, database portability"),
    (90, "relational database, database migration"),
]

for sid, terminos in PRUEBAS:
    sub = SimpleNamespace(terminos_busqueda=terminos, nombre="")
    n = contar_openalex(generar_consulta(sub))
    print(sid, "->", n, "|", terminos)
    time.sleep(1)