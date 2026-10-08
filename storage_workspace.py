from __future__ import annotations

import json
import os
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from storage_utils import baixar_arquivo, listar, normalizar_chave


@dataclass(frozen=True)
class FonteStorage:
    codigo: str
    prefixo: str
    pasta_local: str
    max_partes_referencia: int = 3


FONTES_BASES = (
    FonteStorage("aneel", "raw/aneel", "ANEEL"),
    FonteStorage("anp", "raw/anp", "ANP"),
    FonteStorage("ibge", "raw/ibge", "IBGE_STORAGE", 1),
    FonteStorage("inmetro", "raw/inmetro", "INMETRO"),
    FonteStorage("od2023", "raw/od2023", "ORIGEM_E_DESTINO_2023", 1),
    FonteStorage("senatran", "raw/senatran", "SENATRAN"),
    FonteStorage("abve", "raw/abve/manual", "ABVE"),
    FonteStorage("uber", "raw/uber", "UBER", 1),
)

FONTE_UBER_MATCH = FonteStorage(
    "uber_match",
    "raw/uber_match",
    "UBER_MATCH",
    1,
)


def _relativo(chave: str, prefixo: str) -> str | None:
    chave = normalizar_chave(chave)
    prefixo = normalizar_chave(prefixo).rstrip("/")
    inicio = prefixo + "/"
    if not chave.startswith(inicio):
        return None
    relativo = chave[len(inicio):].strip("/")
    return relativo or None


def _referencia(relativo: str, max_partes: int) -> tuple[int, ...]:
    """Extrai ano/mês/dia numéricos do começo do caminho relativo.

    Exemplos:
    - ``2026/08/precos.xlsx`` -> (2026, 8)
    - ``2026/data.xlsx`` -> (2026,)
    - ``arquivo.xlsx`` -> ()
    """
    partes = relativo.split("/")[:-1]
    referencia: list[int] = []
    for parte in partes[:max_partes]:
        if not parte.isdigit():
            break
        referencia.append(int(parte))
    return tuple(referencia)


def _selecionar_ultima_referencia(
    objetos: list[dict],
    fonte: FonteStorage,
) -> tuple[list[dict], str | None]:
    candidatos: list[tuple[dict, tuple[int, ...]]] = []
    for obj in objetos:
        relativo = _relativo(str(obj.get("Key", "")), fonte.prefixo)
        if not relativo:
            continue
        candidatos.append(
            (obj, _referencia(relativo, fonte.max_partes_referencia))
        )

    referencias = [ref for _, ref in candidatos if ref]
    if not referencias:
        return [obj for obj, _ in candidatos], None

    ultima = max(referencias)
    selecionados = [obj for obj, ref in candidatos if ref == ultima]
    texto = "-".join(
        [str(ultima[0])] + [f"{valor:02d}" for valor in ultima[1:]]
    )
    return selecionados, texto


def _baixar_fonte(
    fonte: FonteStorage,
    raiz: Path,
    manifesto: dict[str, str],
) -> None:
    objetos = listar(fonte.prefixo)
    selecionados, referencia = _selecionar_ultima_referencia(objetos, fonte)
    if not selecionados:
        print(
            f"Storage/{fonte.codigo}: nenhum objeto encontrado em "
            f"{fonte.prefixo}/"
        )
        return

    baixados = 0
    for obj in selecionados:
        chave = str(obj["Key"])
        relativo = _relativo(chave, fonte.prefixo)
        if not relativo:
            continue
        destino = raiz / fonte.pasta_local / relativo
        baixar_arquivo(chave, destino)
        manifesto[str(destino.resolve())] = normalizar_chave(chave)
        baixados += 1

    sufixo = f" | referência={referencia}" if referencia else ""
    print(
        f"Storage/{fonte.codigo}: {baixados} arquivo(s) preparado(s)"
        f"{sufixo}"
    )


@contextmanager
def workspace_storage(grupo: str) -> Iterator[Path]:
    """Materializa RAW do Storage em uma pasta temporária para o pipeline.

    A pasta temporária existe apenas durante a execução. Os arquivos RAW
    continuam tendo o Object Storage como origem persistente.
    """
    if grupo not in {"bases", "uber-match", "tudo"}:
        raise ValueError(
            "--origem storage só se aplica a bases, uber-match ou tudo."
        )

    with tempfile.TemporaryDirectory(prefix="pi06_storage_") as temporario:
        raiz = Path(temporario).resolve()
        manifesto: dict[str, str] = {}

        if grupo in {"bases", "tudo"}:
            for fonte in FONTES_BASES:
                _baixar_fonte(fonte, raiz, manifesto)

        if grupo in {"uber-match", "tudo"}:
            _baixar_fonte(FONTE_UBER_MATCH, raiz, manifesto)

        arquivo_manifesto = raiz / "_storage_manifest.json"
        arquivo_manifesto.write_text(
            json.dumps(manifesto, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        anteriores = {
            "PI_DATA_ROOT": os.environ.get("PI_DATA_ROOT"),
            "PI_STORAGE_MANIFEST": os.environ.get("PI_STORAGE_MANIFEST"),
        }
        os.environ["PI_DATA_ROOT"] = str(raiz)
        os.environ["PI_STORAGE_MANIFEST"] = str(arquivo_manifesto)

        try:
            yield raiz
        finally:
            for nome, valor in anteriores.items():
                if valor is None:
                    os.environ.pop(nome, None)
                else:
                    os.environ[nome] = valor
