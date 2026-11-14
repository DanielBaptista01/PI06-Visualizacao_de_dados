"""Testes sintéticos: não afirmam cobertura dos microdados reais."""
import tempfile
import unittest
from pathlib import Path
import pandas as pd
from integrar_od2023 import ler_dimensoes,preparar_viagens,faixa_horaria,agregar,executar,salvar_geo

REF=Path(__file__).parent/'dados_referencia_od/dim_zonas_od2023.csv'

class TestOd2023(unittest.TestCase):
 def setUp(self):
  self.zonas=ler_dimensoes(REF)
 def test_referencia_territorial(self):
  self.assertEqual(len(self.zonas),527)
  self.assertEqual(self.zonas['municipio_od_id'].nunique(),39)
  self.assertEqual(int(self.zonas['municipio_od_id'].eq(36).sum()),343)
  self.assertEqual(self.zonas.loc[self.zonas.zona_od_id==485,'municipio_od_id'].iloc[0],20)
 def test_faixa(self):
  self.assertEqual(faixa_horaria(5),'Madrugada (0-5)')
  self.assertEqual(faixa_horaria(6),'Manhã (6-11)')
  self.assertEqual(faixa_horaria(17),'Tarde (12-17)')
  self.assertEqual(faixa_horaria(23),'Noite (18-23)')
  self.assertEqual(faixa_horaria(None),'Hora desconhecida')
 def fixture(self):
  return pd.DataFrame([
   {'ZONA_O':1,'ZONA_D':2,'MUNI_O':36,'MUNI_D':36,'MODOPRIN':12,'FE_VIA':2,'H_SAIDA':8,'DISTANCIA':1000,'DURACAO':10},
   {'ZONA_O':1,'ZONA_D':485,'MUNI_O':36,'MUNI_D':20,'MODOPRIN':12,'FE_VIA':3,'H_SAIDA':8,'DISTANCIA':3000,'DURACAO':30},
   {'ZONA_O':527,'ZONA_D':1,'MUNI_O':25,'MUNI_D':36,'MODOPRIN':12,'FE_VIA':1,'H_SAIDA':23,'DISTANCIA':2000,'DURACAO':20},
   {'ZONA_O':1,'ZONA_D':2,'MUNI_O':36,'MUNI_D':36,'MODOPRIN':9,'FE_VIA':400,'H_SAIDA':8,'DISTANCIA':900,'DURACAO':10},
   {'ZONA_O':1,'ZONA_D':2,'MUNI_O':36,'MUNI_D':36,'MODOPRIN':12,'FE_VIA':-1,'H_SAIDA':8,'DISTANCIA':1000,'DURACAO':10},
   {'ZONA_O':1,'ZONA_D':999,'MUNI_O':36,'MODOPRIN':12,'FE_VIA':4,'H_SAIDA':None,'DISTANCIA':None,'DURACAO':None},
  ])
 def test_pesos_modo_e_linha_reta(self):
  d,qa=preparar_viagens(self.fixture(),self.zonas)
  self.assertEqual(qa['linhas_modo_12'],5)
  self.assertEqual(qa['linhas_app_com_peso_valido'],4)
  self.assertEqual(qa['viagens_expandidas_total_com_peso_valido'],10)
  self.assertEqual(qa['ambas_zonas_validas'],3)
  self.assertEqual(d.loc[d.ZONA_D==485,'municipio_d_od'].iloc[0],20)
  o=agregar(d[d.zona_o_valida & d.faixa_horaria.eq('Manhã (6-11)')],['zona_o_id','faixa_horaria'])
  row=o.loc[o.zona_o_id.eq(1)].iloc[0]
  self.assertEqual(row['viagens_amostra'],2)
  self.assertAlmostEqual(row['viagens_expandidas'],5)
  self.assertAlmostEqual(row['distancia_linha_reta_media_ponderada_km'],2.2)
  self.assertAlmostEqual(row['duracao_media_ponderada_min'],22)
 def test_execucao_arquivos_e_pendencias(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td); data=root/'od.csv';self.fixture().to_csv(data,index=False)
   out=root/'saida';r=executar(data,REF,out)
   self.assertEqual(r['zonas_catalogadas'],527)
   self.assertEqual(r['viagens']['linhas_app_com_peso_valido'],4)
   ind=pd.read_csv(out/'indicadores_zonas_od2023.csv')
   self.assertEqual(len(ind),527)
   self.assertFalse(bool(ind.loc[ind.zona_od_id.eq(3),'tem_amostra_origem'].iloc[0]))
   self.assertTrue(pd.isna(ind.loc[ind.zona_od_id.eq(3),'viagens_origem_expandidas'].iloc[0]))
   self.assertEqual(len(pd.read_csv(out/'fato_od_fluxos_zona_faixa.csv')),3)
   with self.assertRaises(FileExistsError):executar(data,REF,out)

 def test_reparo_geometria_invalida_exportacao_geojson(self):
  import geopandas as gpd
  from shapely.geometry import Polygon
  # 527 polígonos sintéticos, com uma autointerseção tipo laço (bowtie).
  geometrias=[]
  for idx in range(527):
   x=(idx%25)*25; y=(idx//25)*25
   if idx==0:
    geo=Polygon([(x,y),(x+10,y+10),(x,y+10),(x+10,y),(x,y)])
    self.assertFalse(geo.is_valid)
   else:
    geo=Polygon([(x,y),(x+10,y),(x+10,y+10),(x,y+10),(x,y)])
   geometrias.append(geo)
  with tempfile.TemporaryDirectory() as td:
   p=Path(td);shape=p/'zonas.shp'; out=p/'out';out.mkdir()
   gpd.GeoDataFrame({'NumeroZona':list(range(1,528))},geometry=geometrias,crs='EPSG:31983').to_file(shape)
   r=salvar_geo(self.zonas,shape,out)
   self.assertEqual(r['zonas_geometria'],527)
   self.assertEqual(r['municipios_geom_derivada'],39)
   self.assertEqual(r['zonas_originalmente_invalidas'],1)
   self.assertGreaterEqual(r['reparos_totais_incluindo_municipios'],1)
   self.assertEqual(len(gpd.read_file(out/'geo_zonas_od2023_capital.geojson')),343)
   result=gpd.read_file(out/'geo_zonas_od2023_rmsp.geojson')
   self.assertTrue(result.geometry.is_valid.all())
   self.assertTrue(result.geometry.geom_type.isin(['Polygon','MultiPolygon']).all())
   self.assertEqual(str(result.crs),'EPSG:4326')
   a=pd.read_csv(out/'auditoria_geometrias_od2023.csv')
   self.assertIn(1,set(a.zona_od_id))

 def test_reparo_recusa_geometria_colapsada(self):
  import geopandas as gpd
  from shapely.geometry import Polygon
  geometrias=[]
  for idx in range(527):
   x=(idx%25)*25; y=(idx//25)*25
   if idx==0:
    geo=Polygon([(x,y),(x+10,y+10),(x,y)])
   else:
    geo=Polygon([(x,y),(x+10,y),(x+10,y+10),(x,y+10),(x,y)])
   geometrias.append(geo)
  with tempfile.TemporaryDirectory() as td:
   p=Path(td);shape=p/'zonas.shp';out=p/'out';out.mkdir()
   gpd.GeoDataFrame({'NumeroZona':list(range(1,528))},geometry=geometrias,crs='EPSG:31983').to_file(shape)
   with self.assertRaisesRegex(ValueError,'Zona 1'):
    salvar_geo(self.zonas,shape,out)

 def test_reparo_apos_reprojecao_4326(self):
  """Injeta invalidade APÓS a transformação, simulando o caso do SHP real."""
  import geopandas as gpd
  from shapely.geometry import Polygon
  from unittest.mock import patch
  geometrias=[]
  for idx in range(527):
   x=350000+(idx%25)*20
   y=7400000+(idx//25)*20
   geometrias.append(Polygon([(x,y),(x+10,y),(x+10,y+10),(x,y+10)]))
  with tempfile.TemporaryDirectory() as td:
   p=Path(td); shape=p/'zonas.shp'; out=p/'out'; out.mkdir()
   gpd.GeoDataFrame({'NumeroZona':list(range(1,528))},geometry=geometrias,
                     crs='EPSG:31983').to_file(shape)
   original_to_crs=gpd.GeoDataFrame.to_crs
   def to_crs_com_invalidade(self,*args,**kwargs):
    result=original_to_crs(self,*args,**kwargs)
    if kwargs.get('epsg')==4326 and 'zona_od_id' in result:
     result=result.copy()
     lo,la=result.geometry.iloc[0].centroid.coords[0]
     b=0.00005
     bowtie=Polygon([(lo-b,la-b),(lo+b,la+b),
                     (lo-b,la+b),(lo+b,la-b),(lo-b,la-b)])
     assert not bowtie.is_valid
     result.at[result.index[0],'geometry']=bowtie
    return result
   with patch.object(gpd.GeoDataFrame,'to_crs',to_crs_com_invalidade):
    report=salvar_geo(self.zonas,shape,out)
   self.assertEqual(report['zonas_geometria'],527)
   self.assertEqual(report['municipios_geom_derivada'],39)
   self.assertEqual(report['reparos_apos_reprojecao_epsg4326'],1)
   self.assertIn(1,report['ids_reparados_apos_reprojecao_epsg4326'])
   auditoria=pd.read_csv(out/'auditoria_geometrias_od2023.csv')
   self.assertIn('crs_da_fase',auditoria.columns)
   self.assertIn('apos_reprojecao_epsg4326',auditoria.fase.tolist())
   g=gpd.read_file(out/'geo_zonas_od2023_rmsp.geojson')
   self.assertEqual(len(g),527)
   self.assertTrue(g.geometry.is_valid.all())

if __name__=='__main__':unittest.main()
