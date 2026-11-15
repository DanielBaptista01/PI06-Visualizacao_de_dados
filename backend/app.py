"""API de leitura PI06 v1 (FastAPI + PostgreSQL/PostGIS).

Executar a partir da raiz: python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
Swagger: http://127.0.0.1:8000/docs
Nenhuma credencial de PostgreSQL é enviada ao navegador.
"""
from __future__ import annotations
import json
import os
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query
from dotenv import load_dotenv
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

load_dotenv()

# Sem coringa: o navegador só poderá acessar a partir das origens configuradas.
origins=[x.strip() for x in os.getenv('PI06_CORS_ORIGINS','').split(',') if x.strip()]
app=FastAPI(title='PI06 — backend analítico v1',version='1.0.0',
 description='OD 2023 (táxi não convencional/aplicativo), tecnologia de veículos e simulações econômicas. Não estima lucro observado por zona.')
if origins:
    app.add_middleware(CORSMiddleware,allow_origins=origins,
                       allow_methods=['GET'],allow_headers=['Content-Type'],allow_credentials=False)

LIMIT=Annotated[int,Query(ge=1,le=100)]
OFFSET=Annotated[int,Query(ge=0,le=100000)]
ZONA=Annotated[int,Query(ge=1,le=527)]
GRUPOS=['Gasolina','Híbrido','Elétrico','Não classificado']
DISCLAIMER_OD='Pesquisa OD 2023, MODOPRIN=12 (táxi não convencional/aplicativo). Não é base exclusiva da Uber. FE_VIA expande viagens, não motoristas.'
DISCLAIMER_ECO='Simulação independente da zona OD. Preço/consumo não comprovam vínculo FIPE–INMETRO nem elegibilidade Uber. Resultado somente com todos os custos preenchidos.'


def get_connection():
    """Gerador de conexão por requisição. Use credencial do papel de leitura em produção."""
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError:
        raise HTTPException(503,'Dependência psycopg não instalada no servidor')
    dsn=os.getenv('PI06_API_DATABASE_URL') or os.getenv('DATABASE_URL')
    if not dsn:
        raise HTTPException(503,'Banco não configurado no servidor')
    try:
        conn=psycopg.connect(dsn,row_factory=dict_row,autocommit=True,
                              options='-c search_path=public,extensions -c default_transaction_read_only=on -c statement_timeout=5000')
    except Exception:
        raise HTTPException(503,'Banco indisponível')
    try:
        yield conn
    finally:
        conn.close()


def _rows(conn,sql,params=()):
    with conn.cursor() as cur:
        cur.execute(sql,params)
        return [dict(row) for row in cur.fetchall()]


def _first(conn,sql,params=()):
    rows=_rows(conn,sql,params)
    return rows[0] if rows else None


def _response(data):
    return JSONResponse(content=jsonable_encoder(data))


def _filter_allowed(grupo):
    if grupo and grupo not in GRUPOS:
        raise HTTPException(422,detail='grupo deve ser Gasolina, Híbrido, Elétrico ou Não classificado')


def _feature_collection(rows,idfield,extra=None):
    features=[]
    for row in rows:
        geom=row.pop('geojson',None)
        if not geom: continue
        features.append({'type':'Feature','id':row[idfield],
                         'properties':row,'geometry':json.loads(geom)})
    return {'type':'FeatureCollection','features':features,'metadados':extra or {}}


@app.get('/api/v1/health')
def health(conn=Depends(get_connection)):
    _first(conn,'SELECT 1 AS ok')
    return {'status':'ok','servico':'pi06-backend-v1'}


@app.get('/api/v1/meta')
def meta(conn=Depends(get_connection)):
    registro=_first(conn,'SELECT * FROM api_v1.carga_atual WHERE id=1')
    if not registro: raise HTTPException(503,'Snapshot analítico ainda não carregado')
    return _response({'carga':registro,
      'cenarios':['mobilidade_od','fluxos_od','energia_veiculos','economia_motorista','recarga','comparacao_independente'],
      'fontes':{'od':'Metrô OD 2023 (MODOPRIN=12)','energia':'INMETRO + ANP/ANEEL 2026',
                'motorista':'Premissas referenciais e hipóteses','recarga':'Open Charge Map (snapshot)'},
      'restricoes':[DISCLAIMER_OD,DISCLAIMER_ECO,'Distância OD é linha reta, não km viário',
                   'Pontos Open Charge Map não representam disponibilidade em tempo real']})


@app.get('/api/v1/od/municipios')
def municipios(conn=Depends(get_connection)):
    rows=_rows(conn,'SELECT * FROM api_v1.od_municipios ORDER BY municipio_nome')
    return _response({'itens':rows,'total':len(rows),'aviso':DISCLAIMER_OD})


@app.get('/api/v1/od/municipios/{municipio_od_id}/zonas')
def municipio_zonas(municipio_od_id:int,limite:LIMIT=100,offset:OFFSET=0,conn=Depends(get_connection)):
    if not(1<=municipio_od_id<=39):raise HTTPException(422,'Município OD fora de 1–39')
    rows=_rows(conn,'''SELECT * FROM api_v1.od_zonas WHERE municipio_od_id=%s
                  ORDER BY zona_od_id LIMIT %s OFFSET %s''',(municipio_od_id,limite,offset))
    return _response({'itens':rows,'limite':limite,'offset':offset,'aviso':DISCLAIMER_OD})


@app.get('/api/v1/od/municipios/{municipio_od_id}/distritos')
def distritos(municipio_od_id:int,conn=Depends(get_connection)):
    if municipio_od_id!=36:raise HTTPException(404,'Distritos OD detalhados apenas para município de São Paulo (ID 36)')
    rows=_rows(conn,'SELECT * FROM api_v1.od_distritos_capital ORDER BY distrito_nome')
    return _response({'itens':rows,'total':len(rows),'aviso':DISCLAIMER_OD})


@app.get('/api/v1/od/zonas/{zona_od_id}')
def zona(zona_od_id:int,conn=Depends(get_connection)):
    if not(1<=zona_od_id<=527):raise HTTPException(422,'Zona OD fora de 1–527')
    z=_first(conn,'SELECT * FROM api_v1.od_zonas WHERE zona_od_id=%s',(zona_od_id,))
    if not z: raise HTTPException(404,'Zona OD inexistente')
    return _response({'territorio':z,'aviso':DISCLAIMER_OD})


@app.get('/api/v1/od/zonas/{zona_od_id}/destinos')
def destinos(zona_od_id:int,faixa_horaria:str|None=None,limite:LIMIT=20,conn=Depends(get_connection)):
    if not(1<=zona_od_id<=527):raise HTTPException(422,'Zona OD fora de 1–527')
    if faixa_horaria:
        sql='''SELECT * FROM api_v1.od_top_destinos
               WHERE zona_origem_id=%s AND faixa_horaria=%s ORDER BY posicao LIMIT %s'''
        p=(zona_od_id,faixa_horaria,limite)
    else:
        sql='''SELECT * FROM api_v1.od_top_destinos WHERE zona_origem_id=%s
               ORDER BY faixa_horaria,posicao LIMIT %s'''
        p=(zona_od_id,limite)
    return _response({'itens':_rows(conn,sql,p),'aviso':'DISTANCIA é linha reta. '+DISCLAIMER_OD})


@app.get('/api/v1/mapa/municipios')
def mapa_municipios(conn=Depends(get_connection)):
    rows=_rows(conn,'''SELECT m.municipio_od_id,m.municipio_nome,m.qtd_zonas,
            ST_AsGeoJSON(g.geom,6) AS geojson FROM api_v1.od_municipios m
            JOIN api_v1.municipios_geometrias g USING(municipio_od_id)
            ORDER BY m.municipio_od_id''')
    return _response(_feature_collection(rows,'municipio_od_id',
        {'origem_geometria':'Dissolve das zonas OD, não malha legal dos municípios','periodo':'2023'}))


@app.get('/api/v1/mapa/zonas')
def mapa_zonas(municipio_od_id:int=Query(ge=1,le=39),limite:int=Query(30,ge=1,le=50),
               offset:OFFSET=0,conn=Depends(get_connection)):
    rows=_rows(conn,'''SELECT z.zona_od_id,z.zona_nome,z.municipio_od_id,z.distrito_nome,
                z.viagens_origem_expandidas,z.tem_amostra_origem,
                ST_AsGeoJSON(g.geom,6) AS geojson
                FROM api_v1.od_zonas z JOIN api_v1.zonas_geometrias g USING(zona_od_id)
                WHERE z.municipio_od_id=%s ORDER BY z.zona_od_id LIMIT %s OFFSET %s''',
               (municipio_od_id,limite,offset))
    return _response(_feature_collection(rows,'zona_od_id',{'limit':limite,'offset':offset,
             'aviso':'Sem amostra não equivale a zero deslocamentos. '+DISCLAIMER_OD}))


@app.get('/api/v1/mapa/zonas/{zona_od_id}')
def mapa_zona(zona_od_id:int,conn=Depends(get_connection)):
    if not(1<=zona_od_id<=527):raise HTTPException(422,'Zona OD fora de 1–527')
    rows=_rows(conn,'''SELECT z.zona_od_id,z.zona_nome,z.municipio_od_id,
                ST_AsGeoJSON(g.geom,6) AS geojson
                FROM api_v1.od_zonas z JOIN api_v1.zonas_geometrias g USING(zona_od_id)
                WHERE z.zona_od_id=%s''',(zona_od_id,))
    if not rows: raise HTTPException(404,'Geometria ausente')
    return _response(_feature_collection(rows,'zona_od_id',{'periodo':'2023'}))


@app.get('/api/v1/energia/cenarios')
def energia(grupo:str|None=None,modalidade:str|None=None,
            limite:LIMIT=30,offset:OFFSET=0,conn=Depends(get_connection)):
    _filter_allowed(grupo)
    sql='''SELECT * FROM api_v1.energia_inmetro WHERE (%s::text IS NULL OR grupo_interface=%s)
           AND (%s::text IS NULL OR modalidade=%s) ORDER BY custo_energia_rs_km,inmetro_id,modalidade
           LIMIT %s OFFSET %s'''
    rows=_rows(conn,sql,(grupo,grupo,modalidade,modalidade,limite,offset))
    return _response({'itens':rows,'limite':limite,'offset':offset,'aviso':DISCLAIMER_ECO})


@app.get('/api/v1/motorista/custos')
def motorista(perfil_id:str|None=None,grupo:str|None=None,status:str|None=None,
              limite:LIMIT=30,offset:OFFSET=0,conn=Depends(get_connection)):
    _filter_allowed(grupo)
    if status and status not in ('COMPLETO_CENARIO','PARCIAL_PENDENTE'):
        raise HTTPException(422,'Status desconhecido')
    sql='''SELECT * FROM api_v1.motorista_custos
           WHERE (%s::text IS NULL OR perfil_id=%s) AND (%s::text IS NULL OR grupo_interface=%s)
             AND (%s::text IS NULL OR status=%s)
           ORDER BY perfil_id,inmetro_id,modalidade LIMIT %s OFFSET %s'''
    rows=_rows(conn,sql,(perfil_id,perfil_id,grupo,grupo,status,status,limite,offset))
    return _response({'itens':rows,'limite':limite,'offset':offset,'aviso':DISCLAIMER_ECO})


@app.get('/api/v1/motorista/sensibilidade')
def sensibilidade(perfil_id:str|None=None,cenario_receita_id:str|None=None,grupo:str|None=None,
                  limite:LIMIT=30,offset:OFFSET=0,conn=Depends(get_connection)):
    _filter_allowed(grupo)
    sql='''SELECT * FROM api_v1.sensibilidade_receita
           WHERE (%s::text IS NULL OR perfil_id=%s)
             AND (%s::text IS NULL OR cenario_receita_id=%s)
             AND (%s::text IS NULL OR grupo_interface=%s)
           ORDER BY perfil_id,inmetro_id,modalidade,cenario_receita_id LIMIT %s OFFSET %s'''
    rows=_rows(conn,sql,(perfil_id,perfil_id,cenario_receita_id,cenario_receita_id,grupo,grupo,limite,offset))
    return _response({'itens':rows,'limite':limite,'offset':offset,
       'aviso':'Receitas didáticas, nunca renda observada; resultado NULL quando custo incompleto. '+DISCLAIMER_ECO})


@app.get('/api/v1/premissas/receita')
def premissas(conn=Depends(get_connection)):
    rows=_rows(conn,'SELECT * FROM api_v1.premissas_receita ORDER BY receita_apos_plataforma_rs_mes')
    return _response({'itens':rows,'aviso':'Hipóteses didáticas, sem receita observada.'})


@app.get('/api/v1/recarga/pontos')
def pontos(zona_od_id:int|None=Query(default=None,ge=1,le=527),status:str|None=None,
           limite:LIMIT=50,offset:OFFSET=0,conn=Depends(get_connection)):
    sql='''SELECT p.id_posto,p.titulo,p.operadora,p.cidade,p.latitude,p.longitude,
                  p.potencia_max_kw,p.qtd_conexoes,p.tipos_conectores,p.status_cadastral,
                  p.data_coleta,p.fonte_url,r.zona_od_id,r.situacao
           FROM api_v1.recarga_pontos p JOIN api_v1.recarga_zonas r USING(id_posto)
           WHERE (%s::integer IS NULL OR r.zona_od_id=%s)
             AND (%s::text IS NULL OR p.status_cadastral=%s)
           ORDER BY p.id_posto LIMIT %s OFFSET %s'''
    rows=_rows(conn,sql,(zona_od_id,zona_od_id,status,status,limite,offset))
    return _response({'itens':rows,'limite':limite,'offset':offset,
            'aviso':'Snapshot Open Charge Map; status cadastral não garante disponibilidade instantânea. Associações ambíguas não recebem zona.'})


@app.get('/api/v1/recarga/zonas/{zona_od_id}/resumo')
def pontos_por_zona(zona_od_id:int,conn=Depends(get_connection)):
    if not(1<=zona_od_id<=527):raise HTTPException(422,'Zona OD fora de 1–527')
    rows=_rows(conn,'''SELECT p.status_cadastral,COUNT(*)::integer AS pontos_cadastrados
            FROM api_v1.recarga_zonas r JOIN api_v1.recarga_pontos p USING(id_posto)
            WHERE r.zona_od_id=%s AND r.situacao='ZONA_UNICA'
            GROUP BY p.status_cadastral ORDER BY pontos_cadastrados DESC''',(zona_od_id,))
    return _response({'zona_od_id':zona_od_id,'itens':rows,
      'aviso':'Contagem de pontos cadastrados na data de coleta, não disponibilidade em tempo real.'})


@app.get('/api/v1/comparador')
def comparador(zona_od_id:int=Query(ge=1,le=527),inmetro_id:str=Query(min_length=1,max_length=60),
               modalidade:str=Query(min_length=1,max_length=40),perfil_id:str|None=None,
               conn=Depends(get_connection)):
    # NÃO há join territorial × INMETRO. Consultas distintas e comparativo explicitamente genérico.
    territorio=_first(conn,'SELECT * FROM api_v1.od_zonas WHERE zona_od_id=%s',(zona_od_id,))
    if not territorio: raise HTTPException(404,'Zona OD inexistente')
    energia_row=_first(conn,'SELECT * FROM api_v1.energia_inmetro WHERE inmetro_id=%s AND modalidade=%s',
                       (inmetro_id,modalidade))
    if not energia_row: raise HTTPException(404,'Cenário energético inexistente')
    cost=None
    if perfil_id:
        cost=_first(conn,'''SELECT * FROM api_v1.motorista_custos
                WHERE perfil_id=%s AND inmetro_id=%s AND modalidade=%s''',(perfil_id,inmetro_id,modalidade))
    return _response({'territorio_od':territorio,'cenario_energia':energia_row,
      'cenario_motorista':cost,'vinculo_geografico_economico':'INEXISTENTE_SEM_FONTE',
      'aviso':DISCLAIMER_OD+' '+DISCLAIMER_ECO})
