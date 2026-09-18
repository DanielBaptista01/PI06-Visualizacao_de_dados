from __future__ import annotations

import argparse
import json
import os
import time
from datetime import date

import pandas as pd
import requests

from pipeline_utils import CACHE_DIR, OUTPUT_DIR, localizar_coluna, normalizar_texto, registrar_coleta

API_BASE = os.getenv("FIPE_API_BASE", "https://fipe.parallelum.com.br/api/v2/cars")
MAPEAMENTO = CACHE_DIR / "fipe_mapeamento.csv"
CATALOGO = CACHE_DIR / "fipe_catalogo.json"
CHECKPOINT = CACHE_DIR / "fipe_checkpoint.csv"
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
    df["ano_min_consulta"] = df[anos].min(axis=1, skipna=True)
    return df.loc[df["ano_min_consulta"].notna()].copy()


def _filtrar_inmetro(uber: pd.DataFrame) -> pd.DataFrame:
    caminho = OUTPUT_DIR / "05_INMETRO.csv"
    if not caminho.exists():
        return uber
    try:
        inmetro = pd.read_csv(caminho)
    except Exception:
        return uber
    cm = localizar_coluna(inmetro, ["MARCA", "FABRICANTE"], contem=True)
    cmo = localizar_coluna(inmetro, ["MODELO", "VERSAO", "VERSÃO"], contem=True)
    if not cm or not cmo:
        return uber

    chaves = [(normalizar_texto(m), normalizar_texto(x)) for m, x in zip(inmetro[cm], inmetro[cmo])]
    def relevante(row: pd.Series) -> bool:
        marca, modelo = normalizar_texto(row["marca"]), normalizar_texto(row["modelo"])
        return any(
            (marca == mi or marca in mi or mi in marca) and
            (modelo in moi or moi in modelo or any(p in moi.split() for p in modelo.split()))
            for mi, moi in chaves if mi and moi
        )
    filtrado = uber.loc[uber.apply(relevante, axis=1)].copy()
    return filtrado if len(filtrado) >= max(10, int(len(uber) * 0.15)) else uber


def _carregar_catalogo() -> dict:
    if CATALOGO.exists():
        try:
            return json.loads(CATALOGO.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"brands": None, "models": {}, "years": {}}


def _salvar_catalogo(catalogo: dict) -> None:
    CATALOGO.write_text(json.dumps(catalogo, ensure_ascii=False, indent=2), encoding="utf-8")


def _pontuar(uber: str, fipe: str) -> float:
    u, f = normalizar_texto(uber), normalizar_texto(fipe)
    if not u or not f:
        return 0.0
    if u == f:
        return 100.0
    if u in f:
        return 85.0
    if f in u:
        return 75.0
    inter = set(u.split()) & set(f.split())
    return 60.0 * len(inter) / max(len(set(u.split())), 1) if inter else 0.0


def construir_mapeamento(forcar: bool = False) -> pd.DataFrame:
    if MAPEAMENTO.exists() and not forcar:
        return pd.read_csv(MAPEAMENTO)

    uber = _filtrar_inmetro(_uber())[["marca", "modelo", "ano_min_consulta"]].drop_duplicates(["marca", "modelo"])
    cliente, catalogo = ClienteFipe(), _carregar_catalogo()
    if not catalogo.get("brands"):
        catalogo["brands"] = cliente.get_json(f"{API_BASE}/brands")
        _salvar_catalogo(catalogo)

    marcas = {normalizar_texto(x.get("name")): str(x.get("code")) for x in catalogo["brands"] if x.get("name") and x.get("code") is not None}
    equivalencias = {"VW": "VOLKSWAGEN", "GM": "CHEVROLET", "LANDROVER": "LAND ROVER"}
    linhas = []

    for _, row in uber.iterrows():
        marca_uber, modelo_uber = str(row["marca"]).strip(), str(row["modelo"]).strip()
        ano_min = int(row["ano_min_consulta"])
        marca_norm = equivalencias.get(normalizar_texto(marca_uber), normalizar_texto(marca_uber))
        brand_id = marcas.get(marca_norm)
        if not brand_id:
            candidatos = [(n, c) for n, c in marcas.items() if marca_norm in n or n in marca_norm]
            brand_id = candidatos[0][1] if candidatos else None
        if not brand_id:
            linhas.append({"marca_uber": marca_uber, "modelo_uber": modelo_uber, "status": "marca_nao_encontrada"})
            continue

        if brand_id not in catalogo["models"]:
            catalogo["models"][brand_id] = cliente.get_json(f"{API_BASE}/brands/{brand_id}/models")
            _salvar_catalogo(catalogo)
        pontuados = sorted(
            [(_pontuar(modelo_uber, m.get("name", "")), m) for m in catalogo["models"][brand_id]],
            key=lambda x: x[0], reverse=True,
        )
        score, melhor = pontuados[0] if pontuados else (0.0, None)
        if not melhor or score < 30:
            linhas.append({"marca_uber": marca_uber, "modelo_uber": modelo_uber, "brand_id": brand_id, "status": "modelo_nao_encontrado"})
            continue

        model_id = str(melhor.get("code"))
        chave = f"{brand_id}:{model_id}"
        if chave not in catalogo["years"]:
            catalogo["years"][chave] = cliente.get_json(f"{API_BASE}/brands/{brand_id}/models/{model_id}/years")
            _salvar_catalogo(catalogo)

        elegiveis = []
        for item in catalogo["years"][chave]:
            codigo = str(item.get("code", ""))
            try:
                ano = int(codigo.split("-")[0])
            except ValueError:
                continue
            if 1900 <= ano <= 3000 and ano >= ano_min:
                elegiveis.append((ano, codigo, item.get("name")))
        elegiveis.sort(key=lambda x: x[0])
        if not elegiveis:
            linhas.append({"marca_uber": marca_uber, "modelo_uber": modelo_uber, "brand_id": brand_id, "model_id": model_id, "status": "ano_nao_encontrado"})
            continue

        ano, year_code, year_name = elegiveis[0]
        linhas.append({
            "marca_uber": marca_uber, "modelo_uber": modelo_uber, "ano_min_uber": ano_min,
            "brand_id": brand_id, "model_id": model_id, "year_code": year_code,
            "ano_escolhido": ano, "year_name": year_name, "modelo_fipe_match": melhor.get("name"),
            "pontuacao_match": score, "revisar_match": score < 70, "status": "mapeado",
        })

    mapa = pd.DataFrame(linhas)
    mapa.to_csv(MAPEAMENTO, index=False, encoding="utf-8-sig")
    return mapa


def atualizar_precos(forcar_mapeamento: bool = False) -> pd.DataFrame:
    mapa = construir_mapeamento(forcar=forcar_mapeamento)
    validos = mapa.loc[mapa["status"] == "mapeado"].copy()
    if validos.empty:
        raise RuntimeError("Nenhum veículo FIPE mapeado.")

    checkpoint = pd.read_csv(CHECKPOINT) if CHECKPOINT.exists() else pd.DataFrame()
    hoje = date.today().isoformat()
    feitos = set(checkpoint.loc[checkpoint.get("data_coleta", pd.Series(dtype=str)) == hoje, "chave"].astype(str)) if not checkpoint.empty else set()
    cliente = ClienteFipe()

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

        novo = pd.DataFrame([{
            "chave": chave, "marca_uber": row["marca_uber"], "modelo_uber": row["modelo_uber"],
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

    atual = checkpoint.loc[checkpoint["data_coleta"] == hoje].copy() if not checkpoint.empty else checkpoint
    if atual.empty and not checkpoint.empty:
        atual = checkpoint.sort_values("data_coleta").drop_duplicates("chave", keep="last")
    atual.to_csv(SAIDA, index=False, encoding="utf-8-sig")
    registrar_coleta(
        "FIPE_API", API_BASE, SAIDA, len(atual),
        data_referencia=str(atual["mes_referencia"].dropna().iloc[0]) if not atual.empty and atual["mes_referencia"].notna().any() else hoje,
        observacao="Atualização incremental com cache e checkpoint",
        extras={"mapeamento": str(MAPEAMENTO), "checkpoint": str(CHECKPOINT)},
    )
    return atual


def main() -> None:
    parser = argparse.ArgumentParser(description="Pipeline FIPE incremental")
    parser.add_argument("--remapear", action="store_true")
    parser.add_argument("--somente-mapear", action="store_true")
    args = parser.parse_args()
    mapa = construir_mapeamento(forcar=args.remapear)
    print(f"Mapeamento FIPE: {len(mapa):,} modelos")
    if not args.somente_mapear:
        atual = atualizar_precos()
        print(f"FIPE: {len(atual):,} preços -> {SAIDA}")


if __name__ == "__main__":
    main()
