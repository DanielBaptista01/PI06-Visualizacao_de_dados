"""Região oficial por distrito e recorte 343 zonas da capital, sem consultas à rede."""
import csv
import json
import tempfile
import unittest
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from preparar_site_offline import ler_regioes_sp, build_map

REGIONS=Path(__file__).resolve().parents[1]/'regioes_sp_2025.csv'


def fake_districts_zones():
    with REGIONS.open(encoding='utf-8-sig',newline='') as f:
        nomes=[r['distrito_nome'] for r in csv.DictReader(f)]
    ds=[{'distrito_od_id':i+1,'distrito_nome':n} for i,n in enumerate(nomes)]
    zones=[{'zona_od_id':i+1,'municipio_od_id':36,
            'distrito_od_id':(i%96)+1,'distrito_nome':nomes[i%96]} for i in range(343)]
    zones.append({'zona_od_id':344,'municipio_od_id':15,'distrito_od_id':1,'distrito_nome':'Outro município'})
    return ds,zones


class TestRecorteCapital(unittest.TestCase):
    def test_todas_96_regioes_e_so_343_zonas_sp(self):
        ds,zones=fake_districts_zones()
        capital=ler_regioes_sp(REGIONS,ds,zones)
        self.assertEqual(len(capital),343)
        self.assertEqual({z['regiao_sp'] for z in capital},{'Centro','Norte','Sul','Leste','Oeste'})
        self.assertTrue(all(z['municipio_od_id']==36 for z in capital))
        self.assertTrue(all('regiao_sp' not in z for z in zones))

    def test_rejeita_distrito_nao_mapeado(self):
        ds,zones=fake_districts_zones()
        ds[0]['distrito_nome']='Nome sem referência oficial'
        with self.assertRaisesRegex(ValueError,'não coincidem'):
            ler_regioes_sp(REGIONS,ds,zones)

    def test_shapefile_527_para_mapa_somente_capital(self):
        ds,zones=fake_districts_zones()
        capital=ler_regioes_sp(REGIONS,ds,zones)
        feats=[]
        for i in range(1,528):
            xx=(i-1)%31;yy=(i-1)//31
            lon=-47.5+xx*.05;lat=-24+yy*.05
            ring=[[lon,lat],[lon+.045,lat],[lon+.045,lat+.045],[lon,lat+.045],[lon,lat]]
            feats.append({'type':'Feature','properties':{'zona_od_id':i},
                          'geometry':{'type':'Polygon','coordinates':[ring]}})
        muns=[]
        for i in range(1,40):
            lon=-47.3+i*.01;lat=-23.9+i*.01
            ring=[[lon,lat],[lon+.05,lat],[lon+.05,lat+.05],[lon,lat+.05],[lon,lat]]
            muns.append({'type':'Feature','properties':{'municipio_od_id':i},
                         'geometry':{'type':'Polygon','coordinates':[ring]}})
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);zp=p/'zonas.geojson';mp=p/'municipios.geojson'
            zp.write_text(json.dumps({'type':'FeatureCollection','features':feats}))
            mp.write_text(json.dumps({'type':'FeatureCollection','features':muns}))
            shapes,borders,points=build_map(zp,mp,capital,[{'id_posto':'42','longitude':-47.1,'latitude':-23.8}])
            self.assertEqual(len(shapes),343)
            self.assertEqual({x['id'] for x in shapes},set(range(1,344)))
            self.assertEqual([x['id'] for x in borders],[36])

if __name__=='__main__':unittest.main()
