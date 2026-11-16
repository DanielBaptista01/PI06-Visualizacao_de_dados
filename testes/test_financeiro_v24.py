"""Testes de proveniência do simulador v2.4 — sem servidor nem rede."""
from pathlib import Path
import csv
import tempfile
import unittest
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from preparar_site_offline import financial_sources,inject


def sheet(root, name, headers, rows):
    p=root/name;p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=headers);w.writeheader();w.writerows(rows)


class TestFinanceiroV24(unittest.TestCase):
    def test_valores_fontes_sem_vinculo_automatico_de_veiculo(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            sheet(root,'dados_limpos/03_ANP_PRECOS_CAPITAL_NOV2026.csv',['municipio','produto','preco_medio_rs_litro'],[
                {'municipio':'SAO PAULO','produto':'ETANOL','preco_medio_rs_litro':'4.089952380952381'},
                {'municipio':'SAO PAULO','produto':'GASOLINA COMUM','preco_medio_rs_litro':'6.342190476190476'}])
            sheet(root,'dados_limpos/02_ANEEL_CENARIO_ENERGIA_SP.csv',['municipio_referencia','mes_cenario','tarifa_base_rs_kwh'],[
                {'municipio_referencia':'Sao Paulo','mes_cenario':'2026-11','tarifa_base_rs_kwh':'0.78938'}])
            sheet(root,'dados_complementares/etapa19/cotacoes.csv',['categoria','valor_brl'],[
                {'categoria':'recarga_publica_mediana','valor_brl':'2.1'}])
            sheet(root,'dados_config/cenarios_motorista_pesquisa_2026.csv',[
                'regime','manutencao_rs_km','pneus_rs_km','seguro_rs_mes','lavagem_rs_mes','celular_rs_mes','licenciamento_rs_ano'],[
                {'regime':'proprio','manutencao_rs_km':'0.10','pneus_rs_km':'0.03','seguro_rs_mes':'400','lavagem_rs_mes':'80','celular_rs_mes':'50','licenciamento_rs_ano':'174.08'}])
            sheet(root,'dados_limpos/17_UBER_MATCH_OFERTAS_SP.csv',[
                'cidade','tipo_oferta_fonte','apto_modelo_economico','revisar_oferta','valor_mensal_equivalente',
                'seguro_incluso','manutencao_inclusa','ipva_incluso','sem_limite_quilometragem',
                'km_inclusos','valor_km_excedente_reais','caucao_reais','id_publico_oferta','locadora','veiculo','data_coleta','url_oferta'],[
                {'cidade':'São Paulo','tipo_oferta_fonte':'aluguel','apto_modelo_economico':'True','revisar_oferta':'False',
                'valor_mensal_equivalente':'3200','seguro_incluso':'True','manutencao_inclusa':'True','ipva_incluso':'False',
                'sem_limite_quilometragem':'False','km_inclusos':'3000','valor_km_excedente_reais':'0.60','caucao_reais':'1000',
                'id_publico_oferta':'abc','locadora':'Exemplo','veiculo':'Veículo não homologado','data_coleta':'2026-11-07',
                'url_oferta':'https://earn.uber.com/offer/abc'}])
            sheet(root,'dados_limpos/08_FIPE_VEICULOS_PARCIAL.csv',
                ['marca_fipe','modelo_fipe','ano_modelo','preco_fipe','mes_referencia'],[
                {'marca_fipe':'Fiat','modelo_fipe':'Mobi Like','ano_modelo':'2024','preco_fipe':'R$ 58.000,00','mes_referencia':'novembro de 2026'}])
            d=financial_sources(root)
            self.assertAlmostEqual(d['reference']['gasoline'],6.342190476,places=5)
            self.assertEqual(d['reference']['home_kwh'],0.78938)
            self.assertEqual(d['reference']['maintenance_km'],.10)
            self.assertEqual(len(d['offers']),1)
            self.assertEqual(d['offers'][0]['kmIncluded'],3000)
            self.assertEqual(d['offers'][0]['extraKm'],.6)
            self.assertTrue(d['offers'][0]['insurance'])
            self.assertFalse(d['offers'][0]['ipva'])
            self.assertEqual(d['offers'][0]['deposit'],1000)
            self.assertNotIn('inmetro_id',d['offers'][0])
            self.assertEqual(d['fipe'][0]['price'],58000)
            self.assertEqual(d['fipe'][0]['year'],2024)
            self.assertNotIn('inmetro_id',d['fipe'][0])

    def test_template_mantem_mapas_e_nova_secao_financeira(self):
        template=(Path(__file__).resolve().parents[1]/'modelo.html').read_text(encoding='utf-8')
        for key in ('id="mobilidade"','id="fluxos"','id="energia"','id="recarga"','id="viabilidade"',
                    'id="simulador"','id="fin-rental"','id="fin-rental-overage"',
                    'id="fin-electric-share"','id="fin-includes-ins"','id="fin-save-a"',
                    'id="fin-save-b"','function financeCalc()','function financeEnergy('):
            self.assertIn(key,template)
        text=inject(template,{'full':False,'meta':{},'zones':[]},'')
        self.assertNotIn('__PI06_DATA__',text)
        self.assertEqual(text.count('id="simulador"'),1)

if __name__=='__main__':unittest.main()
