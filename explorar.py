from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from pipeline_utils import REPORT_DIR, ROOT, localizar_todos


def _ler_tabela(caminho: Path) -> pd.DataFrame:
    sufixo = caminho.suffix.lower()
    if sufixo == ".csv":
        return pd.read_csv(caminho, low_memory=False)
    if sufixo in {".xlsx", ".xls"}:
        return pd.read_excel(caminho)
    if sufixo == ".dbf":
        import pyogrio
        return pyogrio.read_dataframe(caminho)
    if sufixo == ".sav":
        import pyreadstat
        df, _ = pyreadstat.read_sav(caminho)
        return df
    raise ValueError(f"Formato não suportado: {sufixo}")


def _perfil_tabela(caminho: Path) -> dict:
    df = _ler_tabela(caminho)
    total = max(1, df.shape[0] * max(1, df.shape[1]))
    nulos = int(df.isna().sum().sum())
    return {
        "arquivo": str(caminho.relative_to(ROOT)) if caminho.is_relative_to(ROOT) else str(caminho),
        "tipo": "tabela",
        "linhas": len(df),
        "colunas": len(df.columns),
        "duplicados": int(df.duplicated().sum()),
        "nulos": nulos,
        "percentual_nulos": round(100 * nulos / total, 3),
        "nomes_colunas": json.dumps([str(c) for c in df.columns], ensure_ascii=False),
        "crs": "",
        "geometrias_invalidas": "",
        "erro": "",
    }


def _perfil_shape(caminho: Path) -> dict:
    import geopandas as gpd

    try:
        gdf = gpd.read_file(caminho, encoding="utf-8")
    except UnicodeDecodeError:
        gdf = gpd.read_file(caminho)

    atributos = gdf.drop(columns="geometry")
    return {
        "arquivo": str(caminho.relative_to(ROOT)) if caminho.is_relative_to(ROOT) else str(caminho),
        "tipo": "geografico",
        "linhas": len(gdf),
        "colunas": len(gdf.columns),
        "duplicados": int(atributos.duplicated().sum()),
        "nulos": int(atributos.isna().sum().sum()),
        "percentual_nulos": "",
        "nomes_colunas": json.dumps([str(c) for c in gdf.columns], ensure_ascii=False),
        "crs": str(gdf.crs),
        "geometrias_invalidas": int((~gdf.geometry.is_valid).sum()) if not gdf.empty else 0,
        "erro": "",
    }


def catalogar() -> pd.DataFrame:
    padroes = [
        "dados_limpos/*.csv",
        "ANEEL/**/*.xlsx",
        "ANP/**/*.csv",
        "ANP/**/*.xlsx",
        "INMETRO/**/*.xlsx",
        "SENATRAN/**/*.xlsx",
        "ABVE/**/*.csv",
        "ORIGEM_E_DESTINO*/**/*.sav",
        "ORIGEM_E_DESTINO*/**/*.dbf",
        "ORIGEM_E_DESTINO*/**/*.shp",
        "IBGE*/**/*.shp",
    ]
    perfis = []
    for caminho in localizar_todos(padroes):
        try:
            print(f"Analisando: {caminho.name}")
            perfis.append(_perfil_shape(caminho) if caminho.suffix.lower() == ".shp" else _perfil_tabela(caminho))
        except Exception as exc:
            perfis.append({
                "arquivo": str(caminho), "tipo": "erro", "linhas": "", "colunas": "",
                "duplicados": "", "nulos": "", "percentual_nulos": "", "nomes_colunas": "",
                "crs": "", "geometrias_invalidas": "", "erro": str(exc),
            })

    catalogo = pd.DataFrame(perfis)
    catalogo.to_csv(REPORT_DIR / "catalogo_fontes.csv", index=False, encoding="utf-8-sig")
    return catalogo


def gerar_relatorio(catalogo: pd.DataFrame) -> Path:
    destino = REPORT_DIR / "relatorio_fontes.md"
    linhas = [
        "# Relatório automático das fontes\n\n",
        "Gerado pelo `explorar.py`. Use-o para detectar mudanças de estrutura, volume e qualidade.\n\n",
    ]
    for _, row in catalogo.iterrows():
        linhas += [
            f"## {row.get('arquivo', '')}\n",
            f"- Tipo: {row.get('tipo', '')}\n",
            f"- Linhas: {row.get('linhas', '')}\n",
            f"- Colunas: {row.get('colunas', '')}\n",
            f"- Duplicados: {row.get('duplicados', '')}\n",
        ]
        if row.get("crs"):
            linhas += [
                f"- CRS: {row.get('crs')}\n",
                f"- Geometrias inválidas: {row.get('geometrias_invalidas', '')}\n",
            ]
        if row.get("erro"):
            linhas.append(f"- Erro: `{row.get('erro')}`\n")
        linhas.append("\n")
    destino.write_text("".join(linhas), encoding="utf-8")
    return destino


def main() -> None:
    catalogo = catalogar()
    relatorio = gerar_relatorio(catalogo)
    print(f"\nCatálogo: {REPORT_DIR / 'catalogo_fontes.csv'}")
    print(f"Relatório: {relatorio}")
    if not catalogo.empty:
        cols = [c for c in ["arquivo", "tipo", "linhas", "colunas", "duplicados", "crs"] if c in catalogo.columns]
        print(catalogo[cols].to_string(index=False))


if __name__ == "__main__":
    main()
