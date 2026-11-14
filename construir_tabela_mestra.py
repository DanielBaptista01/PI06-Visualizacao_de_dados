"""PI06 — tabela mestre provisória e auditoria de correspondências.

Escopo: FIPE novembro/2026, INMETRO PBEV, catálogo Uber São Paulo.
O script NUNCA declara automaticamente a elegibilidade Uber nem atribui
consumo INMETRO a uma versão FIPE sem correspondência revisada.

Execução: python construir_tabela_mestra.py
"""
from __future__ import annotations

import argparse
import json
import re
import unicodedata
from pathlib import Path

import pandas as pd

BASE = Path(__file__).resolve().parent
COLS_CHAVE = ["brand_id", "model_id", "year_code"]
EQUIV_MARCA = {
    "GM CHEVROLET": "CHEVROLET", "GM": "CHEVROLET",
    "VW VOLKSWAGEN": "VOLKSWAGEN", "VW": "VOLKSWAGEN",
    "KIA MOTORS": "KIA", "JAC MOTORS": "JAC",
    "HYUNDAI MOTORS": "HYUNDAI", "LANDROVER": "LAND ROVER",
}


def norm(valor: object) -> str:
    if pd.isna(valor):
        return ""
    texto = unicodedata.normalize("NFKD", str(valor))
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = re.sub(r"[^A-Z0-9]+", " ", texto.upper()).strip()
    return " ".join(texto.split())


def marca_padrao(valor: object) -> str:
    n = norm(valor)
    return EQUIV_MARCA.get(n, n)


def preco_brl(valor: object) -> float | None:
    if pd.isna(valor):
        return None
    s = str(valor).strip().replace("R$", "").replace(" ", "")
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        n = float(s)
    except ValueError:
        return None
    return n if n > 0 else None


def tokens_iniciais(texto: str, prefixo: str) -> bool:
    """Confere limite de token: ONIX não deve casar com ONIXPLUS."""
    return bool(prefixo) and (texto == prefixo or texto.startswith(prefixo + " "))


def propulsao_fipe(combustivel: object) -> str:
    n = norm(combustivel)
    if "HIBR" in n:
        return "Híbrido (tipo não confirmado)"
    if "ELETR" in n:
        return "Elétrico"
    if n in {"GASOLINA", "ALCOOL", "ETANOL", "FLEX", "DIESEL"}:
        return "Combustão (revisar flex/híbrido)"
    return "Não identificado"


def executar(raiz: Path, saida: Path) -> dict:
    fipe_path = raiz / "dados_limpos/08_FIPE_VEICULOS_PARCIAL.csv"
    checkpoint_path = raiz / "dados_cache/fipe_precos_catalogados_checkpoint.csv"
    inmetro_path = raiz / "dados_limpos/05_INMETRO_VALIDADO.csv"
    uber_path = raiz / "dados_limpos/09_UBER_MODELOS_SP.csv"
    for p in [inmetro_path, uber_path]:
        if not p.is_file():
            raise FileNotFoundError(f"Arquivo necessário ausente: {p}")

    # Prioriza checkpoint mais recente se contiver mais chaves únicas para a referência.
    fontes_fipe = []
    for p in [fipe_path, checkpoint_path]:
        if p.is_file():
            temp = pd.read_csv(p, dtype=str, low_memory=False)
            exigidas = set(COLS_CHAVE + ["preco_fipe", "mes_referencia", "marca_fipe", "modelo_fipe", "ano_modelo"])
            if not exigidas.issubset(temp.columns):
                raise ValueError(f"FIPE sem colunas {sorted(exigidas - set(temp.columns))}: {p}")
            fontes_fipe.append((p, temp))
    if not fontes_fipe:
        raise FileNotFoundError("FIPE parcial/checkpoint não encontrados")

    # Mesma referência e chaves únicas; não confundir duplicação de histórico com cobertura.
    referencias = set()
    for _, df in fontes_fipe:
        referencias.update(df["mes_referencia"].dropna().str.strip().unique())
    if referencias != {"novembro de 2026"}:
        raise ValueError(f"Referência FIPE inesperada ou mista: {sorted(referencias)}")

    # Se houver um checkpoint com mais chaves, ele será a base; empates favorecem CSV de exportação.
    fi_path, fi = max(fontes_fipe, key=lambda p: len(p[1].drop_duplicates(COLS_CHAVE)))
    fi = fi.drop_duplicates(COLS_CHAVE, keep="last").copy()
    fi["preco_fipe_rs"] = fi["preco_fipe"].map(preco_brl)
    fi["marca_key"] = fi["marca_fipe"].map(marca_padrao)
    fi["modelo_key"] = fi["modelo_fipe"].map(norm)
    fi["ano_modelo_num"] = pd.to_numeric(fi["ano_modelo"], errors="coerce")
    fi["veiculo_id"] = fi[COLS_CHAVE].fillna("").agg(":".join, axis=1)
    fi["propulsao_fipe_inferida"] = fi["combustivel_fipe"].map(propulsao_fipe)
    if fi["veiculo_id"].duplicated().any():
        raise AssertionError("FIPE duplicada após deduplicação")

    u = pd.read_csv(uber_path, dtype=str, low_memory=False)
    i = pd.read_csv(inmetro_path, dtype=str, low_memory=False)
    uber_necessarias = {"marca", "modelo", "uberx_ano_min", "comfort_ano_min", "black_ano_min", "electric_ano_min"}
    inmetro_necessarias = {"marca", "modelo", "versao", "tipo_propulsao", "linha_origem_excel"}
    if not uber_necessarias.issubset(u.columns):
        raise ValueError(f"UBER: colunas ausentes {sorted(uber_necessarias - set(u.columns))}")
    if not inmetro_necessarias.issubset(i.columns):
        raise ValueError(f"INMETRO: colunas ausentes {sorted(inmetro_necessarias - set(i.columns))}")

    u["marca_key"] = u["marca"].map(marca_padrao)
    u["modelo_key"] = u["modelo"].map(norm)
    i["marca_key"] = i["marca"].map(marca_padrao)
    i["modelo_key"] = i["modelo"].map(norm)
    u_por_marca = {k: g for k, g in u.groupby("marca_key")}
    i_por_marca = {k: g for k, g in i.groupby("marca_key")}

    # Mapeamentos são candidatos, não a aplicação de consumo nem elegibilidade automática.
    candidatos_uber = []
    candidatos_inmetro = []
    auditoria = []
    for _, v in fi.iterrows():
        vid, mk, nome = v["veiculo_id"], v["marca_key"], v["modelo_key"]
        uber_c = []
        if mk in u_por_marca:
            for _, r in u_por_marca[mk].iterrows():
                # O nome Uber precisa ser prefixo delimitado do nome comercial da FIPE.
                if tokens_iniciais(nome, r["modelo_key"]):
                    uber_c.append(r)
                    for cat, campo in [
                        ("UberX", "uberx_ano_min"), ("Comfort", "comfort_ano_min"),
                        ("Black", "black_ano_min"), ("Electric", "electric_ano_min")
                    ]:
                        ano_min = pd.to_numeric(r[campo], errors="coerce")
                        if pd.notna(ano_min):
                            ano = v["ano_modelo_num"]
                            janela = "candidato_ano_compativel" if pd.notna(ano) and ano >= ano_min else (
                                "candidato_ano_inferior" if pd.notna(ano) else "ano_ausente_ou_zero_km"
                            )
                            candidatos_uber.append({
                                "veiculo_id": vid, "marca_fipe": v["marca_fipe"],
                                "modelo_fipe": v["modelo_fipe"], "ano_modelo": v["ano_modelo"],
                                "marca_uber": r["marca"], "modelo_uber": r["modelo"],
                                "categoria_uber": cat, "ano_min_catalogo": r[campo],
                                "status": janela, "elegibilidade_confirmada": False,
                            })
        inm_c = []
        if mk in i_por_marca:
            for _, r in i_por_marca[mk].iterrows():
                if tokens_iniciais(nome, r["modelo_key"]):
                    inm_c.append(r)
                    candidatos_inmetro.append({
                        "veiculo_id": vid, "marca_fipe": v["marca_fipe"],
                        "modelo_fipe": v["modelo_fipe"], "versao_fipe": v["modelo_fipe"],
                        "marca_inmetro": r["marca"], "modelo_inmetro": r["modelo"],
                        "versao_inmetro": r["versao"],
                        "tipo_propulsao_inmetro": r["tipo_propulsao"],
                        "linha_origem_excel": r["linha_origem_excel"],
                        "status": "candidato_por_marca_modelo_revisar_versao_ano",
                        "consumo_atribuido": False,
                    })
        auditoria.append({
            "veiculo_id": vid,
            "candidatos_uber": len(uber_c),
            "candidatos_inmetro": len(inm_c),
            "status_uber": "sem_candidato" if len(uber_c) == 0 else "revisar_manual",
            "status_inmetro": "sem_candidato" if len(inm_c) == 0 else "revisar_manual",
        })

    audit = pd.DataFrame(auditoria)
    mestre = fi.merge(audit, on="veiculo_id", how="left", validate="one_to_one")
    mestre["elegibilidade_uber_confirmada"] = False
    mestre["consumo_inmetro_confirmado"] = False
    mestre["consumo_gasolina_cidade_km_l"] = float("nan")
    mestre["consumo_etanol_cidade_km_l"] = float("nan")
    mestre["consumo_eletrico_kwh_km"] = float("nan")
    mestre["custo_energia_rs_km"] = float("nan")
    mestre["status_modelo_economico"] = "pendente_match_consumo"
    mestre["observacao"] = "Preço FIPE não demonstra elegibilidade Uber nem consumo de versão específica"

    saida.mkdir(parents=True, exist_ok=True)
    arquivos_saida = {
        "tabela_mestra_fipe_parcial.csv": mestre,
        "auditoria_matches.csv": audit,
        "candidatos_uber.csv": pd.DataFrame(candidatos_uber, columns=[
            "veiculo_id", "marca_fipe", "modelo_fipe", "ano_modelo", "marca_uber", "modelo_uber", "categoria_uber", "ano_min_catalogo", "status", "elegibilidade_confirmada"
        ]),
        "candidatos_inmetro.csv": pd.DataFrame(candidatos_inmetro, columns=[
            "veiculo_id", "marca_fipe", "modelo_fipe", "versao_fipe", "marca_inmetro", "modelo_inmetro", "versao_inmetro", "tipo_propulsao_inmetro", "linha_origem_excel", "status", "consumo_atribuido"
        ]),
    }
    for nome, dados in arquivos_saida.items():
        dados.to_csv(saida / nome, index=False, encoding="utf-8-sig")

    resumo = {
        "referencia_fipe": "novembro de 2026",
        "fonte_fipe": str(fi_path),
        "versoes_ano_fipe": int(len(mestre)),
        "com_preco_fipe_valido": int(mestre["preco_fipe_rs"].notna().sum()),
        "com_candidato_uber": int((audit["candidatos_uber"] > 0).sum()),
        "com_candidato_inmetro": int((audit["candidatos_inmetro"] > 0).sum()),
        "com_candidato_ambos": int(((audit["candidatos_uber"] > 0) & (audit["candidatos_inmetro"] > 0)).sum()),
        "elegibilidade_uber_confirmada_automaticamente": 0,
        "consumo_inmetro_atribuido_automaticamente": 0,
        "metodo": "candidatos por marca e prefixo de modelo com limite de token; sem homologação automática de versão",
    }
    (saida / "resumo_integracao.json").write_text(
        json.dumps(resumo, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(resumo, indent=2, ensure_ascii=False))
    print("Saídas:", saida)
    return resumo


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raiz", type=Path, default=Path("."))
    parser.add_argument("--saida", type=Path, default=Path("dados_relatorios/integracao_veiculos"))
    args = parser.parse_args()
    executar(args.raiz, args.saida)


if __name__ == "__main__":
    main()
