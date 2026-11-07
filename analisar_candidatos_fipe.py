
import json
from pathlib import Path

import pandas as pd

ENTRADA = Path("dados_cache/fipe_mapeamento.csv")
SAIDA = Path("dados_relatorios/fipe_candidatos_revisao.csv")


def gerar_candidatos() -> None:
    df = pd.read_csv(ENTRADA, dtype=str)

    colunas = {"marca_uber", "modelo_uber", "status", "candidatos_modelos"}
    faltantes = colunas - set(df.columns)

    if faltantes:
        raise ValueError(f"Colunas ausentes: {faltantes}")

    status_revisao = {
        "revisao_modelo_ambiguo",
        "revisao_prefixo_unico",
    }

    registros = []

    for _, row in df[df["status"].isin(status_revisao)].iterrows():
        bruto = row["candidatos_modelos"]

        if pd.isna(bruto):
            raise ValueError(
                f"Candidatos ausentes: {row['marca_uber']} {row['modelo_uber']}"
            )

        candidatos = json.loads(bruto)

        for candidato in candidatos:
            registros.append({
                "marca_uber": row["marca_uber"],
                "modelo_uber": row["modelo_uber"],
                "status_origem": row["status"],
                "brand_id": row.get("brand_id"),
                "model_id": candidato["code"],
                "modelo_fipe": candidato["name"],
                "status_validacao": "pendente",
            })

    resultado = pd.DataFrame(registros)

    if resultado.empty:
        raise ValueError("Nenhum candidato encontrado.")

    duplicatas = resultado.duplicated(
        ["marca_uber", "modelo_uber", "brand_id", "model_id"]
    ).sum()

    if duplicatas:
        raise ValueError(f"Encontradas {duplicatas} duplicatas.")

    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    resultado.to_csv(SAIDA, index=False, encoding="utf-8-sig")

    print(f"Modelos Uber em revisão: {df['status'].isin(status_revisao).sum()}")
    print(f"Versões FIPE candidatas: {len(resultado)}")
    print(f"Arquivo gerado: {SAIDA}")


if __name__ == "__main__":
    gerar_candidatos()
