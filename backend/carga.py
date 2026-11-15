"""Carrega os 8 CSVs analíticos, GeoJSON das zonas OD e snapshot OCM no PostGIS.

Modo validar, sem DB:
  python -m backend.carga --validar
Modo publicar (em banco de desenvolvimento):
  python -m backend.carga --publicar
Todos os INSERT/COPY/TRUNCATE de publicação acontecem numa única transação.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import os
import math
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAINEIS = Path('dados_analiticos/cenarios_2026')
GEOJSON = Path('dados_relatorios/territorio_od2023/geo_zonas_od2023_rmsp.geojson')
GEO_MUNICIPIOS = Path('dados_relatorios/territorio_od2023/geo_municipios_derivados_zonas_od2023.geojson')
OCM = Path('dados_limpos/10_OPEN_CHARGE_MAP_SP.csv')
SQL = Path('db/006_backend_api_v1.sql')

# Contrato fechado: nenhum nome de tabela ou coluna vem de usuário/URL.
TABLES = {
  'od_municipios': 'painel_od_municipios.csv',
  'od_distritos_capital': 'painel_od_distritos_capital.csv',
  'od_zonas': 'painel_od_zonas.csv',
  'od_top_destinos': 'painel_od_top_destinos.csv',
  'energia_inmetro': 'painel_energia_inmetro.csv',
  'motorista_custos': 'painel_motorista_custos.csv',
  'premissas_receita': 'dim_premissas_receita.csv',
  'sensibilidade_receita': 'painel_sensibilidade_receita.csv',
}

# A ordem dos campos deve coincidir integralmente com a saída do bloco analítico.
FIELDS = {
 'od_municipios': 'municipio_od_id municipio_nome qtd_zonas zonas_com_amostra_origem zonas_com_amostra_destino viagens_origem_amostra viagens_origem_expandidas viagens_destino_amostra viagens_destino_expandidas fonte natureza_dado',
 'od_distritos_capital': 'distrito_od_id distrito_nome qtd_zonas zonas_com_amostra_origem zonas_com_amostra_destino viagens_origem_amostra viagens_origem_expandidas viagens_destino_amostra viagens_destino_expandidas fonte natureza_dado',
 'od_zonas': 'zona_od_id zona_nome municipio_od_id municipio_nome distrito_od_id distrito_nome escopo viagens_origem_amostra viagens_origem_expandidas viagens_destino_amostra viagens_destino_expandidas tem_amostra_origem tem_amostra_destino fonte natureza_dado observacao',
 'od_top_destinos': 'zona_origem_id zona_destino_id faixa_horaria viagens_amostra viagens_expandidas amostra_com_distancia duracao_media_ponderada_min distancia_linha_reta_media_ponderada_km posicao nome_zona_destino municipio_destino fonte natureza_dado observacao',
 'energia_inmetro': 'inmetro_id marca_inmetro modelo_inmetro versao_inmetro tecnologia modalidade custo_energia_rs_km km_mes_hipotese custo_energia_rs_mes_hipotetico grupo_interface fonte natureza_dado observacao',
 'motorista_custos': 'perfil_id regime inmetro_id marca_inmetro modelo_inmetro versao_inmetro tecnologia modalidade status campos_pendentes fonte_premissas km_mes receita_liquida_plataforma_rs_mes custo_total_economico_rs_mes resultado_economico_rs_mes custo_total_rs_km receita_equilibrio_rs_km receita_equilibrio_rs_hora componentes_custos_informados componentes_custos_pendentes subtotal_custos_conhecidos_rs_mes todos_custos_preenchidos grupo_interface fonte natureza_dado observacao',
 'premissas_receita': 'cenario_receita_id titulo receita_apos_plataforma_rs_mes fonte observacao natureza_dado',
 'sensibilidade_receita': 'perfil_id regime inmetro_id modalidade tecnologia grupo_interface km_mes custo_total_economico_rs_mes subtotal_custos_conhecidos_rs_mes componentes_custos_pendentes campos_pendentes todos_custos_preenchidos cenario_receita_id receita_apos_plataforma_rs_mes resultado_economico_simulado_rs_mes resultado_simulado_rs_km situacao_calculo natureza_dado observacao',
}
FIELDS = {name: field_list.split() for name, field_list in FIELDS.items()}
OCM_FIELDS = 'id_posto titulo operadora logradouro cidade estado_provincia cep latitude longitude qtd_conexoes potencia_max_kw tipos_conectores status_cadastral custo_uso data_coleta fonte_url recorte_geografico'.split()


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024*1024), b''):
            h.update(chunk)
    return h.hexdigest()


def csv_records(path: Path, cols: list[str]) -> list[dict]:
    if not path.is_file():
        raise FileNotFoundError(f'CSV ausente: {path}')
    with path.open('r',encoding='utf-8-sig',newline='') as f:
        reader=csv.DictReader(f)
        if reader.fieldnames != cols:
            raise ValueError(f'{path}: cabeçalho divergente. Esperado: {cols}; recebido: {reader.fieldnames}')
        records=list(reader)
    if not records:
        raise ValueError(f'{path}: tabela vazia')
    if any(None in row for row in records):
        raise ValueError(f'{path}: linha com colunas extras')
    return records


def _verificar_crs_geojson(crs: object) -> None:
    """GeoJSON RFC 7946: CRS omitido implica WGS84 lon/lat.

    Exportacoes GeoPandas/GDAL tambem podem indicar OGC:CRS84
    (longitude/latitude), equivalente espacial para GeoJSON web.
    CRS projetado deve ser rejeitado e reprojetado na origem.
    """
    if crs is None:
        return  # GeoJSON moderno nao precisa de uma propriedade crs.
    if not isinstance(crs, dict) or crs.get('type') != 'name':
        raise ValueError('GeoJSON: declaracao CRS desconhecida; exporte em EPSG:4326')
    props = crs.get('properties')
    if not isinstance(props, dict):
        raise ValueError('GeoJSON: propriedades CRS ausentes')
    name = str(props.get('name', '')).strip().upper()
    # Ex.: EPSG:4326, urn:ogc:def:crs:EPSG::4326,
    # urn:ogc:def:crs:OGC:1.3:CRS84 e OGC:CRS84.
    permitted = (
        re.fullmatch(r'(?:EPSG:)?4326', name) is not None
        or re.fullmatch(r'(?:OGC:)?CRS84', name) is not None
        or re.fullmatch(r'URN:OGC:DEF:CRS:EPSG:(?:[0-9.]*:)?4326', name) is not None
        or re.fullmatch(r'URN:OGC:DEF:CRS:OGC:(?:[0-9.]*:)?CRS84', name) is not None
    )
    if not permitted:
        raise ValueError(f'GeoJSON nao esta em WGS84/CRS84 (recebido {name!r}); reprojete para EPSG:4326')


def _coordenadas_geograficas(coords: object) -> bool:
    """Valida recursivamente GeoJSON Polygon/MultiPolygon em lon/lat.

    Nao corrige um arquivo reprojetado incorretamente: recusa-o.
    """
    if not isinstance(coords, list) or not coords:
        return False
    stack = [coords]
    points = 0
    while stack:
        seq = stack.pop()
        if not isinstance(seq, list) or not seq:
            return False
        if isinstance(seq[0], (int, float)):
            if len(seq) < 2:
                return False
            lon, lat = seq[:2]
            if (isinstance(lon, bool) or isinstance(lat, bool)
                    or not isinstance(lon, (int, float)) or not isinstance(lat, (int, float))
                    or not math.isfinite(lon) or not math.isfinite(lat)
                    or not (-180 <= lon <= 180 and -90 <= lat <= 90)):
                return False
            points += 1
        else:
            stack.extend(seq)
    return points >= 4  # pelo menos um anel de poligono.


def load_geo(path: Path, expected_ids: set[int], id_col: str = 'zona_od_id') -> list[tuple[int, str]]:
    if not path.is_file():
        raise FileNotFoundError(f'GeoJSON ausente: {path}')
    obj = json.loads(path.read_text(encoding='utf-8-sig'))
    if obj.get('type') != 'FeatureCollection':
        raise ValueError('GeoJSON exige FeatureCollection')
    _verificar_crs_geojson(obj.get('crs'))
    result = []
    seen = set()
    for feature in obj.get('features', []):
        props = feature.get('properties') or {}
        if id_col not in props:
            raise ValueError(f'GeoJSON: propriedade {id_col} ausente')
        try:
            zid = int(props[id_col])
        except (ValueError, TypeError) as exc:
            raise ValueError(f'GeoJSON: {id_col} invalido: {props[id_col]!r}') from exc
        geom = feature.get('geometry') or {}
        if zid in seen:
            raise ValueError(f'GeoJSON: identificador repetido {zid}')
        if geom.get('type') not in ('Polygon', 'MultiPolygon'):
            raise ValueError(f'GeoJSON: geometria nao-poligonal no ID {zid}')
        if not _coordenadas_geograficas(geom.get('coordinates')):
            raise ValueError(f'GeoJSON: coordenadas invalidas ou fora de lon/lat WGS84 no ID {zid}')
        seen.add(zid)
        result.append((zid, json.dumps(geom, separators=(',', ':'), ensure_ascii=False)))
    if seen != expected_ids:
        raise ValueError(f'GeoJSON: zonas incompatíveis; faltando={len(expected_ids-seen)}; extras={len(seen-expected_ids)}')
    return result


def validar(paineis: Path, geo: Path, geo_municipios: Path, ocm: Path):
    manifest_path=paineis/'manifesto_cenarios_analiticos.json'
    if not manifest_path.is_file():
        raise FileNotFoundError(f'Manifesto ausente: {manifest_path}')
    manifesto=json.loads(manifest_path.read_text(encoding='utf-8-sig'))
    expected=manifesto.get('saidas_sha256') or {}
    counts={}
    cache={}
    for table,filename in TABLES.items():
        file=paineis/filename
        if filename not in expected:
            raise ValueError(f'Manifesto não relaciona {filename}')
        digest=sha256(file)
        if digest!=expected[filename]['sha256']:
            raise ValueError(f'{filename}: SHA256 diferente do manifesto: entrada possivelmente alterada')
        data=csv_records(file,FIELDS[table])
        if len(data)!=expected[filename]['linhas']:
            raise ValueError(f'{filename}: linhas diferentes do manifesto')
        counts[table]=len(data)
        cache[table]=data
    if (counts['od_zonas'],counts['od_municipios'],counts['od_distritos_capital'])!=(527,39,96):
        raise ValueError('Baseline territorial incorreto: esperado 527/39/96')
    zones={int(r['zona_od_id']) for r in cache['od_zonas']}
    if len(zones)!=527: raise ValueError('Zona OD repetida')
    munis={int(r['municipio_od_id']) for r in cache['od_municipios']}
    if len(munis)!=39 or any(int(r['municipio_od_id']) not in munis for r in cache['od_zonas']):
        raise ValueError('FK territorial inválida')
    if sum(int(r['municipio_od_id'])==36 for r in cache['od_zonas'])!=343:
        raise ValueError('Esperadas 343 zonas na capital')
    for row in cache['od_top_destinos']:
        if int(row['zona_origem_id']) not in zones or int(row['zona_destino_id']) not in zones:
            raise ValueError('Fluxo com zona inexistente')
    energia={(r['inmetro_id'],r['modalidade']) for r in cache['energia_inmetro']}
    if len(energia)!=counts['energia_inmetro']: raise ValueError('Energia INMETRO duplicada')
    motorists={(r['perfil_id'],r['inmetro_id'],r['modalidade']) for r in cache['motorista_custos']}
    if len(motorists)!=counts['motorista_custos']: raise ValueError('Motorista duplicado')
    receita={r['cenario_receita_id'] for r in cache['premissas_receita']}
    for r in cache['motorista_custos']:
        if (r['inmetro_id'],r['modalidade']) not in energia: raise ValueError('Motorista sem INMETRO')
        if int(r['componentes_custos_pendentes'])>0 and (r['custo_total_economico_rs_mes'] or r['resultado_economico_rs_mes']):
            raise ValueError('Lucro/custo total indevido em cenário incompleto')
        if r['status']=='PARCIAL_PENDENTE' and r['resultado_economico_rs_mes']:
            raise ValueError('Lucro indevido com status parcial')
    for r in cache['premissas_receita']:
        if r['fonte'] != 'HIPOTESE_DIDATICA_NAO_OBSERVADA':
            raise ValueError('Receita apresentada como fato observado')
    if len(receita)!=counts['premissas_receita']: raise ValueError('Premissa de receita duplicada')
    if counts['sensibilidade_receita'] != counts['motorista_custos']*counts['premissas_receita']:
        raise ValueError('Sensibilidade não cobre todas as hipóteses')
    for r in cache['sensibilidade_receita']:
        if (r['perfil_id'],r['inmetro_id'],r['modalidade']) not in motorists or r['cenario_receita_id'] not in receita:
            raise ValueError('Sensibilidade órfã')
        if int(r['componentes_custos_pendentes'])>0 and r['resultado_economico_simulado_rs_mes']:
            raise ValueError('Lucro indevido na sensibilidade incompleta')
    geo_rows=load_geo(geo,zones)
    municipios_geo_rows=load_geo(geo_municipios,munis,'municipio_od_id')
    pontos=csv_records(ocm,OCM_FIELDS)
    ids=set()
    for p in pontos:
        pid=int(p['id_posto'])
        if pid in ids: raise ValueError('OCM duplicado')
        ids.add(pid)
        if p['latitude'] and p['longitude']:
            lat=float(p['latitude']);lon=float(p['longitude'])
            if not(-90<=lat<=90 and -180<=lon<=180):
                raise ValueError(f'OCM {pid}: latitude/longitude inválidas')
    return {
        'manifesto_sha256':sha256(manifest_path), 'versao':str(manifesto.get('versao','1.0')),
        'counts':counts, 'geometrias_zona':len(geo_rows),'pontos_recarga':len(pontos),
        'geo_rows':geo_rows,'municipios_geo_rows':municipios_geo_rows,'ocm_rows':pontos,
    }


def _copy(cur, file: Path, table: str, cols: list[str]) -> None:
    # Nomes de tabela e colunas só vêm de TABLES/FIELDS constantes.
    cols_sql=','.join(cols)
    with cur.copy(f'COPY api_v1.{table} ({cols_sql}) FROM STDIN WITH (FORMAT csv, HEADER true)') as copy:
        with file.open('r',encoding='utf-8-sig',newline='') as f:
            while data:=f.read(65536):
                copy.write(data)


def publicar(conf: dict, paineis:Path, ocm:Path, sql_path:Path, dsn:str) -> None:
    if not dsn: raise RuntimeError('DATABASE_URL ausente; configure .env localmente')
    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError('Instale: python -m pip install -r requirements-backend.txt') from exc
    # DDL e carga são transacionais; qualquer falha faz rollback.
    with psycopg.connect(dsn,options='-c search_path=public,extensions') as conn:
        with conn.cursor() as cur:
            ddl=sql_path.read_text(encoding='utf-8')
            # Não confirmar a migration separadamente: DDL + carga na MESMA transação.
            ddl=ddl.replace('\nBEGIN;\n','\n').replace('\nCOMMIT;','')
            cur.execute(ddl)
            ordered=[*TABLES,'zonas_geometrias','municipios_geometrias','recarga_pontos','recarga_zonas','carga_atual']
            cur.execute('TRUNCATE '+', '.join('api_v1.'+table for table in ordered))
            for table,filename in TABLES.items():
                _copy(cur,paineis/filename,table,FIELDS[table])
                cur.execute('SELECT COUNT(*) FROM api_v1.'+table)
                actual=cur.fetchone()[0]
                if actual!=conf['counts'][table]:
                    raise ValueError(f'{table}: PostgreSQL={actual}, CSV={conf["counts"][table]}')
            for zid,geom in conf['geo_rows']:
                cur.execute('''INSERT INTO api_v1.zonas_geometrias(zona_od_id,geom)
                  VALUES (%s, ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%s),4326)))''',(zid,geom))
            for mid,geom in conf['municipios_geo_rows']:
                cur.execute('''INSERT INTO api_v1.municipios_geometrias(municipio_od_id,geom)
                    VALUES (%s, ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%s),4326)))''',(mid,geom))
            cur.execute('SELECT COUNT(*) FROM api_v1.municipios_geometrias')
            if cur.fetchone()[0]!=39: raise ValueError('Esperadas 39 geometrias municipais')
            _copy(cur,ocm,'recarga_pontos',OCM_FIELDS)
            cur.execute('''UPDATE api_v1.recarga_pontos
                SET geom = ST_SetSRID(ST_MakePoint(longitude::double precision,latitude::double precision),4326)
                WHERE latitude IS NOT NULL AND longitude IS NOT NULL''')
            # Borda pode cobrir mais de uma zona: nunca escolher arbitrariamente.
            cur.execute('''INSERT INTO api_v1.recarga_zonas(id_posto,zona_od_id,qtd_zonas_cobrem_ponto,situacao)
                SELECT p.id_posto,
                    CASE WHEN COUNT(z.zona_od_id)=1 THEN MIN(z.zona_od_id) END,
                    COUNT(z.zona_od_id)::integer,
                    CASE WHEN p.geom IS NULL THEN 'SEM_COORDENADAS'
                         WHEN COUNT(z.zona_od_id)=0 THEN 'SEM_ZONA'
                         WHEN COUNT(z.zona_od_id)=1 THEN 'ZONA_UNICA'
                         ELSE 'AMBIGUO' END
                FROM api_v1.recarga_pontos p
                LEFT JOIN api_v1.zonas_geometrias z ON p.geom IS NOT NULL AND ST_Covers(z.geom,p.geom)
                GROUP BY p.id_posto,p.geom''')
            counts=json.dumps(conf['counts'],ensure_ascii=False)
            cur.execute('''INSERT INTO api_v1.carga_atual
              (id,manifesto_sha256,versao,contagens,zonas_com_geometria,pontos_recarga,observacoes)
              VALUES (1,%s,%s,%s::jsonb,%s,%s,%s)''',(
                conf['manifesto_sha256'],conf['versao'],counts,conf['geometrias_zona'],
                conf['pontos_recarga'],
                'OD 2023 não é Uber exclusiva. Energia e receitas são cenários sem matching FIPE homologado.'
            ))
    # commit via context manager somente após todas as verificações.


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--paineis',type=Path,default=PAINEIS)
    p.add_argument('--geo',type=Path,default=GEOJSON)
    p.add_argument('--geo-municipios',type=Path,default=GEO_MUNICIPIOS)
    p.add_argument('--ocm',type=Path,default=OCM)
    p.add_argument('--sql',type=Path,default=SQL)
    p.add_argument('--validar',action='store_true',help='valida todos os arquivos sem tocar no banco')
    p.add_argument('--publicar',action='store_true',help='substitui snapshot no banco, de forma transacional')
    args=p.parse_args(argv)
    if not args.validar and not args.publicar:
        p.error('Use --validar primeiro e depois --publicar')
    conf=validar(args.paineis,args.geo,args.geo_municipios,args.ocm)
    print(json.dumps({k:v for k,v in conf.items() if k not in ('geo_rows','municipios_geo_rows','ocm_rows')},indent=2,ensure_ascii=False))
    if args.publicar:
        from dotenv import load_dotenv
        load_dotenv()
        if not args.sql.is_file():raise FileNotFoundError(args.sql)
        publicar(conf,args.paineis,args.ocm,args.sql,os.getenv('DATABASE_URL',''))
        print('Snapshot API v1 publicado com transação concluída.')
    else:
        print('Validação concluída. Nenhum dado escrito no banco.')

if __name__=='__main__': main()
