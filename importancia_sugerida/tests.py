from decimal import Decimal

from django.test import SimpleTestCase

from evaluacion.logic import (MATRIZ_IMPORTANCIA, derive, init_state,
                              recomendacion, relative)
from importancia_sugerida.services import calcular_il, cuartiles

# (NS, TC, IE, IL esperado, IS esperado): Tabla 5.3 de la tesis (Rea Sánchez, 2022)
TABLA_5_3 = [
    (8, 33, 3, 3, 3), (5, 19, 3, 3, 3), (1, 4, 3, 3, 3), (6, 30, 3, 4, 3),
    (1, 4, 3, 3, 3), (11, 20, 3, 1, 2), (2, 4, 3, 2, 2), (2, 5, 3, 2, 2),
    (4, 14, 3, 2, 2), (1, 5, 3, 4, 3), (4, 27, 3, 4, 3), (6, 43, 3, 4, 3),
    (2, 3, 3, 1, 2), (1, 3, 3, 2, 2), (1, 1, 3, 1, 2), (2, 2, 3, 1, 2),
    (2, 2, 3, 1, 2), (2, 24, 3, 4, 3),
]


class ImportanciaTests(SimpleTestCase):
    def test_il_e_is_coinciden_con_la_tabla_5_3(self):
        rs = [Decimal(tc) / ns for ns, tc, *_ in TABLA_5_3]
        rq = cuartiles(rs)
        for r, (_, _, ie, il_esp, is_esp) in zip(rs, TABLA_5_3):
            il = calcular_il(r, rq)
            self.assertEqual(il, il_esp)
            self.assertEqual(MATRIZ_IMPORTANCIA[(il, ie)], is_esp)

    def test_matriz_igual_a_formula_original(self):
        for a in range(1, 5):
            for b in range(1, 5):
                self.assertEqual(relative(a, b), ((a - 1) + (b - 1)) // 2)


class RecomendacionTests(SimpleTestCase):
    def _cat(self, suggested):
        return [{"factor_id": 1, "name": "F", "dimension": "D",
                 "subfactors": ["s"], "subfactor_ids": [1],
                 "suggested": suggested, "expert": 3, "scope": "Interno"}]

    def _reco(self, suggested, decisor, peso):
        cat = self._cat(suggested)
        st = init_state(cat)
        st["0"].update(decisor=decisor, weights=[peso], saved=True)
        return recomendacion(derive(cat, st))[:16]

    def test_a_b_c(self):
        self.assertEqual(self._reco(4, 4, 4), "Recomendación A:")
        self.assertEqual(self._reco(2, 2, 1), "Recomendación B:")  # relativa Opcional
        self.assertEqual(self._reco(3, 3, 1), "Recomendación C:")  # relativa Importante

    def test_sin_evaluar_no_falla(self):
        cat = self._cat(3)
        self.assertEqual(recomendacion(derive(cat, init_state(cat))), "")