from __future__ import annotations

import argparse
from pathlib import Path

from database_utils import registrar_coleta_db
from storage_utils import bucket, iterar_arquivos, normalizar_chave, sha256_arquivo, upload_arquivo


def chave_destino(arquivo: Path, raiz: Path, prefixo: str) -> str:
    relativo = arquivo.name if raiz.is_file() else arquivo.relative_to(raiz).as_posix()
    return normalizar_chave(f"{prefixo}/{relativo}")


def origem_relativa(arquivo: Path, raiz: Path) -> str:
    if raiz.is_file():
        return arquivo.name
    return arquivo.relative_to(raiz).as_posix()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Migra arquivos brutos para Object Storage sem apagar a origem local."
    )
    parser.add_argument("--origem", required=True, help="Arquivo ou pasta local a migrar")
    parser.add_argument("--fonte", required=True, help="Código cadastrado em metadata.fontes")
    parser.add_argument(
        "--prefixo",
        required=True,
        help="Prefixo no bucket, ex.: raw/anp/2026/08",
    )
    parser.add_argument("--referencia", help="Referência textual, ex.: 2026-08")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--sem-banco", action="store_true")
    parser.add_argument("--sobrescrever", action="store_true")
    args = parser.parse_args()

    raiz = Path(args.origem).expanduser().resolve()
    if not raiz.exists():
        raise FileNotFoundError(f"Origem não encontrada: {raiz}")

    arquivos = list(iterar_arquivos(raiz))
    if not arquivos:
        raise RuntimeError(f"Nenhum arquivo encontrado em {raiz}")

    print(f"Arquivos encontrados: {len(arquivos)}")
    for arquivo in arquivos:
        chave = chave_destino(arquivo, raiz, args.prefixo)
        sha = sha256_arquivo(arquivo)
        if args.dry_run:
            print(f"DRY-RUN\t{origem_relativa(arquivo, raiz)}\t->\ts3://{bucket()}/{chave}\t{sha}")
            continue

        resultado = upload_arquivo(
            arquivo,
            chave,
            sobrescrever=args.sobrescrever,
        )
        print(
            f"{'UPLOAD' if resultado['enviado'] else 'SKIP'}\t{arquivo.name}\t->\t{chave}"
        )

        if not args.sem_banco and bool(resultado["enviado"]):
            registrar_coleta_db(
                codigo_fonte=args.fonte,
                origem=origem_relativa(arquivo, raiz),
                caminho_storage=f"s3://{bucket()}/{chave}",
                sha256=str(resultado["sha256"]),
                tamanho_bytes=int(resultado["tamanho_bytes"]),
                referencia_texto=args.referencia,
                status="raw_armazenado",
                extras={"acao": resultado["motivo"]},
            )


if __name__ == "__main__":
    main()
