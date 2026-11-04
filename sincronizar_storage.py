from __future__ import annotations

import argparse
from pathlib import Path, PurePosixPath

from storage_utils import baixar_arquivo, listar, normalizar_chave


def caminho_local_seguro(destino: Path, chave_relativa: str) -> Path:
    """Converte uma chave do Storage em caminho local sem permitir sair da pasta destino."""
    relativo = PurePosixPath(chave_relativa)

    if relativo.is_absolute() or not relativo.parts:
        raise ValueError(f"Caminho relativo inválido no Storage: {chave_relativa!r}")

    if any(parte in {"", ".", ".."} for parte in relativo.parts):
        raise ValueError(f"Caminho inseguro no Storage: {chave_relativa!r}")

    arquivo_local = (destino / Path(*relativo.parts)).resolve()

    try:
        arquivo_local.relative_to(destino)
    except ValueError as exc:
        raise ValueError(
            f"O caminho do objeto sairia da pasta de destino: {chave_relativa!r}"
        ) from exc

    return arquivo_local


def sincronizar(
    *,
    prefixo: str,
    destino: Path,
    sobrescrever: bool = True,
    dry_run: bool = False,
) -> tuple[int, int, int]:
    """
    Baixa os objetos de um prefixo do Supabase Storage.

    Retorna: (baixados, ignorados, erros).
    Não remove arquivos locais que não existam no Storage.
    """
    prefixo_normalizado = normalizar_chave(prefixo).strip("/")
    consulta = f"{prefixo_normalizado}/" if prefixo_normalizado else ""

    objetos = listar(consulta)
    arquivos = [
        obj for obj in objetos
        if obj.get("Key") and not str(obj["Key"]).endswith("/")
    ]

    if not arquivos:
        print(f"Nenhum arquivo encontrado no prefixo: {consulta or '(bucket inteiro)'}")
        return 0, 0, 0

    destino.mkdir(parents=True, exist_ok=True)
    destino = destino.resolve()

    print(f"Bucket consultado pelo prefixo: {consulta or '(bucket inteiro)'}")
    print(f"Pasta local: {destino}")
    print(f"Arquivos encontrados: {len(arquivos)}")
    print("-" * 72)

    baixados = 0
    ignorados = 0
    erros = 0

    for objeto in arquivos:
        chave = str(objeto["Key"])

        if prefixo_normalizado:
            inicio = f"{prefixo_normalizado}/"
            if not chave.startswith(inicio):
                continue
            chave_relativa = chave[len(inicio):]
        else:
            chave_relativa = chave

        try:
            arquivo_local = caminho_local_seguro(destino, chave_relativa)
            existe_local = arquivo_local.exists()
            tamanho = objeto.get("Size", "?")

            if dry_run:
                if existe_local and not sobrescrever:
                    acao = "IGNORARIA (já existe)"
                elif existe_local:
                    acao = "SUBSTITUIRIA"
                else:
                    acao = "BAIXARIA"

                print(f"DRY-RUN | {acao} | {chave} -> {arquivo_local} | {tamanho} bytes")
                continue

            if existe_local and not sobrescrever:
                print(f"SKIP     | já existe | {chave}")
                ignorados += 1
                continue

            baixar_arquivo(
                chave,
                arquivo_local,
                sobrescrever=sobrescrever,
            )
            print(f"DOWNLOAD | {chave} -> {arquivo_local} | {tamanho} bytes")
            baixados += 1

        except Exception as exc:
            print(f"ERRO     | {chave} | {exc}")
            erros += 1

    print("-" * 72)
    if dry_run:
        print("Simulação concluída. Nenhum arquivo foi baixado.")
    else:
        print(
            f"Sincronização concluída | baixados={baixados} | "
            f"ignorados={ignorados} | erros={erros}"
        )

    return baixados, ignorados, erros


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Sincroniza arquivos do Supabase Storage para uma pasta local do PI06. "
            "Não apaga arquivos locais."
        )
    )
    parser.add_argument(
        "--prefixo",
        required=True,
        help="Prefixo no bucket, por exemplo: raw/anp/2026/08",
    )
    parser.add_argument(
        "--destino",
        required=True,
        help="Pasta local de destino, por exemplo: dados/raw/anp/2026/08",
    )
    parser.add_argument(
        "--nao-sobrescrever",
        action="store_true",
        help="Mantém os arquivos locais existentes, mesmo que haja versão no Storage.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Mostra o que seria baixado sem alterar arquivos.",
    )

    args = parser.parse_args()

    _, _, erros = sincronizar(
        prefixo=args.prefixo,
        destino=Path(args.destino).expanduser(),
        sobrescrever=not args.nao_sobrescrever,
        dry_run=args.dry_run,
    )

    if erros:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
