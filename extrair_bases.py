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


def _ler_aneel(origem: Path) -> pd.DataFrame:
    """Lê a base de tarifas ANEEL em XLSX, CSV, CSV.GZ ou ZIP.

    Os formatos compactados são preservados no RAW e lidos diretamente pelo
    pandas, sem descompactar ou alterar o arquivo original no Storage.
    """
    nome = origem.name.lower()
    if nome.endswith(".xlsx"):
        return pd.read_excel(origem)

    if nome.endswith((".csv", ".csv.gz", ".zip")):
        ultimo_erro: Exception | None = None
        for separador in (";", ","):
            for encoding in ("utf-8-sig", "latin1"):
                try:
                    df = pd.read_csv(
                        origem,
                        sep=separador,
                        encoding=encoding,
                        compression="infer",
                        low_memory=False,
                    )
                    if len(df.columns) > 1:
                        return df
                except Exception as exc:
                    ultimo_erro = exc
        if ultimo_erro:
            raise ultimo_erro
        raise ValueError(f"ANEEL: não foi possível identificar o CSV em {origem.name}")

    raise ValueError(f"ANEEL: formato não suportado: {origem.name}")


def processar_aneel() -> None:
    origem = localizar_primeiro([
        "ANEEL/data.xlsx",
        "ANEEL/**/*.csv.gz",
        "ANEEL/**/*.zip",
        "ANEEL/**/*.csv",
        "ANEEL/**/*.xlsx",
    ])
    if not origem:
        print("ANEEL: arquivo não encontrado.")
        return

df_original = _ler_aneel(origem)

coluna_uf = localizar_coluna(
    df_original,
    ["UF", "SG_UF", "SIGLA_UF", "ESTADO"],
    contem=True,
)

if coluna_uf:
    df = _filtrar_uf_sp(df_original)
    nome_saida = "02_ANEEL_SP.csv"
    observacao = "Tarifas filtradas para SP"
else:
    df = df_original.copy()
    nome_saida = "02_ANEEL_NACIONAL.csv"
    observacao = (
        "Fonte sem coluna explícita de UF; "
        "não foi possível confirmar o recorte de SP"
    )

destino = salvar_csv(df, nome_saida)
registrar_coleta(
    "ANEEL",
    origem,
    destino,
    len(df),
    observacao=observacao,
)

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
                    temp = pd.read_csv(origem, sep=";", encoding="utf-8-sig", low_memory=False)
                except Exception:
                    temp = pd.read_csv(origem, sep=",", encoding="utf-8-sig", low_memory=False)
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
    
    # Limpa espaços extras nos nomes das colunas
    df.columns = df.columns.str.strip()
    
    # ---> REMOVE A COLUNA DE VALOR DE COMPRA SE ELA ESTIVER VAZIA OU NULA <---
    colunas_para_remover = ["Valor de Compra", "VALOR DE COMPRA"]
    for col in colunas_para_remover:
        if col in df.columns and df[col].isna().all():
            df = df.drop(columns=[col])
            print(f"ANP: Coluna '{col}' removida por estar 100% vazia.")

    destino = salvar_csv(df, "03_ANP_SP.csv")
    registrar_coleta("ANP", "múltiplos arquivos", destino, len(df), observacao=f"{len(dfs)} arquivo(s) consolidados")
    print(f"ANP: {len(df):,} registros -> {destino}")
    
def processar_ibge() -> None:
    origem = localizar_primeiro(["IBGE*/**/*.shp", "IBGE*/**/*.dbf", "**/*.shp"])
    if not origem:
        print("IBGE: arquivo não encontrado.")
        return
    try:
        import geopandas as gpd
        gdf = gpd.read_file(origem)
        if "geometry" in gdf.columns:
            gdf = pd.DataFrame(gdf.drop(columns="geometry"))
        
        # Padroniza preenchimento de concentrações urbanas ausentes
        if "CD_CONCURB" in gdf.columns:
            gdf["CD_CONCURB"] = gdf["CD_CONCURB"].fillna(0)
        if "NM_CONCURB" in gdf.columns:
            gdf["NM_CONCURB"] = gdf["NM_CONCURB"].fillna("Não aplicável")

        destino = salvar_csv(gdf, "04_IBGE_SP.csv")
        registrar_coleta("IBGE_SP", origem, destino, len(gdf), observacao="Tratamento de vazios em concentração urbana")
        print(f"IBGE SP: {len(gdf):,} registros -> {destino}")
    except Exception as exc:
        print(f"IBGE: erro ao processar: {exc}")

def processar_inmetro() -> None:
    arquivos = localizar_todos(["INMETRO/**/*.xlsx"])

    if not arquivos:
        print("INMETRO: nenhum arquivo XLSX encontrado.")
        return

    # Prioriza a planilha que contém as tabelas extraídas do PBEV.
    escolhido = None
    abas_tabela = []

    for origem in arquivos:
        try:
            xls = pd.ExcelFile(origem)
            abas = [
                aba for aba in xls.sheet_names
                if re.fullmatch(r"Table\d+ \(Page \d+\)", aba)
            ]

            if abas:
                escolhido = origem
                abas_tabela = abas
                break

        except Exception as exc:
            print(f"INMETRO: não foi possível inspecionar {origem.name}: {exc}")

    if escolhido is None:
        print(
            "INMETRO: não encontrei abas Table... (Page ...). "
            "Não gerei uma tabela supostamente limpa."
        )
        return

    print(f"INMETRO: fonte selecionada: {escolhido}")
    registros = []

    colunas_base = [
        "categoria",
        "marca",
        "modelo",
        "versao",
        "motor",
        "tipo_propulsao",
        "transmissao",
        "ar_condicionado",
        "direcao_assistida",
        "combustivel",
    ]

    for aba in abas_tabela:
        bruto = pd.read_excel(
            escolhido,
            sheet_name=aba,
            header=None,
            dtype=object,
        )

        for indice, linha in bruto.iterrows():
            # As linhas de veículos precisam ter categoria, marca,
            # modelo e versão. Isso elimina boa parte dos cabeçalhos.
            primeiros = linha.iloc[:4]

            if primeiros.isna().any():
                continue

            categoria, marca, modelo, versao = [
                normalizar_texto(v) for v in primeiros.tolist()
            ]

            if (
                categoria in {"CATEGORIA", "COLUMN1", ""}
                or marca in {"MARCA", "COLUMN2", ""}
                or modelo in {"MODELO", "COLUMN3", ""}
                or versao in {"VERSAO", "COLUMN4", ""}
            ):
                continue

            registro = {
                "_aba_origem": aba,
                "_linha_origem": int(indice) + 1,
            }

            for posicao, nome in enumerate(colunas_base):
                registro[nome] = linha.iloc[posicao]

            # Preserva os demais valores sem inventar nomes técnicos
            # para colunas cuja posição varia entre as páginas.
            for posicao in range(10, len(linha)):
                registro[f"campo_bruto_{posicao:02d}"] = linha.iloc[posicao]

            registros.append(registro)

    if not registros:
        print("INMETRO: nenhuma linha de veículo reconhecida.")
        return

    df = pd.DataFrame(registros)

    # Não remove duplicatas automaticamente: primeiro precisamos
    # distinguir duplicação real de repetição/extração da fonte.
    duplicadas = df.duplicated(
        subset=["marca", "modelo", "versao", "motor", "tipo_propulsao"],
        keep=False,
    ).sum()

    destino = salvar_csv(df, "05_INMETRO_BRUTO_VALIDACAO.csv")

    registrar_coleta(
        "INMETRO_PBEV",
        escolhido,
        destino,
        len(df),
        observacao=(
            "Extração das abas por página; campos técnicos brutos preservados; "
            f"{duplicadas} linhas pertencem a grupos com chave de veículo repetida; "
            "mapeamento de consumo/autonomia pendente de validação"
        ),
    )

    print(f"INMETRO: {len(df):,} registros extraídos -> {destino}")
    print(f"INMETRO: {duplicadas:,} linhas em grupos com chave repetida.")
    print(
        "Atenção: os campos campo_bruto_* ainda não estão prontos "
        "para cálculos de consumo ou autonomia."
    )

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
            grupo = _grupo_senatran(origem.name)
            
            # Pula as linhas de cabeçalho descritivo se for a tabela de tipo de veículo
            if grupo == "tipo_veiculo":
                df = pd.read_excel(origem, skiprows=3)
            else:
                df = pd.read_excel(origem)
                
            df = _filtrar_uf_sp(df)
            df["_arquivo_origem"] = origem.name
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
        if grupo not in saidas:
            continue
        final = pd.concat(dfs, ignore_index=True, sort=False)
        
        # Remove colunas Unnamed e colunas totalmente nulas
        final = final.loc[:, ~final.columns.astype(str).str.contains('^Unnamed', case=False, na=False)]
        final = final.dropna(how='all', axis=1)
        final = final.dropna(subset=["UF", "Município"] if "UF" in final.columns and "Município" in final.columns else [])
        
        destino = salvar_csv(final, saidas[grupo])
        registrar_coleta(f"SENATRAN_{grupo.upper()}", "múltiplos arquivos", destino, len(final), observacao="Limpeza de colunas vazias e Unnamed")
        print(f"SENATRAN/{grupo}: {len(final):,} registros limpos -> {destino}")


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
    # 1. Procura o arquivo de microdados .sav ou .dbf nas pastas de origem
    origem = localizar_primeiro([
        "ORIGEM_E_DESTINO*/**/Banco2023_divulgacao_190225.sav",
        "**/Banco2023_divulgacao_190225.sav",
        "ORIGEM_E_DESTINO*/**/Banco2023_divulgacao_190225.dbf",
        "**/Banco2023_divulgacao_190225.dbf",
    ])
    
    if not origem:
        print("OD 2023: microdados .sav/.dbf não encontrados.")
        return

    print(f"OD 2023: Lendo microdados de {origem.name}...")
    
    # 2. Lê usando a biblioteca apropriada (pyreadstat para .sav ou pyogrio para .dbf)
    if origem.suffix.lower() == ".sav":
        import pyreadstat
        df, _ = pyreadstat.read_sav(origem)
    else:
        import pyogrio
        df = pyogrio.read_dataframe(origem)
        if "geometry" in df.columns:
            df = pd.DataFrame(df.drop(columns="geometry"))

    # 3. Normaliza os nomes das colunas para letras maiúsculas para evitar erros de busca
    df.columns = [c.upper() for c in df.columns]

    # 4. Filtra as viagens por aplicativo (MODOPRIN == 12)
    if "MODOPRIN" in df.columns:
        app = df.loc[pd.to_numeric(df["MODOPRIN"], errors="coerce") == 12].copy()
    else:
        print("Aviso: coluna MODOPRIN não encontrada. Mantendo base completa.")
        app = df.copy()

    # 5. Salva diretamente como o novo CSV limpo na pasta dados_limpos/
    # (Isso vai substituir o arquivo antigo problemático)
    destino = salvar_csv(app, "07_ORIGEM_DESTINO.csv")
    
    registrar_coleta(
        "METRO_OD2023", origem, destino, len(app), data_referencia="2023",
        observacao="Microdados OD 2023 filtrados para aplicativo (MODOPRIN=12)"
    )
    print(f"OD 2023: {len(app):,} registros processados -> {destino}")

   

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
