"""Converte uma RESPOSTA JSON da consulta querydata do Power BI ABVE em CSV.

Uso:
    python converter_abve_powerbi.py resposta_abve.json --saida 11_ABVE_VENDAS_TECNOLOGIA_BRASIL_MENSAL.csv

Entrada: conteúdo JSON de Response (não Payload), salvo SEM cookies ou tokens.
Preserva MHEV ausente como vazio, não zero. Não faz requisições.
"""
from __future__ import annotations
import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path

FIELDS = ["BEV", "PHEV", "HEV", "HEV FLEX", "MHEV", "TOTAL"]


def extrair(resposta: dict) -> list[dict]:
    resultados = resposta.get("results", [])
    if len(resultados) != 1:
        raise ValueError("Esperada exatamente uma consulta em results")
    data = resultados[0]["result"]["data"]
    descr = [x["Name"] for x in data["descriptor"]["Select"]]
    esperados = ["Tcalendario.MêsAno", "BaseVendas_ABVE.BEV", "BaseVendas_ABVE.PHEV", "BaseVendas_ABVE.HEV", "BaseVendas_ABVE.HEV FLEX", "BaseVendas_ABVE.MHEV", "BaseVendas_ABVE.TotalGeral_ELETRIFICADOS"]
    if descr != esperados:
        raise ValueError(f"Formato diferente do esperado: {descr}")
    ds = data["dsr"]["DS"]
    if len(ds) != 1:
        raise ValueError("Quantidade inesperada de datasets")
    grupo = ds[0]["PH"][0]
    linhas = grupo["DM1"]
    periodos = ds[0]["ValueDicts"]["D0"]
    saida = []
    for linha in linhas:
        vals = list(linha["C"])
        # DSR omite a coluna MHEV em meses posteriores à mudança de metodologia.
        # O campo R/Ø com bit 32 indica a ausência da quinta medida (MHEV).
        faltante = int(linha.get("R", linha.get("Ø", 0)))
        if faltante not in (0, 32):
            raise ValueError(f"Máscara não reconhecida: {faltante}")
        idx = vals[0]
        if not isinstance(idx, int) or not 0 <= idx < len(periodos):
            raise ValueError(f"Índice de período inválido: {idx}")
        periodo_br = periodos[idx]
        mes, ano = periodo_br.split("/")
        periodo = f"20{ano}-{mes}"
        medidas = vals[1:]
        if faltante == 32:
            if len(medidas) != 5:
                raise ValueError(f"MHEV omitido mas quantidade de valores inesperada em {periodo}")
            medidas.insert(4, None)
        elif len(medidas) != 6:
            raise ValueError(f"Quantidade de valores inesperada em {periodo}")
        if not all(v is None or isinstance(v, int) and v >= 0 for v in medidas):
            raise ValueError(f"Valor inválido no período {periodo}")
        # Em 2022-2024, o total inclui MHEV; em 2025+, a ABVE exclui MHEV do total.
        calculado = sum(v for v in medidas[:5] if v is not None)
        if calculado != medidas[5]:
            raise ValueError(f"Total incoerente em {periodo}: {calculado} != {medidas[5]}")
        saida.append(dict(periodo=periodo, abrangencia="Brasil", bev=medidas[0], phev=medidas[1], hev=medidas[2], hev_flex=medidas[3], mhev=medidas[4], total_eletrificados=medidas[5], mhev_incluido_total=(medidas[4] is not None), fonte="ABVE Data - consulta Power BI", data_consulta_utc=data.get("timestamp", "")))
    if len({r["periodo"] for r in saida}) != len(saida):
        raise ValueError("Períodos duplicados")
    saida.sort(key=lambda r:r["periodo"])
    subtotais = grupo.get("DM0", [])
    if subtotais:
        dados_subtotal = subtotais[0]["C"]
        if sum(x["total_eletrificados"] for x in saida) != dados_subtotal[-1]:
            raise ValueError("Soma do total mensal diferente do subtotal Power BI")
    return saida


def salvar(linhas: list[dict], destino: Path) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    with destino.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(linhas[0].keys()), delimiter=";")
        w.writeheader()
        w.writerows(linhas)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("resposta", type=Path)
    parser.add_argument("--saida", type=Path, default=Path("11_ABVE_VENDAS_TECNOLOGIA_BRASIL_MENSAL.csv"))
    args = parser.parse_args()
    resposta = json.loads(args.resposta.read_text(encoding="utf-8-sig"))
    linhas = extrair(resposta)
    salvar(linhas, args.saida)
    print(f"OK: {len(linhas)} meses, {linhas[0]['periodo']} até {linhas[-1]['periodo']}; total={sum(x['total_eletrificados'] for x in linhas):,}")
    print(f"MHEV ausente: {sum(x['mhev'] is None for x in linhas)} períodos")
    print(f"Arquivo: {args.saida}")

if __name__ == "__main__":
    main()
