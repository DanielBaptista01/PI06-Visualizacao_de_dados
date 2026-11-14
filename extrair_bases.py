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
    if coluna is None:
        raise ValueError("UF não identificada; recorte SP não comprovado")
    valores = df[coluna].astype("string").map(normalizar_texto)
    mascara = valores.isin({"SP", "SAO PAULO"})
    if not mascara.any():
        raise ValueError("Nenhum registro de SP encontrado; arquivo não processado")
    return df.loc[mascara].copy()

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


def _filtrar_rmsp(
    df: pd.DataFrame,
    municipios: set[str],
) -> pd.DataFrame:
    if not municipios:
        raise ValueError(
            "RMSP: lista de municípios vazia; "
            "não é possível confirmar o filtro geográfico."
        )

    col = localizar_coluna(
        df,
        ["MUNICIPIO", "MUNICÍPIO", "CIDADE", "NOME_MUNICIPIO"],
        contem=True,
    )

    if not col:
        raise ValueError(
            "RMSP: coluna de município não encontrada na fonte."
        )

    mascara = df[col].astype(str).map(normalizar_texto).isin(municipios)

    if not mascara.any():
        raise ValueError(
            "RMSP: o filtro não encontrou municípios correspondentes."
        )

    return df.loc[mascara].copy()


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
        raise FileNotFoundError("ANEEL: arquivo não encontrado no workspace")

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
    print(f"[OK] ANEEL | registros={len(df)} | saida={destino} | {observacao}")


def processar_anp() -> None:
    from pathlib import Path
    import unicodedata

    def normalizar(valor):
        texto = unicodedata.normalize("NFKD", str(valor))
        return "".join(
            c for c in texto
            if not unicodedata.combining(c)
        ).strip().upper()

    def converter_preco(valor):
        if pd.isna(valor):
            return float("nan")

        texto = (
            str(valor)
            .strip()
            .replace("R$", "")
            .replace(" ", "")
        )

        if "," in texto and "." in texto:
            texto = texto.replace(".", "").replace(",", ".")
        elif "," in texto:
            texto = texto.replace(",", ".")

        try:
            return float(texto)
        except ValueError:
            return float("nan")

    # Fonte selecionada explicitamente.
    origem = Path(
        "ANP/novembro-26/"
        "revendas_lpc_2026_11_08-2026_11_14.xlsx"
    )

    if not origem.is_file():
        raise FileNotFoundError(
            f"ANP: arquivo nao encontrado: {origem}"
        )

    print("\n[ANP] Iniciando processamento...")
    print("Fonte:", origem)

    # A linha 10 da planilha e o cabecalho real.
    df = pd.read_excel(
        origem,
        sheet_name="POSTOS REVENDEDORES",
        header=9,
        dtype=str,
    )

    df.columns = [normalizar(c) for c in df.columns]

    obrigatorias = {
        "CNPJ",
        "MUNICIPIO",
        "ESTADO",
        "PRODUTO",
        "UNIDADE DE MEDIDA",
        "PRECO DE REVENDA",
        "DATA DA COLETA",
    }

    ausentes = obrigatorias - set(df.columns)

    if ausentes:
        raise ValueError(
            f"ANP: colunas ausentes: {sorted(ausentes)}"
        )

    total_nacional = len(df)

    # Filtra o estado e os combustiveis relevantes.
    df["ESTADO"] = df["ESTADO"].map(normalizar)
    df["MUNICIPIO"] = df["MUNICIPIO"].map(normalizar)
    df["PRODUTO"] = df["PRODUTO"].map(normalizar)

    df = df.loc[
        df["ESTADO"].isin({"SAO PAULO", "SP"})
        & df["PRODUTO"].isin({"GASOLINA COMUM", "ETANOL"})
    ].copy()

    if df.empty:
        raise ValueError(
            "ANP: nenhum registro de gasolina ou etanol em SP"
        )

    print("Registros nacionais:", total_nacional)
    print("Registros selecionados em SP:", len(df))

    # Verifica a unidade de medida.
    unidades = df["UNIDADE DE MEDIDA"].map(normalizar)

    unidade_valida = unidades.isin({
        "R$ / LITRO",
        "R$/LITRO",
    })

    if not unidade_valida.all():
        print(
            df.loc[
                ~unidade_valida,
                ["PRODUTO", "UNIDADE DE MEDIDA"]
            ].drop_duplicates().to_string(index=False)
        )
        raise ValueError("ANP: unidades inesperadas")

    # Corrige tanto precos com virgula quanto com ponto.
    df["preco_rs_litro"] = (
        df["PRECO DE REVENDA"].apply(converter_preco)
    )

    # Valida todos os precos antes de descartar qualquer linha.
    invalidos = df[
        df["preco_rs_litro"].isna()
        | ~df["preco_rs_litro"].between(1, 20)
    ]

    if not invalidos.empty:
        print("\nPrecos invalidos ou suspeitos:")
        print(
            invalidos[
                ["MUNICIPIO", "PRODUTO",
                 "PRECO DE REVENDA", "preco_rs_litro"]
            ].head(15).to_string(index=False)
        )
        raise ValueError(
            f"ANP: {len(invalidos)} precos requerem revisao"
        )

    # Confere as datas da coleta.
    df["data_coleta"] = pd.to_datetime(
   df["DATA DA COLETA"],
    format="%Y-%m-%d %H:%M:%S",
    errors="coerce",
  )

    inicio = pd.Timestamp("2026-11-08")
    fim = pd.Timestamp("2026-11-14")

    datas_validas = df["data_coleta"].between(inicio, fim)

    if not datas_validas.all():
        print("\nDatas fora do periodo:")
        print(
            df.loc[
                ~datas_validas,
                ["DATA DA COLETA", "data_coleta"]
            ].head(15).to_string(index=False)
        )
        raise ValueError(
            "ANP: datas invalidas ou fora da semana"
        )

    # Mantem somente uma copia de linhas totalmente identicas.
    antes = len(df)
    df = df.drop_duplicates().copy()
    duplicadas = antes - len(df)

    df["periodo_inicio"] = "2026-11-08"
    df["periodo_fim"] = "2026-11-14"
    df["arquivo_origem"] = origem.name

    # Padroniza nomes para facilitar integracao posterior.
    df = df.rename(columns={
        "CNPJ": "cnpj",
        "MUNICIPIO": "municipio",
        "ESTADO": "estado",
        "PRODUTO": "produto",
        "UNIDADE DE MEDIDA": "unidade_medida",
        "BANDEIRA": "bandeira_posto",
    })

    df["data_coleta"] = df["data_coleta"].dt.strftime(
        "%Y-%m-%d"
    )

    # Medias por municipio e combustivel.
    resumo_municipios = (
        df.groupby(
            ["estado", "municipio", "produto"],
            as_index=False,
        )
        .agg(
            preco_medio_rs_litro=(
                "preco_rs_litro", "mean"
            ),
            preco_mediano_rs_litro=(
                "preco_rs_litro", "median"
            ),
            preco_minimo_rs_litro=(
                "preco_rs_litro", "min"
            ),
            preco_maximo_rs_litro=(
                "preco_rs_litro", "max"
            ),
            quantidade_observacoes=(
                "preco_rs_litro", "size"
            ),
            quantidade_postos=(
                "cnpj", "nunique"
            ),
        )
    )

    resumo_municipios["periodo_inicio"] = "2026-11-08"
    resumo_municipios["periodo_fim"] = "2026-11-14"

    # Recorte especifico da capital paulista.
    resumo_capital = resumo_municipios.loc[
        resumo_municipios["municipio"].eq("SAO PAULO")
    ].copy()

    if set(resumo_capital["produto"]) != {
        "GASOLINA COMUM", "ETANOL"
    }:
        raise ValueError(
            "ANP: faltam dados de gasolina ou etanol na capital"
        )

    # Validacao cruzada das agregacoes.
    if resumo_municipios["quantidade_observacoes"].sum() != len(df):
        raise ValueError(
            "ANP: total agregado diverge dos registros"
        )

    print("\n[ANP] Validacao:")
    print("Registros validos:", len(df))
    print("Duplicatas exatas removidas:", duplicadas)
    print("Municipios:", df["municipio"].nunique())
    print("Postos distintos:", df["cnpj"].nunique())

    print("\nPrecos estaduais por produto:")
    print(
        df.groupby("produto")["preco_rs_litro"]
        .agg(["count", "min", "mean", "max"])
        .to_string()
    )

    print("\nPrecos da capital:")
    print(
        resumo_capital[
            [
                "produto",
                "preco_medio_rs_litro",
                "preco_mediano_rs_litro",
                "quantidade_observacoes",
                "quantidade_postos",
            ]
        ].to_string(index=False)
    )

    # Exporta somente depois de todas as validacoes.
    destino_sp = salvar_csv(
        df,
        "03_ANP_SP_NOV2026.csv"
    )

    destino_municipios = salvar_csv(
        resumo_municipios,
        "03_ANP_PRECOS_MUNICIPIOS_NOV2026.csv"
    )

    destino_capital = salvar_csv(
        resumo_capital,
        "03_ANP_PRECOS_CAPITAL_NOV2026.csv"
    )

    registrar_coleta(
        "ANP",
        origem.name,
        destino_sp,
        len(df),
        observacao=(
            "Semana 2026-11-08 a 2026-11-14; "
            "São Paulo; gasolina comum e etanol; "
            f"{df['municipio'].nunique()} municipios"
        ),
    )

    print("\n[OK] ANP processada com sucesso")
    print("Registros SP:", destino_sp)
    print("Medias municipais:", destino_municipios)
    print("Medias capital:", destino_capital)
    
def processar_ibge() -> None:
    origem = localizar_primeiro([
        "IBGE*/**/*.shp",
        "IBGE*/**/*.dbf",
    ])

    if origem is None:
        raise FileNotFoundError(
            "IBGE: Shapefile ou DBF não encontrado."
        )

    import geopandas as gpd

    gdf = gpd.read_file(origem)
    df = pd.DataFrame(
        gdf.drop(columns="geometry", errors="ignore")
    )

    destino = salvar_csv(df, "04_IBGE_SP.csv")

    registrar_coleta(
        "IBGE_SP",
        origem,
        destino,
        len(df),
        observacao="Atributos da base geográfica IBGE",
    )

    print(f"IBGE: {len(df)} registros -> {destino}")

def processar_inmetro() -> None:
    """Lê a planilha organizada do INMETRO, preservando nulos e fonte RAW."""
    candidatos = localizar_todos(["INMETRO/**/*.xlsx"])
    organizados = [
        p for p in candidatos
        if normalizar_texto(p.stem) == "DADOS INMETRO ORGANIZADO"
    ]
    if len(organizados) != 1:
        raise FileNotFoundError(
            "INMETRO: esperado exatamente um arquivo de dados organizados "
            "na referência selecionada. Encontrados: "
            f"{[str(p) for p in organizados]}. "
            f"Todos os XLSX: {[p.name for p in candidatos]}"
        )

    origem = organizados[0]
    colunas_esperadas = [
        "categoria", "marca", "modelo", "versao", "motor",
        "tipo_propulsao", "consumo_energetico_mj_km",
        "autonomia_eletrica_km", "linha_origem_excel",
    ]
    # Aceita variantes de nome de aba, mas nunca assume a primeira aba.
    with pd.ExcelFile(origem) as excel:
        preferidas = [
            nome for nome in excel.sheet_names
            if normalizar_texto(nome) in {
                "DADOS ORGANIZADOS", "DADOS INMETRO ORGANIZADO"
            }
        ]
        if not preferidas:
            raise ValueError(
                f"INMETRO: aba organizada não encontrada em {origem.name}. "
                f"Abas disponíveis: {excel.sheet_names}"
            )
        if len(preferidas) != 1:
            raise ValueError(
                f"INMETRO: abas organizadas ambíguas: {preferidas}"
            )
        aba = preferidas[0]
        df = pd.read_excel(excel, sheet_name=aba, dtype=object)

    df.columns = [str(col).strip() for col in df.columns]
    faltantes = sorted(set(colunas_esperadas) - set(df.columns))
    if faltantes:
        raise ValueError(
            f"INMETRO: aba {aba!r} sem as colunas {faltantes}"
        )
    if df.empty:
        raise ValueError("INMETRO: aba organizada sem registros")

    chave = ["marca", "modelo", "versao", "motor", "tipo_propulsao"]
    grupos_repetidos = int(df.duplicated(subset=chave, keep=False).sum())
    vazios = df.isna().sum()
    destino = salvar_csv(df, "05_INMETRO_ORGANIZADO.csv")
    registrar_coleta(
        "INMETRO_PBEV", origem, destino, len(df),
        observacao=(
            f"Planilha organizada, aba={aba}; "
            "nulos e marcadores originais preservados; "
            f"{grupos_repetidos} linhas em grupos de chave repetida."
        ),
    )
    print(
        f"[OK] INMETRO | arquivo={origem.name} | aba={aba} | "
        f"registros={len(df)} | duplicidade_de_chave={grupos_repetidos} | "
        f"colunas_com_nulos={int((vazios > 0).sum())} | saida={destino}"
    )

def validar_inmetro() -> None:
    """Normaliza e valida o INMETRO sem modificar a base organizada."""
    import unicodedata

    origem = OUTPUT_DIR / "05_INMETRO_ORGANIZADO.csv"

    if not origem.is_file():
        raise FileNotFoundError(
            f"INMETRO: base organizada nao encontrada: {origem}"
        )

    df = pd.read_csv(origem, dtype=str, low_memory=False)

    total_original = len(df)

    # Corrige marcadores textuais de valores ausentes.
    df = df.replace(
        r"^\s*(?:\\|-|--|N/?A|NULO|NULL)?\s*$",
        pd.NA,
        regex=True,
    )

    def normalizar(valor):
        if pd.isna(valor):
            return ""

        texto = unicodedata.normalize("NFKD", str(valor))
        texto = "".join(
            c for c in texto
            if not unicodedata.combining(c)
        )

        return (
            texto.strip()
            .upper()
            .replace("–", "-")
            .replace("—", "-")
            .replace("_", "-")
            .replace(" ", "")
        )

    mapa_propulsao = {
        "COMBUSTAO": "Combustão",
        "ELETRICO": "Elétrico",
        "HIBRIDO": "Híbrido",
        "PLUG-IN": "Plug-in",
        "PLUGIN": "Plug-in",
    }

    originais = df["tipo_propulsao"].copy()

    df["tipo_propulsao"] = (
        originais.map(normalizar).map(mapa_propulsao)
    )

    invalidos = df["tipo_propulsao"].isna()

    if invalidos.any():
        print("\n[INMETRO] Propulsoes nao reconhecidas:")
        print(
            originais[invalidos]
            .value_counts(dropna=False)
            .to_string()
        )
        raise ValueError(
            "INMETRO: existem propulsoes nao reconhecidas"
        )

    def converter_numero(valor):
        if pd.isna(valor):
            return float("nan")

        texto = str(valor).strip().replace(" ", "")

        if "," in texto and "." in texto:
            texto = texto.replace(".", "").replace(",", ".")
        elif "," in texto:
            texto = texto.replace(",", ".")

        try:
            return float(texto)
        except ValueError:
            return float("nan")

    colunas_numericas = [
        "consumo_etanol_cidade_km_l",
        "consumo_etanol_estrada_km_l",
        "consumo_etanol_combinado_km_l",
        "consumo_gasolina_diesel_cidade_km_l",
        "consumo_gasolina_diesel_estrada_km_l",
        "consumo_gasolina_diesel_combinado_km_l",
        "consumo_energetico_mj_km",
        "autonomia_eletrica_km",
        "eficiencia_modo_eletrico_ve_vehp_gasolina_cidade_km_le",
        "eficiencia_modo_eletrico_ve_vehp_gasolina_estrada_km_le",
        "eficiencia_modo_eletrico_vehp_flex_etanol_cidade_km_le",
        "eficiencia_modo_eletrico_vehp_flex_etanol_estrada_km_le",
    ]

    for coluna in colunas_numericas:
        if coluna not in df.columns:
            raise ValueError(
                f"INMETRO: coluna ausente: {coluna}"
            )

        df[coluna] = df[coluna].map(converter_numero)

    if len(df) != total_original:
        raise ValueError(
            "INMETRO: quantidade de registros alterada"
        )

    print("\n[INMETRO] Registros:", len(df))

    print("\nPropulsao:")
    print(
        df["tipo_propulsao"]
        .value_counts(dropna=False)
        .to_string()
    )

    print("\nCobertura por propulsao (%):")
    cobertura = df.groupby("tipo_propulsao")[
        colunas_numericas
    ].agg(
        lambda serie: round(
            serie.notna().mean() * 100, 1
        )
    )

    print(cobertura.to_string())

    print("\nCombustiveis por propulsao:")
    print(
        pd.crosstab(
            df["tipo_propulsao"],
            df["combustivel"],
            dropna=False,
        ).to_string()
    )

    print("\nDuplicatas exatas:", df.duplicated().sum())

    destino = salvar_csv(
        df,
        "05_INMETRO_VALIDADO.csv"
    )

    registrar_coleta(
        "INMETRO_PBEV",
        origem,
        destino,
        len(df),
        observacao=(
            "Validacao de categorias de propulsao, "
            "nulos e indicadores de consumo; "
            "base organizada preservada"
        ),
    )

    print(
        f"\n[OK] INMETRO validado | "
        f"registros={len(df)} | saida={destino}"
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



def processar_senatran(
    arquivos_selecionados: list[Path] | None = None
) -> None:

    if arquivos_selecionados is not None:
        arquivos = arquivos_selecionados
    else:
        base = Path(__file__).resolve().parent / "SENATRAN"

        nomes = [
            "Setembro_2026/A_Frota_por_UF_Municipio_CEP_Setembro_2026.xlsx",
            "Setembro_2026/D_Frota_por_UF_Municipio_COMBUSTIVEL_Setembro_2026.xlsx",
            "Setembro_2026/E_Frota_por_UF_Municipio_POTENCIA_Setembro_2026.xlsx",
            "Setembro_2026/F_Frota_por_UF_Municipio_ANO_FAB_MOD_Setembro_2026.xlsx",
            "Setembro_2026/G_Frota_por_UF_Municipio_TIPO_ESPECIE_EIXOS_Setembro_2026.xlsx",
            "Julho-26/i_frota_por_uf_municipio_marca_e_modelo_ano_julho_2026(Sao_Paulo).xlsx",
        ]

        arquivos = [base / nome for nome in nomes]

    ausentes = [str(p) for p in arquivos if not p.is_file()]

    if ausentes:
        raise FileNotFoundError(
            "Arquivos SENATRAN ausentes:\n" + "\n".join(ausentes)
        )

    grupos: dict[str, list[pd.DataFrame]] = {}

    for origem in arquivos:
        try:
            grupo = _grupo_senatran(origem.name)
            nome = origem.stem.lower()

            # TRATAMENTO ESPECÍFICO DA FROTA POR TIPO DE VEÍCULO
            if grupo == "tipo_veiculo":
                if all(termo in origem.stem.upper()for termo in ("TIPO", "ESPECIE", "EIXOS")):
                    print(f"SENATRAN: processando layout G: {origem.name}")

                    df_g = pd.read_excel(
                        origem,
                        sheet_name="Layout G",
                        dtype=object,
                    )

                    import unicodedata

                    def normalizar_coluna(valor):
                        texto = unicodedata.normalize("NFKD", str(valor))
                        return "".join(
                            c for c in texto
                            if not unicodedata.combining(c)
                        ).strip().upper()

                    df_g.columns = [
                        normalizar_coluna(c) for c in df_g.columns
                    ]

                    exigidas = {
                        "UF", "MUNICIPIO", "TIPO VEICULO", "QTD. VEICULOS"
                    }
                    if not exigidas.issubset(df_g.columns):
                        raise ValueError(
                            f"Layout G incompatível: {origem.name}"
                        )

                    for coluna in ["UF", "MUNICIPIO", "TIPO VEICULO"]:
                        df_g[coluna] = df_g[coluna].map(normalizar_coluna)

                    df_g = df_g[
                        df_g["UF"].isin(["SP", "SAO PAULO"])
                    ].copy()

                    df_g["QTD. VEICULOS"] = pd.to_numeric(
                        df_g["QTD. VEICULOS"],
                        errors="coerce",
                    )

                    if (
                        df_g.empty
                        or df_g["QTD. VEICULOS"].isna().any()
                        or (df_g["QTD. VEICULOS"] < 0).any()
                    ):
                        raise ValueError("Layout G: quantidades inválidas")

                    total_origem = df_g["QTD. VEICULOS"].sum()
                    df = df_g.pivot_table(
                        index="MUNICIPIO",
                        columns="TIPO VEICULO",
                        values="QTD. VEICULOS",
                        aggfunc="sum",
                        fill_value=0,
                    ).reset_index()
                    df.columns.name = None

                    equivalencias = {
                        "CHASSI/PLATAFORMA": "CHASSI PLATAF",
                        "MICROONIBUS": "MICRO-ONIBUS",
                        "TRATOR DE ESTEIRAS": "TRATOR ESTEI",
                        "TRATOR DE RODAS": "TRATOR RODAS",
                    }
                    df = df.rename(columns=equivalencias)

                    if df.columns.duplicated().any():
                        raise ValueError("Layout G: colunas duplicadas")

                    tipos = [c for c in df.columns if c != "MUNICIPIO"]
                    df["TOTAL"] = df[tipos].sum(axis=1)
                    df.insert(0, "UF", "SP")

                    if df["TOTAL"].sum() != total_origem:
                        raise ValueError("Layout G: totais inconsistentes")

                    df["_referencia"] = "2026-09"
                else:
                    # Compatibilidade com layout municipal de julho.
                    if "por_municipio_e_tipo" not in nome:
                        print(f"SENATRAN: ignorado: {origem.name}")
                        continue

                    df = pd.read_excel(
                        origem,
                        sheet_name=0,
                        header=2,
                        dtype=object,
                    )
                    df.columns = [
                        str(c).strip().upper() for c in df.columns
                    ]

                    if not {"UF", "MUNICIPIO"}.issubset(df.columns):
                        raise ValueError("Cabeçalhos municipais ausentes")

                    df = df[
                        df["UF"].astype("string").str.strip().str.upper()
                        .eq("SP")
                    ].copy()
                    df["_referencia"] = "2026-07"
            else:
                df = pd.read_excel(origem)
                df = _filtrar_uf_sp(df)

            # Classificação específica da tabela de combustíveis.
            if grupo == "combustivel":
                coluna_combustivel = localizar_coluna(
                    df,
                    ["COMBUSTIVEL", "COMBUSTIVEL VEICULO"],
                    contem=True,
                )

                if not coluna_combustivel:
                    raise ValueError(
                        f"Coluna de combustível não encontrada em {origem.name}. "
                        f"Colunas disponíveis: {df.columns.tolist()}"
                    )

                # Diagnóstico dos valores originais.
                print("\nCombustíveis encontrados:")
                print(
                    df[coluna_combustivel]
                    .value_counts(dropna=False)
                    .to_string()
                )

                # Preserva o combustível original.
                df["combustivel_original"] = df[coluna_combustivel]

                # Cria a categoria analítica.
                from pipeline_utils import classificar_combustivel

                df["categoria_visualizacao"] = (
                    df[coluna_combustivel]
                    .apply(classificar_combustivel)
                )
                # Mantém somente as três categorias desejadas.
                df = df[
                    df["categoria_visualizacao"].isin(
                        ["Gasolina", "Híbrido", "Elétrico"]
                    )
                ].copy()

            df["_arquivo_origem"] = origem.name
            grupos.setdefault(grupo, []).append(df)

        except Exception as exc:
            raise RuntimeError(
                f"SENATRAN: falha ao processar {origem.name}"
            ) from exc

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

        final = pd.concat(
            dfs,
            ignore_index=True,
            sort=False,
        )

        # Remove colunas vazias e Unnamed.
        final = final.loc[
            :,
            ~final.columns.astype(str).str.contains(
                "^Unnamed",
                case=False,
                na=False,
            )
        ]

        final = final.dropna(how="all", axis=1)

        # Remove registros sem identificação geográfica,
        # quando essas colunas estiverem disponíveis.
        col_uf = next(
            (c for c in final.columns
             if str(c).strip().upper() == "UF"),
            None,
        )

        col_municipio = next(
            (c for c in final.columns
             if str(c).strip().upper() in
             {"MUNICIPIO", "MUNICÍPIO"}),
            None,
        )

        if col_uf and col_municipio:
            final = final.dropna(
                subset=[col_uf, col_municipio]
            )

        destino = salvar_csv(final, saidas[grupo])

        registrar_coleta(
            f"SENATRAN_{grupo.upper()}",
            "múltiplos arquivos",
            destino,
            len(final),
            observacao=(
                "Leitura com cabeçalhos específicos por fonte; "
                "frota municipal separada da frota estadual/nacional."
            ),
        )

        print(
            f"SENATRAN/{grupo}: "
            f"{len(final):,} registros -> {destino}"
        )


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

    print(f"OD 2023: Lendo microdados de {origem.name}...")

    # Lê o arquivo uma única vez
    if origem.suffix.lower() == ".sav":
        import pyreadstat
        df, metadata = pyreadstat.read_sav(origem)

    else:
        import pyogrio
        df = pyogrio.read_dataframe(origem)

        if "geometry" in df.columns:
            df = pd.DataFrame(df.drop(columns="geometry"))

    # Padroniza os nomes das colunas
    df.columns = [str(c).strip().upper() for c in df.columns]

    # Diagnóstico antes de qualquer filtro
    print("\n=== DIAGNÓSTICO OD 2023 ===")
    print("Total de colunas:", len(df.columns))
    print("MODOPRIN existe?", "MODOPRIN" in df.columns)
    print("Colunas disponíveis:")
    print(df.columns.tolist())

    candidatas = [
        c for c in df.columns
        if "MOD" in c or "PRIN" in c or "MODO" in c
    ]

    print("\nPossíveis colunas relacionadas ao modo:")
    print(candidatas)
    print("============================\n")

    if "MODOPRIN" not in df.columns:
        raise ValueError(
            "OD 2023: MODOPRIN não encontrada. "
            "Verifique as colunas apresentadas no diagnóstico."
        )

    # Filtra viagens por aplicativo
    app = df.loc[
        pd.to_numeric(df["MODOPRIN"], errors="coerce") == 12
    ].copy()

    print("\n=== VALIDAÇÃO DA OD FILTRADA ===")
    print("Total de viagens:", len(app))
    print("MODOPRIN:")
    print(app["MODOPRIN"].value_counts(dropna=False))
    print("FE_VIA preenchido:", app["FE_VIA"].notna().sum())
    print("FE_VIA ausente:", app["FE_VIA"].isna().sum())
    print("Soma dos fatores de expansão:", app["FE_VIA"].sum())
    print("================================")

    destino = salvar_csv(app, "07_ORIGEM_DESTINO.csv")

    registrar_coleta(
        "METRO_OD2023",
        origem,
        destino,
        len(app),
        data_referencia="2023",
        observacao="Microdados OD 2023 filtrados para aplicativo (MODOPRIN=12)"
    )

    print(
        f"OD 2023: {len(app):,} registros processados -> {destino}"
    )
   


def processar_abve() -> None:
    """
    Processa as bases da ABVE.

    - Filtra por RMSP as bases que possuem dados municipais.
    - Preserva bases nacionais e estaduais sem filtro municipal.
    - Mantém separadas as vendas acumuladas e mensais.
    - Registra a origem e a quantidade de registros processados.
    """

    municipios = _municipios_rmsp()

    # ---------------------------------------------------------
    # 1. CONFIGURAÇÃO DAS FONTES
    # ---------------------------------------------------------

    fontes = [
        {
            "saida": "abve_resumo_tecnologia.csv",
            "padroes": [
                "ABVE/**/abve_resumo_tecnologia.csv",
                "**/abve_resumo_tecnologia.csv",
            ],
            "filtro_rmsp": True,
            "observacao": "Resumo de tecnologias ABVE.",
        },

        {
            "saida": "11_ABVE_VENDAS_MUNICIPIOS_RMSP.csv",
            "padroes": [
                "ABVE/**/dados_limpos_11_ABVE_VENDAS_MUNICIPIOS.csv",
                "**/dados_limpos_11_ABVE_VENDAS_MUNICIPIOS.csv",
            ],
            "filtro_rmsp": True,
            "observacao": "Vendas por município, filtradas para a RMSP.",
        },

        {
            "saida": "14_ABVE_VENDAS_POR_MODELO.csv",
            "padroes": [
                "ABVE/**/dados_limpos_14_ABVE_VENDAS_POR_MODELO.csv",
                "**/dados_limpos_14_ABVE_VENDAS_POR_MODELO.csv",
            ],
            "filtro_rmsp": False,
            "observacao": (
                "Vendas agregadas por modelo. "
                "Sem dimensão temporal mensal."
            ),
        },

        {
            "saida": "abve_vendas_modelos.csv",
            "padroes": [
                "ABVE/**/abve_vendas_modelos.csv",
                "**/abve_vendas_modelos.csv",
            ],
            "filtro_rmsp": False,
            "observacao": "Base auxiliar de vendas por modelo.",
        },

        {
            "saida": "15_ABVE_ELETROPOSTOS_RMSP.csv",
            "padroes": [
                "ABVE/**/dados_limpos_15_ABVE_ELETROPOSTOS_SP.csv",
                "**/dados_limpos_15_ABVE_ELETROPOSTOS_SP.csv",
            ],
            "filtro_rmsp": True,
            "observacao": (
                "Distribuição de eletropostos por município, "
                "filtrada para a RMSP."
            ),
        },

        {
            "saida": "16_ABVE_VENDAS_MHEV_BRASIL.csv",
            "padroes": [
                "ABVE/**/dados_limpos_16_ABVE_VENDAS_MHEV_MUNICIPIOS.csv",
                "**/dados_limpos_16_ABVE_VENDAS_MHEV_MUNICIPIOS.csv",
            ],
            "filtro_rmsp": False,
            "observacao": (
                "Base nacional de vendas MHEV por município. "
                "Mantida sem filtro RMSP."
            ),
        },

        {
            "saida": "17_ABVE_EVOLUCAO_ELETROPOSTOS_SP.csv",
            "padroes": [
                "ABVE/**/dados_limpos_17_ABVE_EVOLUCAO_ELETROPOSTOS_SP.csv",
                "**/dados_limpos_17_ABVE_EVOLUCAO_ELETROPOSTOS_SP.csv",
            ],
            "filtro_rmsp": False,
            "observacao": (
                "Série temporal de eletropostos em âmbito estadual (SP). "
                "Não representa exclusivamente a RMSP."
            ),
        },

        {
            "saida": "14_ABVE_VENDAS_MODELOS_MENSAL_SP_2026.csv",
            "padroes": [
                "ABVE/**/dados_limpos_14_ABVE_VENDAS_MODELOS_MENSAL_SP_2026.csv",
                "**/dados_limpos_14_ABVE_VENDAS_MODELOS_MENSAL_SP_2026.csv",
            ],
            "filtro_rmsp": False,
            "mensal": True,
            "observacao": (
                "Vendas mensais por modelo, São Paulo capital, "
                "janeiro a março de 2026. "
                "Dados recuperados das capturas do Power BI."
            ),
        },
    ]

    # ---------------------------------------------------------
    # 2. PROCESSAMENTO DAS FONTES
    # ---------------------------------------------------------

    for fonte in fontes:

        nome_saida = fonte["saida"]
        padroes = fonte["padroes"]
        aplicar_filtro = fonte["filtro_rmsp"]

        print(f"\nProcessando ABVE: {nome_saida}")

        # Localiza o arquivo de origem
        origem = localizar_primeiro(padroes)

        if not origem:
            print(
                f"ABVE: fonte para {nome_saida} não localizada."
            )
            continue

        try:
            # Lê o CSV
            df = pd.read_csv(origem)

            if df.empty:
                print(
                    f"ABVE: arquivo vazio, ignorado: {origem}"
                )
                continue

            # -------------------------------------------------
            # 3. VALIDAÇÃO ESPECÍFICA DAS VENDAS MENSAIS
            # -------------------------------------------------

            if fonte.get("mensal", False):

                colunas_obrigatorias = [
                    "Ano",
                    "Mes",
                    "Data_Referencia",
                    "Municipio",
                    "Estado",
                    "Modelo",
                    "Fabricante",
                    "Veiculos_Vendidos",
                    "Part_Mercado_Pct",
                ]

                faltantes = [
                    coluna
                    for coluna in colunas_obrigatorias
                    if coluna not in df.columns
                ]

                if faltantes:
                    print(
                        "ABVE: arquivo mensal não processado. "
                        f"Colunas ausentes: {faltantes}"
                    )
                    continue

                # Confere se Ano e Mes são numéricos
                df["Ano"] = pd.to_numeric(
                    df["Ano"],
                    errors="coerce"
                )

                df["Mes"] = pd.to_numeric(
                    df["Mes"],
                    errors="coerce"
                )

                # Impede períodos inválidos
                if (
                    df["Ano"].isna().any()
                    or df["Mes"].isna().any()
                    or not df["Mes"].between(1, 12).all()
                ):
                    print(
                        "ABVE: existem períodos inválidos "
                        "na base mensal. Arquivo não processado."
                    )
                    continue

                # A captura recuperada é da capital paulista
                if not (
                    df["Municipio"].astype(str).str.strip()
                    .eq("São Paulo").all()
                    and df["Estado"].astype(str).str.strip()
                    .eq("SP").all()
                ):
                    print(
                        "ABVE: abrangência geográfica inesperada "
                        "na base mensal. Arquivo não processado."
                    )
                    continue

            # -------------------------------------------------
            # 4. FILTRO RMSP
            # -------------------------------------------------

            observacao = fonte["observacao"]

            if aplicar_filtro:

                # Só filtra se existir a coluna de município
                if "Municipio" in df.columns:

                    quantidade_antes = len(df)

                    df = _filtrar_rmsp(
                        df,
                        municipios
                    )

                    quantidade_depois = len(df)

                    observacao += (
                        f" Filtro RMSP aplicado: "
                        f"{quantidade_antes} registros originais; "
                        f"{quantidade_depois} após o filtro."
                    )

                    if df.empty:
                        print(
                            f"ABVE: nenhum registro permaneceu "
                            f"após o filtro RMSP em {nome_saida}."
                        )
                        continue

                else:
                    observacao += (
                        " Sem filtro municipal: "
                        "a fonte não possui coluna Municipio."
                    )

            # -------------------------------------------------
            # 5. SALVAMENTO
            # -------------------------------------------------

            destino = salvar_csv(
                df,
                nome_saida
            )

            # -------------------------------------------------
            # 6. REGISTRO DA COLETA
            # -------------------------------------------------

            registrar_coleta(
                "ABVE",
                origem,
                destino,
                len(df),
                observacao=observacao
            )

            print(
                f"ABVE concluído: "
                f"{len(df):,} registros -> {destino}"
            )

        except Exception as erro:

            print(
                f"ERRO ao processar {nome_saida}: {erro}"
            )

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
        marca_extraida = summary.get_text(" ", strip=True)
        marca_normalizada = re.sub(r"\s*Down\s*$", "", marca_extraida, flags=re.I).strip()
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
                    "marca": marca_normalizada, "modelo": modelo, "uberx_ano_min": x,
                    "comfort_ano_min": comfort, "black_ano_min": black, "electric_ano_min": electric,
                })

    df = pd.DataFrame(dados).drop_duplicates()
    destino = salvar_csv(df, "09_UBER_MODELOS_SP.csv")
    registrar_coleta("UBER_ELEGIBILIDADE", origem, destino, len(df), observacao="Regras extraídas do HTML/MHT arquivado")
    print(f"UBER: {len(df):,} regras -> {destino}")


def executar_bases() -> None:
    tarefas = [
        processar_aneel,
        processar_anp,
        processar_ibge,
        processar_inmetro,
        processar_senatran,
        processar_od,
        processar_abve,
        processar_uber,
    ]

    falhas = []

    for tarefa in tarefas:
        print(f"\n=== {tarefa.__name__} ===")

        try:
            tarefa()
        except Exception as exc:
            falhas.append(f"{tarefa.__name__}: {exc}")
            print(f"[ERRO] {tarefa.__name__}: {exc}")

    if falhas:
        raise RuntimeError(
            "O processamento de bases terminou com falhas:\n"
            + "\n".join(falhas)
        )

    print("\nProcessamento concluído sem exceções nas tarefas.")