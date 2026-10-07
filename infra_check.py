from __future__ import annotations

from database_utils import testar_conexao
from storage_utils import testar_storage


def main() -> None:
    erros = []
    try:
        info_db = testar_conexao()
        print(
            "[OK] PostgreSQL | "
            f"database={info_db['database']} | "
            f"PostGIS={'sim' if info_db['postgis_instalado'] else 'não'}"
        )
    except Exception as exc:  # diagnóstico de configuração
        erros.append(f"PostgreSQL: {exc}")
        print(f"[ERRO] PostgreSQL | {exc}")

    try:
        info_storage = testar_storage()
        print(
            "[OK] Storage | "
            f"bucket={info_storage['bucket']} | "
            f"objetos={info_storage['objetos_primeira_pagina']}"
        )
    except Exception as exc:  # diagnóstico de configuração
        erros.append(f"Storage: {exc}")
        print(f"[ERRO] Storage | {exc}")

    if erros:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
