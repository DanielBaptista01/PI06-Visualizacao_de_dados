import tempfile
import unittest
from pathlib import Path
import pandas as pd
from construir_tabela_mestra import norm, preco_brl, tokens_iniciais, executar

class MestreTests(unittest.TestCase):
    def test_normalizacao(self):
        self.assertEqual(norm('São Paulo'), 'SAO PAULO')
    def test_preco(self):
        self.assertEqual(preco_brl('R$ 141.461,00'), 141461.0)
        self.assertEqual(preco_brl('141461.00'), 141461.0)
    def test_prefixo(self):
        self.assertTrue(tokens_iniciais('DOLPHIN MINI GS EV', 'DOLPHIN MINI'))
        self.assertFalse(tokens_iniciais('ONIXPLUS', 'ONIX'))
    def test_integracao_nao_homologa(self):
        with tempfile.TemporaryDirectory() as d:
            r=Path(d)
            (r/'dados_limpos').mkdir()
            pd.DataFrame([{
                'brand_id':'1','model_id':'2','year_code':'2026-3',
                'codigo_fipe':'12345-6','marca_fipe':'BYD','modelo_fipe':'Dolphin Mini GS EV',
                'ano_modelo':'2026','combustivel_fipe':'Elétrico','preco_fipe':'R$ 141.461,00',
                'mes_referencia':'novembro de 2026'
            }]).to_csv(r/'dados_limpos/08_FIPE_VEICULOS_PARCIAL.csv',index=False)
            pd.DataFrame([{'marca':'BYD','modelo':'Dolphin Mini',
                'uberx_ano_min':'2024','comfort_ano_min':'','black_ano_min':'',
                'electric_ano_min':'2024'}]).to_csv(r/'dados_limpos/09_UBER_MODELOS_SP.csv',index=False)
            pd.DataFrame([{'marca':'BYD','modelo':'Dolphin Mini','versao':'GS EV',
                'tipo_propulsao':'Elétrico','linha_origem_excel':'11'}]).to_csv(r/'dados_limpos/05_INMETRO_VALIDADO.csv',index=False)
            resumo=executar(r, r/'dados_relatorios/integracao_veiculos')
            self.assertEqual(resumo['com_candidato_ambos'],1)
            m=pd.read_csv(r/'dados_relatorios/integracao_veiculos/tabela_mestra_fipe_parcial.csv')
            self.assertTrue(pd.isna(m.loc[0,'consumo_eletrico_kwh_km']))
            self.assertEqual(m.loc[0,'preco_fipe_rs'],141461.0)
            self.assertFalse(m.loc[0,'elegibilidade_uber_confirmada'])

if __name__ == '__main__':
    unittest.main()
