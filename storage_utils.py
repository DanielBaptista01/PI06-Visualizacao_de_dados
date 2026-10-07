from __future__ import annotations

import argparse
import hashlib
import mimetypes
import os
from pathlib import Path
from typing import Iterator

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")


def _obrigatoria(nome: str) -> str:
    valor = os.getenv(nome, "").strip()
    if not valor:
        raise RuntimeError(
            f"{nome} não configurada. Copie .env.example para .env e preencha as credenciais do Storage."
        )
    return valor


def bucket() -> str:
    return _obrigatoria("S3_BUCKET")


def cliente_storage():
    return boto3.client(
        "s3",
        endpoint_url=_obrigatoria("S3_ENDPOINT_URL"),
        region_name=_obrigatoria("S3_REGION"),
        aws_access_key_id=_obrigatoria("S3_ACCESS_KEY_ID"),
        aws_secret_access_key=_obrigatoria("S3_SECRET_ACCESS_KEY"),
        config=Config(s3={"addressing_style": "path"}),
    )


def sha256_arquivo(caminho: Path) -> str:
    h = hashlib.sha256()
    with caminho.open("rb") as arq:
        for bloco in iter(lambda: arq.read(1024 * 1024), b""):
            h.update(bloco)
    return h.hexdigest()


def normalizar_chave(chave: str) -> str:
    return "/".join(parte for parte in chave.replace("\\", "/").split("/") if parte)


def iterar_arquivos(raiz: Path) -> Iterator[Path]:
    if raiz.is_file():
        yield raiz
        return
    for caminho in sorted(raiz.rglob("*")):
        if caminho.is_file() and not caminho.name.startswith("~$"):
            yield caminho


def objeto_existe(chave: str) -> dict | None:
    client = cliente_storage()
    try:
        return client.head_object(Bucket=bucket(), Key=normalizar_chave(chave))
    except ClientError as exc:
        codigo = str(exc.response.get("Error", {}).get("Code", ""))
        if codigo in {"404", "NoSuchKey", "NotFound"}:
            return None
        raise


def upload_arquivo(
    caminho: Path,
    chave: str,
    *,
    sobrescrever: bool = False,
) -> dict[str, str | int | bool]:
    caminho = caminho.resolve()
    chave = normalizar_chave(chave)
    sha = sha256_arquivo(caminho)
    existente = objeto_existe(chave)
    if existente and not sobrescrever:
        metadata = existente.get("Metadata", {}) or {}
        if metadata.get("sha256") == sha:
            return {
                "chave": chave,
                "sha256": sha,
                "tamanho_bytes": caminho.stat().st_size,
                "enviado": False,
                "motivo": "já_existente_mesmo_hash",
            }
        raise FileExistsError(
            f"Objeto já existe com conteúdo diferente: s3://{bucket()}/{chave}. "
            "Use sobrescrever=True apenas após revisão."
        )

    content_type = mimetypes.guess_type(caminho.name)[0] or "application/octet-stream"
    cliente_storage().upload_file(
        str(caminho),
        bucket(),
        chave,
        ExtraArgs={
            "ContentType": content_type,
            "Metadata": {"sha256": sha},
        },
    )
    return {
        "chave": chave,
        "sha256": sha,
        "tamanho_bytes": caminho.stat().st_size,
        "enviado": True,
        "motivo": "upload",
    }


def listar(prefixo: str = "") -> list[dict]:
    client = cliente_storage()
    resposta = client.list_objects_v2(
        Bucket=bucket(), Prefix=normalizar_chave(prefixo), MaxKeys=1000
    )
    return resposta.get("Contents", []) or []


def testar_storage() -> dict[str, str | int]:
    objetos = listar("")
    return {"bucket": bucket(), "objetos_primeira_pagina": len(objetos)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Utilitários do Object Storage do PI06")
    sub = parser.add_subparsers(dest="acao", required=True)
    sub.add_parser("testar")
    p_listar = sub.add_parser("listar")
    p_listar.add_argument("--prefixo", default="")
    args = parser.parse_args()

    if args.acao == "testar":
        info = testar_storage()
        print(
            f"Storage OK | bucket={info['bucket']} | "
            f"objetos_primeira_pagina={info['objetos_primeira_pagina']}"
        )
    elif args.acao == "listar":
        for obj in listar(args.prefixo):
            print(f"{obj['Key']}\t{obj['Size']}")


if __name__ == "__main__":
    main()
