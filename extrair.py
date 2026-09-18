"""Orquestrador do pipeline de dados.

Uso:
    python extrair.py bases
    python extrair.py apis
    python extrair.py fipe
    python extrair.py tudo
"""

from __future__ import annotations

import argparse


def main() -> None:
    parser = argparse.ArgumentParser(description="Pipeline de dados do PI06")
    parser.add_argument("grupo", choices=["bases", "apis", "fipe", "tudo"], nargs="?", default="bases")
    args = parser.parse_args()

    if args.grupo in {"bases", "tudo"}:
        from extrair_bases import executar_bases
        executar_bases()

    if args.grupo in {"apis", "tudo"}:
        from extrair_apis import executar_apis
        executar_apis()

    if args.grupo in {"fipe", "tudo"}:
        from extrair_fipe import atualizar_precos
        atualizar_precos()


if __name__ == "__main__":
    main()
