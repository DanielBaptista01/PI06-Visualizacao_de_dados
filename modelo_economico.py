"""PI06 — modelo econômico auditável para cenários da etapa 1.9.

Executar na raiz do projeto, ao lado de consolidar_variaveis_19.py:
    python modelo_economico.py

Reutiliza as validações e fórmulas do módulo da etapa 1.9.
NÃO preenche preços, não cria lucro para cenários incompletos e não altera entradas.
"""
from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from consolidar_variaveis_19 import (
    CENARIO_COLS,
    _calcular,
    _localizar_mestre,
    _ofertas,
    _veiculos,
    executar as atualizar_etapa19,
)

CHAVES = [
    "cenario_id", "modalidade", "status", "km_mes", "horas_online_mes",
    "receita_brl_hora_online", "receita_mensal_brl", "custo_total_mensal_brl",
    "custo_fixo_mensal_estimado_brl", "custo_variavel_por_km_estimado_brl",
    "custo_total_por_km_brl", "receita_minima_brl_hora_online",
    "receita_minima_brl_km", "resultado_liquido_estimado_brl",
    "margem_estimada_pct", "fonte_parametros", "observacoes", "lacunas",
]


def numero(valor: object) -> float | None:
    if pd.isna(valor) or str(valor).strip() == "":
        return None
    s = str(valor).strip().replace("R$", "").replace(" ", "")
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    n = float(s)
    if not math.isfinite(n) or n < 0:
        raise ValueError(f"Número monetário inválido: {valor!r}")
    return n


def decompor_componentes(texto: str, km: float) -> tuple[float | None, float | None]:
    """Lê itens calculados pela etapa 1.9; classifica custos fixos/variáveis."""
    if km <= 0:
        raise ValueError("km_mes deve ser >0")
    if not texto or pd.isna(texto):
        return None, None
    fixos = {"licenciamento", "ipva", "seguro", "depreciacao", "aluguel", "outros"}
    variaveis = {"manutencao", "pneus", "combustivel", "energia"}
    f = v = 0.0
    for parte in str(texto).split("; "):
        if not parte.strip():
            continue
        chave, sep, valor = parte.partition("=")
        if not sep:
            raise ValueError(f"Componente econômico inválido: {parte}")
        n = numero(valor)
        if n is None:
            raise ValueError(f"Componente econômico sem valor: {parte}")
        if chave in fixos:
            f += n
        elif chave in variaveis:
            v += n
        else:
            raise ValueError(f"Componente desconhecido: {chave}")
    return round(f, 2), round(v / km, 6)


def rodar(raiz: Path) -> tuple[Path, int, int]:
    raiz = raiz.resolve()
    script_origem = raiz / "consolidar_variaveis_19.py"
    if not script_origem.is_file():
        raise FileNotFoundError(f"Falta {script_origem.name} na raiz do projeto")
    # Atualiza resultados e lacunas, mas respeita parâmetros/cotações editados.
    atualizar_etapa19(raiz)
    entrada = raiz / "dados_complementares" / "etapa19"
    params = pd.read_csv(entrada / "parametros_cenarios.csv", dtype="string", keep_default_na=False)
    if set(CENARIO_COLS) - set(params.columns):
        raise ValueError("Arquivo de cenários sem as colunas esperadas da etapa 1.9")
    if params["cenario_id"].duplicated().any():
        raise ValueError("IDs de cenário duplicados")
    pasta_mestre, versao = _localizar_mestre(raiz)
    veiculos = _veiculos(pasta_mestre)
    ofertas = _ofertas(pasta_mestre)
    ids = set(veiculos["veiculo_id_inmetro"])
    saidas = []
    curvas = []
    for _, item in params.iterrows():
        calculo = _calcular(item, ids, ofertas)
        km = numero(item["km_mes"])
        horas = numero(item["horas_online_mes"])
        receita_h = numero(item["receita_brl_por_hora_online"])
        nome = str(item["cenario_id"])
        pronto = calculo["status"] == "calculado_condicional_parametros_declarados"
        linha = {
            "cenario_id": nome,
            "modalidade": str(item["modalidade"]),
            "status": "calculado_condicional" if pronto else "pendente_lacunas",
            "km_mes": km,
            "horas_online_mes": horas,
            "receita_brl_hora_online": receita_h,
            "receita_mensal_brl": calculo["receita_mensal_brl"],
            "custo_total_mensal_brl": calculo["custo_total_mensal_brl"],
            "custo_fixo_mensal_estimado_brl": None,
            "custo_variavel_por_km_estimado_brl": None,
            "custo_total_por_km_brl": calculo["custo_por_km_brl"],
            "receita_minima_brl_hora_online": None,
            "receita_minima_brl_km": None,
            "resultado_liquido_estimado_brl": calculo["resultado_liquido_estimado_brl"],
            "margem_estimada_pct": None,
            "fonte_parametros": str(item["fonte_parametros"]),
            "observacoes": str(item["observacoes"]),
            "lacunas": calculo["lacunas"],
        }
        if pronto:
            custo = float(calculo["custo_total_mensal_brl"])
            receita = float(calculo["receita_mensal_brl"])
            assert km is not None and km > 0 and horas is not None and horas > 0
            f, v = decompor_componentes(calculo["componentes_conhecidos"], km)
            linha.update({
                "custo_fixo_mensal_estimado_brl": f,
                "custo_variavel_por_km_estimado_brl": v,
                "receita_minima_brl_hora_online": round(custo / horas, 4),
                "receita_minima_brl_km": round(custo / km, 4),
                "margem_estimada_pct": round(100 * (receita - custo) / receita, 2) if receita > 0 else None,
            })
            # Simulações de variação da receita por hora, sem alterar custo.
            for delta in (-0.2, -0.1, 0.0, 0.1, 0.2):
                receita_s = round(receita * (1 + delta), 2)
                curvas.append({
                    "cenario_id": nome,
                    "variacao_receita_pct": round(delta * 100),
                    "receita_mensal_brl": receita_s,
                    "custo_mensal_brl": custo,
                    "resultado_estimado_brl": round(receita_s - custo, 2),
                    "tipo": "sensibilidade_hipotetica_receita",
                })
        saidas.append(linha)
    destino = raiz / "dados_analiticos" / "modelo_economico"
    destino.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(saidas, columns=CHAVES).to_csv(destino / "indicadores_cenarios.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(curvas, columns=["cenario_id", "variacao_receita_pct", "receita_mensal_brl", "custo_mensal_brl", "resultado_estimado_brl", "tipo"]).to_csv(
        destino / "sensibilidade_receita.csv", index=False, encoding="utf-8-sig")
    log = {
        "gerado_em_utc": datetime.now(timezone.utc).isoformat(),
        "versao_tabelas_mestres": versao,
        "cenarios_total": len(saidas),
        "cenarios_completos": sum(r["status"] == "calculado_condicional" for r in saidas),
        "observacoes": [
            "Não é lucro observado: modelo condicional aos parâmetros declarados.",
            "Receita é em R$/hora online, não em hora de corrida.",
            "Análise de sensibilidade varia receita, mantendo custos fixos.",
            "Apenas cenários com todos os campos obrigatórios recebem resultado final.",
            "Custos fixos/variáveis são uma classificação para análise, não novos valores de fonte.",
            "Impostos sobre a atividade e custo de oportunidade podem permanecer fora do modelo.",
        ],
    }
    (destino / "manifesto.json").write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
    return destino, len(saidas), log["cenarios_completos"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raiz", type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    destino, total, completos = rodar(args.raiz)
    print(f"[OK] Modelo econômico: {total} cenários; {completos} completos")
    print(f"[OK] Saídas: {destino}")
    if completos == 0:
        print("[PENDENTE] Preencha as lacunas documentadas da etapa 1.9 antes de calcular resultado líquido.")


if __name__ == "__main__":
    main()
