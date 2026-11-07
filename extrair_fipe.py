from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from datetime import date

import pandas as pd
import requests

from pipeline_utils import CACHE_DIR, OUTPUT_DIR, normalizar_texto, registrar_coleta

API_BASE = os.getenv("FIPE_API_BASE", "https://fipe.parallelum.com.br/api/v2/cars")
MAPEAMENTO = CACHE_DIR / "fipe_mapeamento.csv"
CATALOGO = CACHE_DIR / "fipe_catalogo.json"
CHECKPOINT = CACHE_DIR / "fipe_checkpoint.csv"
ASSINATURA = CACHE_DIR / "fipe_mapeamento_origem.sha256"
SAIDA = OUTPUT_DIR / "08_FIPE_VEICULOS.csv"


class ClienteFipe:
    def __init__(self, intervalo_min: float = 0.25, tentativas: int = 5):
        self.session = requests.Session()
        self.intervalo_min = intervalo_min
        self.tentativas = tentativas
        self.ultima = 0.0

    def get_json(self, url: str):
        for tentativa in range(self.tentativas):
            espera = self.intervalo_min - (time.monotonic() - self.ultima)
            if espera > 0:
                time.sleep(espera)
            try:
                resposta = self.session.get(url, timeout=20)
                self.ultima = time.monotonic()
                if resposta.status_code == 429:
                    time.sleep(min(30, 2 ** tentativa))
                    continue
                resposta.raise_for_status()
                return resposta.json()
            except requests.RequestException:
                if tentativa == self.tentativas - 1:
                    raise
                time.sleep(min(10, 1.5 ** tentativa))
        raise RuntimeError(f"Falha ao consultar {url}")


def _uber() -> pd.DataFrame:
    caminho = OUTPUT_DIR / "09_UBER_MODELOS_SP.csv"
    if not caminho.exists():
        raise FileNotFoundError(f"Arquivo da Uber não encontrado: {caminho}")
    df = pd.read_csv(caminho)
    if not {"marca", "modelo"}.issubset(df.columns):
        raise ValueError("Arquivo da Uber sem marca/modelo")
    anos = [c for c in ["uberx_ano_min", "comfort_ano_min", "black_ano_min", "electric_ano_min"] if c in df.columns]
    if not anos:
        raise ValueError("Arquivo da Uber sem ano mínimo por categoria")
    for coluna in anos:
        df[coluna] = pd.to_numeric(df[coluna], errors="coerce")
    from datetime import date

    ano_atual = date.today().year
    ano_min_fabricacao_sp = ano_atual - 10

    df["ano_min_fonte"] = df[anos].min(
        axis=1,
        skipna=True
    )

    df["ano_min_consulta"] = df["ano_min_fonte"].clip(
        lower=ano_min_fabricacao_sp
    )
    return df.loc[df["ano_min_consulta"].notna()].copy()



def _carregar_catalogo() -> dict:
    if CATALOGO.exists():
        try:
            return json.loads(CATALOGO.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"brands": None, "models": {}, "years": {}}


def _salvar_catalogo(catalogo: dict) -> None:
    CATALOGO.write_text(json.dumps(catalogo, ensure_ascii=False, indent=2), encoding="utf-8")


def _assinatura_uber(uber: pd.DataFrame) -> str:
    """Detecta mudanças na fonte que invalidam o mapeamento FIPE em cache."""
    colunas = ["marca", "modelo", "ano_min_consulta"]
    serializado = (
        uber[colunas].fillna("").astype(str).sort_values(colunas)
        .to_csv(index=False).encode("utf-8")
    )
    return hashlib.sha256(serializado).hexdigest()


def _selecionar_modelo(modelo_uber: str, modelos_fipe: list[dict]) -> dict:
    """Exige correspondência exata ou prefixo por palavra, sem escolher versão ambígua.

    Uma correspondência de prefixo não autoriza preço automaticamente, porque
    FIPE lista versões/motorizações distintas sob o mesmo modelo comercial.
    """
    nome = normalizar_texto(modelo_uber)
    if not nome:
        return {"status": "modelo_nao_encontrado", "candidatos": []}

    registros = [
        {"code": str(item["code"]), "name": str(item["name"])}
        for item in modelos_fipe
        if item.get("code") is not None and item.get("name")
    ]
    exatos = [r for r in registros if normalizar_texto(r["name"]) == nome]
    if len(exatos) == 1:
        return {"status": "modelo_exato", "candidatos": exatos}
    if len(exatos) > 1:
        return {"status": "revisao_modelo_ambiguo", "candidatos": exatos}

    prefixos = [
        r
        for r in registros
        if normalizar_texto(r["name"]).startswith(nome + " ")
    ]

    if len(prefixos) == 1:
        return {
            "status": "revisao_prefixo_unico",
            "candidatos": prefixos,
        }

    if len(prefixos) > 1:
        return {
            "status": "revisao_modelo_ambiguo",
            "candidatos": prefixos,
        }

    return {
        "status": "modelo_nao_encontrado",
        "candidatos": [],
    }


def _selecionar_ano(ano_min: int, anos_fipe: list[dict]) -> dict:
    """Seleciona um ano de referência somente quando seu código é inequívoco.

    O menor ano elegível é uma referência ilustrativa, NÃO o ano de um carro
    real da Uber; múltiplos combustíveis/códigos no mesmo ano exigem revisão.
    """
    elegiveis = []
    for item in anos_fipe:
        codigo = str(item.get("code", ""))
        try:
            ano = int(codigo.split("-")[0])
        except ValueError:
            continue
        if 1900 <= ano <= date.today().year + 2 and ano >= ano_min:
            elegiveis.append({"ano": ano, "code": codigo, "name": str(item.get("name", ""))})
    if not elegiveis:
        return {"status": "ano_nao_encontrado", "candidatos": []}
    menor_ano = min(x["ano"] for x in elegiveis)
    candidatos = [x for x in elegiveis if x["ano"] == menor_ano]
    if len({x["code"] for x in candidatos}) != 1:
        return {"status": "revisao_ano_combustivel", "candidatos": candidatos}
    return {"status": "ano_unico", "candidatos": candidatos}

EQUIVALENCIAS_MARCAS = {
    "CHEVROLET": "GM CHEVROLET",
    "GM": "GM CHEVROLET",
    "VOLKSWAGEN": "VW VOLKSWAGEN",
    "VW": "VW VOLKSWAGEN",
    "KIA": "KIA MOTORS",
    "JAC MOTORS": "JAC",
    "HYUNDAI MOTORS": "HYUNDAI",
    "LANDROVER": "LAND ROVER",
}


def resolver_marca_fipe(marca_uber: str, marcas: dict):
    """Resolve somente equivalências verificadas no catálogo FIPE."""
    nome = normalizar_texto(marca_uber)
    nome = EQUIVALENCIAS_MARCAS.get(nome, nome)

    codigo = marcas.get(nome)

    if codigo is not None:
        return codigo, "marca_encontrada"

    return None, "marca_nao_encontrada"


def construir_mapeamento(forcar: bool = False) -> pd.DataFrame:
    """Constrói mapa auditável; nunca escolhe automaticamente versões ambíguas."""
    uber = _uber()[["marca", "modelo", "ano_min_consulta"]].copy()
    uber = uber.drop_duplicates(["marca", "modelo"]).reset_index(drop=True)
    assinatura = _assinatura_uber(uber)
    if MAPEAMENTO.exists() and not forcar and ASSINATURA.exists():
        if ASSINATURA.read_text(encoding="utf-8").strip() == assinatura:
            mapa_cache = pd.read_csv(MAPEAMENTO)
            if {"status", "marca_uber", "modelo_uber"}.issubset(mapa_cache.columns):
                return mapa_cache

    cliente, catalogo = ClienteFipe(), _carregar_catalogo()
    if not catalogo.get("brands"):
        catalogo["brands"] = cliente.get_json(f"{API_BASE}/brands")
        _salvar_catalogo(catalogo)

    marcas = {
        normalizar_texto(x["name"]): str(x["code"])
        for x in catalogo["brands"] if x.get("name") and x.get("code") is not None
    }

    linhas = []
    for _, row in uber.iterrows():
        marca = str(row["marca"]).strip()
        modelo = str(row["modelo"]).strip()
        ano_min = int(row["ano_min_consulta"])
        registro = {"marca_uber": marca, "modelo_uber": modelo, "ano_min_uber": ano_min,
                    "status": "pendente", "revisar_match": True}
        brand_id, status_marca = resolver_marca_fipe(
        marca,
        marcas
        )

        if brand_id is None:
            registro["status"] = "marca_nao_encontrada"
            linhas.append(registro)
            continue
        registro["brand_id"] = brand_id
        if brand_id not in catalogo["models"]:
            catalogo["models"][brand_id] = cliente.get_json(f"{API_BASE}/brands/{brand_id}/models")
            _salvar_catalogo(catalogo)

        selecao = _selecionar_modelo(modelo, catalogo["models"][brand_id])
        registro["status"] = selecao["status"]
        registro["candidatos_modelos"] = json.dumps(selecao["candidatos"], ensure_ascii=False)
        if selecao["status"] != "modelo_exato":
            linhas.append(registro)
            continue
        melhor = selecao["candidatos"][0]
        model_id = melhor["code"]
        registro.update({"model_id": model_id, "modelo_fipe_match": melhor["name"]})
        chave = f"{brand_id}:{model_id}"
        if chave not in catalogo["years"]:
            catalogo["years"][chave] = cliente.get_json(
                f"{API_BASE}/brands/{brand_id}/models/{model_id}/years"
            )
            _salvar_catalogo(catalogo)
        ano = _selecionar_ano(ano_min, catalogo["years"][chave])
        registro["status"] = ano["status"]
        registro["candidatos_anos"] = json.dumps(ano["candidatos"], ensure_ascii=False)
        if ano["status"] == "ano_unico":
            escolhido = ano["candidatos"][0]
            registro.update({
                "ano_escolhido": escolhido["ano"], "year_code": escolhido["code"],
                "year_name": escolhido["name"], "status": "mapeado",
                "revisar_match": False,
                "criterio_ano": "primeiro_ano_fipe_a_partir_min_uber_nao_ano_real",
                "pontuacao_match": 100.0,
            })
        linhas.append(registro)

    mapa = pd.DataFrame(linhas)
    # Grava artefatos derivados; não apaga RAW nem checkpoint histórico.
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    mapa.to_csv(MAPEAMENTO, index=False, encoding="utf-8-sig")
    ASSINATURA.write_text(assinatura, encoding="utf-8")
    return mapa


def atualizar_precos(forcar_mapeamento: bool = False) -> pd.DataFrame:
    mapa = construir_mapeamento(forcar=forcar_mapeamento)
    validos = mapa.loc[mapa["status"] == "mapeado"].copy()
    if validos.empty:
        raise RuntimeError("Nenhum veículo FIPE mapeado.")

    checkpoint = pd.read_csv(CHECKPOINT) if CHECKPOINT.exists() else pd.DataFrame()
    hoje = date.today().isoformat()
    assinatura_atual = ASSINATURA.read_text(encoding="utf-8").strip()
    if {"data_coleta", "chave", "assinatura_origem"}.issubset(checkpoint.columns):
        mascara = (checkpoint["data_coleta"].astype(str) == hoje) & (checkpoint["assinatura_origem"].astype(str) == assinatura_atual)
        feitos = set(checkpoint.loc[mascara, "chave"].astype(str))
    else:
        feitos = set()
    cliente = ClienteFipe()
    referencia_alvo = None

    for i, (_, row) in enumerate(validos.iterrows(), start=1):
        chave = f"{row['brand_id']}:{row['model_id']}:{row['year_code']}"
        if chave in feitos:
            continue
        url = f"{API_BASE}/brands/{row['brand_id']}/models/{row['model_id']}/years/{row['year_code']}"
        try:
            info = cliente.get_json(url)
        except Exception as exc:
            print(f"FIPE [{i}/{len(validos)}] falhou: {exc}")
            continue

        if (str(info.get("modelYear", "")) != str(int(row["ano_escolhido"]))
                or not info.get("codeFipe") or not info.get("price")):
            print(f"FIPE [{i}/{len(validos)}] resposta inconsistente: {chave}")
            continue

        mes_resposta = str(info["referenceMonth"]).strip()

        if referencia_alvo is None:
            referencia_alvo = mes_resposta
        elif mes_resposta != referencia_alvo:
            print(
                "A referência FIPE mudou: "
                f"{referencia_alvo} -> {mes_resposta}. "
                "Coleta interrompida para não misturar meses."
            )
            break
        
        novo = pd.DataFrame([{
            "chave": chave, "brand_id": row["brand_id"], "model_id": row["model_id"],
            "year_code": row["year_code"], "criterio_ano": row["criterio_ano"],
            "assinatura_origem": assinatura_atual, "marca_uber": row["marca_uber"], "modelo_uber": row["modelo_uber"],
            "marca_fipe": info.get("brand"), "modelo_fipe": info.get("model"),
            "ano_modelo": info.get("modelYear"), "combustivel": info.get("fuel"),
            "preco_fipe": info.get("price"), "codigo_fipe": info.get("codeFipe"),
            "mes_referencia": info.get("referenceMonth"), "data_coleta": hoje,
            "pontuacao_match": row.get("pontuacao_match"), "revisar_match": row.get("revisar_match"),
        }])
        checkpoint = pd.concat([checkpoint, novo], ignore_index=True, sort=False)
        checkpoint.to_csv(CHECKPOINT, index=False, encoding="utf-8-sig")
        feitos.add(chave)
        print(f"FIPE [{i}/{len(validos)}] OK: {row['marca_uber']} {row['modelo_uber']}")

    atual = checkpoint.loc[
        (checkpoint["data_coleta"].astype(str) == hoje)
        & (checkpoint["assinatura_origem"].astype(str) == assinatura_atual)
    ].drop_duplicates("chave", keep="last").copy() if not checkpoint.empty else checkpoint
    if atual.empty:
        raise RuntimeError("Nenhum preço FIPE obtido hoje; histórico mantido no checkpoint, sem substituir saída por valores antigos.")
    atual.to_csv(SAIDA, index=False, encoding="utf-8-sig")
    registrar_coleta(
        "FIPE_API", API_BASE, SAIDA, len(atual),
        data_referencia=str(atual["mes_referencia"].dropna().iloc[0]) if not atual.empty and atual["mes_referencia"].notna().any() else hoje,
        observacao="Atualização incremental com cache e checkpoint",
        extras={"mapeamento": str(MAPEAMENTO), "checkpoint": str(CHECKPOINT)},
    )
    return atual


def coletar_precos_catalogados(
    limite_requisicoes: int = 50,
) -> pd.DataFrame:
    """Coleta preços por versão/ano FIPE sem presumir elegibilidade Uber."""

    from pathlib import Path

    if limite_requisicoes < 0:
        raise ValueError("Limite de requisições deve ser >= 0.")

    origem = Path(
        "dados_relatorios/fipe_anos_catalogados_2026.csv"
    )
    checkpoint_path = CACHE_DIR / "fipe_precos_catalogados_checkpoint.csv"
    saida = OUTPUT_DIR / "08_FIPE_VEICULOS_PARCIAL.csv"

    if not origem.exists():
        raise FileNotFoundError(f"Catálogo não encontrado: {origem}")

    colunas_chave = ["brand_id", "model_id", "year_code"]
    colunas_obrigatorias = set(colunas_chave) | {
        "status_ano_catalogo"
    }

    anos = pd.read_csv(origem, dtype=str)
    faltantes = colunas_obrigatorias - set(anos.columns)

    if faltantes:
        raise ValueError(f"Colunas ausentes: {sorted(faltantes)}")

    anos = anos[
        anos["status_ano_catalogo"].isin([
            "dentro_da_janela_de_estudo",
            "zero_km",
        ])
    ].copy()

    for coluna in colunas_chave:
        anos[coluna] = anos[coluna].astype("string").str.strip()

    if anos[colunas_chave].isna().any().any():
        raise ValueError("Existem identificadores FIPE ausentes.")

    anos = anos.drop_duplicates(colunas_chave).reset_index(drop=True)

    colunas_saida = [
        "brand_id", "model_id", "year_code",
        "codigo_fipe", "marca_fipe", "modelo_fipe",
        "ano_modelo", "combustivel_fipe",
        "preco_fipe", "mes_referencia",
        "status_ano_catalogo", "data_coleta",
        "url_fonte", "elegibilidade_uber_confirmada",
    ]

    if checkpoint_path.exists():
        historico = pd.read_csv(checkpoint_path, dtype=str)
        faltantes_historico = set(colunas_saida) - set(historico.columns)

        if faltantes_historico:
            raise ValueError(
                "Checkpoint com estrutura inesperada: "
                f"{sorted(faltantes_historico)}"
            )

        historico = historico[colunas_saida].copy()
    else:
        historico = pd.DataFrame(columns=colunas_saida)

    hoje = date.today().isoformat()

    # Identifica o mês de referência presente no checkpoint.
    meses = (
        historico["mes_referencia"]
        .dropna()
        .astype(str)
        .str.strip()
        .unique()
        .tolist()
    )

    if len(meses) > 1:
        raise ValueError(
            "O checkpoint contém mais de um mês FIPE. "
            "É necessário selecionar a referência antes da coleta."
        )

    referencia_alvo = meses[0] if meses else None

    ja_coletados_referencia = set(
        map(
            tuple,
            historico.loc[
                historico["mes_referencia"].eq(referencia_alvo),
                colunas_chave,
            ].to_numpy(),
        )
    ) if referencia_alvo is not None else set()

    print(f"Referência FIPE: {referencia_alvo or 'a identificar'}")

    cliente = ClienteFipe()
    novas_linhas = []
    requisicoes = 0
    falhas = 0

    for _, registro in anos.iterrows():
        chave = tuple(str(registro[c]) for c in colunas_chave)

        if chave in ja_coletados_referencia:
            continue

        if requisicoes >= limite_requisicoes:
            break

        brand_id, model_id, year_code = chave

        url = (
            f"{API_BASE}/brands/{brand_id}"
            f"/models/{model_id}/years/{year_code}"
        )

        requisicoes += 1

        try:
            info = cliente.get_json(url)

            if not isinstance(info, dict):
                raise ValueError("Resposta não é um objeto.")

            if not all(
                info.get(campo)
                for campo in ("codeFipe", "price", "referenceMonth")
            ):
                raise ValueError("Resposta sem preço ou identificação.")

            ano_resposta = info.get("modelYear")

            if year_code.startswith("32000-"):
                # Zero km é um código especial, não um ano-modelo.
                ano_modelo = None
            else:
                ano_esperado = int(year_code.split("-")[0])
                if str(ano_resposta) != str(ano_esperado):
                    raise ValueError(
                        f"Ano divergente: {ano_resposta} != {ano_esperado}"
                    )
                ano_modelo = ano_resposta

            novo = {
                "brand_id": brand_id,
                "model_id": model_id,
                "year_code": year_code,
                "codigo_fipe": info["codeFipe"],
                "marca_fipe": info.get("brand"),
                "modelo_fipe": info.get("model"),
                "ano_modelo": ano_modelo,
                "combustivel_fipe": info.get("fuel"),
                "preco_fipe": info["price"],
                "mes_referencia": info["referenceMonth"],
                "status_ano_catalogo": registro["status_ano_catalogo"],
                "data_coleta": hoje,
                "url_fonte": url,
                "elegibilidade_uber_confirmada": False,
            }

            novas_linhas.append(novo)
            ja_coletados_referencia.add(chave)

            # Salva cada resultado, permitindo retomada segura.
            historico = pd.concat(
                [historico, pd.DataFrame([novo])],
                ignore_index=True,
            )
            checkpoint_path.parent.mkdir(
                parents=True, exist_ok=True
            )
            historico.to_csv(
                checkpoint_path,
                index=False,
                encoding="utf-8-sig",
            )

        except (requests.RequestException, ValueError) as exc:
            falhas += 1
            print(f"Falha FIPE {chave}: {exc}")

            if isinstance(exc, requests.HTTPError):
                resposta = exc.response
                if resposta is not None and resposta.status_code == 429:
                    print("Cota da API atingida. Interrompendo coleta.")
                    break

    # Exporta apenas uma cotação por chave no dia de referência.
    atual = historico.loc[
    historico["mes_referencia"].eq(referencia_alvo)
    ].sort_values(
    "data_coleta"
    ).drop_duplicates(
    colunas_chave,
    keep="last"
    ).copy()

    saida.parent.mkdir(parents=True, exist_ok=True)
    atual.to_csv(saida, index=False, encoding="utf-8-sig")

    chaves_atual = set(
        map(tuple, atual[colunas_chave].to_numpy())
    )

    chaves_esperadas = set(
        map(tuple, anos[colunas_chave].to_numpy())
    )

    print(f"Combinações no catálogo: {len(anos)}")
    print(f"Novas requisições: {requisicoes}")
    print(f"Falhas: {falhas}")
    print(f"Preços válidos de hoje: {len(chaves_atual)}")
    print(
        "Combinações pendentes:",
        len(chaves_esperadas - chaves_atual),
    )
    print(f"CSV parcial: {saida}")

    if chaves_esperadas == chaves_atual:
        print("Cobertura integral do catálogo de entrada atual.")
    else:
        print("Coleta parcial; CSV principal preservado.")

    return atual


def main() -> None:
    parser = argparse.ArgumentParser(description="Pipeline FIPE incremental")
    parser.add_argument("--remapear", action="store_true")
    parser.add_argument("--somente-mapear", action="store_true")

    parser.add_argument(
        "--precos-catalogados",
        action="store_true",
        help="Coletar preços das versões/anos catalogados."
    )

    parser.add_argument(
        "--limite-precos",
        type=int,
        default=50,
        help="Máximo de requisições de preço nesta execução."
    )

    args = parser.parse_args()
    if args.precos_catalogados:
        coletar_precos_catalogados(args.limite_precos)
        return

    mapa = construir_mapeamento(forcar=args.remapear)
    print(f"Mapeamento FIPE: {len(mapa):,} modelos")
    if not args.somente_mapear:
        atual = atualizar_precos()
        print(f"FIPE: {len(atual):,} preços -> {SAIDA}")


if __name__ == "__main__":
    main()
