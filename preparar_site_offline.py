"""PI06 · Gera um HTML totalmente offline usando os arquivos locais do repositório.

Somente biblioteca padrão do Python. Não conecta ao Supabase e não usa internet.
Uso (copie este arquivo e modelo.html para a raiz do PI06):
    python preparar_site_offline.py

Opcional:
    python preparar_site_offline.py --raiz "C:\\caminho\\PI06" --saida apresentacao_PI06.html
"""
from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import json
import math
import statistics
import re
import unicodedata
import sys
from pathlib import Path
from typing import Any

CSV_SPECS = {
    "zones": ("painel_od_zonas.csv", ("zona_od_id", "zona_nome", "municipio_od_id", "municipio_nome", "distrito_od_id", "distrito_nome", "escopo", "viagens_origem_expandidas", "viagens_destino_expandidas", "viagens_origem_amostra", "tem_amostra_origem")),
    "municipios": ("painel_od_municipios.csv", ("municipio_od_id", "municipio_nome", "qtd_zonas", "viagens_origem_expandidas", "viagens_destino_expandidas", "zonas_com_amostra_origem", "zonas_com_amostra_destino")),
    "distritos": ("painel_od_distritos_capital.csv", ("distrito_od_id", "distrito_nome", "qtd_zonas", "viagens_origem_expandidas", "viagens_destino_expandidas")),
    "fluxos": ("painel_od_top_destinos.csv", ("zona_origem_id", "zona_destino_id", "faixa_horaria", "viagens_amostra", "viagens_expandidas", "duracao_media_ponderada_min", "posicao", "nome_zona_destino", "municipio_destino")),
    "energia": ("painel_energia_inmetro.csv", ("inmetro_id", "marca_inmetro", "modelo_inmetro", "versao_inmetro", "tecnologia", "modalidade", "custo_energia_rs_km", "grupo_interface")),
    "motoristas": ("painel_motorista_custos.csv", ("perfil_id", "regime", "inmetro_id", "marca_inmetro", "modelo_inmetro", "versao_inmetro", "tecnologia", "modalidade", "status", "campos_pendentes", "km_mes", "custo_total_economico_rs_mes", "componentes_custos_pendentes", "subtotal_custos_conhecidos_rs_mes")),
    "premissas": ("dim_premissas_receita.csv", ("cenario_receita_id", "titulo", "receita_apos_plataforma_rs_mes", "fonte")),
    "sensibilidade": ("painel_sensibilidade_receita.csv", ("perfil_id", "inmetro_id", "cenario_receita_id", "situacao_calculo")),
}

# As colunas numéricas/booleanas seguem o formato dos arquivos de saída do próprio PI06.
INT_FIELDS = {"zona_od_id", "municipio_od_id", "distrito_od_id", "qtd_zonas", "zonas_com_amostra_origem", "zonas_com_amostra_destino", "zona_origem_id", "zona_destino_id", "inmetro_id", "posicao", "componentes_custos_pendentes"}
NUM_FIELDS = {"viagens_origem_expandidas", "viagens_destino_expandidas", "viagens_origem_amostra", "viagens_expandidas", "viagens_amostra", "duracao_media_ponderada_min", "custo_energia_rs_km", "km_mes", "custo_total_economico_rs_mes", "subtotal_custos_conhecidos_rs_mes", "receita_apos_plataforma_rs_mes"}
BOOL_FIELDS = {"tem_amostra_origem"}


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_cell(k: str, value: str) -> Any:
    value = value.strip()
    if value == "":
        return None
    if k in INT_FIELDS:
        n = float(value)
        if not n.is_integer() or not math.isfinite(n):
            raise ValueError(f"Campo inteiro inválido {k}: {value}")
        return int(n)
    if k in NUM_FIELDS:
        x = float(value)
        if not math.isfinite(x):
            raise ValueError(f"Campo numérico inválido {k}: {value}")
        return x
    if k in BOOL_FIELDS:
        if value.lower() not in ("true", "false"):
            raise ValueError(f"Booleano inválido {k}: {value}")
        return value.lower() == "true"
    return value


def read_csv(path: Path, keep: tuple[str, ...], *, only_count=False) -> list[dict[str, Any]] | int:
    if not path.is_file():
        raise FileNotFoundError(f"Falta arquivo: {path}. Execute gerar_cenarios_analiticos.py antes.")
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        missing = set(keep) - set(reader.fieldnames or ())
        if missing:
            raise ValueError(f"{path.name}: colunas ausentes {sorted(missing)}")
        if only_count:
            return sum(1 for _ in reader)
        return [{k: parse_cell(k, row.get(k, "") or "") for k in keep} for row in reader]


def valid_coords(point: list) -> bool:
    return (len(point) >= 2 and isinstance(point[0], (int, float)) and isinstance(point[1], (int, float)) and
            math.isfinite(point[0]) and math.isfinite(point[1]) and -180 <= point[0] <= 180 and -90 <= point[1] <= 90)


def polygon_coords(geometry: dict) -> list[list[list[list[float]]]]:
    if not isinstance(geometry, dict):
        raise ValueError("GeoJSON com geometria ausente")
    typ, coords = geometry.get("type"), geometry.get("coordinates")
    if typ == "Polygon":
        return [coords]
    if typ == "MultiPolygon":
        return coords
    raise ValueError(f"Esperado Polygon/MultiPolygon, recebido: {typ}")


def as_geo(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8-sig") as f:
        doc = json.load(f)
    if doc.get("type") != "FeatureCollection":
        raise ValueError(f"{path.name}: esperado FeatureCollection")
    crs = ((doc.get("crs") or {}).get("properties") or {}).get("name", "")
    if crs and crs.lower() not in ("ogc:crs84", "urn:ogc:def:crs:ogc:1.3:crs84") and not (crs.upper().endswith("4326") or "4326" in crs):
        raise ValueError(f"{path.name}: CRS diferente de WGS84/CRS84/EPSG:4326 ({crs})")
    return doc.get("features", [])


def extract_id(feat: dict, keys: tuple[str, ...]) -> int:
    props = feat.get("properties") or {}
    norm = lambda s: "".join(x for x in str(s).lower() if x.isalnum())
    d = {norm(k): v for k, v in props.items()}
    for k in keys:
        v = d.get(norm(k))
        if v is not None and str(v) != "":
            return int(v)
    raise ValueError(f"GeoJSON não possui chave de zona/município. Propriedades: {list(props)}")


def collect_bounds(features: list[dict]):
    xs, ys = [], []
    for feat in features:
        for poly in polygon_coords(feat["geometry"]):
            for ring in poly:
                if len(ring) < 4:
                    raise ValueError("Polígono sem anel fechado suficiente")
                for p in ring:
                    if not valid_coords(p):
                        raise ValueError("Coordenadas do GeoJSON inválidas ou projetadas; execute a integração OD em EPSG:4326")
                    xs.append(p[0]);ys.append(p[1])
    if not xs or max(xs) - min(xs) < .05 or max(ys) - min(ys) < .05:
        raise ValueError("Extensão geográfica das zonas OD incoerente")
    # Faixa ampla da Grande São Paulo; impede geometrias projetadas e coordenadas de outro lugar.
    if not (-49.5 < min(xs) < -45.0 and -49.5 < max(xs) < -45.0 and -25.5 < min(ys) < -21.5 and -25.5 < max(ys) < -21.5):
        raise ValueError(f"GeoJSON fora da região da RMSP: lon[{min(xs)},{max(xs)}] lat[{min(ys)},{max(ys)}]")
    return min(xs), min(ys), max(xs), max(ys)


def sqdist(p, a, b):
    vx = b[0] - a[0]; vy = b[1] - a[1]
    if vx == 0 and vy == 0:
        return (p[0] - a[0])**2 + (p[1] - a[1])**2
    t = max(0, min(1, ((p[0]-a[0])*vx+(p[1]-a[1])*vy)/(vx*vx+vy*vy)))
    return (p[0]-a[0]-t*vx)**2+(p[1]-a[1]-t*vy)**2


def simplify(points: list[tuple[float, float]], tol: float = .85):
    """Douglas-Peucker iterativo; preserva início/fim e limites poligonais."""
    if len(points) <= 8:
        return points
    keep = {0, len(points)-1};stack = [(0,len(points)-1)];t2=tol*tol
    while stack:
        left,right = stack.pop()
        a,b=points[left],points[right]
        best=-1; idx=-1
        for i in range(left+1,right):
            d=sqdist(points[i],a,b)
            if d>best:best=d;idx=i
        if best>t2:
            keep.add(idx)
            stack.extend([(left,idx),(idx,right)])
    return [points[i] for i in sorted(keep)]


def project_paths(feat: dict, project) -> str:
    paths=[]
    for poly in polygon_coords(feat['geometry']):
        for ring in poly:
            pt=[project(v) for v in ring]
            pt=simplify(pt)
            if len(pt)<3:continue
            # arredondar para reduzir o HTML e carregar mais rápido
            parts=[f"M{pt[0][0]:.1f} {pt[0][1]:.1f}"]
            parts.extend(f"L{x:.1f} {y:.1f}" for x,y in pt[1:])
            parts.append('Z')
            paths.append(''.join(parts))
    return ''.join(paths)


def build_map(geo_path: Path, municipalities_path: Path | None, zones: list[dict], charging: list[dict]):
    features=as_geo(geo_path)
    ids=[extract_id(f,("zona_od_id","NumeroZona","numero_zona")) for f in features]
    expected={int(z['zona_od_id']) for z in zones}
    if len(features)!=527 or len(set(ids))!=527 or not expected.issubset(set(ids)) or len(expected)!=343:
        raise ValueError(f"GeoJSON precisa ter 527 zonas originais e cobrir as 343 da capital (encontradas {len(features)}, únicas {len(set(ids))})")
    selection=[(i,f) for i,f in zip(ids,features) if i in expected]
    if len(selection)!=343:
        raise ValueError('Mapa: há IDs duplicados ou zonas da capital ausentes')
    lon0, lat0, lon1, lat1=collect_bounds([f for _,f in selection])
    # Longitude é escalada pela latitude média para preservar aspecto geográfico aproximado.
    xfactor=math.cos(math.radians((lat0+lat1)/2))
    width=(lon1-lon0)*xfactor;height=lat1-lat0
    scale=min(930/width,700/height)
    ox=(1000-width*scale)/2;oy=(760-height*scale)/2
    def project(p):
        return ox+(p[0]-lon0)*xfactor*scale,oy+(lat1-p[1])*scale
    shapes=[{'id':i,'p':project_paths(f,project)} for i,f in selection]
    if any(not x['p'] for x in shapes):
        raise ValueError('GeoJSON contém polígono que desapareceu na preparação dos caminhos SVG')
    muns=[]
    if municipalities_path and municipalities_path.is_file():
        mfeatures=as_geo(municipalities_path)
        if len(mfeatures)!=39:
            raise ValueError(f"Esperados 39 polígonos municipais, recebidos {len(mfeatures)}")
        muns=[{'id':36,'p':project_paths(f,project)} for f in mfeatures
              if extract_id(f,("municipio_od_id",))==36]
        if len(muns)!=1:
            raise ValueError('GeoJSON de municípios não possui São Paulo (ID OD 36)')
    chargingXY=[]
    for p in charging:
        try:
            lon=float(p.get('longitude') or '')
            lat=float(p.get('latitude') or '')
        except ValueError:
            continue
        if lon0<=lon<=lon1 and lat0<=lat<=lat1:
            px,py=project([lon,lat]);chargingXY.append({'id':str(p['id_posto']),'x':round(px,1),'y':round(py,1)})
    return shapes,muns,chargingXY


def inject(template: str, obj: dict, image: str):
    if '__PI06_DATA__' not in template or '__PI06_IMAGE__' not in template:
        raise ValueError('modelo.html não é o template do PI06')
    # Impede fechamento acidental da tag <script> em rótulos externos/observações.
    dat=json.dumps(obj,ensure_ascii=False,separators=(',',':')).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
    return template.replace('__PI06_DATA__',dat).replace('__PI06_IMAGE__',json.dumps(image))



def normalize_label(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", str(text or "").upper()) if not unicodedata.combining(c)).strip()


REGIOES_2025_URL = "https://prefeitura.sp.gov.br/documents/d/licenciamento/2025_regioes_subprefeituras_e_distritos_municipais-1-"


def ler_regioes_sp(path: Path, distritos: list[dict], zonas: list[dict]) -> list[dict]:
    """Agrupa APENAS as zonas da capital nas cinco regiões oficiais da Prefeitura (2025).

    A relação se dá pelo nome oficial do distrito OD, verificada contra os 96 nomes
    municipais, sem aproximar posição geográfica ou atribuir região a município externo.
    """
    if not path.is_file():
        raise FileNotFoundError('Falta tabela oficial de regiões distribuída no site: '+str(path))
    catalog={}
    with path.open(encoding='utf-8-sig',newline='') as h:
        reader=csv.DictReader(h)
        if not {'distrito_nome','regiao'}.issubset(reader.fieldnames or []):
            raise ValueError('Regiões da capital: CSV sem distrito_nome/regiao')
        for row in reader:
            key=normalize_label(row['distrito_nome'])
            region=row['regiao']
            if region not in {'Centro','Leste','Norte','Oeste','Sul'} or key in catalog:
                raise ValueError('Região duplicada ou inválida: '+str(row))
            catalog[key]=region
    if len(catalog)!=96:
        raise ValueError(f'Regiões incompletas: {len(catalog)}/96 distritos')
    district_names={normalize_label(d['distrito_nome']) for d in distritos}
    if district_names != set(catalog):
        raise ValueError('Distritos da OD não coincidem com os 96 distritos oficiais da tabela de regiões. Faltam: '+str(sorted(district_names-set(catalog))))
    capital=[]
    for z in zonas:
        if int(z['municipio_od_id'])!=36:
            continue
        region=catalog.get(normalize_label(z['distrito_nome']))
        if not region:
            raise ValueError('Zona sem região por distrito: '+str(z['zona_od_id']))
        capital.append({**z,'regiao_sp':region})
    if len(capital)!=343:
        raise ValueError(f'Recorte da capital deve ter 343 zonas, encontradas {len(capital)}')
    return capital


def load_abve_annual(path: Path) -> list[dict[str, Any]]:
    """Série nacional ABVE, vendas BEV e híbridos comparáveis; não soma MHEV.

    2025/26 têm MHEV ausente na fonte por mudança de metodologia.
    Usar os 12 ou menos meses disponíveis e comparar com o MESMO período anterior.
    """
    if not path.exists():
        print(f'  AVISO: histórico ABVE não encontrado em {path}; painel histórico ficará indisponível')
        return []
    monthly={}
    with path.open(encoding="utf-8-sig",newline="") as handle:
        reader=csv.DictReader(handle,delimiter=";")
        needed={"periodo","abrangencia","bev","phev","hev","hev_flex"}
        if not needed.issubset(reader.fieldnames or []):
            raise ValueError("ABVE mensal sem colunas obrigatórias: "+str(needed-set(reader.fieldnames or [])))
        for row in reader:
            period=(row.get('periodo') or '').strip()
            if not re.fullmatch(r'202[2-6]-(0[1-9]|1[0-2])',period):
                continue
            if (row.get('abrangencia') or '').strip().lower()!='brasil':
                continue
            if period in monthly:
                raise ValueError('ABVE com mês duplicado: '+period)
            def value(k):
                v=str(row.get(k) or '').strip()
                if not v or not re.fullmatch(r'\d+',v):
                    raise ValueError(f'ABVE {period}: {k} ausente ou não inteiro')
                return int(v)
            monthly[period]={'bev':value('bev'),'hybrid':sum(value(k) for k in ('phev','hev','hev_flex'))}
    output=[]
    for year in range(2022,2027):
        months=[mo for mo in range(1,13) if f'{year}-{mo:02}' in monthly]
        if not months: continue
        # Não apresentar soma anual com meses intermediários ausentes como série completa.
        if months != list(range(1,max(months)+1)):
            raise ValueError(f'ABVE {year}: há lacunas de meses; revisar antes de gerar gráfico')
        bev=sum(monthly[f'{year}-{mo:02}']['bev'] for mo in months)
        hybrid=sum(monthly[f'{year}-{mo:02}']['hybrid'] for mo in months)
        prev=[monthly.get(f'{year-1}-{mo:02}') for mo in months]
        prior_total=sum(v['bev']+v['hybrid'] for v in prev) if all(v is not None for v in prev) else None
        output.append({'year':year,'months':len(months),'bev':bev,'hybrid':hybrid,
                       'prior_matching_total':prior_total,'source':'ABVE_DATA_POWERBI_BRASIL_VENDAS'})
    return output


def load_fleet_municipal(path: Path, municipios: list[dict[str,Any]]) -> list[dict[str,Any]]:
    """Retrato municipal da SENATRAN sem inventar frota por zona nem por tipo.

    Fonte agrega *todos os tipos de veículo* no arquivo combustível.
    """
    if not path.is_file():
        print(f'  AVISO: SENATRAN municipal ausente: {path}')
        return []
    names={normalize_label(str(m['municipio_nome'])):str(m['municipio_nome']) for m in municipios}
    result={}
    with path.open(encoding='utf-8-sig',newline='') as handle:
        reader=csv.DictReader(handle)
        need={'Município','Qtd. Veículos','categoria_visualizacao'}
        if not need.issubset(reader.fieldnames or []):
            raise ValueError('SENATRAN combustível: colunas faltantes')
        for x in reader:
            normalized=normalize_label(x.get('Município') or '')
            if normalized not in names: continue
            category=x.get('categoria_visualizacao','').strip()
            if category not in {'Gasolina','Híbrido','Elétrico'}: continue
            try: qty=int(str(x['Qtd. Veículos']).strip())
            except ValueError: raise ValueError('SENATRAN Qtd. Veículos inválida para '+normalized)
            if qty<0: raise ValueError('SENATRAN frota negativa: '+normalized)
            item=result.setdefault(normalized, {'municipio_nome':names[normalized],
                                                'Gasolina':0,'Híbrido':0,'Elétrico':0})
            item[category]+=qty
    return [result[x] for x in sorted(result)]


def load_fipe_years(path: Path) -> list[dict[str,Any]]:
    """Agrupa *ano-modelo* de preços FIPE coletados em novembro de 2026;
    NÃO é histórico de preços no respectivo ano-modelo.
    """
    if not path.is_file():
        print(f'  AVISO: FIPE parcial não encontrada: {path}')
        return []
    byyear={}
    with path.open(encoding='utf-8-sig',newline='') as handle:
        reader=csv.DictReader(handle)
        need={'ano_modelo','preco_fipe','combustivel_fipe'}
        if not need.issubset(reader.fieldnames or []):
            raise ValueError('FIPE parcial sem colunas de ano/preço/combustível')
        for r in reader:
            ano=str(r.get('ano_modelo') or '').strip()
            if not re.fullmatch('202[2-6]',ano): continue
            raw=str(r.get('preco_fipe') or '').replace('R$','').replace('.','').replace(',','.').strip()
            try: price=float(raw)
            except ValueError: continue
            if not math.isfinite(price) or price<=0: continue
            byyear.setdefault(int(ano),[]).append((price, str(r.get('combustivel_fipe') or '')))
    out=[]
    for y in sorted(byyear):
        vals=byyear[y]
        counts={'Gasolina':0,'Híbrido':0,'Elétrico':0}
        for _,category in vals:
            c=normalize_label(category)
            group='Híbrido' if 'HIBRID' in c else ('Elétrico' if 'ELETRIC' in c else 'Gasolina')
            counts[group]+=1
        out.append({'year':y,'qtd':len(vals),'mediana_brl':round(statistics.median(v[0] for v in vals),2),'categorias':counts,
                    'fonte':'FIPE_NOVEMBRO_2026_AMOSTRA_PARCIAL'})
    return out


def main():
    parser=argparse.ArgumentParser(description='Gera a apresentação HTML offline completa do PI06')
    parser.add_argument('--raiz',type=Path,default=Path.cwd(),help='Raiz do repositório PI06')
    parser.add_argument('--saida',type=Path,default=Path('apresentacao_PI06_capital_v22.html'),help='Arquivo final de apresentação')
    parser.add_argument('--geo',type=Path,default=Path('dados_relatorios/territorio_od2023/geo_zonas_od2023_rmsp.geojson'))
    parser.add_argument('--geo-municipios',type=Path,default=Path('dados_relatorios/territorio_od2023/geo_municipios_derivados_zonas_od2023.geojson'))
    parser.add_argument('--ocm',type=Path,default=Path('dados_limpos/10_OPEN_CHARGE_MAP_SP.csv'))
    parser.add_argument('--modelo',type=Path,default=None,help='Caminho do template modelo.html (normalmente ao lado do script)')
    args=parser.parse_args()
    root=args.raiz.resolve()
    folder=root/'dados_analiticos'/'cenarios_2026'
    manifest=folder/'manifesto_cenarios_analiticos.json'
    if not manifest.is_file():
        raise FileNotFoundError(f"Manifesto não encontrado: {manifest}")
    m=json.loads(manifest.read_text(encoding='utf-8-sig'))
    datasets={}
    for key,(filename,columns) in CSV_SPECS.items():
        path=folder/filename
        meta=(m.get('saidas_sha256') or {}).get(filename)
        if meta and sha(path)!=meta.get('sha256'):
            raise ValueError(f"{filename}: SHA256 divergente do manifesto. Recalcule os cenários antes de apresentar.")
        if key=='sensibilidade':
            count=read_csv(path,columns,only_count=True)
            if meta and count!=meta.get('linhas'):
                raise ValueError('Contagem da sensibilidade divergente do manifesto')
            datasets['sensibilidade_linhas']=count
        else:
            rows=read_csv(path,columns)
            if meta and len(rows)!=meta.get('linhas'):
                raise ValueError(f"{filename}: contagem diferente do manifesto")
            datasets[key]=rows
        print(f"  OK: {filename}")
    zones, municipalities, districts = datasets['zones'], datasets['municipios'], datasets['distritos']
    if (len(zones),len(municipalities),len(districts))!=(527,39,96):
        raise ValueError('Baseline territorial divergente: exigidas 527 zonas, 39 municípios e 96 distritos')
    if len({z['zona_od_id'] for z in zones})!=527:
        raise ValueError('Zonas duplicadas no CSV analítico')
    if len({x['municipio_od_id'] for x in municipalities})!=39:
        raise ValueError('Municípios duplicados no CSV analítico')
    for z in zones:
        if z['tem_amostra_origem'] and z['viagens_origem_expandidas'] is None:
            raise ValueError('Indicador de origem inconsistente com flag de amostra')
    # Recorte de apresentação: a OD cobre a RMSP, mas o site estuda somente São Paulo capital.
    zonas_capital=ler_regioes_sp(Path(__file__).resolve().parent/'regioes_sp_2025.csv',districts,zones)
    capital_ids={z['zona_od_id'] for z in zonas_capital}
    capital_flows=[x for x in datasets['fluxos']
                   if x['zona_origem_id'] in capital_ids and x['zona_destino_id'] in capital_ids]
    sp_municipio=[x for x in municipalities if int(x['municipio_od_id'])==36]
    if len(sp_municipio)!=1:
        raise ValueError('Dimensão municipal de São Paulo (ID OD 36) ausente')
    chargepath=args.ocm if args.ocm.is_absolute() else root/args.ocm
    with chargepath.open('r',encoding='utf-8-sig',newline='') as f:
        reader=csv.DictReader(f)
        req={'id_posto','titulo','latitude','longitude','status_cadastral','potencia_max_kw','cidade'}
        if not req.issubset(reader.fieldnames or []):
            raise ValueError(f'OCM faltando colunas: {req-set(reader.fieldnames or [])}')
        charging=[{k:r.get(k,'') for k in ['id_posto','titulo','operadora','logradouro','cidade','estado_provincia','cep','latitude','longitude','qtd_conexoes','potencia_max_kw','tipos_conectores','status_cadastral','custo_uso','data_coleta','fonte_url']} for r in reader]
    charging=[x for x in charging if normalize_label(x['cidade'])=='SAO PAULO']
    if len({p['id_posto'] for p in charging})!=len(charging):
        raise ValueError('Identificador repetido em eletropostos OCM')
    geo=args.geo if args.geo.is_absolute() else root/args.geo
    geom=args.geo_municipios if args.geo_municipios.is_absolute() else root/args.geo_municipios
    if not geo.exists():
        raise FileNotFoundError('Falta o GeoJSON das 527 zonas: '+str(geo)+'\nExecute integrar_od2023.py --shape ... --sobrescrever, ou use --geo CAMINHO')
    geo_shapes,mun_shapes,charge_xy=build_map(geo,geom,zonas_capital,charging)
    print(f'  OK: {len(geo_shapes)} zonas da capital, {len(mun_shapes)} limite municipal, {len(charge_xy)} pontos de recarga, {len(capital_flows)} fluxos internos')
    tpath=args.modelo or Path(__file__).resolve().parent/'modelo.html'
    template=tpath.read_text(encoding='utf-8')
    impath=Path(__file__).resolve().parent/'assets'/'od2023_mapa_referencia.jpg'
    image='data:image/jpeg;base64,'+base64.b64encode(impath.read_bytes()).decode('ascii') if impath.is_file() else ''
    history=load_abve_annual(root/'dados_padronizados/11_ABVE_VENDAS_TECNOLOGIA_BRASIL_MENSAL.csv')
    fleet=load_fleet_municipal(root/'dados_limpos/06_SENATRAN_COMBUSTIVEL_SP.csv',sp_municipio)
    fipe_years=load_fipe_years(root/'dados_limpos/08_FIPE_VEICULOS_PARCIAL.csv')
    print(f'  Contexto: {len(history)} anos ABVE, {len(fleet)} municípios SENATRAN, {len(fipe_years)} anos-modelo FIPE')
    obj={'full':True,'version':str(m.get('gerado_em_utc','2026-11-14')),'meta':{
        'zonas':len(zonas_capital),'municipios':1,'distritos':96,
        'amostra_origem':sum(int(float(z['viagens_origem_amostra'])) for z in zonas_capital if z['viagens_origem_amostra'] is not None),
        'energia_cenarios':len(datasets['energia']),
        'viagens_expandidas':round(sum(float(z['viagens_origem_expandidas']) for z in zonas_capital if z['viagens_origem_expandidas'] is not None),2),
        'sensibilidade_linhas':datasets['sensibilidade_linhas'],
        'saidas_sha256':{k:v.get('sha256') for k,v in m['saidas_sha256'].items()}},
        'zones':zonas_capital,'municipios':sp_municipio,'distritos':districts,
        'fluxos':capital_flows,'energia':datasets['energia'],
        'motoristas':datasets['motoristas'],'premissas':datasets['premissas'],
        'recarga':charging,'geo':geo_shapes,'municipioGeo':mun_shapes,'chargingXY':charge_xy,
        'historyAnnual':history,'fleet':fleet,'fipeYears':fipe_years}
    html=inject(template,obj,image)
    out=args.saida if args.saida.is_absolute() else root/args.saida
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(html,encoding='utf-8')
    print(f"\nSUCESSO! Apresentação offline: {out} ({out.stat().st_size/1024/1024:.2f} MiB)")
    print('Abra o arquivo HTML no navegador. Não é necessário instalar servidor nem conectar ao Supabase em sala.')

if __name__=='__main__':
    try:
        main()
    except (ValueError,FileNotFoundError,KeyError,TypeError) as e:
        print(f'ERRO DE PREPARAÇÃO: {e}',file=sys.stderr)
        sys.exit(2)
