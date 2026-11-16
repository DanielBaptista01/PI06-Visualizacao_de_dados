"""Valida georreferenciamento da recarga ao zoneamento, sem rede ou API."""
import json
import tempfile
import unittest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from preparar_site_offline import charging_by_zone, point_in_geometry, point_in_ring


def geom(x0,y0,x1,y1):
    return {'type':'Polygon','coordinates':[[
        [x0,y0],[x1,y0],[x1,y1],[x0,y1],[x0,y0]
    ]]}


class TestMapaDecisao(unittest.TestCase):
    def test_ponto_externo_e_buraco(self):
        g=geom(-46.8,-23.7,-46.4,-23.3)
        self.assertTrue(point_in_geometry(-46.6,-23.5,g))
        self.assertFalse(point_in_geometry(-46.1,-23.5,g))
        g['coordinates'].append([[-46.7,-23.6],[-46.5,-23.6],[-46.5,-23.4],[-46.7,-23.4],[-46.7,-23.6]])
        self.assertFalse(point_in_geometry(-46.6,-23.5,g))
        self.assertTrue(point_in_geometry(-46.75,-23.65,g))

    def test_relacao_ocm_nao_atribui_por_nome_de_bairro(self):
        zones=[{'zona_od_id':1},{'zona_od_id':2}]
        feats=[{'type':'Feature','properties':{'zona_od_id':1},'geometry':geom(-46.8,-23.7,-46.65,-23.5)},
               {'type':'Feature','properties':{'zona_od_id':2},'geometry':geom(-46.65,-23.7,-46.50,-23.5)}]
        charging=[{'id_posto':'10','longitude':'-46.75','latitude':'-23.6','status_cadastral':'Operational','logradouro':'Outro bairro'},
                  {'id_posto':'11','longitude':'-46.55','latitude':'-23.6','status_cadastral':'Not Operational'},
                  {'id_posto':'12','longitude':'-46.1','latitude':'-23.6','status_cadastral':'Operational'},
                  {'id_posto':'13','longitude':'','latitude':'','status_cadastral':'Operational'}]
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'s.geojson'
            p.write_text(json.dumps({'type':'FeatureCollection','features':feats}),encoding='utf-8')
            r=charging_by_zone(p,zones,charging)
        self.assertEqual(r['atribuidos'],2)
        self.assertEqual(r['nao_atribuidos'],2)
        self.assertEqual(r['zonas_com_ocm'],2)
        self.assertEqual([z['pontos_ocm_cadastrados'] for z in zones],[1,1])
        self.assertEqual([z['pontos_ocm_status_operational'] for z in zones],[1,0])

    def test_multigeometria(self):
        g={'type':'MultiPolygon','coordinates': [geom(-46.9,-23.9,-46.8,-23.8)['coordinates'],geom(-46.7,-23.7,-46.6,-23.6)['coordinates']]}
        self.assertTrue(point_in_geometry(-46.85,-23.85,g))
        self.assertTrue(point_in_geometry(-46.65,-23.65,g))
        self.assertFalse(point_in_geometry(-46.75,-23.75,g))

    def test_modelo_site_contem_filtro_responsivo_e_recomendacao_condicional(self):
        html=(Path(__file__).resolve().parents[1]/'modelo.html').read_text(encoding='utf-8')
        for content in ['id="viabilidade"','id="decision-map"','id="decision-confirm"','id="mobile-menu"',
                        '@media(max-width:700px)','initDecision();','initMobileMenu();',
                        'Não é um mapa de lucro observado']:
            self.assertIn(content,html)

if __name__=='__main__':unittest.main()
