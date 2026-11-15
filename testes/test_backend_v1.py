"""Validação estrutural e HTTP sem tocar no Supabase.
Execute: python -m unittest -v testes.test_backend_v1
"""
from __future__ import annotations
import csv
import json
import tempfile
import unittest
from pathlib import Path
from fastapi.testclient import TestClient
from backend.app import app, get_connection
from backend.carga import TABLES, FIELDS, OCM_FIELDS, sha256, validar, load_geo


def make_snapshot(root: Path):
    p=root/'paineis';p.mkdir()
    # Fixture territorial completa em dimensão (527 zonas, 39 municípios, 96 distritos)
    # sem fingir viagens reais da OD.
    rows={}
    for table in TABLES:
        rows[table]=[]
    for m in range(1,40):
        row=dict.fromkeys(FIELDS['od_municipios'],'')
        row.update(municipio_od_id=str(m),municipio_nome=('São Paulo' if m==36 else f'Município {m}'),
                   qtd_zonas='343' if m==36 else '1',zonas_com_amostra_origem='0',
                   zonas_com_amostra_destino='0',fonte='METRO_OD_2023_MODOPRIN_12',natureza_dado='AMOSTRAL_EXPANDIDO')
        rows['od_municipios'].append(row)
    for d in range(1,97):
        row=dict.fromkeys(FIELDS['od_distritos_capital'],'')
        row.update(distrito_od_id=str(d),distrito_nome=f'Distrito {d}',qtd_zonas='1',
                   zonas_com_amostra_origem='0',zonas_com_amostra_destino='0',
                   fonte='METRO_OD_2023_MODOPRIN_12',natureza_dado='AMOSTRAL_EXPANDIDO')
        rows['od_distritos_capital'].append(row)
    ids=[m for m in range(1,40) if m!=36]
    ids=([36]*343) + ([m for m in ids]*(184//38) + ids[:184%38])
    assert len(ids)==527
    for z in range(1,528):
        row=dict.fromkeys(FIELDS['od_zonas'],'')
        row.update(zona_od_id=str(z),zona_nome=f'Zona {z}',municipio_od_id=str(ids[z-1]),
                   municipio_nome='São Paulo' if ids[z-1]==36 else 'Município',
                   distrito_od_id=str((z-1)%96+1),distrito_nome='Distrito',
                   escopo='SAO_PAULO' if ids[z-1]==36 else 'RMSP_OUTROS',
                   tem_amostra_origem='False',tem_amostra_destino='False',
                   fonte='METRO_OD_2023_MODOPRIN_12',natureza_dado='AMOSTRAL_EXPANDIDO',observacao='Amostra sintética')
        rows['od_zonas'].append(row)
    f=dict.fromkeys(FIELDS['od_top_destinos'],'')
    f.update(zona_origem_id='1',zona_destino_id='2',faixa_horaria='Manhã (6-11)',
             viagens_amostra='1',viagens_expandidas='20.2',amostra_com_distancia='1',posicao='1',
             nome_zona_destino='Zona 2',municipio_destino='São Paulo',
             fonte='METRO_OD_2023_MODOPRIN_12',natureza_dado='AMOSTRAL_EXPANDIDO',observacao='Linha reta')
    rows['od_top_destinos'].append(f)
    e=dict.fromkeys(FIELDS['energia_inmetro'],'')
    e.update(inmetro_id='11',marca_inmetro='BYD',modelo_inmetro='DOLPHIN MINI',versao_inmetro='GS',
             tecnologia='Eletrico',modalidade='eletricidade',custo_energia_rs_km='0.1',
             km_mes_hipotese='3000',custo_energia_rs_mes_hipotetico='300',grupo_interface='Elétrico',
             fonte='INMETRO_PBEV',natureza_dado='SIMULADO_ENERGIA',observacao='Hipótese')
    rows['energia_inmetro'].append(e)
    m=dict.fromkeys(FIELDS['motorista_custos'],'')
    m.update(perfil_id='proprio_base',regime='proprio',inmetro_id='11',marca_inmetro='BYD',
             modelo_inmetro='DOLPHIN MINI',versao_inmetro='GS',tecnologia='Eletrico',modalidade='eletricidade',
             status='PARCIAL_PENDENTE',campos_pendentes='ipva;receita',fonte_premissas='SIMULACAO',
             km_mes='3000',componentes_custos_informados='2',componentes_custos_pendentes='9',
             subtotal_custos_conhecidos_rs_mes='300',todos_custos_preenchidos='False',
             grupo_interface='Elétrico',fonte='PI06',natureza_dado='SIMULADO_COM_PREMISSAS',observacao='Hipótese')
    rows['motorista_custos'].append(m)
    rr=dict.fromkeys(FIELDS['premissas_receita'],'')
    rr.update(cenario_receita_id='hipotese_6000',titulo='Receita didática',
              receita_apos_plataforma_rs_mes='6000',fonte='HIPOTESE_DIDATICA_NAO_OBSERVADA',
              natureza_dado='HIPOTESE_DIDATICA',observacao='Não observada')
    rows['premissas_receita'].append(rr)
    sr=dict.fromkeys(FIELDS['sensibilidade_receita'],'')
    sr.update(perfil_id='proprio_base',regime='proprio',inmetro_id='11',modalidade='eletricidade',
              tecnologia='Eletrico',grupo_interface='Elétrico',km_mes='3000',
              componentes_custos_pendentes='9',subtotal_custos_conhecidos_rs_mes='300',
              campos_pendentes='ipva;receita',todos_custos_preenchidos='False',
              cenario_receita_id='hipotese_6000',receita_apos_plataforma_rs_mes='6000',
              situacao_calculo='CUSTOS_INCOMPLETOS_SEM_RESULTADO',natureza_dado='SIMULACAO_HIPOTETICA',
              observacao='Hipótese')
    rows['sensibilidade_receita'].append(sr)
    entries={}
    for table,filename in TABLES.items():
        file=p/filename
        with file.open('w',encoding='utf-8-sig',newline='') as out:
            w=csv.DictWriter(out,fieldnames=FIELDS[table]);w.writeheader();w.writerows(rows[table])
        entries[filename]={'linhas':len(rows[table]),'sha256':sha256(file)}
    (p/'manifesto_cenarios_analiticos.json').write_text(json.dumps({'versao':'test-fixture',
        'saidas_sha256':entries}),encoding='utf-8')
    g=root/'geo_zonas.geojson'
    gm=root/'geo_municipios.geojson'
    # retângulos válidos, só para testar o parser (não para modelar uma região real)
    def feature(prop,idx):
        x=-47.0 + idx*0.00001
        coordinates=[[[x,-23.5],[x+0.000004,-23.5],[x+0.000004,-23.499996],[x,-23.499996],[x,-23.5]]]
        return {'type':'Feature','properties':prop,
                'geometry':{'type':'Polygon','coordinates':coordinates}}
    g.write_text(json.dumps({'type':'FeatureCollection','features':[
        feature({'zona_od_id':i},i) for i in range(1,528)]}),encoding='utf-8')
    gm.write_text(json.dumps({'type':'FeatureCollection','features':[
        feature({'municipio_od_id':i},i) for i in range(1,40)]}),encoding='utf-8')
    ocm=root/'ocm.csv'
    with ocm.open('w',encoding='utf-8-sig',newline='') as out:
        w=csv.DictWriter(out,fieldnames=OCM_FIELDS);w.writeheader()
        row=dict.fromkeys(OCM_FIELDS,'');row.update(id_posto='1',titulo='Exemplo',
                                                    latitude='-23.5',longitude='-46.9',
                                                    status_cadastral='Unknown',data_coleta='2026-11-01')
        w.writerow(row)
    return p,g,gm,ocm


class TestValidacaoCarga(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.p,self.geo,self.muni,self.ocm=make_snapshot(self.root)
    def tearDown(self):
        self.tmp.cleanup()
    def test_valida_oito_tabelas_e_geometrias(self):
        data=validar(self.p,self.geo,self.muni,self.ocm)
        self.assertEqual(data['counts']['od_zonas'],527)
        self.assertEqual(data['geometrias_zona'],527)
        self.assertEqual(len(data['municipios_geo_rows']),39)
        self.assertEqual(data['counts']['sensibilidade_receita'],1)
    def test_checksum_detecta_modificacao(self):
        with (self.p/'painel_od_zonas.csv').open('a',encoding='utf8') as f:f.write('\n')
        with self.assertRaisesRegex(ValueError,'SHA256 diferente'):
            validar(self.p,self.geo,self.muni,self.ocm)
    def test_bloqueia_lucro_em_custo_parcial(self):
        target=self.p/'painel_motorista_custos.csv'
        with target.open('r',encoding='utf-8-sig',newline='') as f:
            rr=list(csv.DictReader(f))
        rr[0]['resultado_economico_rs_mes']='5000'
        with target.open('w',encoding='utf-8-sig',newline='') as f:
            w=csv.DictWriter(f,fieldnames=FIELDS['motorista_custos']);w.writeheader();w.writerows(rr)
        mf=self.p/'manifesto_cenarios_analiticos.json'
        manifest=json.loads(mf.read_text())
        manifest['saidas_sha256']['painel_motorista_custos.csv']['sha256']=sha256(target)
        mf.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError,'Lucro/custo total indevido'):
            validar(self.p,self.geo,self.muni,self.ocm)
    def test_aceita_crs84_ogr_do_metro(self):
        # GeoPandas/GDAL pode emitir a identificacao OGC:CRS84 em GeoJSON EPSG:4326.
        for path in (self.geo, self.muni):
            obj=json.loads(path.read_text())
            obj['crs']={'type':'name','properties':{'name':'urn:ogc:def:crs:OGC:1.3:CRS84'}}
            path.write_text(json.dumps(obj),encoding='utf-8')
        data=validar(self.p,self.geo,self.muni,self.ocm)
        self.assertEqual(data['geometrias_zona'],527)
        self.assertEqual(len(data['municipios_geo_rows']),39)
    def test_rejeita_crs_metrico(self):
        obj=json.loads(self.geo.read_text())
        obj['crs']={'type':'name','properties':{'name':'EPSG:3857'}}
        self.geo.write_text(json.dumps(obj),encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'reprojete para EPSG:4326'):
            validar(self.p,self.geo,self.muni,self.ocm)
    def test_rejeita_coordenadas_fora_wgs84(self):
        obj=json.loads(self.geo.read_text())
        # Simula coordenada projetada em metros em arquivo sem declaracao CRS.
        obj['features'][0]['geometry']['coordinates'][0][0][0]=-5200000
        self.geo.write_text(json.dumps(obj),encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'coordenadas invalidas'):
            validar(self.p,self.geo,self.muni,self.ocm)
    def test_aceita_epsg4326_nomeado(self):
        obj=json.loads(self.geo.read_text())
        obj['crs']={'type':'name','properties':{'name':'EPSG:4326'}}
        self.geo.write_text(json.dumps(obj),encoding='utf-8')
        self.assertEqual(len(load_geo(self.geo,set(range(1,528)))),527)
    def test_recusa_geo_incompleto(self):
        obj=json.loads(self.geo.read_text())
        obj['features'].pop()
        self.geo.write_text(json.dumps(obj))
        with self.assertRaisesRegex(ValueError,'zonas incompatíveis'):
            validar(self.p,self.geo,self.muni,self.ocm)
    def test_recusa_coordenada_ocm_invalida(self):
        s=self.ocm.read_text(encoding='utf-8-sig').replace('-23.5','-123.5')
        self.ocm.write_text(s,encoding='utf-8-sig')
        with self.assertRaisesRegex(ValueError,'latitude/longitude inválidas'):
            validar(self.p,self.geo,self.muni,self.ocm)


class FakeCursor:
    def __init__(self,connection):self.connection=connection;self.result=[]
    def __enter__(self):return self
    def __exit__(self,*a):return False
    def execute(self,sql,params=()):
        self.connection.executions.append((sql,params))
        if 'FROM api_v1.od_zonas WHERE zona_od_id=' in sql:
            self.result=[{'zona_od_id':1,'zona_nome':'Sé','municipio_od_id':36,
                          'tem_amostra_origem':True}]
        elif 'FROM api_v1.energia_inmetro WHERE inmetro_id=' in sql:
            self.result=[{'inmetro_id':'11','modalidade':'eletricidade','custo_energia_rs_km':0.1}]
        elif 'FROM api_v1.motorista_custos' in sql:
            self.result=[{'perfil_id':'proprio_base','inmetro_id':'11','resultado_economico_rs_mes':None}]
        elif 'ST_AsGeoJSON' in sql:
            self.result=[{'zona_od_id':1,'zona_nome':'Sé','municipio_od_id':36,
                          'geojson':'{"type":"Polygon","coordinates":[[[-47,-23],[-46,-23],[-46,-24],[-47,-23]]]}' }]
        elif 'FROM api_v1.carga_atual' in sql:
            self.result=[{'versao':'test','zonas_com_geometria':527}]
        elif 'SELECT 1' in sql:self.result=[{'ok':1}]
        else:self.result=[]
    def fetchall(self):return self.result

class FakeDB:
    def __init__(self):self.executions=[]
    def cursor(self):return FakeCursor(self)

class TestHTTP(unittest.TestCase):
    def setUp(self):
        self.db=FakeDB()
        app.dependency_overrides[get_connection]=lambda:self.db
        self.client=TestClient(app)
    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
    def test_health(self):
        self.assertEqual(self.client.get('/api/v1/health').json()['status'],'ok')
    def test_validacao_parametros(self):
        self.assertEqual(self.client.get('/api/v1/energia/cenarios?grupo=Invalido').status_code,422)
        self.assertEqual(self.client.get('/api/v1/mapa/zonas?municipio_od_id=36&limite=1000').status_code,422)
        self.assertEqual(self.client.get('/api/v1/od/municipios/12/distritos').status_code,404)
    def test_comparador_independente(self):
        r=self.client.get('/api/v1/comparador?zona_od_id=1&inmetro_id=11&modalidade=eletricidade&perfil_id=proprio_base')
        self.assertEqual(r.status_code,200)
        self.assertEqual(r.json()['vinculo_geografico_economico'],'INEXISTENTE_SEM_FONTE')
        self.assertIsNone(r.json()['cenario_motorista']['resultado_economico_rs_mes'])
        self.assertEqual(len(self.db.executions),3)
        self.assertFalse(any('JOIN api_v1.energia_inmetro' in sql and 'od_zonas' in sql for sql,p in self.db.executions))
    def test_sql_parametrizado(self):
        marker="a' OR 1=1 --"
        resp=self.client.get('/api/v1/motorista/custos',params={'perfil_id':marker})
        self.assertEqual(resp.status_code,200)
        sql,args=self.db.executions[-1]
        self.assertNotIn(marker,sql)
        self.assertIn(marker,args)
    def test_geojson_formatado(self):
        r=self.client.get('/api/v1/mapa/zonas/1')
        self.assertEqual(r.status_code,200)
        self.assertEqual(r.json()['type'],'FeatureCollection')
        self.assertEqual(r.json()['features'][0]['geometry']['type'],'Polygon')

if __name__=='__main__': unittest.main()
