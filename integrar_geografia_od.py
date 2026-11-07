"""PI06: integrar Zonas OD 2023, distritos da pesquisa, regiões oficiais e eletropostos.

Leitura não destrutiva. Saídas novas por execução, sem publicar automaticamente.
Requer geopandas, shapely, pyogrio, pandas (e openpyxl somente para outras etapas).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely import make_valid
from shapely.geometry import MultiPolygon, Polygon, GeometryCollection
from shapely.validation import explain_validity

METRIC_CRS = 'EPSG:31983'  # SIRGAS 2000 / UTM 23S, adequado ao município de SP
REQUIRED_SIDECARS = ('.shp', '.dbf', '.shx', '.prj')
OUTPUT_DIR = 'dados_geograficos/execucoes'


def key(text: object) -> str:
    value = unicodedata.normalize('NFKD', str(text)).encode('ascii', 'ignore').decode('ascii')
    return re.sub(r'[^A-Z0-9]+', '', value.upper())


def choose_column(columns, names: tuple[str, ...], label: str, *, required: bool = True) -> str | None:
    """Detecta somente equivalência exata normalizada; falha em ambiguidades."""
    options = {key(name) for name in names}
    matches = [c for c in columns if key(c) in options]
    if len(matches) > 1:
        raise ValueError(f'{label}: colunas ambíguas {matches}. Informe coluna explicitamente.')
    if not matches and required:
        raise ValueError(f'{label}: coluna não identificada; disponíveis: {list(columns)}')
    return matches[0] if matches else None


def shapefile(root: Path, base: str) -> Path:
    options = list(root.rglob(base + '.shp'))
    if len(options) != 1:
        raise FileNotFoundError(f'Esperado exatamente um {base}.shp sob {root}; encontrados: {options}')
    result = options[0]
    missing = [e for e in REQUIRED_SIDECARS if not result.with_suffix(e).is_file()]
    if missing:
        raise FileNotFoundError(f'{result.name}: arquivos auxiliares ausentes: {missing}. Sincronize pasta Shape completa.')
    return result


def _apenas_poligonos(geometria):
    """Extrai apenas componentes poligonais do resultado de make_valid."""
    if isinstance(geometria, (Polygon, MultiPolygon)):
        return geometria
    if isinstance(geometria, GeometryCollection):
        partes = []
        for item in geometria.geoms:
            extraido = _apenas_poligonos(item)
            if extraido is None:
                continue
            if isinstance(extraido, Polygon):
                partes.append(extraido)
            else:
                partes.extend(extraido.geoms)
        if not partes:
            return None
        return MultiPolygon(partes) if len(partes) > 1 else partes[0]
    return None


def read_geo(
    path: Path,
    label: str,
    *,
    reparar: bool = False,
    limite_area_pct: float = 1.0,
    auditoria: list[dict] | None = None,
    diagnosticar: bool = False,
) -> gpd.GeoDataFrame:
    """Lê a camada e opcionalmente repara topologia em memória.

    Não modifica arquivos originais. Bloqueia reparos com alteração de área
    acima do limite informado, em CRS métrico, para revisão manual.
    """
    frame = gpd.read_file(path)
    if frame.empty or frame.crs is None:
        raise ValueError(f'{label}: camada vazia ou sem CRS declarado: {path}')
    if frame.geometry.isna().any() or frame.geometry.is_empty.any():
        raise ValueError(f'{label}: geometria nula/vazia. Verifique o RAW.')
    if not frame.geometry.geom_type.isin(['Polygon', 'MultiPolygon']).all():
        raise ValueError(f'{label}: a camada precisa conter polígonos.')
    invalidos = frame.index[~frame.geometry.is_valid].tolist()
    print(f'{label}: {len(frame)} geometrias; {len(invalidos)} inválidas (antes do reparo).')
    if invalidos:
        exemplos = [(str(i), explain_validity(frame.at[i, frame.geometry.name])) for i in invalidos[:5]]
        print(f'{label}: motivos (amostra até 5): {exemplos}')
    if diagnosticar:
        return frame
    if invalidos and not reparar:
        raise ValueError(
            f'{label}: contém {len(invalidos)} geometrias inválidas. '
            'Execute com --reparar-geometrias para correção auditada em memória.'
        )
    if not invalidos:
        return frame
    if not 0 <= limite_area_pct <= 100:
        raise ValueError('--limite-alteracao-area-pct deve estar entre 0 e 100')

    original = frame.copy()
    # Mede em metros quadrados; a geometria inválida é medida apenas para
    # diagnóstico da magnitude do reparo, não para inferência estatística.
    original_metrico = original.to_crs(METRIC_CRS)
    reparados = frame.geometry.copy()
    for idx in invalidos:
        anterior = frame.at[idx, frame.geometry.name]
        corrigida = _apenas_poligonos(make_valid(anterior))
        if corrigida is None or corrigida.is_empty or not corrigida.is_valid:
            raise ValueError(f'{label}: reparo falhou para índice {idx}')
        reparados.at[idx] = corrigida
    frame = frame.set_geometry(reparados)
    if (~frame.geometry.is_valid).any() or frame.geometry.is_empty.any():
        raise ValueError(f'{label}: ainda há geometrias inválidas após reparo')
    novo_metrico = frame.to_crs(METRIC_CRS)
    for idx in invalidos:
        area_antes = float(original_metrico.loc[idx].geometry.area)
        area_depois = float(novo_metrico.loc[idx].geometry.area)
        delta_pct = abs(area_depois-area_antes)/area_antes*100 if area_antes>0 else float('inf')
        detalhe = {
            'camada':label,
            'indice_registro':str(idx),
            'problema_original':explain_validity(original.loc[idx].geometry),
            'area_original_m2':round(area_antes,4),
            'area_reparada_m2':round(area_depois,4),
            'variacao_area_pct':round(delta_pct,6),
            'metodo':'shapely.make_valid; somente componentes poligonais',
        }
        if auditoria is not None:
            auditoria.append(detalhe)
        if area_depois <= 0 or delta_pct > limite_area_pct:
            raise ValueError(
                f'{label}: índice {idx} mudou {delta_pct:.3f}% da área '
                f'(limite {limite_area_pct:.2f}%). Requer revisão manual; RAW preservado.'
            )
    print(f'{label}: {len(invalidos)} geometrias reparadas em memória e auditadas.')
    return frame


def export_csv(frame: pd.DataFrame, path: Path) -> None:
    frame.to_csv(path, index=False, encoding='utf-8-sig')


def identify_zone_id(zonas: gpd.GeoDataFrame, explicit: str | None) -> str:
    if explicit:
        if explicit not in zonas.columns:
            raise ValueError(f'Coluna de identificação {explicit!r} não encontrada: {list(zonas.columns)}')
        col = explicit
    else:
        col = choose_column(zonas.columns, ('NumeroZona', 'Numero_Zona', 'Zona', 'ZonaOD', 'Zona_OD', 'CodZona', 'Cod_Zona', 'ID_Zona', 'IDZona', 'N_Zona'), 'ID Zona OD')
    if zonas[col].isna().any() or zonas[col].astype(str).duplicated().any():
        raise ValueError(f'ID Zona OD {col}: ausências ou valores duplicados')
    return col


def diagnose(zonas, distritos, field_zone, field_city):
    print(f'Zonas: {len(zonas)} | CRS={zonas.crs} | colunas={list(zonas.columns)}')
    print(f'Distritos OD: {len(distritos)} | CRS={distritos.crs} | colunas={list(distritos.columns)}')
    print(f'Campo ID zona: {field_zone}; campo município: {field_city}')
    if field_city:
        print('Municípios mais frequentes:', zonas[field_city].value_counts(dropna=False).head(12).to_dict())


def overlay_by_area(source: gpd.GeoDataFrame, target: gpd.GeoDataFrame, source_id: str, target_id: str, target_label: str) -> pd.DataFrame:
    """Interseção: proporção sobre a área da zona, sem atribuir viagens proporcionalmente."""
    a = source[[source_id, 'geometry']].to_crs(METRIC_CRS).copy()
    b = target[[target_id, target_label, 'geometry']].to_crs(METRIC_CRS).copy()
    # Evita choque de nomes se os dois esquemas usam campos iguais.
    a = a.rename(columns={source_id: 'zona_od'})
    b = b.rename(columns={target_id: 'territorio_id', target_label: 'territorio_nome'})
    a['zona_area_m2'] = a.area
    if (a['zona_area_m2'] <= 0).any():
        raise ValueError('Existem zonas com área nula')
    intersections = gpd.overlay(a, b, how='intersection', keep_geom_type=True)
    if intersections.empty:
        raise ValueError('Nenhuma interseção espacial detectada. Verifique CRS e abrangência.')
    intersections['area_intersecao_m2'] = intersections.area
    intersections = intersections.loc[intersections['area_intersecao_m2'] > 1.0].copy()
    intersections['pct_area_zona'] = intersections['area_intersecao_m2'] / intersections['zona_area_m2'] * 100
    return pd.DataFrame(intersections.drop(columns=['geometry']))[['zona_od','territorio_id','territorio_nome','area_intersecao_m2','pct_area_zona']].sort_values(['zona_od','pct_area_zona'], ascending=[True,False])


def load_optional_official(path: str | None, label: str) -> gpd.GeoDataFrame | None:
    return read_geo(Path(path), label) if path else None


def assign_points(ocm_path: Path, zones_sp: gpd.GeoDataFrame, city_districts: gpd.GeoDataFrame | None) -> tuple[pd.DataFrame, dict]:
    df = pd.read_csv(ocm_path, encoding='utf-8-sig', dtype={'id_posto': 'string'})
    for name in ('id_posto','latitude','longitude'):
        if name not in df.columns:
            raise ValueError(f'OCM: coluna obrigatória ausente {name}')
    if df['id_posto'].isna().any() or df['id_posto'].duplicated().any():
        raise ValueError('OCM: id_posto ausente ou repetido; não é possível identificar pontos sem duplicações')
    df['latitude'] = pd.to_numeric(df['latitude'], errors='coerce')
    df['longitude'] = pd.to_numeric(df['longitude'], errors='coerce')
    valid = df['latitude'].between(-90,90) & df['longitude'].between(-180,180)
    points = gpd.GeoDataFrame(df.loc[valid].copy(), geometry=gpd.points_from_xy(df.loc[valid,'longitude'],df.loc[valid,'latitude']), crs='EPSG:4326')
    z = zones_sp[['zona_od','geometry']].to_crs('EPSG:4326')
    # intersects, não within: contempla pontos exatamente na borda e marca ambiguidades
    join = gpd.sjoin(points, z, how='left', predicate='intersects')
    counts = join.groupby('id_posto')['zona_od'].nunique(dropna=True)
    first = join.drop_duplicates('id_posto').copy()
    first['zonas_encontradas'] = first['id_posto'].map(counts).fillna(0).astype(int)
    first.loc[first['zonas_encontradas'] != 1, 'zona_od'] = None
    selected = first[['id_posto','zona_od','zonas_encontradas']].copy()
    if city_districts is not None:
        d = city_districts[['distrito_id','distrito_nome','geometry']].to_crs('EPSG:4326')
        matching = gpd.sjoin(points, d, how='left', predicate='intersects')
        dc = matching.groupby('id_posto')['distrito_id'].nunique(dropna=True)
        dfirst = matching.drop_duplicates('id_posto')[['id_posto','distrito_id','distrito_nome']].copy()
        dfirst['distritos_encontrados'] = dfirst['id_posto'].map(dc).fillna(0).astype(int)
        dfirst.loc[dfirst['distritos_encontrados'] != 1, ['distrito_id','distrito_nome']] = None
        selected = selected.merge(dfirst, on='id_posto', how='left', validate='one_to_one')
    invalid = df.loc[~valid,['id_posto']].copy()
    invalid['zona_od'] = None
    invalid['zonas_encontradas'] = 0
    all_rows = pd.concat([selected,invalid], ignore_index=True)
    stats = {'pontos_total':len(df), 'coordenadas_invalidas':int((~valid).sum()), 'associados_uma_zona':int(all_rows['zona_od'].notna().sum()), 'nao_associados_ou_ambiguos':int(all_rows['zona_od'].isna().sum())}
    return all_rows,stats


def run(args) -> None:
    root = Path(args.origem).resolve()
    zp, dp = shapefile(root,'Zonas_2023'), shapefile(root,'Distritos_2023_region')
    auditoria_reparos=[]
    opts={'reparar': args.reparar_geometrias, 'limite_area_pct': args.limite_alteracao_area_pct, 'auditoria': auditoria_reparos, 'diagnosticar': args.diagnosticar}
    zones = read_geo(zp,'Zonas OD 2023', **opts)
    districts = read_geo(dp,'Distritos OD 2023', **opts)
    zone_col=identify_zone_id(zones,args.campo_zona)
    city_col = args.campo_municipio or choose_column(zones.columns, ('NomeMunici','Nome_Municipio','Municipio','NomeMunicipio','Município'), 'município da zona')
    if city_col not in zones.columns:
        raise ValueError(f'Coluna município inexistente: {city_col}')
    diagnose(zones,districts,zone_col,city_col)
    if args.diagnosticar:
        return
    city_mask = zones[city_col].astype(str).map(key).eq('SAOPAULO')
    if not city_mask.any():
        raise ValueError(f'Nenhuma zona com município São Paulo em {city_col!r}')
    zones_sp = zones.loc[city_mask].copy().rename(columns={zone_col:'zona_od'})
    zones_sp['municipio_nome']='São Paulo'
    zones_sp['origem_geometria']='Pesquisa OD 2023'
    # Há diferença entre distritos da pesquisa OD e distritos administrativos GeoSampa.
    dist_id=args.campo_distrito_od or choose_column(districts.columns,("NumeroDist",'CodDistrit','CodDistrito','CodigoDistrito','Cod_Distrito','NumeroDistrito','NumDistrito','Distrito','ID_Distrito','IDDistrito','Codigo','ID'), 'ID distrito OD')
    dist_name=args.campo_nome_distrito_od or choose_column(districts.columns,('NomeDistri','NomeDistrito','Nome_Distrito','NomeDistrit','Nome','DistritoNome','NomeDist','DistNome'), 'nome distrito OD')
    if dist_id==dist_name:
        raise ValueError('Colunas de ID e nome do distrito OD coincidem; informe corretamente.')
    rel_od=overlay_by_area(zones_sp, districts, 'zona_od', dist_id, dist_name)
    rel_od=rel_od.rename(columns={'territorio_id':'distrito_od_id','territorio_nome':'distrito_od_nome'})
    official_d=read_geo(Path(args.distritos_oficiais),'Distritos oficiais GeoSampa', **opts) if args.distritos_oficiais else None
    official_s=read_geo(Path(args.subprefeituras),'Subprefeituras GeoSampa', **opts) if args.subprefeituras else None
    official_info={}
    geo_d=None
    if official_d is not None:
        official_id=args.campo_distrito_oficial or choose_column(official_d.columns,('CD_DIST','CD_DISTRI','COD_DISTRITO','COD_DISTR','CODIGO','CODIGO_DIST','ID'), 'ID distrito GeoSampa')
        official_name=args.campo_nome_distrito_oficial or choose_column(official_d.columns,('NM_DIST','NM_DISTRIT','NOME_DISTRITO','NOME','DISTRITO'), 'nome distrito GeoSampa')
        geo_d=official_d.rename(columns={official_id:'distrito_id',official_name:'distrito_nome'})
        rel_off=overlay_by_area(zones_sp,geo_d,'zona_od','distrito_id','distrito_nome')
        official_info['distritos_oficiais']=len(geo_d)
    else: rel_off=None
    if official_s is not None:
        sid=args.campo_subprefeitura or choose_column(official_s.columns,('CD_SUB','CD_SUBPREF','COD_SUBPREF','CODIGO','ID'), 'ID subprefeitura GeoSampa')
        sn=args.campo_nome_subprefeitura or choose_column(official_s.columns,('NM_SUB','NM_SUBPREF','NOME_SUBPREFEITURA','NOME','SUBPREFEITURA'), 'nome subprefeitura GeoSampa')
        sr=args.campo_regiao or choose_column(official_s.columns,('REGIAO','NM_REGIAO','REGIAO_5','NOME_REGIAO','ZONA'), 'região oficial GeoSampa',required=False)
        geo_s=official_s.rename(columns={sid:'subprefeitura_id',sn:'subprefeitura_nome'})
        rel_sub=overlay_by_area(zones_sp,geo_s,'zona_od','subprefeitura_id','subprefeitura_nome').rename(columns={'territorio_id':'subprefeitura_id','territorio_nome':'subprefeitura_nome'})
        if sr:
            # Mapear a região a partir da própria camada oficial, nunca por uma lista inventada.
            map_reg=geo_s.set_index('subprefeitura_id')[sr]
            rel_sub['regiao_oficial']=rel_sub['subprefeitura_id'].map(map_reg)
            official_info['coluna_regiao_oficial']=sr
        official_info['subprefeituras_oficiais']=len(geo_s)
    else: rel_sub=None
    now=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out=Path(args.saida).resolve()/now
    out.mkdir(parents=True,exist_ok=False)
    zones_sp.to_crs('EPSG:4326').to_file(out/'dim_zonas_od_capital.geojson',driver='GeoJSON')
    export_csv(pd.DataFrame(zones_sp.drop(columns='geometry')),out/'dim_zonas_od_capital.csv')
    export_csv(rel_od,out/'rel_zona_od_distrito_od.csv')
    if auditoria_reparos:
        export_csv(pd.DataFrame(auditoria_reparos),out/'auditoria_reparos_geometricos.csv')
    if rel_off is not None:
        export_csv(rel_off,out/'rel_zona_od_distrito_oficial.csv')
        geo_d.to_crs('EPSG:4326').to_file(out/'dim_distritos_oficiais.geojson',driver='GeoJSON')
    if rel_sub is not None:
        export_csv(rel_sub,out/'rel_zona_od_subprefeitura.csv')
        geo_s.to_crs('EPSG:4326').to_file(out/'dim_subprefeituras.geojson',driver='GeoJSON')
        if 'regiao_oficial' in rel_sub.columns:
            # Soma sobreposições de subprefeituras da mesma região; não soma indicadores OD.
            rel_reg=(rel_sub.groupby(['zona_od','regiao_oficial'],dropna=False,as_index=False)
                     .agg(area_intersecao_m2=('area_intersecao_m2','sum'),pct_area_zona=('pct_area_zona','sum')))
            if rel_reg['regiao_oficial'].isna().any():
                raise ValueError('Existem subprefeituras sem região. Preencha os atributos oficiais antes da publicação.')
            export_csv(rel_reg,out/'rel_zona_od_regiao.csv')
            regioes=geo_s[[sr,'geometry']].rename(columns={sr:'regiao_oficial'}).dissolve(by='regiao_oficial',as_index=False)
            regioes.to_crs('EPSG:4326').to_file(out/'dim_regioes_sp.geojson',driver='GeoJSON')
            official_info['regioes_distintas']=int(regioes['regiao_oficial'].nunique())
    stats={}
    if args.ocm:
        locations,stats=assign_points(Path(args.ocm),zones_sp,geo_d)
        export_csv(locations,out/'rel_eletropostos_zonas_od.csv')
    manifest={'gerado_utc':datetime.now(timezone.utc).isoformat(),'status':'integracao_espacial_sem_inferencia_de_viagens',
      'fontes':{'zonas_od':str(zp),'distritos_od':str(dp),'distritos_oficiais':args.distritos_oficiais,'subprefeituras':args.subprefeituras,'ocm':args.ocm},
      'contagens':{'zonas_od_rmsp':len(zones),'zonas_od_capital_por_campo_municipio':len(zones_sp),'distritos_od_rmsp':len(districts),'relacoes_od_distritos_od':len(rel_od),**official_info,**stats},
      'pendencias':(['Regiões Norte/Sul/Leste/Oeste/Centro exigem camada GeoSampa de subprefeituras com campo de região ou tabela oficial de correspondência'] if rel_sub is None or 'coluna_regiao_oficial' not in official_info else []) + (['Limites GeoSampa não integrados: distritos OD não são tratados como limites distritais oficiais'] if rel_off is None else []),
      'reparo_geometrico':{'habilitado':args.reparar_geometrias,'limite_alteracao_area_pct':args.limite_alteracao_area_pct,'registros_reparados':len(auditoria_reparos),'auditoria':'auditoria_reparos_geometricos.csv' if auditoria_reparos else None},
      'observacoes':['Percentuais de área são relações geométricas, não percentuais de viagens ou população.','Pontos sobre fronteiras são marcados ambíguos.','Não modifica arquivos anteriores nem base SQL/Supabase.']}
    (out/'manifesto.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Saídas:',out)
    print('Resumo:',json.dumps(manifest['contagens'],ensure_ascii=False))
    if manifest['pendencias']:
        print('Pendências:', ' | '.join(manifest['pendencias']))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--origem',required=True,help='Diretório local que contém a pasta Shape completa sincronizada do Supabase')
    p.add_argument('--saida',default=OUTPUT_DIR)
    p.add_argument('--diagnosticar',action='store_true')
    p.add_argument('--reparar-geometrias',action='store_true',help='Corrige polígonos inválidos somente em memória, com auditoria e limite de área')
    p.add_argument('--limite-alteracao-area-pct',type=float,default=1.0,help='Variação máxima permitida na área por geometria reparada (padrão: 1%%)')
    p.add_argument('--campo-zona')
    p.add_argument('--campo-municipio')
    p.add_argument('--campo-distrito-od')
    p.add_argument('--campo-nome-distrito-od')
    p.add_argument('--distritos-oficiais',help='GeoJSON/GPKG do GeoSampa, opcional')
    p.add_argument('--subprefeituras',help='GeoJSON/GPKG do GeoSampa, opcional; necessário para macro-regiões oficiais')
    p.add_argument('--campo-distrito-oficial')
    p.add_argument('--campo-nome-distrito-oficial')
    p.add_argument('--campo-subprefeitura')
    p.add_argument('--campo-nome-subprefeitura')
    p.add_argument('--campo-regiao')
    p.add_argument('--ocm',help='CSV de eletropostos do Open Charge Map, opcional')
    args=p.parse_args()
    try: run(args)
    except (ValueError,FileNotFoundError,RuntimeError) as exc:
        print(f'ERRO DE VALIDAÇÃO: {exc}',file=sys.stderr); sys.exit(2)

if __name__=='__main__': main()
