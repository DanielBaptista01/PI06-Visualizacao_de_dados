from __future__ import annotations

import os
from datetime import date

import pandas as pd
import requests

from pipeline_utils import OUTPUT_DIR, registrar_coleta, salvar_csv

OCM_URL = "https://api.openchargemap.io/v3/poi/"


def _recortar_rmsp(df: pd.DataFrame) -> tuple[pd.DataFrame, bool]:
    zonas = OUTPUT_DIR / "07_OD2023_ZONAS.geojson"
    if not zonas.exists() or df.empty:
        return df, False
    try:
        import geopandas as gpd

        pontos = gpd.GeoDataFrame(
            df.copy(),
            geometry=gpd.points_from_xy(df["longitude"], df["latitude"]),
            crs="EPSG:4326",
        )
        gzonas = gpd.read_file(zonas).to_crs(4326)
        limite = gzonas[["geometry"]].dissolve()
        recorte = gpd.sjoin(pontos, limite, predicate="within", how="inner")
        recorte = pd.DataFrame(recorte.drop(columns=[c for c in ["geometry", "index_right"] if c in recorte.columns]))
        return recorte, True
    except Exception as exc:
        print(f"Open Charge Map: recorte espacial não aplicado: {exc}")
        return df, False


def coletar_open_charge_map() -> None:
    api_key = os.getenv("OPEN_CHARGE_MAP_API_KEY")
    if not api_key:
        raise RuntimeError("Defina OPEN_CHARGE_MAP_API_KEY no ambiente; não versione a chave no GitHub.")

    parametros = {
        "key": api_key,
        "countrycode": "BR",
        "latitude": -23.5505,
        "longitude": -46.6333,
        "distance": 100,
        "distanceunit": "KM",
        "maxresults": 1000,
        "compact": True,
        "verbose": False,
    }
    headers = {"User-Agent": "PI06-Visualizacao-de-Dados/1.0", "X-API-Key": api_key}
    resposta = requests.get(OCM_URL, params=parametros, headers=headers, timeout=30)
    resposta.raise_for_status()

    registros = []
    for item in resposta.json():
        endereco = item.get("AddressInfo") or {}
        conexoes = item.get("Connections") or []
        operador = item.get("OperatorInfo") or {}
        status = item.get("StatusType") or {}
        potencias = [c.get("PowerKW") for c in conexoes if c.get("PowerKW") is not None]
        conectores = sorted({
            (c.get("ConnectionType") or {}).get("Title", "Desconhecido")
            for c in conexoes if c.get("ConnectionType")
        })
        registros.append({
            "id_posto": item.get("ID"),
            "titulo": endereco.get("Title"),
            "operadora": operador.get("Title"),
            "logradouro": endereco.get("AddressLine1"),
            "cidade": endereco.get("Town"),
            "estado_provincia": endereco.get("StateOrProvince"),
            "cep": endereco.get("Postcode"),
            "latitude": endereco.get("Latitude"),
            "longitude": endereco.get("Longitude"),
            "qtd_conexoes": len(conexoes),
            "potencia_max_kw": max(potencias) if potencias else None,
            "tipos_conectores": ", ".join(conectores),
            "status_cadastral": status.get("Title"),
            "custo_uso_informado": item.get("UsageCost"),
            "data_coleta": date.today().isoformat(),
        })

    df = pd.DataFrame(registros)
    if not df.empty:
        df = df.dropna(subset=["latitude", "longitude"]).drop_duplicates(subset=["id_posto"], keep="last")
    df, recortado = _recortar_rmsp(df)
    destino = salvar_csv(df, "10_OPEN_CHARGE_MAP_SP.csv")
    registrar_coleta(
        "OPEN_CHARGE_MAP", OCM_URL, destino, len(df), data_referencia=date.today().isoformat(),
        observacao="Raio de 100 km + recorte pelas Zonas OD 2023" if recortado else "Raio de 100 km; sem recorte espacial",
    )
    print(f"Open Charge Map: {len(df):,} pontos -> {destino}")


def executar_apis() -> None:
    coletar_open_charge_map()


if __name__ == "__main__":
    executar_apis()
