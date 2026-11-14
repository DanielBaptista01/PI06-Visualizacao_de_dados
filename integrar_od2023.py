"""PI06 — Integração territorial e estatística da Pesquisa OD 2023 (Metrô-SP).

Base: dados_limpos/07_ORIGEM_DESTINO.csv filtrada MODOPRIN=12 pelo extrair_bases.py.
Dimensões: dados_referencia_od/dim_zonas_od2023.csv extraídas da correspondência
oficial 19/02/2025, com anomalia da zona 485 explicitada no manifesto.

Gera indicadores descritivos por zona/município/faixa horária, SEM atribuir
viagens reais da Uber, ganhos, distâncias viárias ou frota às zonas.
Geometrias opcionais via Zonas_2023.shp do pacote oficial do Metrô.
"""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import unicodedata
import pandas as pd

COLUNAS_MIN = {'ZONA_O','ZONA_D','FE_VIA','MODOPRIN'}
COLUNAS_OPCIONAIS=['MUNI_O','MUNI_D','H_SAIDA','DURACAO','DISTANCIA','DIA_SEM']
FAIXAS=('Madrugada (0-5)','Manhã (6-11)','Tarde (12-17)','Noite (18-23)','Hora desconhecida')

def sha256(path:Path)->str:
 h=hashlib.sha256()
 with path.open('rb') as f:
  for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
 return h.hexdigest()

def faixa_horaria(hour):
 if pd.isna(hour) or hour<0 or hour>23:return 'Hora desconhecida'
 hour=int(hour)
 if hour<6:return FAIXAS[0]
 if hour<12:return FAIXAS[1]
 if hour<18:return FAIXAS[2]
 return FAIXAS[3]

def ler_dimensoes(path:Path)->pd.DataFrame:
 if not path.is_file():raise FileNotFoundError(f'Dimensão OD não encontrada: {path}')
 z=pd.read_csv(path,encoding='utf-8-sig')
 obrig={'zona_od_id','zona_nome','municipio_od_id','municipio_nome','distrito_od_id','distrito_nome','area_hectares','escopo'}
 if obrig-set(z.columns):raise ValueError('Dimensão com colunas ausentes: '+str(obrig-set(z.columns)))
 if len(z)!=527 or z['zona_od_id'].nunique()!=527 or set(z['zona_od_id'])!=set(range(1,528)):
  raise ValueError('Dimensão oficial deve possuir 527 zonas únicas [1..527]')
 if z['municipio_od_id'].nunique()!=39 or z['municipio_od_id'].eq(36).sum()!=343:
  raise ValueError('Hierarquia OD deve conter 39 municípios e 343 zonas de São Paulo')
 if z[z.municipio_od_id==36].distrito_od_id.nunique()!=96:
  raise ValueError('Esperados 96 distritos na capital')
 if z['zona_nome'].isna().any() or z['municipio_nome'].isna().any():
  raise ValueError('Nomes de zona/município ausentes')
 return z

def ler_viagens(path:Path)->pd.DataFrame:
 if not path.is_file():raise FileNotFoundError(f'Viagens OD não encontradas: {path}. Rode extrair_bases.py / processar_od() antes.')
 if path.suffix.lower()=='.csv':
  return pd.read_csv(path,encoding='utf-8-sig',low_memory=False)
 if path.suffix.lower()=='.sav':
  import pyreadstat
  available=pyreadstat.read_sav(path,metadataonly=True)[1].column_names
  cols=list(COLUNAS_MIN.intersection(available)) + [c for c in COLUNAS_OPCIONAIS if c in available]
  return pyreadstat.read_sav(path,usecols=cols)[0]
 if path.suffix.lower()=='.dbf':
  import pyogrio
  return pyogrio.read_dataframe(path)
 raise ValueError('OD aceita .csv, .sav ou .dbf; extraia o ZIP oficial primeiro')

def preparar_viagens(df:pd.DataFrame,zonas:pd.DataFrame):
 faltam=COLUNAS_MIN-set(df.columns)
 if faltam:raise ValueError('Base OD sem campos essenciais: '+str(sorted(faltam)))
 d=df.copy()
 amostra_entrada=len(d)
 for col in ['MODOPRIN','FE_VIA','ZONA_O','ZONA_D','H_SAIDA','DURACAO','DISTANCIA','MUNI_O','MUNI_D']:
  if col in d.columns:d[col]=pd.to_numeric(d[col],errors='coerce')
 d=d[d['MODOPRIN']==12].copy()
 amostra_app=len(d)
 if amostra_app==0:raise ValueError('Nenhuma viagem com MODOPRIN=12. Verifique a fonte.')
 # Uma viagem deve ter fator de expansão positivo para compor estimativas.
 pesos_validos=d['FE_VIA'].notna() & d['FE_VIA'].gt(0) & (d['FE_VIA']<float('inf'))
 pesos_invalidos=int((~pesos_validos).sum())
 d=d[pesos_validos].copy()
 if d.empty:raise ValueError('Nenhuma viagem OD possui FE_VIA válido e positivo')
 zona_set=set(zonas['zona_od_id'])
 for tipo in ['O','D']:
  raw=d[f'ZONA_{tipo}']
  valida=raw.notna() & raw.eq(raw.round()) & raw.isin(zona_set)
  d[f'zona_{tipo.lower()}_valida']=valida
  d[f'zona_{tipo.lower()}_id']=raw.where(valida).astype('Int64')
  # Não atribuir município ao endereço externo/sem zona.
  lookup=zonas.set_index('zona_od_id')['municipio_od_id']
  d[f'municipio_{tipo.lower()}_od']=d[f'zona_{tipo.lower()}_id'].map(lookup)
  if f'MUNI_{tipo}' in d:
   m=d[f'MUNI_{tipo}']
   d[f'municipio_{tipo.lower()}_divergente']=(m.notna() & d[f'zona_{tipo.lower()}_valida'] & m.ne(d[f'municipio_{tipo.lower()}_od']))
  else:d[f'municipio_{tipo.lower()}_divergente']=False
 d['hora_saida']=d['H_SAIDA'] if 'H_SAIDA' in d else float('nan')
 d['faixa_horaria']=d['hora_saida'].map(faixa_horaria)
 # DISTANCIA É LINHA RETA EM METROS, não percurso viário percorrido pelo carro.
 if 'DISTANCIA' in d:
  d['dist_linha_reta_km']=(d['DISTANCIA']/1000).where(d['DISTANCIA'].ge(0))
 else:d['dist_linha_reta_km']=float('nan')
 if 'DURACAO' in d:
  d['duracao_min']=d['DURACAO'].where(d['DURACAO'].ge(0))
 else:d['duracao_min']=float('nan')
 qa={
  'linhas_entrada':amostra_entrada,'linhas_modo_12':amostra_app,
  'linhas_peso_invalido_excluidas':pesos_invalidos,'linhas_app_com_peso_valido':len(d),
  'viagens_expandidas_total_com_peso_valido':round(float(d['FE_VIA'].sum()),2),
  'origem_zona_valida':int(d.zona_o_valida.sum()),
  'destino_zona_valida':int(d.zona_d_valida.sum()),
  'ambas_zonas_validas':int((d.zona_o_valida & d.zona_d_valida).sum()),
  'divergencias_municipio_origem':int(d.municipio_o_divergente.sum()),
  'divergencias_municipio_destino':int(d.municipio_d_divergente.sum()),
  'hora_saida_ausente_ou_invalida':int(d.faixa_horaria.eq('Hora desconhecida').sum()),
  'observacao':'Modo 12 inclui táxi não convencional/aplicativo, não exclusivamente Uber',
 }
 return d,qa

def agregar(df:pd.DataFrame,cols:list[str])->pd.DataFrame:
 if df.empty:
  return pd.DataFrame(columns=cols+['viagens_amostra','viagens_expandidas','duracao_media_ponderada_min',
                                   'distancia_linha_reta_media_ponderada_km','amostra_com_distancia'])
 work=df.copy()
 w=work['FE_VIA'].astype(float)
 for col,src in [('duracao','duracao_min'),('distancia','dist_linha_reta_km')]:
  ok=work[src].notna()
  work[f'_w_{col}']=w.where(ok,0)
  work[f'_wx_{col}']=work[src].fillna(0)*work[f'_w_{col}']
 work['_amostra_distancia']=work['dist_linha_reta_km'].notna().astype(int)
 a=(work.groupby(cols,dropna=False,observed=True).agg(
  viagens_amostra=('FE_VIA','size'),
  viagens_expandidas=('FE_VIA','sum'),
  _w_duracao=('_w_duracao','sum'),_wx_duracao=('_wx_duracao','sum'),
  _w_distancia=('_w_distancia','sum'),_wx_distancia=('_wx_distancia','sum'),
  amostra_com_distancia=('_amostra_distancia','sum')
 ).reset_index())
 a['duracao_media_ponderada_min']=(a['_wx_duracao']/a['_w_duracao'].where(a['_w_duracao'].gt(0))).round(2)
 a['distancia_linha_reta_media_ponderada_km']=(a['_wx_distancia']/a['_w_distancia'].where(a['_w_distancia'].gt(0))).round(3)
 a['viagens_expandidas']=a['viagens_expandidas'].round(2)
 return a.drop(columns=['_w_duracao','_wx_duracao','_w_distancia','_wx_distancia'])

def salvar_geo(zonas:pd.DataFrame,shape:Path,out:Path,campo_zona:str|None=None):
    """Exporta geometrias OD, reparando topologia sem adulterar o SHP de origem.

    Shapely make_valid preserva a linha original na medida do possível; quando
    retornar GeometryCollection mantemos somente os componentes poligonais.
    A auditoria registra reparos e variações de área. Não atesta cobertura
    territorial sem sobreposições, nem substitui a validação cartográfica.
    """
    import geopandas as gpd
    from shapely import make_valid
    from shapely.geometry import Polygon, MultiPolygon, GeometryCollection
    from shapely.ops import unary_union
    from shapely.validation import explain_validity

    g = gpd.read_file(shape)
    if g.crs is None:
        raise ValueError('SHP sem CRS declarado (.prj): não é seguro gerar GeoJSON')

    def norm(s):
        return ''.join(c for c in unicodedata.normalize('NFKD', str(s))
                       if not unicodedata.combining(c)).lower().replace('_','').replace(' ','')

    candidatos = ([campo_zona] if campo_zona else
                  [c for c in g.columns if norm(c) in
                   {'numerozona','numzona','zona','zonaod','zonapesq','zonanum','zona2023','numzonaod'}])
    compativeis=[]
    for c in candidatos:
        if c not in g.columns:
            continue
        ids=pd.to_numeric(g[c],errors='coerce')
        if (ids.notna().all() and ids.eq(ids.round()).all() and
            set(ids.astype(int))==set(zonas.zona_od_id)):
            compativeis.append(c)
    if len(compativeis)!=1:
        raise ValueError('Coluna de zona OD não identificada unicamente. Colunas: '
                         +str(list(g.columns))+'. Informe --campo-zona.')

    key=compativeis[0]
    g['zona_od_id']=pd.to_numeric(g[key]).astype(int)
    if g.geometry.isna().any() or g.geometry.is_empty.any():
        ids=g.loc[g.geometry.isna()|g.geometry.is_empty,'zona_od_id'].tolist()
        raise ValueError(f'Geometrias ausentes/vazias nas zonas: {ids[:20]}')

    def apenas_poligonos(geom):
        if isinstance(geom, (Polygon,MultiPolygon)):
            return geom
        if isinstance(geom, GeometryCollection):
            partes=[]
            for parte in geom.geoms:
                pol=apenas_poligonos(parte)
                if pol is not None and not pol.is_empty:
                    partes.append(pol)
            return unary_union(partes) if partes else None
        return None

    def reparar_poligono(geom, zona, fase):
        """Corrige somente inválidos e recusa geometria não-poligonal."""
        if geom is None or geom.is_empty:
            raise ValueError(f'Zona {zona} ({fase}): geometria vazia')
        if geom.is_valid and isinstance(geom,(Polygon,MultiPolygon)):
            return geom, None
        motivo=explain_validity(geom)
        original_tipo=geom.geom_type
        antes=geom.area
        try:
            reparado=apenas_poligonos(make_valid(geom))
        except Exception as exc:
            raise ValueError(f'Zona {zona} ({fase}): falha em make_valid: {motivo}') from exc
        if (reparado is None or reparado.is_empty or
                not reparado.is_valid or reparado.area<=0):
            raise ValueError(f'Zona {zona} ({fase}): reparo sem polígono válido; motivo={motivo}; '
                             'requer inspeção no QGIS')
        depois=reparado.area
        # Percentual relativo à maior área: funciona também para anéis com área zero.
        delta_pct=round(100*abs(depois-antes)/max(abs(antes),abs(depois)),5)
        retorno={'zona_od_id':int(zona),'fase':fase,'motivo_original':motivo,
                 'tipo_original':original_tipo,'tipo_corrigido':reparado.geom_type,
                 'crs_da_fase':'EPSG:4326' if fase in ('apos_reprojecao_epsg4326','municipio_derivado') else str(g.crs),
                 'area_original_unidade_crs2':float(f'{antes:.12g}'),
                 'area_corrigida_unidade_crs2':float(f'{depois:.12g}'),
                 'diferenca_area_pct':delta_pct,
                 'revisao_area_recomendada':bool(delta_pct>5),
                 'metodo':'shapely.make_valid + extracao_poligonal'}
        return reparado, retorno

    # Reparar ANTES da dissolução: dissolve pode falhar ao unir anéis inválidos.
    auditoria=[]
    novas=[]
    for zona,geom in zip(g['zona_od_id'],g.geometry):
        corrigido,evento=reparar_poligono(geom,zona,'arquivo_original')
        novas.append(corrigido)
        if evento is not None:
            auditoria.append(evento)
    g=g[['zona_od_id','geometry']].copy()
    g['geometry']=gpd.GeoSeries(novas,index=g.index,crs=g.crs)
    if g.zona_od_id.duplicated().any():
        g=g.dissolve(by='zona_od_id',as_index=False)

    # Reparo pós-união, caso polígonos agrupados tenham problemas de topologia.
    novas=[]
    for zona,geom in zip(g['zona_od_id'],g.geometry):
        corrigido,evento=reparar_poligono(geom,zona,'apos_dissolucao')
        novas.append(corrigido)
        if evento is not None:
            auditoria.append(evento)
    g['geometry']=gpd.GeoSeries(novas,index=g.index,crs=g.crs)

    if len(g)!=527 or set(g.zona_od_id)!=set(zonas.zona_od_id):
        raise ValueError('SHP não corresponde às 527 zonas OD. '
                         f'Encontradas: {len(g)}')
    if g.geometry.isna().any() or g.geometry.is_empty.any() or not g.geometry.is_valid.all():
        raise ValueError('Falha na validação final: ainda há polígonos inválidos')

    g=g.merge(zonas,on='zona_od_id',validate='one_to_one')
    g=gpd.GeoDataFrame(g,geometry='geometry',crs=g.crs).to_crs(epsg=4326)
    # IMPORTANTE: uma geometria válida no CRS de origem pode se tornar inválida
    # ao transformar as coordenadas (precisão numérica/topologia dos anéis).
    # Reparar novamente, neste CRS, antes de dissolver e exportar GeoJSON.
    novas_4326=[]
    for zona,geom in zip(g['zona_od_id'],g.geometry):
        corrigido,evento=reparar_poligono(geom,zona,'apos_reprojecao_epsg4326')
        novas_4326.append(corrigido)
        if evento is not None:
            auditoria.append(evento)
    g['geometry']=gpd.GeoSeries(novas_4326,index=g.index,crs=g.crs)
    geometrias_ok=(g.geometry.notna().all() and
                   not g.geometry.is_empty.any() and
                   g.geometry.is_valid.all() and
                   g.geometry.geom_type.isin(['Polygon','MultiPolygon']).all())
    if not geometrias_ok:
        ids=g.loc[(g.geometry.isna()|g.geometry.is_empty|~g.geometry.is_valid),
                  'zona_od_id'].tolist()
        raise ValueError(f'Geometrias inválidas mesmo após reparo EPSG:4326: {ids[:20]}')

    mun=g[['municipio_od_id','municipio_nome','geometry']].dissolve(
        by=['municipio_od_id','municipio_nome'],as_index=False)
    # O dissolve das zonas pode gerar geometrias inválidas; corrigir a malha derivada.
    novas_m=[]
    for municipio,geom in zip(mun['municipio_od_id'],mun.geometry):
        corrigido,evento=reparar_poligono(geom,municipio,'municipio_derivado')
        novas_m.append(corrigido)
        if evento is not None:
            auditoria.append(evento)
    mun['geometry']=gpd.GeoSeries(novas_m,index=mun.index,crs=mun.crs)
    if len(mun)!=39 or not mun.geometry.is_valid.all():
        raise ValueError('Municípios OD derivados: contagem/topologia inválida')

    # Só exporta GeoJSONs após validação de todas as camadas.
    g.to_file(out/'geo_zonas_od2023_rmsp.geojson',driver='GeoJSON')
    g[g.municipio_od_id==36].to_file(out/'geo_zonas_od2023_capital.geojson',driver='GeoJSON')
    mun.to_file(out/'geo_municipios_derivados_zonas_od2023.geojson',driver='GeoJSON')

    colunas=['zona_od_id','fase','motivo_original','tipo_original',
             'tipo_corrigido','crs_da_fase','area_original_unidade_crs2',
             'area_corrigida_unidade_crs2','diferenca_area_pct',
             'revisao_area_recomendada','metodo']
    pd.DataFrame(auditoria,columns=colunas).to_csv(
        out/'auditoria_geometrias_od2023.csv',index=False,encoding='utf-8-sig')
    return {
        'campo_zona_shape':key,
        'zonas_geometria':len(g),
        'municipios_geom_derivada':len(mun),
        'zonas_originalmente_invalidas':len(set(x['zona_od_id'] for x in auditoria
                                                 if x['fase']=='arquivo_original')),
        'reparos_apos_reprojecao_epsg4326':sum(
            x['fase']=='apos_reprojecao_epsg4326' for x in auditoria),
        'ids_reparados_apos_reprojecao_epsg4326':sorted(set(
            int(x['zona_od_id']) for x in auditoria
            if x['fase']=='apos_reprojecao_epsg4326')),
        'reparos_totais_incluindo_municipios':len(auditoria),
        'reparos_com_variacao_area_maior_5pct':sum(
            x['revisao_area_recomendada'] for x in auditoria),
        'ids_com_revisao_area_recomendada':sorted(set(
            int(x['zona_od_id']) for x in auditoria
            if x['revisao_area_recomendada'] and x['fase']!='municipio_derivado')),
        'auditoria':'auditoria_geometrias_od2023.csv',
        'aviso':('Reparos registrados com shapely.make_valid, sem alterar SHP RAW. '
                 'Limites municipais derivados por dissolve das zonas OD; '
                 'não substituem malha municipal legal. Áreas usam unidades '
                 'do CRS de cada fase (origem ou EPSG:4326); comparar somente '
                 'antes/depois dentro da mesma fase. Diferenças >5% exigem '
                 'revisão cartográfica.')
    }

def executar(entrada:Path,dim:Path,saida:Path,shape:Path|None=None,campo_zona:str|None=None,sobrescrever=False):
 zonas=ler_dimensoes(dim)
 viagem=ler_viagens(entrada)
 d,qa=preparar_viagens(viagem,zonas)
 filenames=['dim_zonas_od2023.csv','dim_municipios_od2023.csv','dim_distritos_sp_od2023.csv',
            'fato_od_origens_zona_faixa.csv','fato_od_destinos_zona_faixa.csv',
            'fato_od_fluxos_zona_faixa.csv','fato_od_municipios_origem_faixa.csv',
            'indicadores_zonas_od2023.csv','resumo_territorial_od2023.json']
 if shape:
  filenames+=['geo_zonas_od2023_rmsp.geojson','geo_zonas_od2023_capital.geojson','geo_municipios_derivados_zonas_od2023.geojson','auditoria_geometrias_od2023.csv']
 if not sobrescrever and any((saida/n).exists() for n in filenames):
  raise FileExistsError('Saídas já existem em '+str(saida)+'; use --sobrescrever apenas se quiser recalcular')
 saida.mkdir(parents=True,exist_ok=True)
 for f in ['dim_zonas_od2023.csv','dim_municipios_od2023.csv','dim_distritos_sp_od2023.csv']:
  from shutil import copyfile
  copyfile(dim.parent/f,saida/f)
 orig=d[d.zona_o_valida].copy(); orig['zona_od_id']=orig['zona_o_id'].astype(int)
 dest=d[d.zona_d_valida].copy(); dest['zona_od_id']=dest['zona_d_id'].astype(int)
 flux=d[d.zona_o_valida & d.zona_d_valida].copy()
 flux['zona_origem_id']=flux['zona_o_id'].astype(int);flux['zona_destino_id']=flux['zona_d_id'].astype(int)
 o=agregar(orig,['zona_od_id','faixa_horaria'])
 p=agregar(dest,['zona_od_id','faixa_horaria'])
 f=agregar(flux,['zona_origem_id','zona_destino_id','faixa_horaria'])
 m=agregar(orig,['municipio_o_od','faixa_horaria']).rename(columns={'municipio_o_od':'municipio_od_id'})
 o.to_csv(saida/'fato_od_origens_zona_faixa.csv',index=False,encoding='utf-8-sig')
 p.to_csv(saida/'fato_od_destinos_zona_faixa.csv',index=False,encoding='utf-8-sig')
 f.to_csv(saida/'fato_od_fluxos_zona_faixa.csv',index=False,encoding='utf-8-sig')
 m.to_csv(saida/'fato_od_municipios_origem_faixa.csv',index=False,encoding='utf-8-sig')
 sumo=o.groupby('zona_od_id',as_index=False).agg(
  viagens_origem_amostra=('viagens_amostra','sum'),viagens_origem_expandidas=('viagens_expandidas','sum'))
 sumd=p.groupby('zona_od_id',as_index=False).agg(
  viagens_destino_amostra=('viagens_amostra','sum'),viagens_destino_expandidas=('viagens_expandidas','sum'))
 ind=zonas.merge(sumo,on='zona_od_id',how='left',validate='one_to_one').merge(sumd,on='zona_od_id',how='left',validate='one_to_one')
 # Sem registro amostral não implica inexistência de viagens. Não preencher como zero.
 ind['tem_amostra_origem']=ind['viagens_origem_amostra'].notna()
 ind['tem_amostra_destino']=ind['viagens_destino_amostra'].notna()
 ind.to_csv(saida/'indicadores_zonas_od2023.csv',index=False,encoding='utf-8-sig')
 shape_report=None
 if shape:
  if not shape.is_file():raise FileNotFoundError('Shape não encontrado: '+str(shape))
  shape_report=salvar_geo(zonas,shape,saida,campo_zona)
 report={'executado_em_utc':datetime.now(timezone.utc).isoformat(timespec='seconds'),
         'fonte_microdados':str(entrada),'sha256_microdados':sha256(entrada),
         'fonte_zonas':str(dim),'sha256_zonas':sha256(dim),
         'zonas_catalogadas':len(zonas),'municipios':39,'zonas_capital':343,'distritos_capital':96,
         'origens_grupos':len(o),'destinos_grupos':len(p),'fluxos_grupos':len(f),
         'zonas_com_amostra_origem':int(ind.tem_amostra_origem.sum()),
         'zonas_com_amostra_destino':int(ind.tem_amostra_destino.sum()),
         'viagens':qa,'geometrias':shape_report,
         'restricoes':[
           'OD MODO 12 = táxi não convencional / aplicativo, NÃO viagens exclusivas Uber',
           'FE_VIA é fator de expansão de viagens, não motorista nem corrida observada',
           'DISTANCIA é linha reta em metros, NÃO quilômetros rodados pelo carro',
           'Não inferir receita, custos ou participação de frota por Zona OD',
           'Zonas sem amostra permanecem sem indicadores de demanda, não zero verdadeiro',
           'Os valores são descritivos da OD 2023, não da operação em 2026',
         ],'arquivos_gerados':filenames}
 (saida/'resumo_territorial_od2023.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print(json.dumps(report,ensure_ascii=False,indent=2))
 return report

if __name__=='__main__':
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--entrada',type=Path,default=Path('dados_limpos/07_ORIGEM_DESTINO.csv'))
 parser.add_argument('--dim',type=Path,default=Path('dados_referencia_od/dim_zonas_od2023.csv'))
 parser.add_argument('--saida',type=Path,default=Path('dados_relatorios/territorio_od2023'))
 parser.add_argument('--shape',type=Path,help='Zonas_2023.shp do pacote oficial, opcional')
 parser.add_argument('--campo-zona',type=str,help='Nome da coluna da zona no shapefile, se necessário')
 parser.add_argument('--sobrescrever',action='store_true',help='Refazer somente os arquivos derivados')
 args=parser.parse_args()
 executar(args.entrada,args.dim,args.saida,args.shape,args.campo_zona,args.sobrescrever)
