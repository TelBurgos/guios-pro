"""Reglas puras de GUIOS (sin acceso a BD, request ni settings).

Mantiene la escala 1-4, importancia relativa con división entera,
ponderación media, FODA y prioridades A/B/C originales.
El catálogo ya NO se lee aquí: vive en services.catalogue() (desde la BD).
"""
import re

LEVELS = ["Irrelevante", "Opcional", "Importante", "Fundamental"]
SUB_LEVELS = [
    "No cumple el requisito",
    "Desconozco si cumple requisito",
    "Cumple parcialmente el requisito",
    "Cumple el requisito",
]

# Fuente única de los títulos de recomendación (modelo, vistas y plantillas)
RECO_TITULOS = {
    "A": "Adopción recomendada",
    "B": "Adopción con plan de mitigación",
    "C": "Adopción no recomendada",
}


def init_state(catalog):
    return {
        str(i): {
            "decisor": 1,
            "scope": "Interno" if f["scope"] == "Ambos" else f["scope"],
            "weights": [1] * len(f["subfactors"]),
            "saved": False,
        }
        for i, f in enumerate(catalog)
    }


def relative(suggested, decisor):
    # Código original: índices base cero y división entera.
    return (suggested - 1 + decisor - 1) // 2


def derive(catalog, state):
    rows = []
    for i, f in enumerate(catalog):
        s = state[str(i)]
        rel = relative(f["suggested"], s["decisor"])
        relevant = rel > 0
        score = (
            sum(s["weights"]) / len(s["weights"])
            if s["weights"] and s["saved"] and relevant
            else None
        )
        foda = None
        if score is not None:
            if s["scope"] == "Interno":
                foda = "Fortaleza" if score >= 3 else "Debilidad"
            else:
                foda = "Oportunidad" if score >= 3 else "Amenaza"
        rows.append({
            **f,
            "id": i,
            "decisor": s["decisor"],
            "decisor_label": LEVELS[s["decisor"] - 1],
            "relative": LEVELS[rel],
            "relevant": relevant,
            "scope_selected": s["scope"],
            "weights": s["weights"],
            "saved": s["saved"],
            "score": score,
            "foda": foda,
        })
    return rows


# Textos originales de GUIOS (no modificar: RNF-01)
RECO_C = "Recomendación C: La organización debe de proporcionar los recursos necesarios que garanticen una adopción satisfactoria. Si se trata de factores internos deben de ser aspectos a mejorar dentro de la organización y si son factores externos, dedicar recursos de ingeniería para mejorar el software."
RECO_B = "Recomendación B: Es posible adoptar. A pesar que se han detectado amenazas y/o debilidades en factores cuya importancia relativa es opcional, por lo tanto, se sugiere revisar los criterios que no cumplen con lo mínimo requerido para adoptar."
RECO_A = "Recomendación A: Adoptar. Todos los factores han sido identifcados como Oportunidades y/o Fortalezas. Esto quiere decir que la organización cumple satisfactoriamente con la mayoria de requisitos para adoptar la solución FLOSS."


def recomendacion(rows):
    evaluated = [r for r in rows if r["foda"]]
    if not evaluated:
        return ""  # Evita el IndexError original cuando no hay factores evaluados.
    a = any(r["foda"] in ("Amenaza", "Debilidad") and r["relative"] in ("Importante", "Fundamental") for r in evaluated)
    b = any(r["foda"] in ("Amenaza", "Debilidad") and r["relative"] == "Opcional" for r in evaluated)
    return RECO_C if a else RECO_B if b else RECO_A

ESCALA = 4


def subfactores_pendientes(rows):
    """HU-06: subfactores sin valorar en los factores relevantes."""
    return sum(len(r["subfactors"]) for r in rows if r["relevant"] and not r["saved"])


def codigo_recomendacion(texto):
    m = re.search(r"Recomendación ([ABC]):", texto or "")
    return m.group(1) if m else ""


def detalle_recomendacion(texto):
    """(código, título, cuerpo) a partir del texto original de GUIOS."""
    m = re.search(r"Recomendación ([ABC]):\s*(.*)", texto or "", re.S)
    codigo = m.group(1) if m else ""
    cuerpo = m.group(2).strip() if m else (texto or "")
    return codigo, RECO_TITULOS.get(codigo, "Recomendación"), cuerpo


def factores_a_reevaluar(rows):
    """HU-09. SUPUESTO: la segunda evaluación repite solo los factores con Debilidad o Amenaza.
    Verificar con la tesis (Rea Sánchez, 2022, pp. 104-105) y con original/guiosad.py."""
    return [r for r in rows if r["foda"] in ("Debilidad", "Amenaza")]


def _tono(pct):
    return "high" if pct >= 60 else "mid" if pct >= 40 else "low"


def resumen_resultados(rows):
    """Pasos 4 a 6: ponderación media, FODA y recomendación (HU-07, HU-08, HU-09)."""
    con_score = [r for r in rows if r["score"] is not None]

    pond_rows = []
    for r in sorted(con_score, key=lambda x: x["score"], reverse=True):
        pct = int(round(r["score"] / ESCALA * 100))
        pond_rows.append({"name": r["name"], "score": r["score"], "pct": pct, "tone": _tono(pct)})

    pond_media, pond_pct, pond_nivel, pond_dim = None, 0, "", []
    if con_score:
        pond_media = round(sum(r["score"] for r in con_score) / len(con_score), 2)
        pond_pct = int(round(pond_media / ESCALA * 100))
        pond_nivel = ("Nivel favorable" if pond_pct >= 75
                      else "Nivel moderado" if pond_pct >= 50 else "Nivel bajo")
        por_dim = {}
        for r in con_score:
            por_dim.setdefault(r["dimension"], []).append(r["score"])
        for nombre, valores in por_dim.items():
            media = round(sum(valores) / len(valores), 2)
            pond_dim.append({"name": nombre, "score": media, "pct": int(round(media / ESCALA * 100))})

    foda_cfg = [("Fortaleza", "Fortalezas", "F", "f"), ("Oportunidad", "Oportunidades", "O", "o"),
                ("Debilidad", "Debilidades", "D", "d"), ("Amenaza", "Amenazas", "A", "a")]
    foda_groups = []
    for clave, titulo, letra, css in foda_cfg:
        nombres = [r["name"] for r in con_score if r["foda"] == clave]
        foda_groups.append({"title": titulo, "letter": letra, "css": css,
                            "count": len(nombres), "names": nombres})

    reco_text = recomendacion(rows) if con_score else ""
    codigo, titulo, cuerpo = detalle_recomendacion(reco_text)
    riesgos = [r["name"] for r in con_score if r["foda"] in ("Debilidad", "Amenaza")]

    return {
        "pond_rows": pond_rows, "pond_media": pond_media, "pond_pct": pond_pct,
        "pond_nivel": pond_nivel, "pond_dim": pond_dim, "escala": ESCALA,
        "foda_groups": foda_groups, "foda_total": len(con_score),
        "reco_text": reco_text, "reco_code": codigo, "reco_title": titulo, "reco_body": cuerpo,
        "reco_actions": [f"Mitigar: {n}" for n in riesgos[:3]],
    }


def comparar_evaluaciones(primera, segunda):
    """Puntaje y FODA de cada factor en la primera y la segunda evaluación."""
    por_nombre = {r["name"]: r for r in segunda}
    filas = []
    for a in primera:
        if a["score"] is None:
            continue
        s = por_nombre.get(a["name"])
        filas.append({
            "name": a["name"],
            "score_1": a["score"], "foda_1": a["foda"],
            "score_2": s["score"] if s else None, "foda_2": s["foda"] if s else None,
            "reevaluado": bool(s) and s["weights"] != a["weights"],
        })
    return filas