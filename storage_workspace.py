"""Workspace de arquivos RAW do Object Storage para o PI06.

Seleciona a referencia mais recente por fonte sem misturar referencias,
valida as chaves e prepara copias temporarias dos RAW para o pipeline.
Nao modifica nem remove os objetos remotos.
"""
from __future__ import annotations

import argparse
import json
import os
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
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
    "uber_match", "raw/uber_match", "UBER_MATCH", 1
)


def _relativo(chave: str, prefixo: str) -> str | None:
    chave = normalizar_chave(chave)
    inicio = normalizar_chave(prefixo).rstrip("/") + "/"
    if not chave.startswith(inicio):
        return None
    return chave[len(inicio):] or None


def _referencia(relativo: str, max_partes: int) -> tuple[int, ...]:
    """Lê ano/mes/dia do inicio do caminho, validando os intervalos."""
    partes = relativo.split("/")[:-1]
    valores = []
    for parte in partes[:max_partes]:
        if not parte.isdigit():
            break
        valores.append(int(parte))

    if not valores:
        return ()
    ano = valores[0]
    if not 2000 <= ano <= 2100:
        raise ValueError(f"Ano de referencia invalido: {relativo}")
    if len(valores) > 1 and not 1 <= valores[1] <= 12:
        raise ValueError(f"Mes de referencia invalido: {relativo}")
    if len(valores) > 2 and not 1 <= valores[2] <= 31:
        raise ValueError(f"Dia de referencia invalido: {relativo}")
    return tuple(valores)


def _selecionar_ultima_referencia(
    objetos: list[dict], fonte: FonteStorage
) -> tuple[list[dict], str | None]:
    """Seleciona um conjunto temporal coerente sem descartar RAW sem aviso."""
    candidatos = []
    for obj in objetos:
        chave = str(obj.get("Key", ""))
        relativo = _relativo(chave, fonte.prefixo)
        if not relativo or chave.endswith("/"):
            continue
        ref = _referencia(relativo, fonte.max_partes_referencia)
        candidatos.append((obj, ref))

    if not candidatos:
        return [], None

    refs = {ref for _, ref in candidatos if ref}
    possui_sem_ref = any(not ref for _, ref in candidatos)
    if refs and possui_sem_ref:
        raise ValueError(
            f"Storage/{fonte.codigo}: ha arquivos com e sem referencia "
            f"em {fonte.prefixo}/. Separe as versoes ou ajuste o layout; "
            "nenhum arquivo sera omitido silenciosamente."
        )

    if not refs:
        return [obj for obj, _ in candidatos], None

    ultima = max(refs)
    # Se coexistem 2026/10 e 2026/10/08, evita misturar snapshots.
    selecionados = [obj for obj, ref in candidatos if ref == ultima]
    texto = "-".join(
        [str(ultima[0])] + [f"{parte:02d}" for parte in ultima[1:]]
    )
    return selecionados, texto


def _destino_seguro(raiz: Path, fonte: FonteStorage, relativo: str) -> Path:
    """Garante que nenhuma chave S3 escape da pasta temporaria."""
    posix = PurePosixPath(relativo)
    partes = posix.parts
    if (
        not partes
        or posix.is_absolute()
        or any(p in {"", ".", ".."} or ":" in p or "\\" in p for p in partes)
    ):
        raise ValueError(f"Chave insegura: {relativo!r}")

    raiz_resolvida = raiz.resolve()
    destino = (raiz_resolvida / fonte.pasta_local / Path(*partes)).resolve()
    destino.relative_to(raiz_resolvida)
    return destino


def planejar_fonte(fonte: FonteStorage) -> tuple[list[tuple[str, str]], str | None]:
    """Retorna (chave S3, caminho relativo) e referencia, sem baixar nada."""
    objetos = listar(fonte.prefixo.rstrip("/") + "/")
    selecionados, ref = _selecionar_ultima_referencia(objetos, fonte)
    if not selecionados:
        raise FileNotFoundError(
            f"Nenhum RAW para {fonte.codigo} em {fonte.prefixo}/"
        )

    plano = []
    chaves_vistas = set()
    for obj in selecionados:
        chave = str(obj["Key"])
        relativo = _relativo(chave, fonte.prefixo)

        if not relativo:
            continue

        # Uber Match: ignora recursos auxiliares de HTML salvo.
        # O extrator utiliza os documentos HTML, não imagens/CSS.
        partes = relativo.replace("\\", "/").split("/")

        if fonte.codigo == "uber_match":
            if any(
                parte.lower().endswith("_files")
                for parte in partes[:-1]
            ):
                continue

            # Mantém apenas HTMLs do Uber Match.
            if not relativo.lower().endswith(".html"):
                continue
            _destino_seguro(Path(tempfile.gettempdir()), fonte, relativo)
            if chave in chaves_vistas:
                raise ValueError(f"Chave duplicada na listagem: {chave}")
            chaves_vistas.add(chave)
            plano.append((chave, relativo))
    if not plano:
        raise RuntimeError(f"Nenhum arquivo valido para {fonte.codigo}")
    return plano, ref


def fontes_do_grupo(grupo: str) -> tuple[FonteStorage, ...]:
    if grupo == "bases":
        return FONTES_BASES
    if grupo == "uber-match":
        return (FONTE_UBER_MATCH,)
    if grupo == "tudo":
        return (*FONTES_BASES, FONTE_UBER_MATCH)
    raise ValueError("Grupo invalido; use bases, uber-match ou tudo.")


def auditar_storage(grupo: str = "bases") -> dict[str, dict]:
    """Valida selecao de fontes e referencias sem escrever CSVs nem baixar RAW."""
    resumo = {}
    falhas = []
    for fonte in fontes_do_grupo(grupo):
        try:
            plano, referencia = planejar_fonte(fonte)
            resumo[fonte.codigo] = {
                "referencia": referencia,
                "arquivos": len(plano),
                "chaves": [chave for chave, _ in plano],
            }
            print(
                f"[OK] {fonte.codigo}: {len(plano)} arquivo(s) | "
                f"referencia={referencia or 'sem data no caminho'}"
            )
        except Exception as exc:
            falhas.append(f"{fonte.codigo}: {exc}")
            print(f"[ERRO] {fonte.codigo}: {exc}")
    if falhas:
        raise RuntimeError("Auditoria reprovada: " + " | ".join(falhas))
    return resumo


@contextmanager
def workspace_storage(grupo: str) -> Iterator[Path]:
    """Prepara RAW remoto, com limpeza automatica e falha em fontes ausentes."""
    fontes = fontes_do_grupo(grupo)
    # Planeja tudo antes de iniciar qualquer download.
    planejamentos = [(fonte, *planejar_fonte(fonte)) for fonte in fontes]

    with tempfile.TemporaryDirectory(prefix="pi06_storage_") as temporario:
        raiz = Path(temporario).resolve()
        manifesto = {}
        for fonte, plano, ref in planejamentos:
            for chave, relativo in plano:
                destino = _destino_seguro(raiz, fonte, relativo)
                # Identifica arquivos auxiliares que podem ser vazios.
                partes = Path(chave.replace("\\", "/")).parts
                recurso_html_auxiliar = (
                    any(parte.lower().endswith("_files") for parte in partes[:-1])
                    and Path(chave).suffix == ""
                )
                cpg_auxiliar = destino.suffix.lower() == ".cpg"

                # A regra vale apenas para arquivos auxiliares conhecidos.
                auxiliar_vazio_permitido = (
                    cpg_auxiliar or recurso_html_auxiliar
                )

                baixar_arquivo(chave, destino)

                if not destino.is_file():
                    raise RuntimeError(f"Download ausente: {chave}")

                if destino.stat().st_size == 0:
                    if auxiliar_vazio_permitido:
                        print(f"[AVISO] Auxiliar vazio ignorado: {chave}")
                        continue

                    raise RuntimeError(f"RAW obrigatório vazio: {chave}")

                manifesto[str(destino.resolve())] = normalizar_chave(chave)
            print(
                f"Storage/{fonte.codigo}: {len(plano)} RAW(s) | "
                f"referencia={ref or 'sem data'}"
            )

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


def main() -> None:
    parser = argparse.ArgumentParser(description="Auditoria RAW do Storage PI06")
    parser.add_argument("--auditar", action="store_true")
    parser.add_argument("--grupo", choices=["bases", "uber-match", "tudo"], default="bases")
    args = parser.parse_args()
    if not args.auditar:
        parser.error("Use --auditar para listar e validar as referencias selecionadas.")
    auditar_storage(args.grupo)


if __name__ == "__main__":
    main()
