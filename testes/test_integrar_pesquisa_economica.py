import csv
import tempfile
import unittest
from pathlib import Path
from integrar_pesquisa_economica import d,aluguel_validos,criar_perfis,calcular_recarga_publica,executar

class TestPesquisaEconomia(unittest.TestCase):
 def test_parse_numeros(self):
  self.assertEqual(str(d('R$ 1.234,50')),'1234.50')
  self.assertEqual(str(d('0.78938')),'0.78938')
  self.assertIsNone(d(''))
 def test_ofertas_filtradas(self):
  r={'tipo_oferta_fonte':'aluguel','cidade':'São Paulo','apto_modelo_economico':'True','status_qualidade':'ok','valor_mensal_equivalente':'3032.90'}
  self.assertEqual(len(aluguel_validos([r])),1)
  r['apto_modelo_economico']='False'
  self.assertEqual(len(aluguel_validos([r])),0)
 def test_sem_receita_ou_ipva_inventados(self):
  o,a=criar_perfis()
  self.assertEqual(o['receita_plataforma_liquida_rs_mes'],'')
  self.assertEqual(o['ipva_efetivo_rs_ano'],'')
  self.assertEqual(o['depreciacao_rs_mes'],'')
  self.assertEqual(a['aluguel_rs_mes'],'')
 def test_recarga_publica_separada(self):
  rows=[{'modalidade':'eletricidade','unidade_consumo_original':'MJ/km (PBEV)',
         'consumo_original':'0.41','eficiencia_recarga_hipotese':'0.9',
         'km_mes_hipotese':'3000','inmetro_id':'11'}]
  out=calcular_recarga_publica(rows)
  self.assertEqual(len(out),1)
  self.assertAlmostEqual(float(out[0]['custo_publico_rs_km']),0.265741,places=5)
 def test_end_to_end_sem_sobrescrever_config(self):
  with tempfile.TemporaryDirectory() as tmp:
   raiz=Path(tmp)
   (raiz/'dados_config').mkdir()
   p=raiz/'dados_config/cenarios_motorista_pesquisa_2026.csv'
   p.write_text('arquivo salvo pelo usuario',encoding='utf-8')
   report=executar(raiz)
   self.assertEqual(report['config_estado'],'ja_existia_preservado')
   self.assertEqual(p.read_text(encoding='utf-8'),'arquivo salvo pelo usuario')
   self.assertTrue((raiz/'dados_relatorios/economia_pesquisa_2026/catalogo_premissas_economicas.csv').exists())

if __name__=='__main__': unittest.main()
