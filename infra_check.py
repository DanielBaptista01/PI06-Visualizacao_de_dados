from __future__ import annotations

from database_utils import testar_conexao
from storage_utils import testar_storage


def main() -> None:
    erros = []
    try:
        info_db = testar_conexao()
        if not info_db["postgis_instalado"]:
            raise RuntimeError(
                "PostgreSQL acessível, mas PostGIS não está instalado. "
                "Execute 'python database_utils.py init'."
            )
        print(
            "[OK] PostgreSQL/PostGIS | "
            f"database={info_db['database']} | "
            f"versão={info_db['postgres_version']}"
        )
    except Exception as exc:  # diagnóstico de configuração
        erros.append(f"PostgreSQL/PostGIS: {exc}")
        print(f"[ERRO] PostgreSQL/PostGIS | {exc}")

    try:
        info_storage = testar_storage()
        print(
            "[OK] Storage | "
            f"bucket={info_storage['bucket']} | "
            f"objetos={info_storage['objetos']}"
        )
    except Exception as exc:  # diagnóstico de configuração
        erros.append(f"Storage: {exc}")
        print(f"[ERRO] Storage | {exc}")

    if erros:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
