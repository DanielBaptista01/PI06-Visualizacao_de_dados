"""PI06 — prepara filas auditáveis de revisão FIPE × INMETRO × Uber.
Nunca atribui consumo nem aprova elegibilidade automaticamente.
Execute após construir_tabela_mestra.py e auditar_matches_v2.py.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import pandas as pd

COLS_CHAVE = ["veiculo_id"]

def salvar_novo(df: pd.DataFrame, destino: Path) -> None:
    if destino.exists():
        raise FileExistsError(f"Arquivo já existe: {destino}. Preserve a revisão anterior.")
    df.to_csv(destino, index=False, encoding="utf-8-sig")

def executar(pasta: Path) -> None:
    arquivos = {
        "triagem": pasta / "triagem_priorizada_v2.csv",
        "inmetro": pasta / "candidatos_inmetro.csv",
        "uber": pasta / "candidatos_uber.csv",
    }
    for nome, caminho in arquivos.items():
        if not caminho.is_file():
            raise FileNotFoundError(f"{nome}: {caminho}")

    t = pd.read_csv(arquivos["triagem"], dtype=str).fillna("")
    i = pd.read_csv(arquivos["inmetro"], dtype=str).fillna("")
    u = pd.read_csv(arquivos["uber"], dtype=str).fillna("")
    if t["veiculo_id"].eq("").any() or t["veiculo_id"].duplicated().any():
        raise ValueError("Triagem tem chaves ausentes ou repetidas")
    if i["veiculo_id"].eq("").any() or u["veiculo_id"].eq("").any():
        raise ValueError("Candidatos têm chaves ausentes")

    # Apenas uma linha INMETRO para cada veículo do primeiro grupo.
    unico = t[t["fila_revisao"].eq("revisar_candidato_unico")].copy()
    candidatos = i[i["veiculo_id"].isin(unico["veiculo_id"])].copy()
    contagens = candidatos.groupby("veiculo_id").size()
    if len(unico) != len(contagens) or not contagens.eq(1).all():
        raise ValueError("Fila única deixou de ter exatamente um candidato INMETRO por FIPE")
    prefixo_i = candidatos[[
        "veiculo_id","marca_inmetro","modelo_inmetro","versao_inmetro",
        "tipo_propulsao_inmetro","linha_origem_excel"
    ]].copy()
    fila = unico.merge(prefixo_i, on="veiculo_id", validate="one_to_one")
    cats = (u[u["status"].eq("candidato_ano_compativel")]
            .groupby("veiculo_id")["categoria_uber"]
            .agg(lambda x: ";".join(sorted(set(x)))).rename("categorias_uber_ano"))
    fila = fila.join(cats, on="veiculo_id")
    fila["decisao_match_inmetro"] = "PENDENTE"
    fila["justificativa_match"] = ""
    fila["revisor"] = ""
    fila["data_revisao"] = ""
    fila["observacao_uber"] = "Ano compatível não confirma elegibilidade"
    salvar_novo(fila, pasta / "revisao_inmetro_candidato_unico_v3.csv")

    # Agrupamento de candidatos conflitantes para evitar revisão desordenada.
    amb = t[t["fila_revisao"].isin([
        "revisar_versoes_ambiguas", "revisar_propulsao_divergente"
    ])].copy()
    amb_c = i[i["veiculo_id"].isin(amb["veiculo_id"])].copy()
    detalhado = amb.merge(amb_c[[
        "veiculo_id","modelo_inmetro","versao_inmetro",
        "tipo_propulsao_inmetro","linha_origem_excel"
    ]], on="veiculo_id", how="left", validate="one_to_many")
    salvar_novo(detalhado, pasta / "revisao_inmetro_multiplos_candidatos_v3.csv")

    # Indicadores: sem inferência de versão ou tecnologia.
    print("=== PREPARACAO DE REVISAO V3 ===")
    print("FIPE na triagem:",len(t))
    print("Fila com candidato unico:",len(fila))
    print("Fila com multiplos candidatos:",len(amb))
    print("Linhas detalhadas dos multiplos:",len(detalhado))
    print("Candidatos únicos ainda homologados:",0)
    print("Arquivos gerados:")
    print(" -",pasta / "revisao_inmetro_candidato_unico_v3.csv")
    print(" -",pasta / "revisao_inmetro_multiplos_candidatos_v3.csv")
    print("\nATENCAO: conferir motor, ano e versao na fonte; nao aprovar só por nome.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--pasta", type=Path, default=Path("dados_relatorios/integracao_veiculos"))
    executar(parser.parse_args().pasta)
