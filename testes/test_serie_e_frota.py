"""Testes sem rede para a v2: série ABVE, recorte SENATRAN e FIPE (sem cruzamentos inválidos)."""
import csv
import tempfile
import unittest
from pathlib import Path

import sys
from pathlib import Path as _Path
sys.path.insert(0,str(_Path(__file__).resolve().parents[1]))

from preparar_site_offline import (
    load_abve_annual, load_fipe_years, load_fleet_municipal,
)


class TestDadosNovos(unittest.TestCase):
    def test_abve_parcial_compara_mesmo_periodo_sem_mhev(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "abve.csv"
            with p.open("w", newline="", encoding="utf-8-sig") as fp:
                w=csv.DictWriter(fp,fieldnames=["periodo","abrangencia","bev","phev","hev","hev_flex","mhev"],delimiter=";")
                w.writeheader()
                for ano in (2025, 2026):
                    for mes in range(1, (3 if ano==2025 else 2)):
                        w.writerow(dict(periodo=f"{ano}-{mes:02d}",abrangencia="Brasil",bev=10*mes,
                                        phev=4,hev=2,hev_flex=3,mhev=99999))
            result=load_abve_annual(p)
            self.assertEqual([r['months'] for r in result],[2,1])
            self.assertEqual(result[1]['bev'],10)
            self.assertEqual(result[1]['hybrid'],9)
            self.assertEqual(result[1]['prior_matching_total'],19)

    def test_abve_rejeita_mes_repetido(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'abve.csv'
            p.write_text('periodo;abrangencia;bev;phev;hev;hev_flex\n2022-01;Brasil;1;1;1;1\n2022-01;Brasil;1;1;1;1\n')
            with self.assertRaisesRegex(ValueError,'duplicado'):
                load_abve_annual(p)

    def test_senatran_escopo_municipal_nao_zonal(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'frota.csv'
            with p.open('w',newline='',encoding='utf8') as fp:
                w=csv.DictWriter(fp,fieldnames=['Município','Qtd. Veículos','categoria_visualizacao']);w.writeheader()
                w.writerow({'Município':'SAO PAULO','Qtd. Veículos':300,'categoria_visualizacao':'Gasolina'})
                w.writerow({'Município':'SAO PAULO','Qtd. Veículos':50,'categoria_visualizacao':'Híbrido'})
                w.writerow({'Município':'GUARULHOS','Qtd. Veículos':70,'categoria_visualizacao':'Gasolina'})
            result=load_fleet_municipal(p,[{'municipio_nome':'São Paulo'}])
            self.assertEqual(len(result),1)
            self.assertEqual(result[0]['Gasolina'],300)
            self.assertEqual(result[0]['Híbrido'],50)

    def test_fipe_ano_modelo_mes_de_preco_e_atual(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'fipe.csv'
            with p.open('w',newline='',encoding='utf8') as fp:
                w=csv.DictWriter(fp,fieldnames=['ano_modelo','preco_fipe','combustivel_fipe']);w.writeheader()
                w.writerow({'ano_modelo':'2022','preco_fipe':'R$ 100.000,00','combustivel_fipe':'Gasolina'})
                w.writerow({'ano_modelo':'2022','preco_fipe':'R$ 120.000,00','combustivel_fipe':'Híbrido'})
                w.writerow({'ano_modelo':'2026','preco_fipe':'R$ 180.000,00','combustivel_fipe':'Elétrico'})
            result=load_fipe_years(p)
            self.assertEqual(result[0]['mediana_brl'],110000)
            self.assertEqual(result[0]['categorias']['Híbrido'],1)
            self.assertEqual(result[1]['categorias']['Elétrico'],1)


if __name__=='__main__': unittest.main()
