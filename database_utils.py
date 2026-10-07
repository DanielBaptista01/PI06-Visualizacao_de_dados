from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
import psycopg
from psycopg.types.json import Jsonb

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")


def database_url() -> str:
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        raise RuntimeError(
            "DATABASE_URL não configurada. Copie .env.example para .env e preencha a conexão PostgreSQL."
        )
    return url


def conectar() -> psycopg.Connection:
    return psycopg.connect(database_url())


def testar_conexao() -> dict[str, Any]:
    with conectar() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT current_database(), current_user, current_setting('server_version'), "
            "EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'postgis')"
        )
        banco, usuario, versao, postgis = cur.fetchone()
        return {
            "database": banco,
            "usuario": usuario,
            "postgres_version": versao,
            "postgis_instalado": bool(postgis),
        }


def aplicar_ddl(caminho: str | Path | None = None) -> None:
    ddl = Path(caminho) if caminho else ROOT / "db" / "001_init.sql"
    if not ddl.exists():
        raise FileNotFoundError(f"DDL não encontrado: {ddl}")
    sql = ddl.read_text(encoding="utf-8")
    with conectar() as conn:
        conn.execute(sql)
        conn.commit()


def registrar_coleta_db(
    *,
    codigo_fonte: str,
    origem: str | None = None,
    caminho_storage: str | None = None,
    sha256: str | None = None,
    tamanho_bytes: int | None = None,
    registros: int | None = None,
    data_referencia: str | None = None,
    referencia_texto: str | None = None,
    status: str = "ok",
    observacao: str | None = None,
    extras: dict[str, Any] | None = None,
) -> int:
    with conectar() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT id_fonte
            FROM metadata.fontes
            WHERE codigo = %s
            """,
            (codigo_fonte,),
        )
        row = cur.fetchone()
        if not row:
            raise ValueError(
                f"Fonte '{codigo_fonte}' não cadastrada em metadata.fontes. "
                "Cadastre a fonte antes de registrar a coleta."
            )
        id_fonte = row[0]
        cur.execute(
            """
            INSERT INTO metadata.coletas (
                id_fonte, origem, caminho_storage, sha256, tamanho_bytes,
                registros, data_referencia, referencia_texto, status,
                observacao, extras
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id_coleta
            """,
            (
                id_fonte,
                origem,
                caminho_storage,
                sha256,
                tamanho_bytes,
                registros,
                data_referencia,
                referencia_texto,
                status,
                observacao,
                Jsonb(extras or {}),
            ),
        )
        id_coleta = cur.fetchone()[0]
        conn.commit()
        return int(id_coleta)


def main() -> None:
    parser = argparse.ArgumentParser(description="Utilitários de PostgreSQL/PostGIS do PI06")
    parser.add_argument("acao", choices=["testar", "init"])
    args = parser.parse_args()

    if args.acao == "init":
        aplicar_ddl()
        print("DDL aplicado com sucesso.")

    info = testar_conexao()
    if not info["postgis_instalado"]:
        raise RuntimeError(
            "PostgreSQL respondeu, mas a extensão PostGIS não está instalada. "
            "Execute 'python database_utils.py init' com uma conexão que possa habilitar a extensão."
        )
    print(
        "Conexão OK | "
        f"database={info['database']} | usuário={info['usuario']} | "
        f"PostGIS={'sim' if info['postgis_instalado'] else 'não'}"
    )


if __name__ == "__main__":
    main()
