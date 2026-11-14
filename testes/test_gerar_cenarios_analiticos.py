"""Testes sintéticos e de contrato, sem necessidade de acesso ao PostGIS."""
import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from gerar_cenarios_analiticos import (CUSTOS, energia_tecnica, executar,
                                       custos_motorista, sensibilidade_receita,
                                       renda_premissas, territorial, resumos_hierarquia,
                                       grupo_tecnologia)


def od_zonas():
    return pd.DataFrame([
        {'zona_od_id':'1','zona_nome':'A','municipio_od_id':'36','municipio_nome':'São Paulo',
         'distrito_od_id':'1','distrito_nome':'D','escopo':'SAO_PAULO',
         'viagens_origem_amostra':'2','viagens_origem_expandidas':'10',
         'viagens_destino_amostra':'','viagens_destino_expandidas':'',
         'tem_amostra_origem':'True','tem_amostra_destino':'False'},
        {'zona_od_id':'2','zona_nome':'B','municipio_od_id':'36','municipio_nome':'São Paulo',
         'distrito_od_id':'1','distrito_nome':'D','escopo':'SAO_PAULO',
         'viagens_origem_amostra':'','viagens_origem_expandidas':'',
         'viagens_destino_amostra':'2','viagens_destino_expandidas':'10',
         'tem_amostra_origem':'False','tem_amostra_destino':'True'},
    ])


def od_fluxos():
    return pd.DataFrame([{'zona_origem_id':'1','zona_destino_id':'2',
        'faixa_horaria':'Manhã (6-11)','viagens_amostra':'2','viagens_expandidas':'10',
        'duracao_media_ponderada_min':'12.0','distancia_linha_reta_media_ponderada_km':'3.5',
        'amostra_com_distancia':'2'}])


def energy():
    return pd.DataFrame([{'inmetro_id':'37','marca_inmetro':'BYD','modelo_inmetro':'DOLPHIN MINI',
        'versao_inmetro':'GS EV','tecnologia':'Eletrico','modalidade':'eletricidade',
        'custo_energia_rs_km':'0.12','km_mes_hipotese':'3000'}])


def driver(complete=False):
    row={'perfil_id':'proprio','regime':'proprio','inmetro_id':'37',
         'marca_inmetro':'BYD','modelo_inmetro':'DOLPHIN MINI','versao_inmetro':'GS EV',
         'tecnologia':'Eletrico','modalidade':'eletricidade','km_mes':'3000',
         'fonte_premissas':'CENARIO','custo_energia_rs_mes':'360',
         'status':'COMPLETO_CENARIO' if complete else 'PARCIAL_PENDENTE',
         'campos_pendentes':'' if complete else 'ipva;receita_motorista',
         'receita_liquida_plataforma_rs_mes':'8000' if complete else '',
         'resultado_economico_rs_mes':'5640' if complete else '',
         'custo_total_economico_rs_mes':'2360' if complete else '',
         'custo_total_rs_km':'0.786666' if complete else '',
         'receita_equilibrio_rs_km':'0.786666' if complete else '',
         'receita_equilibrio_rs_hora':'11.8' if complete else ''}
    row.update({c:'0' for c in CUSTOS if c!='custo_energia_rs_mes'})
    row['custo_depreciacao_rs_mes']='2000'
    if not complete:
        row['custo_ipva_rs_mes']=''
    return pd.DataFrame([row])


def earnings():
    return pd.DataFrame([{'cenario_receita_id':'baixo','titulo':'Hipótese ilustrativa',
        'receita_apos_plataforma_rs_mes':'6000',
        'fonte':'HIPOTESE_DIDATICA_NAO_OBSERVADA',
        'observacao':'Não é observação Uber'}])


class TestAnaliticos(unittest.TestCase):
    def test_sem_amostra_nao_e_zero(self):
        z,top,r=territorial(od_zonas(),od_fluxos(),5,validar_baseline=False)
        self.assertTrue(pd.isna(z.loc[z.zona_od_id==2,'viagens_origem_expandidas'].iloc[0]))
        self.assertFalse(bool(z.loc[z.zona_od_id==2,'tem_amostra_origem'].iloc[0]))
        self.assertEqual(len(top),1)
        self.assertEqual(top.iloc[0]['zona_destino_id'],2)
        self.assertEqual(r['zonas'],2)
        m,d = resumos_hierarquia(z)
        self.assertEqual(len(m),1)
        self.assertEqual(int(m.iloc[0]['qtd_zonas']),2)
        self.assertEqual(len(d),1)

    def test_dado_territorial_nao_inclui_receita(self):
        z,_,_=territorial(od_zonas(),od_fluxos(),5,False)
        self.assertFalse(any('receita' in c or 'motorista' in c for c in z.columns))

    def test_economia_incompleta_mantem_resultado_vazio(self):
        costs=custos_motorista(driver(False))
        self.assertEqual(costs.iloc[0]['componentes_custos_pendentes'],1)
        self.assertTrue(pd.isna(costs.iloc[0]['custo_total_economico_rs_mes']))
        self.assertAlmostEqual(costs.iloc[0]['subtotal_custos_conhecidos_rs_mes'],2360)
        scen=sensibilidade_receita(costs,renda_premissas(earnings()))
        self.assertTrue(pd.isna(scen.iloc[0]['resultado_economico_simulado_rs_mes']))
        self.assertEqual(scen.iloc[0]['situacao_calculo'],'CUSTOS_INCOMPLETOS_SEM_RESULTADO')

    def test_economia_completa_calcula_somente_simulacao(self):
        costs=custos_motorista(driver(True))
        scen=sensibilidade_receita(costs,renda_premissas(earnings()))
        self.assertAlmostEqual(scen.iloc[0]['resultado_economico_simulado_rs_mes'],3640.0)
        self.assertEqual(scen.iloc[0]['natureza_dado'],'SIMULACAO_HIPOTETICA')

    def test_nao_associa_fipe_nem_uber(self):
        panel=energia_tecnica(energy())
        self.assertEqual(panel.iloc[0]['grupo_interface'],'Elétrico')
        self.assertEqual(grupo_tecnologia('Hibrido plug-in'),'Híbrido')
        self.assertEqual(grupo_tecnologia('Combustao'),'Gasolina')
        self.assertNotIn('preco_fipe_rs',panel.columns)
        self.assertNotIn('elegibilidade_uber',panel.columns)

    def test_fluxo_zona_invalida_bloqueado(self):
        f=od_fluxos();f.loc[0,'zona_destino_id']='999'
        with self.assertRaisesRegex(ValueError,'fora do catálogo'):
            territorial(od_zonas(),f,5,validar_baseline=False)

    def test_receita_sem_rotulo_hipotese_bloqueada(self):
        r=earnings();r.loc[0,'fonte']='IBGE'
        with self.assertRaisesRegex(ValueError,'hipótese'):
            renda_premissas(r)

    def test_integracao_sintetica_end_to_end(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); od=root/'od'; energia=root/'en'; economia=root/'eco'; conf=root/'cfg'
            for directory in [od,energia,economia,conf]:directory.mkdir()
            od_zonas().to_csv(od/'indicadores_zonas_od2023.csv',index=False)
            od_fluxos().to_csv(od/'fato_od_fluxos_zona_faixa.csv',index=False)
            energy().to_csv(energia/'fato_cenarios_inmetro_energia.csv',index=False)
            driver(False).to_csv(economia/'fato_cenarios_motorista.csv',index=False)
            earnings().to_csv(conf/'receitas.csv',index=False)
            out=root/'result'
            report=executar(root,od,energia,economia,conf/'receitas.csv',out,
                           n_destinos=5,validar_baseline=False)
            self.assertEqual(report['resumo_od']['zonas'],2)
            self.assertEqual(report['sensibilidade_com_resultado'],0)
            self.assertEqual(report['sensibilidade_linhas'],1)
            self.assertEqual(len(list(out.glob('*.csv'))),8)
            self.assertEqual(len(json.loads((out/'manifesto_cenarios_analiticos.json').read_text())['saidas_sha256']),8)
            with self.assertRaises(FileExistsError):
                executar(root,od,energia,economia,conf/'receitas.csv',out,
                         validar_baseline=False)


if __name__=='__main__':
    unittest.main()
