import unittest
from decimal import Decimal as D
from modelo_economico import Cenario, calcular, decimal_br

PRE = {'gasolina_rs_l': D('6.342190476190476'), 'etanol_rs_l': D('4.089952380952381'), 'eletricidade_rs_kwh': D('0.78938')}

class TestModeloEconomico(unittest.TestCase):
    def test_numeros(self):
        self.assertEqual(decimal_br('R$ 1.234,56'), D('1234.56'))
        self.assertEqual(decimal_br('0.78938'), D('0.78938'))

    def test_gasolina(self):
        r = calcular(Cenario('t', 'gasolina', D('100'), consumo_combustivel_km_l=D('10')), PRE)
        self.assertEqual(r['custo_energetico_rs_mes'], PRE['gasolina_rs_l'] * D('10'))
        self.assertIsNone(r['custo_total_rs_mes'])
        self.assertIsNone(r['resultado_liquido_estimado_rs_mes'])

    def test_eletrico(self):
        r = calcular(Cenario('e', 'eletrico', D('100'), consumo_eletrico_kwh_km=D('0.18'), eficiencia_recarga=D('0.9')), PRE)
        self.assertEqual(r['custo_energetico_rs_km'], D('0.18')/D('0.9')*PRE['eletricidade_rs_kwh'])

    def test_plugin(self):
        r = calcular(Cenario('p', 'plugin', D('100'), consumo_combustivel_km_l=D('10'), combustivel='gasolina', consumo_eletrico_kwh_km=D('0.2'), eficiencia_recarga=D('1'), fracao_km_eletrico=D('0.25')), PRE)
        self.assertEqual(r['custo_energetico_rs_km'], D('0.75')*PRE['gasolina_rs_l']/D('10')+D('0.25')*D('0.2')*PRE['eletricidade_rs_kwh'])

    def test_completo(self):
        r = calcular(Cenario('c', 'gasolina', D('100'), consumo_combustivel_km_l=D('10'),
                              custo_variavel_extra_rs_km=D('0.10'), custo_fixo_rs_mes=D('50'), depreciacao_rs_mes=D('20'),
                              receita_motorista_rs_mes=D('300'), horas_trabalhadas_mes=D('20')), PRE)
        total = PRE['gasolina_rs_l']*D('10')+D('10')+D('50')+D('20')
        self.assertEqual(r['custo_total_rs_mes'], total)
        self.assertEqual(r['resultado_liquido_estimado_rs_mes'], D('300')-total)
        self.assertEqual(r['ponto_equilibrio_rs_hora'], total/D('20'))

    def test_erro(self):
        with self.assertRaises(ValueError):
            calcular(Cenario('i', 'eletrico', D('100'), consumo_eletrico_kwh_km=D('0.2'), eficiencia_recarga=D('0')), PRE)
        with self.assertRaises(ValueError):
            calcular(Cenario('i', 'plugin', D('100'), combustivel='gasolina', consumo_combustivel_km_l=D('10'), consumo_eletrico_kwh_km=D('0.2'), eficiencia_recarga=D('0.9'), fracao_km_eletrico=D('1.2')), PRE)

if __name__ == '__main__':
    unittest.main()
