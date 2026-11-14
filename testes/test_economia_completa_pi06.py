import unittest
from decimal import Decimal
from economia_completa_pi06 import result, d, template
from tempfile import TemporaryDirectory
from pathlib import Path
import csv

BASE={'perfil_id':'a','regime':'proprio','km_mes':'1000','horas_mes':'100',
      'receita_plataforma_liquida_rs_mes':'3000','manutencao_rs_km':'0.1','pneus_rs_km':'0.05',
      'lavagem_rs_mes':'100','celular_rs_mes':'40','seguro_rs_mes':'100',
      'outros_fixos_rs_mes':'60','ipva_efetivo_rs_ano':'1200',
      'licenciamento_rs_ano':'180','depreciacao_rs_mes':'200',
      'percentual_energia_pago_motorista':'1','percentual_manutencao_pago_motorista':'1',
      'percentual_pneus_pago_motorista':'1','percentual_seguro_pago_motorista':'1',
      'percentual_ipva_pago_motorista':'1','percentual_licenciamento_pago_motorista':'1'}
ROW={'inmetro_id':'11','custo_energia_rs_km':'0.2','modelo_inmetro':'DOLPHIN MINI'}
class TestEconomia(unittest.TestCase):
    def test_proprio_completo(self):
        r=result(BASE,ROW)
        self.assertEqual(r['status'],'COMPLETO_CENARIO')
        self.assertEqual(Decimal(r['custo_total_economico_rs_mes']),Decimal('965'))
        self.assertEqual(Decimal(r['resultado_economico_rs_mes']),Decimal('2035'))
    def test_sem_receita_nao_fabrica_lucro(self):
        b={**BASE,'receita_plataforma_liquida_rs_mes':''}
        r=result(b,ROW)
        self.assertEqual(r['resultado_economico_rs_mes'],'')
        self.assertEqual(r['status'],'PARCIAL_PENDENTE')
    def test_sem_ipva_nao_vira_zero(self):
        b={**BASE,'ipva_efetivo_rs_ano':''}
        r=result(b,ROW)
        self.assertEqual(r['custo_total_economico_rs_mes'],'')
    def test_aluguel_sem_depreciacao(self):
        b={**BASE,'regime':'alugado','aluguel_rs_mes':'1500',
           'percentual_seguro_pago_motorista':'0','seguro_rs_mes':'',
           'percentual_ipva_pago_motorista':'0','ipva_efetivo_rs_ano':'',
           'percentual_licenciamento_pago_motorista':'0','licenciamento_rs_ano':'',
           'percentual_manutencao_pago_motorista':'0','manutencao_rs_km':'',
           'percentual_pneus_pago_motorista':'0','pneus_rs_km':''}
        r=result(b,ROW)
        self.assertEqual(Decimal(r['custo_depreciacao_rs_mes']),0)
        self.assertEqual(r['status'],'COMPLETO_CENARIO')
    def test_financiamento_bloqueado(self):
        with self.assertRaises(ValueError): result({**BASE,'regime':'financiado'},ROW)
    def test_template_sem_sobrescrever(self):
        with TemporaryDirectory() as td:
            p=Path(td)/'perfis.csv';template(p)
            with self.assertRaises(FileExistsError):template(p)
            with p.open(encoding='utf-8-sig') as f:
                rows=list(csv.DictReader(f))
            self.assertEqual(len(rows),2)
            self.assertEqual(rows[0]['receita_plataforma_liquida_rs_mes'],'')
    def test_decimal_br(self):
        self.assertEqual(d('R$ 1.234,56'),Decimal('1234.56'))
        with self.assertRaises(ValueError): d('-3')
if __name__=='__main__':unittest.main()
