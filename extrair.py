"""Orquestrador do pipeline de dados.

Uso local:
    python extrair.py bases
    python extrair.py uber-match
    python extrair.py apis
    python extrair.py fipe
    python extrair.py tudo

Uso com RAW no Object Storage:
    python extrair.py bases --origem storage
    python extrair.py uber-match --origem storage
    python extrair.py tudo --origem storage
"""

from __future__ import annotations

import argparse
from pathlib import Path


def _executar(grupo: str, workspace: Path | None = None) -> None:
    if grupo in {"bases", "tudo"}:
        from extrair_bases import executar_bases

        executar_bases()

    if grupo in {"uber-match", "tudo"}:
        from extrair_uber_match import coletar, PASTA_PADRAO

        pasta = workspace / "UBER_MATCH" if workspace else PASTA_PADRAO
        coletar(pasta)

    if grupo in {"apis", "tudo"}:
        from extrair_apis import executar_apis

        executar_apis()

    if grupo in {"fipe", "tudo"}:
        from extrair_fipe import atualizar_precos

        atualizar_precos()


def main() -> None:
    parser = argparse.ArgumentParser(description="Pipeline de dados do PI06")
    parser.add_argument(
        "grupo",
        choices=["bases", "uber-match", "apis", "fipe", "tudo"],
        nargs="?",
        default="bases",
    )
    parser.add_argument(
        "--origem",
        choices=["local", "storage"],
        default="local",
        help=(
            "Origem dos arquivos RAW para bases/Uber Match. "
            "Com 'storage', a referência mais recente é baixada "
            "temporariamente do Object Storage."
        ),
    )
    args = parser.parse_args()

    usa_raw = args.grupo in {"bases", "uber-match", "tudo"}
    if args.origem == "storage" and usa_raw:
        from storage_workspace import workspace_storage

        with workspace_storage(args.grupo) as workspace:
            _executar(args.grupo, workspace)
        return

    if args.origem == "storage" and not usa_raw:
        print(
            f"Aviso: --origem storage não altera o grupo '{args.grupo}', "
            "que não lê arquivos RAW locais."
        )

    _executar(args.grupo)


if __name__ == "__main__":
    main()
