from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from pipeline_utils import (
    OUTPUT_DIR,
    localizar_coluna,
    localizar_primeiro,
    localizar_todos,
    normalizar_texto,
    registrar_coleta,
    salvar_csv,
)


def _filtrar_uf_sp(df: pd.DataFrame) -> pd.DataFrame:
    coluna = localizar_coluna(df, ["UF", "SG_UF", "SIGLA_UF", "ESTADO"], contem=True)
    if not coluna:
        return df
    valores = df[coluna].astype(str).map(normalizar_texto)
    mascara = valores.isin({"SP", "SAO PAULO"})
    return df.loc[mascara].copy() if mascara.any() else df


def _shape_zonas() -> Path | None:
    return localizar_primeiro(["ORIGEM_E_DESTINO*/**/Zonas_2023.shp", "**/Zonas_2023.shp"])


def _municipios_rmsp() -> set[str]:
    shape = _shape_zonas()
    if not shape:
        return set()
    try:
        import geopandas as gpd

        zonas = gpd.read_file(shape)
        if "NomeMunici" not in zonas.columns:
            return set()
        return {normalizar_texto(v) for v in zonas["NomeMunici"].dropna().unique()}
    except Exception as exc:
        print(f"Aviso: não foi possível ler municípios da RMSP: {exc}")
        return set()


def _filtrar_rmsp(df: pd.DataFrame, municipios: set[str]) -> pd.DataFrame:
    if not municipios:
        return df
    col = localizar_coluna(df, ["MUNICIPIO", "MUNICÍPIO", "CIDADE", "NOME_MUNICIPIO"], contem=True)
    if not col:
        return df
    return df.loc[df[col].astype(str).map(normalizar_texto).isin(municipios)].copy()


def processar_aneel() -> None:
    origem = localizar_primeiro(["ANEEL/data.xlsx", "ANEEL/**/*.xlsx"])
    if not origem:
        print("ANEEL: arquivo não encontrado.")
        return
    df = _filtrar_uf_sp(pd.read_excel(origem))
    destino = salvar_csv(df, "02_ANEEL_SP.csv")
    registrar_coleta("ANEEL", origem, destino, len(df), observacao="Tarifas filtradas para SP")
    print(f"ANEEL: {len(df):,} registros -> {destino}")


def processar_anp() -> None:
    arquivos = localizar_todos(["ANP/**/*.csv", "ANP/**/*.xlsx"])
    if not arquivos:
        print("ANP: arquivos não encontrados.")
        return
    dfs = []
    for origem in arquivos:
        try:
            if origem.suffix.lower() == ".csv":
                try:
                    temp = pd.read_csv(origem, sep=";", encoding="latin1")
                except Exception:
                    temp = pd.read_csv(origem)
            else:
                temp = pd.read_excel(origem)
            temp = _filtrar_uf_sp(temp)
            temp["_arquivo_origem"] = origem.name
            dfs.append(temp)
        except Exception as exc:
            print(f"ANP: erro em {origem.name}: {exc}")
    if not dfs:
        return
    df = pd.concat(dfs, ignore_index=True, sort=False)
    destino = salvar_csv(df, "03_ANP_SP.csv")
    registrar_coleta("ANP", "múltiplos arquivos", destino, len(df), observacao=f"{len(dfs)} arquivo(s) consolidados")
    print(f"ANP: {len(df):,} registros -> {destino}")


def processar_ibge() -> None:
    shape = localizar_primeiro(["IBGE*/**/SP_Municipios_2025.shp", "**/SP_Municipios_2025.shp"])
    municipios = _municipios_rmsp()
    if shape:
        try:
            import geopandas as gpd

            gdf = gpd.read_file(shape)
            col_nome = localizar_coluna(pd.DataFrame(gdf.drop(columns="geometry")), ["NM_MUN", "NOME", "MUNICIPIO"], contem=True)
            if municipios and col_nome:
                gdf = gdf.loc[gdf[col_nome].astype(str).map(normalizar_texto).isin(municipios)].copy()
            if gdf.crs is None:
                raise ValueError("Shape do IBGE sem CRS")
            crs_origem = str(gdf.crs)
            gdf = gdf.to_crs(4326)
            destino_geo = OUTPUT_DIR / "04_IBGE_RMSP.geojson"
            gdf.to_file(destino_geo, driver="GeoJSON")
            destino_csv = salvar_csv(pd.DataFrame(gdf.drop(columns="geometry")), "04_IBGE_RMSP.csv")
            registrar_coleta(
                "IBGE_MALHA_MUNICIPAL", shape, destino_geo, len(gdf),
                observacao="Malha da RMSP reprojetada para EPSG:4326",
                extras={"crs_origem": crs_origem, "csv_atributos": str(destino_csv)},
            )
            print(f"IBGE: {len(gdf):,} municípios da RMSP -> {destino_geo}")
            return
        except Exception as exc:
            print(f"IBGE: falha no Shape ({exc}); tentando Excel.")

    origem = localizar_primeiro(["IBGE*/**/SP_Municipios_2025.dbf.xlsx", "**/SP_Municipios_2025.dbf.xlsx"])
    if not origem:
        print("IBGE: nenhuma fonte encontrada.")
        return
    df = _filtrar_rmsp(pd.read_excel(origem), municipios)
    destino = salvar_csv(df, "04_IBGE_RMSP.csv")
    registrar_coleta("IBGE_MUNICIPIOS", origem, destino, len(df), observacao="Somente atributos; sem geometria")


def processar_inmetro() -> None:
    origem = localizar_primeiro(["INMETRO/dados-inmetro.xlsx", "INMETRO/**/*.xlsx"])
    if not origem:
        print("INMETRO: arquivo não encontrado.")
        return
    df = pd.read_excel(origem)
    destino = salvar_csv(df, "05_INMETRO.csv")
    registrar_coleta("INMETRO_PBEV", origem, destino, len(df))
    print(f"INMETRO: {len(df):,} registros -> {destino}")


def _grupo_senatran(nome: str) -> str:
    n = normalizar_texto(nome)
    if "COMBUSTIVEL" in n:
        return "combustivel"
    if "POTENCIA" in n:
        return "potencia"
    if "CEP" in n:
        return "cep"
    if "MARCA" in n or "MODELO" in n:
        return "marca_modelo"
    if "ANO" in n or "FAB MOD" in n or "FABRICACAO" in n:
        return "ano"
    if "TIPO" in n:
        return "tipo_veiculo"
    return "outros"


def processar_senatran() -> None:
    arquivos = localizar_todos(["SENATRAN/**/*.xlsx"])
    if not arquivos:
        print("SENATRAN: arquivos não encontrados.")
        return
    grupos: dict[str, list[pd.DataFrame]] = {}
    nomes: dict[str, list[str]] = {}
    for origem in arquivos:
        try:
            df = _filtrar_uf_sp(pd.read_excel(origem))
            df["_arquivo_origem"] = origem.name
            grupo = _grupo_senatran(origem.name)
            grupos.setdefault(grupo, []).append(df)
            nomes.setdefault(grupo, []).append(origem.name)
        except Exception as exc:
            print(f"SENATRAN: erro em {origem.name}: {exc}")

    saidas = {
        "tipo_veiculo": "06_SENATRAN_TIPO_VEICULO_SP.csv",
        "combustivel": "06_SENATRAN_COMBUSTIVEL_SP.csv",
        "marca_modelo": "06_SENATRAN_MARCA_MODELO_SP.csv",
        "ano": "06_SENATRAN_ANO_SP.csv",
        "potencia": "06_SENATRAN_POTENCIA_SP.csv",
        "cep": "06_SENATRAN_CEP_SP.csv",
        "outros": "06_SENATRAN_OUTROS_SP.csv",
    }
    for grupo, dfs in grupos.items():
        final = pd.concat(dfs, ignore_index=True, sort=False)
        destino = salvar_csv(final, saidas[grupo])
        registrar_coleta(f"SENATRAN_{grupo.upper()}", "múltiplos arquivos", destino, len(final), observacao="; ".join(nomes[grupo]))
        print(f"SENATRAN/{grupo}: {len(final):,} registros -> {destino}")


def _ler_od(origem: Path) -> pd.DataFrame:
    colunas = [
        "FE_VIA", "DIA_SEM", "ZONA_O", "MUNI_O", "ZONA_D", "MUNI_D",
        "H_SAIDA", "MIN_SAIDA", "H_CHEG", "MIN_CHEG", "DURACAO",
        "MODOPRIN", "TIPVG", "DISTANCIA", "MODO1", "MODO2", "MODO3", "MODO4", "ID_ORDEM",
    ]
    if origem.suffix.lower() == ".sav":
        import pyreadstat
        df, _ = pyreadstat.read_sav(origem, usecols=colunas)
        return df
    import pyogrio
    return pyogrio.read_dataframe(origem, columns=colunas)


def processar_od() -> None:
    origem = localizar_primeiro([
        "ORIGEM_E_DESTINO*/**/Banco2023_divulgacao_190225.sav",
        "**/Banco2023_divulgacao_190225.sav",
        "ORIGEM_E_DESTINO*/**/Banco2023_divulgacao_190225.dbf",
        "**/Banco2023_divulgacao_190225.dbf",
    ])
    if not origem:
        print("OD 2023: microdados .sav/.dbf não encontrados.")
        return

    df = _ler_od(origem)
    obrigatorias = ["MODOPRIN", "ZONA_O", "ZONA_D", "H_SAIDA", "MIN_SAIDA", "DURACAO", "DISTANCIA", "FE_VIA"]
    faltantes = [c for c in obrigatorias if c not in df.columns]
    if faltantes:
        raise ValueError(f"OD 2023 sem colunas obrigatórias: {faltantes}")

    app = df.loc[pd.to_numeric(df["MODOPRIN"], errors="coerce") == 12].copy()
    hora = pd.to_numeric(app["H_SAIDA"], errors="coerce").astype("Int64")
    app["faixa_horaria"] = hora.astype(str).str.zfill(2) + ":00-" + ((hora + 1) % 24).astype(str).str.zfill(2) + ":00"
    app["viagens_expandidas"] = pd.to_numeric(app["FE_VIA"], errors="coerce").fillna(0)
    app["distancia_linha_reta_km"] = pd.to_numeric(app["DISTANCIA"], errors="coerce") / 1000.0
    destino_micro = salvar_csv(app, "07_OD2023_APP_MICRODADOS.csv")

    agrupadores = ["DIA_SEM", "ZONA_O", "ZONA_D", "faixa_horaria"]

    def resumir(grupo: pd.DataFrame) -> pd.Series:
        pesos = pd.to_numeric(grupo["viagens_expandidas"], errors="coerce").fillna(0)
        duracao = pd.to_numeric(grupo["DURACAO"], errors="coerce")
        distancia = pd.to_numeric(grupo["distancia_linha_reta_km"], errors="coerce")

        def media_ponderada(valores: pd.Series) -> float:
            ok = valores.notna() & (pesos > 0)
            if not ok.any():
                return float("nan")
            return float((valores[ok] * pesos[ok]).sum() / pesos[ok].sum())

        return pd.Series({
            "amostra_viagens": len(grupo),
            "viagens_expandidas": float(pesos.sum()),
            "duracao_media_ponderada_min": media_ponderada(duracao),
            "distancia_linha_reta_media_ponderada_km": media_ponderada(distancia),
        })

    agregado = app.groupby(agrupadores, dropna=False).apply(resumir, include_groups=False).reset_index()
    destino_agg = salvar_csv(agregado, "07_OD2023_APP_ZONA_HORA.csv")

    geo_destino = None
    shape = _shape_zonas()
    if shape:
        try:
            import geopandas as gpd
            zonas = gpd.read_file(shape)
            if zonas.crs is None:
                raise ValueError("Shape das Zonas OD sem CRS")
            zonas = zonas.to_crs(4326)
            geo_destino = OUTPUT_DIR / "07_OD2023_ZONAS.geojson"
            zonas.to_file(geo_destino, driver="GeoJSON")
        except Exception as exc:
            print(f"OD 2023: microdados OK, Shape falhou: {exc}")

    registrar_coleta(
        "METRO_OD2023", origem, destino_micro, len(app), data_referencia="2023",
        observacao="Filtro MODOPRIN=12 (Táxi não convencional/aplicativo)",
        extras={
            "viagens_expandidas": float(app["viagens_expandidas"].sum()),
            "arquivo_agregado": str(destino_agg),
            "zonas_geojson": str(geo_destino or ""),
        },
    )
    print(f"OD 2023: {len(app):,} viagens amostrais; {app['viagens_expandidas'].sum():,.0f} expandidas -> {destino_agg}")


def processar_abve() -> None:
    municipios = _municipios_rmsp()
    fontes = {
        "11_ABVE_VENDAS_RMSP.csv": ["ABVE/**/dados_limpos_11_ABVE_VENDAS_MUNICIPIOS.csv", "**/dados_limpos_11_ABVE_VENDAS_MUNICIPIOS.csv"],
        "15_ABVE_ELETROPOSTOS_RMSP.csv": ["ABVE/**/dados_limpos_15_ABVE_ELETROPOSTOS*.csv", "**/dados_limpos_15_ABVE_ELETROPOSTOS*.csv"],
        "16_ABVE_VENDAS_MHEV_RMSP.csv": ["ABVE/**/dados_limpos_16_ABVE_VENDAS_MHEV_MUNICIPIOS.csv", "**/dados_limpos_16_ABVE_VENDAS_MHEV_MUNICIPIOS.csv"],
    }
    for nome_saida, padroes in fontes.items():
        origem = localizar_primeiro(padroes)
        if not origem:
            print(f"ABVE: fonte para {nome_saida} não localizada.")
            continue
        df = _filtrar_rmsp(pd.read_csv(origem), municipios)
        destino = salvar_csv(df, nome_saida)
        registrar_coleta("ABVE", origem, destino, len(df), observacao="Filtro RMSP via municípios das Zonas OD 2023")
        print(f"ABVE: {len(df):,} registros -> {destino}")

    origem_modelos = localizar_primeiro(["ABVE/**/dados_limpos_14_ABVE_VENDAS_POR_MODELO.csv", "**/dados_limpos_14_ABVE_VENDAS_POR_MODELO.csv"])
    if origem_modelos:
        df = pd.read_csv(origem_modelos)
        destino = salvar_csv(df, "14_ABVE_VENDAS_POR_MODELO.csv")
        registrar_coleta("ABVE_MODELOS", origem_modelos, destino, len(df))


def processar_uber() -> None:
    origem = localizar_primeiro(["UBER/modelos_carros_uber.html", "UBER/**/*.html", "UBER/**/*.mht"])
    if not origem:
        print("UBER: HTML/MHT não encontrado.")
        return

    from bs4 import BeautifulSoup
    soup = BeautifulSoup(origem.read_text(encoding="utf-8", errors="ignore"), "html.parser")
    dados = []
    conforto_geral, black_geral = 2019, 2019
    excecoes_comfort = {"ETIOS SEDAN": 2019, "COBALT": 2019}
    excecoes_black = {"CITY": 2023, "DOLPHIN": 2024, "VIRTUS": 2025, "PEUGEOT 2008": 2025}

    for bloco in soup.find_all("details"):
        summary = bloco.find("summary")
        if not summary:
            continue
        marca = summary.get_text(strip=True)
        for li in bloco.find_all("li"):
            tag_b = li.find("b")
            if not tag_b:
                continue
            modelo = tag_b.get_text(strip=True)
            texto = li.get_text(separator=" ", strip=True)

            def ano(categoria: str) -> int | None:
                achado = re.search(rf"(\d{{4}})\s*\([^)]*{re.escape(categoria)}", texto, flags=re.IGNORECASE)
                return int(achado.group(1)) if achado else None

            x, comfort, black, electric = ano("UberX"), ano("Comfort"), ano("Black"), ano("Electric")
            upper = modelo.upper()
            if comfort is not None:
                limite = next((v for k, v in excecoes_comfort.items() if k in upper), conforto_geral)
                comfort = max(comfort, limite)
            if black is not None:
                limite = next((v for k, v in excecoes_black.items() if k in upper), black_geral)
                black = max(black, limite)
            if any(v is not None for v in [x, comfort, black, electric]):
                dados.append({
                    "marca": marca, "modelo": modelo, "uberx_ano_min": x,
                    "comfort_ano_min": comfort, "black_ano_min": black, "electric_ano_min": electric,
                })

    df = pd.DataFrame(dados).drop_duplicates()
    destino = salvar_csv(df, "09_UBER_MODELOS_SP.csv")
    registrar_coleta("UBER_ELEGIBILIDADE", origem, destino, len(df), observacao="Regras extraídas do HTML/MHT arquivado")
    print(f"UBER: {len(df):,} regras -> {destino}")


def executar_bases() -> None:
    tarefas = [
        processar_aneel, processar_anp, processar_ibge, processar_inmetro,
        processar_senatran, processar_od, processar_abve, processar_uber,
    ]
    for tarefa in tarefas:
        print(f"\n=== {tarefa.__name__} ===")
        try:
            tarefa()
        except Exception as exc:
            print(f"Falha em {tarefa.__name__}: {exc}")


if __name__ == "__main__":
    executar_bases()
