"""Testes isolados do construtor da apresentação, sem baixar nada da internet."""
import unittest
import sys
from pathlib import Path as _Path
sys.path.insert(0,str(_Path(__file__).resolve().parents[1]))

from preparar_site_offline import inject, simplify, project_paths, collect_bounds, valid_coords


class TestSiteOffline(unittest.TestCase):
    def test_injecao_json_e_escapes(self):
        result=inject('<script>__PI06_DATA__</script><script>__PI06_IMAGE__</script>', {'x':'</script><p>oi</p>'}, '')
        self.assertIn('\\u003c/script\\u003e',result)
        self.assertNotIn('</script><p>',result)

    def test_simplificacao_nao_remove_extremos(self):
        pts=[(0,0),(1,0),(2,0),(3,0),(3,1),(3,2),(3,3)]
        out=simplify(pts,tol=.1)
        self.assertEqual(out[0],pts[0])
        self.assertEqual(out[-1],pts[-1])
        self.assertIn((3,0),out)

    def test_geometry_polygon_gera_path(self):
        f={'geometry':{'type':'Polygon','coordinates':[[[-46.9,-23.5],[-46.8,-23.5],[-46.8,-23.4],[-46.9,-23.4],[-46.9,-23.5]]]}}
        self.assertIn('Z',project_paths(f,lambda p:(p[0]*100,p[1]*100)))

    def test_rejeita_coordenadas_projetadas(self):
        f={'geometry':{'type':'Polygon','coordinates':[[[200000,7390000],[200100,7390000],[200100,7390100],[200000,7390100],[200000,7390000]]]}}
        with self.assertRaisesRegex(ValueError,'projetadas'):
            collect_bounds([f])

    def test_valida_lat_lon(self):
        self.assertTrue(valid_coords([-46.6,-23.5]))
        self.assertFalse(valid_coords([1000000,7500000]))


if __name__=='__main__':unittest.main()
