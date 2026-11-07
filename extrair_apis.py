"""Coleta Open Charge Map, recorta município de São Paulo e valida os dados."""
from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import pandas as pd
import requests

from dotenv import load_dotenv
from pipeline_utils import OUTPUT_DIR, registrar_coleta, salvar_csv

load_dotenv(Path(__file__).resolve().parent / '.env')

OCM_URL = 'https://api.openchargemap.io/v3/poi/'
ARQUIVO_LIMITE = OUTPUT_DIR / '04_IBGE_RMSP.geojson'
ARQUIVO_SAIDA = '10_OPEN_CHARGE_MAP_SP.csv'
MAXRESULTS = 1000
COLUNAS = [
    'id_posto', 'titulo', 'operadora', 'logradouro', 'cidade',
    'estado_provincia', 'cep', 'latitude', 'longitude',
    'qtd_conexoes', 'potencia_max_kw', 'tipos_conectores',
    'status_cadastral', 'custo_uso', 'data_coleta',
    'fonte_url', 'recorte_geografico',
]


def _limite_municipio():
    """Usa o polígono municipal oficial de São Paulo (IBGE 3550308)."""
    import geopandas as gpd

    if not ARQUIVO_LIMITE.is_file():
        raise FileNotFoundError(
            f'Limite municipal ausente: {ARQUIVO_LIMITE}. '
            'Não é seguro substituir por um raio de 100 km.'
        )
    geometrias = gpd.read_file(ARQUIVO_LIMITE)
    if 'CD_MUN' not in geometrias.columns or geometrias.crs is None:
        raise ValueError('GeoJSON do IBGE sem CD_MUN ou CRS.')
    municipio = geometrias.loc[
        geometrias['CD_MUN'].astype(str).eq('3550308')
    ].to_crs('EPSG:4326')
    if len(municipio) != 1 or municipio.geometry.isna().any():
        raise ValueError('Município de São Paulo não identificado unicamente.')
    if municipio.geometry.is_empty.any() or not municipio.geometry.is_valid.all():
        raise ValueError('Geometria municipal inválida.')
    return municipio


def _texto(obj: object, padrao: str | None = None) -> str | None:
    if isinstance(obj, dict):
        valor = obj.get('Title') or obj.get('Name')
    elif isinstance(obj, str):
        valor = obj
    else:
        valor = None
    return str(valor).strip() if valor else padrao


def _extrair_postos(itens: list[dict]) -> pd.DataFrame:
    registros = []
    for item in itens:
        if not isinstance(item, dict):
            raise ValueError('Resposta OCM contém item inválido.')
        endereco = item.get('AddressInfo') or {}
        if not isinstance(endereco, dict):
            raise ValueError('AddressInfo inválido.')
        conexoes = item.get('Connections') or []
        if not isinstance(conexoes, list):
            raise ValueError('Connections inválido.')
        potencias = []
        tipos = set()
        for conexao in conexoes:
            if not isinstance(conexao, dict):
                continue
            kw = pd.to_numeric(conexao.get('PowerKW'), errors='coerce')
            if pd.notna(kw) and kw > 0:
                potencias.append(float(kw))
            tipo = _texto(conexao.get('ConnectionType')) or conexao.get('ConnectionTypeName')
            if tipo:
                tipos.add(str(tipo).strip())
        registros.append({
            'id_posto': item.get('ID'),
            'titulo': endereco.get('Title'),
            'operadora': _texto(item.get('OperatorInfo')),
            'logradouro': endereco.get('AddressLine1'),
            'cidade': endereco.get('Town'),
            'estado_provincia': endereco.get('StateOrProvince'),
            'cep': endereco.get('Postcode'),
            'latitude': endereco.get('Latitude'),
            'longitude': endereco.get('Longitude'),
            'qtd_conexoes': len(conexoes),
            'potencia_max_kw': max(potencias) if potencias else None,
            'tipos_conectores': ', '.join(sorted(tipos)) if tipos else None,
            'status_cadastral': _texto(item.get('StatusType')),
            'custo_uso': item.get('UsageCost'),
            'data_coleta': date.today().isoformat(),
            'fonte_url': (
                f"https://openchargemap.org/site/poi/details/{item.get('ID')}"
                if item.get('ID') is not None else None
            ),
            'recorte_geografico': 'municipio_sao_paulo_ibge_3550308',
        })
    return pd.DataFrame(registros, columns=COLUNAS)


def coletar_open_charge_map() -> pd.DataFrame:
    chave = os.getenv('OPEN_CHARGE_MAP_API_KEY', '').strip()
    if not chave:
        raise RuntimeError('OPEN_CHARGE_MAP_API_KEY ausente no .env.')

    municipio = _limite_municipio()
    resposta = requests.get(
        OCM_URL,
        params={
            'countrycode': 'BR',
            'latitude': -23.5505,
            'longitude': -46.6333,
            'distance': 100,
            'distanceunit': 'KM',
            'maxresults': MAXRESULTS,
            'compact': False,
            'verbose': False,
            'output': 'json',
        },
        headers={
            'User-Agent': 'PI06-Visualizacao-de-Dados/1.0',
            'X-API-Key': chave,
        },
        timeout=40,
    )
    resposta.raise_for_status()
    itens = resposta.json()
    if not isinstance(itens, list):
        raise ValueError('API OCM não retornou lista de pontos.')
    if len(itens) >= MAXRESULTS:
        raise RuntimeError(
            'Resposta atingiu maxresults=1000. Pode estar truncada. '
            'Divida a consulta geográfica antes de publicar.'
        )
    df = _extrair_postos(itens)
    if df.empty:
        raise RuntimeError('OCM retornou lista vazia; saída anterior preservada.')

    df['latitude'] = pd.to_numeric(df['latitude'], errors='coerce')
    df['longitude'] = pd.to_numeric(df['longitude'], errors='coerce')
    validas = df['latitude'].between(-90, 90) & df['longitude'].between(-180, 180)
    invalidas = int((~validas).sum())
    df = df.loc[validas].copy()
    if df['id_posto'].isna().any():
        raise ValueError('Existem postos sem ID OCM.')
    df['id_posto'] = df['id_posto'].astype('string')
    duplicados = int(df.duplicated('id_posto').sum())
    df = df.drop_duplicates('id_posto', keep='last')

    import geopandas as gpd
    pontos = gpd.GeoDataFrame(
        df,
        geometry=gpd.points_from_xy(df['longitude'], df['latitude']),
        crs='EPSG:4326',
    )
    zona = municipio.geometry.iloc[0]
    df_sp = pd.DataFrame(
        pontos.loc[pontos.geometry.intersects(zona)].drop(columns='geometry')
    )
    if df_sp.empty:
        raise RuntimeError('Nenhum posto no limite municipal; saída anterior preservada.')
    if df_sp.duplicated('id_posto').any():
        raise ValueError('Duplicatas após recorte espacial.')

    destino = salvar_csv(df_sp[COLUNAS], ARQUIVO_SAIDA)
    registrar_coleta(
        'OPEN_CHARGE_MAP', OCM_URL, destino, len(df_sp),
        data_referencia=date.today().isoformat(),
        observacao=(
            'Consulta raio 100 km; recorte oficial IBGE município SP 3550308; '
            f'API={len(itens)}, coordenadas_invalidas={invalidas}, '
            f'IDs_repetidos={duplicados}, dentro_SP={len(df_sp)}. '
            'Cadastro de pontos, não disponibilidade em tempo real.'
        ),
    )
    print(
        f'OCM: API={len(itens)} | coordenadas inválidas={invalidas} | '
        f'IDs repetidos={duplicados} | município SP={len(df_sp)} | {destino}'
    )
    return df_sp


def executar_apis() -> None:
    coletar_open_charge_map()


if __name__ == '__main__':
    executar_apis()
