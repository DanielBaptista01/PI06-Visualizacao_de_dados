from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = Path(os.getenv("PI_OUTPUT_DIR", ROOT / "dados_limpos"))
CACHE_DIR = Path(os.getenv("PI_CACHE_DIR", ROOT / "dados_cache"))
REPORT_DIR = Path(os.getenv("PI_REPORT_DIR", ROOT / "dados_relatorios"))

for pasta in (OUTPUT_DIR, CACHE_DIR, REPORT_DIR):
    pasta.mkdir(parents=True, exist_ok=True)


def normalizar_texto(valor: object) -> str:
    if pd.isna(valor):
        return ""
    texto = unicodedata.normalize("NFKD", str(valor).strip().upper())
    texto = texto.encode("ASCII", "ignore").decode("ASCII")
    texto = re.sub(r"[^A-Z0-9]+", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


def localizar_coluna(df: pd.DataFrame, candidatos: list[str], contem: bool = False) -> str | None:
    def norm(x: object) -> str:
        return normalizar_texto(x).replace(" ", "_")

    mapa = {norm(c): c for c in df.columns}
    candidatos = [norm(c) for c in candidatos]
    for candidato in candidatos:
        if candidato in mapa:
            return mapa[candidato]
    if contem:
        for chave, original in mapa.items():
            if any(c in chave for c in candidatos):
                return original
    return None


def localizar_primeiro(padroes: list[str]) -> Path | None:
    for padrao in padroes:
        itens = sorted(ROOT.glob(padrao))
        if itens:
            return itens[0]
    return None


def localizar_todos(padroes: list[str]) -> list[Path]:
    vistos, saida = set(), []
    for padrao in padroes:
        for item in sorted(ROOT.glob(padrao)):
            item = item.resolve()
            if item not in vistos:
                vistos.add(item)
                saida.append(item)
    return saida


def sha256_arquivo(caminho: Path) -> str:
    h = hashlib.sha256()
    with caminho.open("rb") as arq:
        for bloco in iter(lambda: arq.read(1024 * 1024), b""):
            h.update(bloco)
    return h.hexdigest()


def salvar_csv(df: pd.DataFrame, nome: str) -> Path:
    destino = OUTPUT_DIR / nome
    destino.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(destino, index=False, encoding="utf-8-sig")
    return destino


def registrar_coleta(
    fonte: str,
    origem: str | Path | None,
    destino: str | Path | None,
    registros: int | None = None,
    data_referencia: str | None = None,
    observacao: str | None = None,
    extras: dict | None = None,
) -> None:
    manifesto = REPORT_DIR / "manifesto_coletas.csv"
    origem_path = Path(origem) if origem and not str(origem).startswith("http") else None
    linha = {
        "fonte": fonte,
        "data_coleta_utc": datetime.now(timezone.utc).isoformat(),
        "data_referencia": data_referencia or "",
        "origem": str(origem or ""),
        "destino": str(destino or ""),
        "registros": "" if registros is None else registros,
        "sha256_origem": sha256_arquivo(origem_path) if origem_path and origem_path.exists() and origem_path.is_file() else "",
        "observacao": observacao or "",
        "extras_json": json.dumps(extras or {}, ensure_ascii=False, sort_keys=True),
    }
    existe = manifesto.exists()
    with manifesto.open("a", newline="", encoding="utf-8") as arq:
        writer = csv.DictWriter(arq, fieldnames=linha.keys())
        if not existe:
            writer.writeheader()
        writer.writerow(linha)
