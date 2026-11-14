import tempfile
import unittest
from pathlib import Path
import pandas as pd
from consolidar_pi06 import run, norm, prefix_model, tech

class TestConsolidacao(unittest.TestCase):
    def test_modelos_delimitados(self):
        self.assertFalse(prefix_model(norm('DOLPHIN MINI'),norm('DOLPHIN MINI GS')))
        self.assertTrue(prefix_model(norm('DOLPHIN MINI GS'),norm('DOLPHIN MINI')))
        self.assertFalse(prefix_model(norm('ORA 03'),norm('ORA 5')))
    def test_propulsao(self):
        self.assertEqual(tech('Elétrico'),'Eletrico')
        self.assertEqual(tech('Híbrido plug-in'),'Hibrido plug-in')
    def test_pipeline(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); d=root/'dados_limpos';d.mkdir()
            def save(filename, rows):pd.DataFrame(rows).to_csv(d/filename,index=False)
            save('08_FIPE_VEICULOS_PARCIAL.csv',[dict(brand_id='99',model_id='1',year_code='2026-4',marca_fipe='BYD',modelo_fipe='Dolphin Mini GS EV',ano_modelo='2026',combustivel_fipe='Elétrico',preco_fipe='R$ 100.000,00',mes_referencia='novembro de 2026')])
            save('05_INMETRO_VALIDADO.csv',[dict(marca='BYD',modelo='DOLPHIN MINI',versao='GS EV',tipo_propulsao='Elétrico',linha_origem_excel='11',combustivel='E',consumo_energetico_mj_km='0.41',consumo_gasolina_diesel_cidade_km_l='',consumo_etanol_cidade_km_l=''),dict(marca='BYD',modelo='DOLPHIN',versao='GS',tipo_propulsao='Elétrico',linha_origem_excel='47',combustivel='E',consumo_energetico_mj_km='0.42',consumo_gasolina_diesel_cidade_km_l='',consumo_etanol_cidade_km_l='')])
            save('09_UBER_MODELOS_SP.csv',[dict(marca='BYD',modelo='Dolphin Mini',uberx_ano_min='2020',comfort_ano_min='',black_ano_min='',electric_ano_min='2024')])
            save('03_ANP_PRECOS_CAPITAL_NOV2026.csv',[dict(municipio='SAO PAULO',produto='GASOLINA COMUM',preco_medio_rs_litro='6.34'),dict(municipio='SAO PAULO',produto='ETANOL',preco_medio_rs_litro='4.09')])
            save('02_ANEEL_CENARIO_ENERGIA_SP.csv',[dict(tarifa_com_bandeira_rs_kwh='0.78938',inclui_tributos=False)])
            r=run(root,root/'output',3000,.90)
            self.assertEqual(r['registros_fipe'],1)
            self.assertEqual(r['links_candidatos_inmetro'],1)
            self.assertEqual(r['consumos_homologados_fipe'],0)
            self.assertEqual(r['simulacoes_inmetro_por_combustivel'],2)
            e=pd.read_csv(root/'output/bridge_fipe_inmetro_pendente.csv')
            self.assertEqual(e.iloc[0]['modelo_inmetro'],'DOLPHIN MINI')

if __name__=='__main__':unittest.main()
