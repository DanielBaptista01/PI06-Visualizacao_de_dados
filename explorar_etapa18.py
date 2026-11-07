"""PI06 - Auditoria de estrutura e padronizacao (Etapa 1.8).

Somente leitura de dados_limpos; gera tres diagnosticos em dados_relatorios.
Mantem arquivos originais, tipos textuais e marcadores de ausencia inalterados.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent

# Unidade e granularidade sao metadados: nao se inferem automaticamente da coluna.
FONTES = {
    "02_ANEEL": ("ANEEL", "tarifa / distribuidora / vigencia / classificacao"),
    "03_ANP": ("ANP", "observacao de preco por estabelecimento / periodo"),
    "04_IBGE": ("IBGE", "municipio ou atributo territorial"),
    "05_INMETRO": ("INMETRO", "veiculo / versao / configuracao"),
    "06_SENATRAN": ("SENATRAN", "agregado de frota; verificar dimensoes no arquivo"),
    "07_": ("OD 2023", "registro de viagem ou agregado OD"),
    "08_FIPE": ("FIPE", "versao FIPE / ano-modelo / mes-referencia"),
    "09_UBER": ("Uber", "modelo / regra de categoria"),
    "10_OPEN_CHARGE": ("Open Charge Map", "ponto de recarga"),
    "11_ABVE": ("ABVE", "vendas agregadas; verificar recorte temporal"),
    "14_ABVE": ("ABVE", "modelo ou serie temporal de vendas"),
    "15_ABVE": ("ABVE", "pontos agregados por municipio"),
    "16_ABVE": ("ABVE", "vendas MHEV por municipio"),
    "17_ABVE": ("ABVE", "serie temporal de infraestrutura"),
    "17_UBER_MATCH": ("Uber Match", "oferta comercial / data de coleta"),
    "abve_": ("ABVE", "verificar recorte e granularidade da fonte"),
}

# Regras de unicidade potencial, nao equivalem a joins autorizados.
CHAVES_CANDIDATAS = {
    "10_OPEN_CHARGE_MAP_SP.csv": ["id_posto"],
    "17_UBER_MATCH_OFERTAS_SP.csv": ["id_publico_oferta"],
    "09_UBER_MODELOS_SP.csv": ["marca", "modelo"],
    "04_IBGE_SP.csv": ["CD_MUN"],
    "04_IBGE_RMSP.csv": ["CD_MUN"],
}

MARCADORES_AUSENCIA = frozenset({"", "ND", "N/D", "N.A.", "N/A", "NA", "NULL", "NONE", "NAN", "-", "--", "SEM INFORMACAO", "NAO INFORMADO"})
UNIDADES = {
    "latitude": "grau decimal (EPSG:4326)",
    "longitude": "grau decimal (EPSG:4326)",
    "potencia_max_kw": "kW",
    "consumo_energetico_mj_km": "MJ/km",
    "autonomia_eletrica_km": "km",
    "valor_reais": "R$ por periodicidade_valor",
    "valor_mensal_equivalente": "R$/mes (calculado)",
    "valor_semanal_equivalente": "R$/semana (calculado)",
    "preco_fipe": "R$ (referencia FIPE)",
    "TUSD": "consultar coluna Unidade/definicao ANEEL",
    "TE": "consultar coluna Unidade/definicao ANEEL",
    "FE_VIA": "fator de expansao de viagens",
    "AREA_KM2": "km2",
}


def _normalizar(valor: object) -> str:
    texto = unicodedata.normalize("NFKD", str(valor).strip().upper())
    return re.sub(r"\s+", " ", texto.encode("ascii", "ignore").decode("ascii"))


def _fonte(nome: str) -> tuple[str, str]:
    for prefixo, info in sorted(FONTES.items(), key=lambda p: -len(p[0])):
        if nome.startswith(prefixo):
            return info
    return "nao catalogada", "a confirmar"


def _hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as arq:
        for b in iter(lambda: arq.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def _ler(path: Path) -> pd.DataFrame:
    # Impede inferencias destrutivas de codigo municipal/identificadores e ND -> zero.
    return pd.read_csv(path, dtype="string", keep_default_na=False,
                       na_filter=False, encoding="utf-8-sig", low_memory=False)


def _perfil_coluna(serie: pd.Series) -> tuple[int, int, int, int, str]:
    v = serie.str.strip()
    normal = v.map(_normalizar)
    marcadores = normal.isin(MARCADORES_AUSENCIA)
    # Nenhum marcador e convertido: contamos somente.
    n_vazio = int(v.eq("").sum())
    n_marcadores = int((marcadores & ~v.eq("")).sum())
    n_preenchido = int((~marcadores).sum())
    distintos = int(v[~marcadores].nunique())
    exemplos = v[~marcadores].drop_duplicates().head(3).tolist()
    return n_vazio, n_marcadores, n_preenchido, distintos, json.dumps(exemplos, ensure_ascii=False)


def auditar(pasta: Path, saida: Path) -> dict[str, object]:
    if not pasta.is_dir():
        raise FileNotFoundError(f"Pasta de entrada nao encontrada: {pasta}")
    arquivos = sorted(pasta.glob("*.csv"))
    if not arquivos:
        raise RuntimeError(f"Nenhum CSV em {pasta}")

    saida.mkdir(parents=True, exist_ok=True)
    resumo: list[dict] = []
    dicionario: list[dict] = []
    alertas: list[str] = []
    hashes: dict[str, str] = {}
    leituras_erro = 0

    for path in arquivos:
        fonte, granularidade = _fonte(path.name)
        try:
            df = _ler(path)
            if df.columns.duplicated().any():
                raise ValueError("cabecalhos duplicados")
            vazios_gerais = 0
            marcadores_gerais = 0
            for col in df.columns:
                vazio, marcador, preenchido, distintos, exemplos = _perfil_coluna(df[col])
                vazios_gerais += vazio
                marcadores_gerais += marcador
                dicionario.append({
                    "arquivo": path.name, "fonte": fonte, "coluna": col,
                    "tipo_leitura": "texto-preservado", "unidade_ou_significado": UNIDADES.get(col, "a confirmar na fonte"),
                    "vazios": vazio, "marcadores_ausencia": marcador,
                    "preenchidos": preenchido, "valores_distintos": distintos,
                    "exemplos": exemplos,
                    "tipo_original": "nao inferido; consultar a fonte",
                    "transformacao_aplicada": "nenhuma (auditoria)",
                })
            linhas_duplicadas = int(df.duplicated().sum())
            chave = CHAVES_CANDIDATAS.get(path.name, [])
            chave_valida = bool(chave) and all(c in df.columns for c in chave)
            chave_duplicada = (int(df.duplicated(subset=chave).sum()) if chave_valida else None)
            chave_vazia = (int(df[chave].apply(lambda s: s.str.strip().eq("")).any(axis=1).sum()) if chave_valida else None)
            sha = _hash(path)
            hashes[path.name] = sha
            resumo.append({
                "arquivo": path.name, "fonte": fonte, "granularidade_proposta": granularidade,
                "linhas": len(df), "colunas": len(df.columns),
                "duplicatas_linha_completa": linhas_duplicadas,
                "chave_candidata": "+".join(chave) if chave else "a definir",
                "duplicatas_chave": chave_duplicada,
                "vazios_chave": chave_vazia,
                "celulas_vazias": vazios_gerais, "marcadores_ausencia": marcadores_gerais,
                "sha256": sha, "status_leitura": "ok", "erro": "",
            })
            if chave_valida and (chave_duplicada or chave_vazia):
                alertas.append(f"{path.name}: chave candidata apresenta duplicatas={chave_duplicada}, vazios={chave_vazia}.")
            if chave and not chave_valida:
                alertas.append(f"{path.name}: faltam colunas da chave candidata: {set(chave)-set(df.columns)}.")
            print(f"[OK] {path.name}: {len(df)} linhas, {len(df.columns)} colunas")
        except Exception as exc:
            leituras_erro += 1
            resumo.append({"arquivo": path.name, "fonte": fonte, "status_leitura": "erro", "erro": str(exc)})
            alertas.append(f"Falha ao ler {path.name}: {exc}")
            print(f"[ERRO] {path.name}: {exc}")

    if hashes.get("02_ANEEL_NACIONAL.csv") == hashes.get("02_ANEEL_SP.csv") and "02_ANEEL_NACIONAL.csv" in hashes:
        alertas.append("ANEEL: arquivos NACIONAL e SP sao IDENTICOS (SHA-256). Nao usar SP como recorte geografico validado.")
    if "08_FIPE_VEICULOS.csv" in hashes:
        alertas.append("FIPE: 08_FIPE_VEICULOS.csv pode ser uma extracao anterior; nao presumir que contem a coleta catalogada completa.")
    if "08_FIPE_VEICULOS_PARCIAL.csv" in hashes:
        alertas.append("FIPE: coleta catalogada PARCIAL; verificar referencia e cobertura antes de utilizar. Nao concatenar com extracao anterior.")
    if "17_UBER_MATCH_FALHAS_SP.csv" in hashes:
        alertas.append("Uber Match: revisar as mensagens de falha/aviso; ofertas ignoradas nao entram na tabela de ofertas.")
    if "09_UBER_MODELOS_SP.csv" in hashes:
        try:
            uber = _ler(pasta / "09_UBER_MODELOS_SP.csv")
            if "marca" in uber.columns:
                n = int(uber["marca"].str.contains(r"Down\s*$", case=False, regex=True, na=False).sum())
                if n:
                    alertas.append(f"Uber: {n} marcas com sufixo 'Down' do HTML; padronizar no campo derivado, preservando o original.")
        except Exception:
            pass

    data = datetime.now(timezone.utc).isoformat(timespec="seconds")
    pd.DataFrame(resumo).to_csv(saida / "etapa18_resumo.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(dicionario).to_csv(saida / "etapa18_dicionario.csv", index=False, encoding="utf-8-sig")
    relatorio = [
        "# PI06 - Etapa 1.8: qualidade e padronizacao\n",
        f"Gerado em UTC: {data}\n",
        "**Metodo:** leitura nao destrutiva dos CSVs de dados_limpos; sem merges, sem imputacao e sem escrita de dados tratados.\n",
        f"Arquivos analisados: {len(arquivos)}; falhas de leitura: {leituras_erro}.\n",
        "## Pendencias para padronizacao\n",
    ]
    relatorio.extend(f"- {a}\n" for a in alertas)
    if not alertas:
        relatorio.append("- Nenhum alerta predefinido; avaliar dicionario, cobertura e granularidade antes de integrar.\n")
    relatorio.extend([
        "\n## Regras de integracao\n",
        "- Dados RAW e CSVs existentes permanecem intactos.\n",
        "- Ausencia (ND, traco, branco) nao significa zero; marcadores sao contados sem alteracao.\n",
        "- Chaves candidatas nao sao autorizacao de merge; validar identidade, periodo, local e cardinalidade.\n",
        "- Dados nacionais/municipais nao podem ser desagregados artificialmente por Zona OD.\n",
        "- FIPE parcial nao representa a distribuicao populacional de precos.\n",
        "- Uber Match e uma oferta comercial, nao um registro de elegibilidade Uber.\n",
        "- Valores derivados exigem fonte, unidade, formula e referencia temporal.\n",
    ])
    (saida / "etapa18_relatorio.md").write_text("\n".join(relatorio), encoding="utf-8")
    print(f"\nRelatorios em: {saida}")
    return {"arquivos": len(arquivos), "falhas": leituras_erro, "alertas": len(alertas), "linhas": resumo}


def main() -> None:
    parser = argparse.ArgumentParser(description="Auditoria de padronizacao PI06 - etapa 1.8")
    parser.add_argument("--entrada", type=Path, default=ROOT / "dados_limpos")
    parser.add_argument("--saida", type=Path, default=ROOT / "dados_relatorios")
    args = parser.parse_args()
    resultado = auditar(args.entrada, args.saida)
    if resultado["falhas"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
