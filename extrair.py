import os
import glob
import re
import time
import unicodedata
import requests
import pandas as pd
from bs4 import BeautifulSoup

# ====================================================
# CONTROLE DE EXECUÇÃO DO PIPELINE
# ====================================================
RODAR_ABVE           = True   # True: Filtra as bases da ABVE para o Município de SP
RODAR_ANEEL          = False  # False: Já gerou 02_ANEEL_SP.csv
RODAR_ANP            = False  # False: Já gerou 03_ANP_SP.csv
RODAR_FIPE           = False  # False: Evita reiniciar a consulta de 20 min à API
RODAR_IBGE           = False  # False: Já gerou 04_IBGE_SP.csv
RODAR_INMETRO        = False  # False: Já gerou 05_INMETRO.csv
RODAR_SENATRAN       = False  # False: Leitura pesada de múltiplos arquivos
RODAR_ORIGEM_DESTINO = False  # False: Leitura pesada de múltiplos arquivos
RODAR_UBER           = False  # False: Já gerou 09_UBER_MODELOS_SP.csv
RODAR_OPEN_CHARGE    = True   # True: Consulta a API e salva eletropostos da Grande SP

# ----------------------------------------------------
# 0. CONFIGURAÇÃO DA PASTA DE SAÍDA
# ----------------------------------------------------
pasta_saida = "dados_limpos"
os.makedirs(pasta_saida, exist_ok=True)
print(f"Salvando bases limpas em: ./{pasta_saida}/\n")

# ----------------------------------------------------
# 1. ABVE (Filtrar exclusivamente o Município de São Paulo)
# ----------------------------------------------------
if RODAR_ABVE:
    print("Processando ABVE (Filtro Município de São Paulo)...")

    # 1.1 Vendas Gerais (BEV / PHEV / HEV)
    caminho_abve_mun = os.path.join("ABVE", "dados_limpos_11_ABVE_VENDAS_MUNICIPIOS.csv")
    if os.path.exists(caminho_abve_mun):
        df_abve_mun = pd.read_csv(caminho_abve_mun)
        df_abve_sp = df_abve_mun[
            (df_abve_mun["Municipio"].astype(str).str.strip().str.upper() == "SÃO PAULO") &
            (df_abve_mun["Estado"].astype(str).str.strip().str.upper() == "SP")
        ].copy()
        saida_abve_sp = os.path.join(pasta_saida, "11_ABVE_VENDAS_SAO_PAULO.csv")
        df_abve_sp.to_csv(saida_abve_sp, index=False, encoding="utf-8-sig")
        print(f"-> Vendas Eletrificados SP: {df_abve_sp['Quantidade'].sum():,} veículos salvos em '{saida_abve_sp}'.")
    else:
        print(f"Aviso: {caminho_abve_mun} não encontrado.")

    # 1.2 Eletropostos (AC e DC)
    caminho_abve_eletro = os.path.join("ABVE", "dados_limpos_15_ABVE_ELETROPOSTOS_MUNICIPIOS.csv")
    if os.path.exists(caminho_abve_eletro):
        df_abve_eletro = pd.read_csv(caminho_abve_eletro)
        df_eletro_sp = df_abve_eletro[
            (df_abve_eletro["Municipio"].astype(str).str.strip().str.upper() == "SÃO PAULO") &
            (df_abve_eletro["Estado"].astype(str).str.strip().str.upper() == "SP")
        ].copy()
        saida_eletro_sp = os.path.join(pasta_saida, "15_ABVE_ELETROPOSTOS_SAO_PAULO.csv")
        df_eletro_sp.to_csv(saida_eletro_sp, index=False, encoding="utf-8-sig")
        print(f"-> Eletropostos SP: {df_eletro_sp['Total_Eletropostos'].sum():,} postos salvos em '{saida_eletro_sp}'.")
    else:
        print(f"Aviso: {caminho_abve_eletro} não encontrado.")

    # 1.3 Micro-Híbridos (MHEV)
    caminho_abve_mhev = os.path.join("ABVE", "dados_limpos_16_ABVE_VENDAS_MHEV_MUNICIPIOS.csv")
    if os.path.exists(caminho_abve_mhev):
        df_abve_mhev = pd.read_csv(caminho_abve_mhev)
        df_mhev_sp = df_abve_mhev[
            (df_abve_mhev["Municipio"].astype(str).str.strip().str.upper() == "SÃO PAULO") &
            (df_abve_mhev["Estado"].astype(str).str.strip().str.upper() == "SP")
        ].copy()
        saida_mhev_sp = os.path.join(pasta_saida, "16_ABVE_VENDAS_MHEV_SAO_PAULO.csv")
        df_mhev_sp.to_csv(saida_mhev_sp, index=False, encoding="utf-8-sig")
        print(f"-> Micro-Híbridos (MHEV) SP: {df_mhev_sp['Quantidade_MHEV'].sum():,} veículos salvos em '{saida_mhev_sp}'.")
    else:
        print(f"Aviso: {caminho_abve_mhev} não encontrado.")

# 1.4 Vendas por Modelo e Fabricante (Cópia / Padronização)
    caminho_abve_mod = os.path.join("ABVE", "dados_limpos_14_ABVE_VENDAS_POR_MODELO.csv")
    if not os.path.exists(caminho_abve_mod):
        caminho_abve_mod = os.path.join(pasta_saida, "14_ABVE_VENDAS_POR_MODELO.csv")

    if os.path.exists(caminho_abve_mod):
        df_abve_mod = pd.read_csv(caminho_abve_mod)
        saida_mod = os.path.join(pasta_saida, "14_ABVE_VENDAS_POR_MODELO.csv")
        df_abve_mod.to_csv(saida_mod, index=False, encoding="utf-8-sig")
        print(f"-> Modelos ABVE: {len(df_abve_mod):,} modelos carregados em '{saida_mod}'.")
    else:
        print(f"Aviso: {caminho_abve_mod} não encontrado.")

# ----------------------------------------------------
# 2. ANEEL (Excel) -> Filtrar SP
# ----------------------------------------------------
if RODAR_ANEEL:
    caminho_aneel = "ANEEL/data.xlsx"
    if os.path.exists(caminho_aneel):
        print("\nProcessando ANEEL...")
        df_aneel = pd.read_excel(caminho_aneel)
        col_uf = [c for c in df_aneel.columns if c.upper() in ['UF', 'SIGLA_UF', 'ESTADO']]
        if col_uf:
            df_aneel = df_aneel[df_aneel[col_uf[0]].astype(str).str.upper() == 'SP']
        df_aneel.to_csv(f"{pasta_saida}/02_ANEEL_SP.csv", index=False, encoding="utf-8-sig")
        print(f"-> ANEEL concluída ({len(df_aneel)} registros salvos).")
    else:
        print(f"\nAviso: {caminho_aneel} não encontrado.")

# ----------------------------------------------------
# 3. ANP (CSV) -> Filtrar SP    
# ----------------------------------------------------
if RODAR_ANP:
    caminho_anp = "ANP/Agosto-26/08-dados-abertos-precos-2026-08-gasolina-etanol.csv"
    if os.path.exists(caminho_anp):
        print("\nProcessando ANP...")
        df_anp = pd.read_csv(caminho_anp, sep=";", encoding="latin1")
        col_uf_anp = [c for c in df_anp.columns if 'ESTADO' in c.upper() or 'UF' in c.upper()]
        if col_uf_anp:
            df_anp = df_anp[df_anp[col_uf_anp[0]].astype(str).str.upper() == 'SP']
        df_anp.to_csv(f"{pasta_saida}/03_ANP_SP.csv", index=False, encoding="utf-8-sig")
        print(f"-> ANP concluída ({len(df_anp)} registros salvos).")
    else:
        print(f"\nAviso: {caminho_anp} não encontrado.")

# ----------------------------------------------------
# 4. FIPE
# ----------------------------------------------------
if RODAR_FIPE:
    caminho_uber = os.path.join(pasta_saida, "09_UBER_MODELOS_SP.csv")
    caminho_csv_fipe = os.path.join(pasta_saida, "08_FIPE_VEICULOS.csv")
    url_base = "https://fipe.parallelum.com.br/api/v2/cars"

    def requisicao_segura(url, max_tentativas=4, espera_base=2.0):
        for tentativa in range(max_tentativas):
            try:
                res = requests.get(url, timeout=15)
                if res.status_code == 429:
                    tempo_espera = espera_base * (tentativa + 1)
                    print(f"  [Aviso 429 - Limite de taxa] Aguardando {tempo_espera:.1f}s...")
                    time.sleep(tempo_espera)
                    continue
                res.raise_for_status()
                return res
            except requests.exceptions.RequestException as e:
                if tentativa == max_tentativas - 1:
                    print(f"  [Falha na URL]: {url} -> {e}")
                    return None
                time.sleep(1.0)
        return None

    if not os.path.exists(caminho_uber):
        print(f"\nErro: Arquivo '{caminho_uber}' não encontrado.")
    else:
        print("\nProcessando FIPE...")
        df_uber = pd.read_csv(caminho_uber)
        colunas_obrigatorias = ["marca", "modelo", "uberx_ano_min"]
        colunas_faltantes = [col for col in colunas_obrigatorias if col not in df_uber.columns]

        if colunas_faltantes:
            print(f"Erro: Colunas não encontradas no arquivo da Uber: {colunas_faltantes}")
        else:
            df_uber["uberx_ano_min"] = pd.to_numeric(df_uber["uberx_ano_min"], errors="coerce")
            df_valido = df_uber[df_uber["uberx_ano_min"].notna()].copy()
            df_valido["uberx_ano_min"] = df_valido["uberx_ano_min"].astype(int)

            def normalizar_texto(texto):
                texto = str(texto).strip().upper()
                texto = re.sub(r"DOWN", "", texto, flags=re.IGNORECASE)
                texto = unicodedata.normalize("NFKD", texto).encode("ASCII", "ignore").decode("ASCII")
                texto = re.sub(r"[^A-Z0-9]+", " ", texto)
                return re.sub(r"\s+", " ", texto).strip()

            equivalencias_marcas = {
                "VW": "VOLKSWAGEN",
                "VOLKSWAGEN": "VOLKSWAGEN",
                "GM": "CHEVROLET",
                "CHEVROLET": "CHEVROLET",
                "MERCEDES BENZ": "MERCEDES BENZ",
                "MERCEDES-BENZ": "MERCEDES BENZ",
                "LAND ROVER": "LAND ROVER",
                "LANDROVER": "LAND ROVER"
            }

            def encontrar_marca(marca_uber, mapa_marcas):
                marca_norm = normalizar_texto(marca_uber)
                marca_norm = equivalencias_marcas.get(marca_norm, marca_norm)
                if marca_norm in mapa_marcas:
                    return mapa_marcas[marca_norm]
                for nome_fipe, codigo_fipe in mapa_marcas.items():
                    nome_norm = normalizar_texto(nome_fipe)
                    if marca_norm == nome_norm or marca_norm in nome_norm or nome_norm in marca_norm:
                        return codigo_fipe
                return None

            res_marcas = requisicao_segura(f"{url_base}/brands")
            marcas_fipe = res_marcas.json() if res_marcas else []

            mapa_marcas = {}
            for marca in marcas_fipe:
                nome = marca.get("name")
                codigo = marca.get("code")
                if nome and codigo:
                    mapa_marcas[normalizar_texto(nome)] = str(codigo)

            modelos_para_consulta = df_valido[["marca", "modelo", "uberx_ano_min"]].drop_duplicates(subset=["marca", "modelo"])
            print(f"Iniciando consulta para {len(modelos_para_consulta)} modelos da Uber...")

            cache_modelos = {}
            cache_anos = {}
            dados_fipe = []

            for _, linha in modelos_para_consulta.iterrows():
                marca_original = str(linha["marca"]).strip()
                modelo_original = str(linha["modelo"]).strip()
                ano_corte = int(linha["uberx_ano_min"])
                modelo_normalizado = normalizar_texto(modelo_original)

                brand_id = encontrar_marca(marca_original, mapa_marcas)
                if not brand_id:
                    print(f"[MARCA NÃO ENCONTRADA] {marca_original}")
                    continue

                if brand_id not in cache_modelos:
                    res_mod = requisicao_segura(f"{url_base}/brands/{brand_id}/models")
                    cache_modelos[brand_id] = res_mod.json() if res_mod else []
                    time.sleep(0.5)

                lista_modelos = cache_modelos[brand_id]
                model_id = None
                melhor_modelo = None
                melhor_pontuacao = 0

                for mod in lista_modelos:
                    nome_mod = str(mod.get("name", "")).strip()
                    nome_mod_norm = normalizar_texto(nome_mod)
                    if not nome_mod_norm:
                        continue

                    pontuacao = 0
                    if modelo_normalizado == nome_mod_norm:
                        pontuacao = 100
                    elif modelo_normalizado in nome_mod_norm:
                        pontuacao = 80
                    elif nome_mod_norm in modelo_normalizado:
                        pontuacao = 70
                    else:
                        palavras_uber = set(modelo_normalizado.split())
                        palavras_fipe = set(nome_mod_norm.split())
                        palavras_comuns = palavras_uber & palavras_fipe
                        if palavras_comuns:
                            pontuacao = (len(palavras_comuns) / max(len(palavras_uber), 1)) * 50

                    if pontuacao > melhor_pontuacao:
                        melhor_pontuacao = pontuacao
                        model_id = str(mod.get("code"))
                        melhor_modelo = nome_mod

                if not model_id:
                    print(f"[MODELO NÃO ENCONTRADO] {marca_original} - {modelo_original}")
                    continue

                print(f"Modelo encontrado: {marca_original} {modelo_original} -> {melhor_modelo}")

                chave_anos = (brand_id, model_id)
                if chave_anos not in cache_anos:
                    res_anos = requisicao_segura(f"{url_base}/brands/{brand_id}/models/{model_id}/years")
                    cache_anos[chave_anos] = res_anos.json() if res_anos else []
                    time.sleep(0.5)

                lista_anos = cache_anos[chave_anos]
                ano_escolhido = None
                for item_ano in lista_anos:
                    codigo_ano = str(item_ano.get("code", ""))
                    if not codigo_ano:
                        continue
                    try:
                        ano_num = int(codigo_ano.split("-")[0])
                    except ValueError:
                        continue
                    if 1900 <= ano_num <= 3000 and ano_num >= ano_corte:
                        ano_escolhido = codigo_ano
                        break

                if not ano_escolhido:
                    print(f"[ANO NÃO ENCONTRADO] {marca_original} - {modelo_original} (mínimo {ano_corte})")
                    continue

                url_detalhe = f"{url_base}/brands/{brand_id}/models/{model_id}/years/{ano_escolhido}"
                res_detalhe = requisicao_segura(url_detalhe)
                if not res_detalhe:
                    continue

                info = res_detalhe.json()
                dados_fipe.append({
                    "marca_uber": marca_original,
                    "modelo_uber": modelo_original,
                    "marca_fipe": info.get("brand"),
                    "modelo_fipe": info.get("model"),
                    "ano_modelo": info.get("modelYear"),
                    "combustivel": info.get("fuel"),
                    "preco_fipe": info.get("price"),
                    "codigo_fipe": info.get("codeFipe"),
                    "mes_referencia": info.get("referenceMonth")
                })
                print(f"  Sucesso: {info.get('model')} ({info.get('modelYear')}) -> {info.get('price')}")
                time.sleep(1.2)

            if dados_fipe:
                df_fipe = pd.DataFrame(dados_fipe)
                df_fipe.to_csv(caminho_csv_fipe, index=False, encoding="utf-8-sig")
                print(f"\nConcluído: {len(df_fipe)} veículos salvos em '{caminho_csv_fipe}'.")
            else:
                print("\nNenhum dado retornado pela FIPE.")

# ----------------------------------------------------
# 5. IBGE (Excel extraído do DBF)
# ----------------------------------------------------
if RODAR_IBGE:
    caminho_ibge = "IBGE—mapa_da_RMSP/SP_Municipios_2025.dbf.xlsx"
    if os.path.exists(caminho_ibge):
        print("\nProcessando IBGE...")
        df_ibge = pd.read_excel(caminho_ibge)
        df_ibge.to_csv(f"{pasta_saida}/04_IBGE_SP.csv", index=False, encoding="utf-8-sig")
        print(f"-> IBGE concluído ({len(df_ibge)} municípios salvos).")
    else:
        print(f"\nAviso: {caminho_ibge} não encontrado.")

# ----------------------------------------------------
# 6. INMETRO (Excel)
# ----------------------------------------------------
if RODAR_INMETRO:
    caminho_inmetro = "INMETRO/dados-inmetro.xlsx"
    if os.path.exists(caminho_inmetro):
        print("\nProcessando INMETRO...")
        df_inmetro = pd.read_excel(caminho_inmetro)
        df_inmetro.to_csv(f"{pasta_saida}/05_INMETRO.csv", index=False, encoding="utf-8-sig")
        print(f"-> INMETRO concluído ({len(df_inmetro)} modelos salvos).")
    else:
        print(f"\nAviso: {caminho_inmetro} não encontrado.")

# ----------------------------------------------------
# 7. SENATRAN (Múltiplos Excels) -> Filtrar SP
# ----------------------------------------------------
if RODAR_SENATRAN:
    print("\nProcessando SENATRAN...")
    arquivos_senatran = glob.glob("SENATRAN/**/*.xlsx", recursive=True)
    if arquivos_senatran:
        dfs_senatran = []
        for arq in arquivos_senatran:
            try:
                temp_df = pd.read_excel(arq)
                col_uf_sena = [c for c in temp_df.columns if c.upper() in ['UF', 'SG_UF', 'ESTADO']]
                if col_uf_sena:
                    temp_df = temp_df[temp_df[col_uf_sena[0]].astype(str).str.upper() == 'SP']
                dfs_senatran.append(temp_df)
            except Exception as e:
                print(f"Erro ao ler {arq}: {e}")
        if dfs_senatran:
            df_senatran_final = pd.concat(dfs_senatran, ignore_index=True)
            df_senatran_final.to_csv(f"{pasta_saida}/06_SENATRAN_SP.csv", index=False, encoding="utf-8-sig")
            print(f"-> SENATRAN concluído ({len(df_senatran_final)} registros salvos).")
    else:
        print("Aviso: Nenhum arquivo Excel encontrado na pasta SENATRAN.")

# ----------------------------------------------------
# 8. ORIGEM E DESTINO (Múltiplos Excels)
# ----------------------------------------------------
if RODAR_ORIGEM_DESTINO:
    print("\nProcessando ORIGEM E DESTINO...")
    arquivos_od = glob.glob("ORIGEM_E_DESTINO*/**/*.xlsx", recursive=True)
    if arquivos_od:
        dfs_od = []
        for arq in arquivos_od:
            try:
                temp_df = pd.read_excel(arq)
                dfs_od.append(temp_df)
            except Exception as e:
                print(f"Erro ao ler {arq}: {e}")
        if dfs_od:
            df_od_final = pd.concat(dfs_od, ignore_index=True)
            df_od_final.to_csv(f"{pasta_saida}/07_ORIGEM_DESTINO.csv", index=False, encoding="utf-8-sig")
            print(f"-> ORIGEM E DESTINO concluído ({len(df_od_final)} registros salvos).")
    else:
        print("Aviso: Nenhum arquivo Excel encontrado na pasta ORIGEM E DESTINO.")

# ----------------------------------------------------
# 9. UBER (HTML/MHT -> SP)
# ----------------------------------------------------
if RODAR_UBER:
    caminho_uber_html = "UBER/modelos_carros_uber.html"
    if os.path.exists(caminho_uber_html):
        print("\nProcessando UBER...")
        ANO_CORTE_GERAL_COMFORT = 2019
        ANO_CORTE_GERAL_BLACK = 2019

        EXCECOES_ANO_COMFORT = {"ETIOS SEDAN": 2019, "COBALT": 2019}
        EXCECOES_ANO_BLACK = {"CITY": 2023, "DOLPHIN": 2024, "VIRTUS": 2025, "PEUGEOT 2008": 2025}

        with open(caminho_uber_html, "r", encoding="utf-8", errors="ignore") as f:
            soup = BeautifulSoup(f.read(), "html.parser")

        dados_uber = []
        blocos = soup.find_all("details")

        for b in blocos:
            summary = b.find("summary")
            if not summary:
                continue
            marca = summary.get_text(strip=True)

            for li in b.find_all("li"):
                tag_b = li.find("b")
                if not tag_b:
                    continue
                modelo = tag_b.get_text(strip=True)
                texto_regra = li.get_text(separator=" ", strip=True)

                ano_x = re.search(r"(\d{4})\s*\([^)]*UberX", texto_regra)
                ano_comfort = re.search(r"(\d{4})\s*\([^)]*Comfort", texto_regra)
                ano_black = re.search(r"(\d{4})\s*\([^)]*Black", texto_regra)
                ano_electric = re.search(r"(\d{4})\s*\([^)]*Electric", texto_regra)

                val_x = int(ano_x.group(1)) if ano_x else None
                val_comfort = int(ano_comfort.group(1)) if ano_comfort else None
                val_black = int(ano_black.group(1)) if ano_black else None
                val_electric = int(ano_electric.group(1)) if ano_electric else None

                modelo_upper = modelo.upper()

                if val_comfort is not None:
                    for mod_exc, ano_min in EXCECOES_ANO_COMFORT.items():
                        if mod_exc in modelo_upper:
                            val_comfort = max(val_comfort, ano_min)
                            break
                    else:
                        val_comfort = max(val_comfort, ANO_CORTE_GERAL_COMFORT)

                if val_black is not None:
                    for mod_exc, ano_min in EXCECOES_ANO_BLACK.items():
                        if mod_exc in modelo_upper:
                            val_black = max(val_black, ano_min)
                            break
                    else:
                        val_black = max(val_black, ANO_CORTE_GERAL_BLACK)

                if any([val_x, val_comfort, val_black, val_electric]):
                    dados_uber.append({
                        "marca": marca,
                        "modelo": modelo,
                        "uberx_ano_min": val_x,
                        "comfort_ano_min": val_comfort,
                        "black_ano_min": val_black,
                        "electric_ano_min": val_electric
                    })

        df_uber = pd.DataFrame(dados_uber)
        caminho_csv_uber = f"{pasta_saida}/09_UBER_MODELOS_SP.csv"
        df_uber.to_csv(caminho_csv_uber, index=False, encoding="utf-8-sig")
        print(f"-> UBER concluída ({len(df_uber)} veículos elegíveis salvos em '{caminho_csv_uber}').")
    else:
        print(f"\nAviso: Arquivo '{caminho_uber_html}' não encontrado.")

# ----------------------------------------------------
# 10. ELETROPOSTOS API (Open Charge Map) -> Grande SP
# ----------------------------------------------------
if RODAR_OPEN_CHARGE:
    print("\nProcessando Open Charge Map...")
    caminho_csv_ocm = os.path.join(pasta_saida, "10_OPEN_CHARGE_MAP_SP.csv")
    API_KEY = "5cbc8144-0d21-4e11-850b-777536b49587"
    url_ocm = "https://api.openchargemap.io/v3/poi/"

    parametros_ocm = {
        "key": API_KEY,
        "countrycode": "BR",
        "latitude": -23.5505,
        "longitude": -46.6333,
        "distance": 50,
        "distanceunit": "KM",
        "maxresults": 500,
        "compact": True,
        "verbose": False
    }

    headers_ocm = {
        "User-Agent": "UberFleetAnalysis/1.0",
        "X-API-Key": API_KEY
    }

    try:
        res = requests.get(url_ocm, params=parametros_ocm, headers=headers_ocm, timeout=20)
        res.raise_for_status()
        dados_ocm = res.json()

        postos_processados = []

        for item in dados_ocm:
            endereco = item.get("AddressInfo", {})
            conexoes = item.get("Connections", [])
            operador = item.get("OperatorInfo", {})

            potencias = [c.get("PowerKW") for c in conexoes if c.get("PowerKW") is not None]
            potencia_max = max(potencias) if potencias else None

            tipos_plugue = list(set([
                c.get("ConnectionType", {}).get("Title", "Desconhecido")
                for c in conexoes if c.get("ConnectionType")
            ]))

            postos_processados.append({
                "id_posto": item.get("ID"),
                "titulo": endereco.get("Title"),
                "operadora": operador.get("Title") if operador else "Não informado",
                "logradouro": endereco.get("AddressLine1"),
                "bairro_cidade": endereco.get("Town"),
                "latitude": endereco.get("Latitude"),
                "longitude": endereco.get("Longitude"),
                "qtd_pontos_recarga": len(conexoes),
                "potencia_max_kw": potencia_max,
                "tipos_conectores": ", ".join(tipos_plugue),
                "status_operacional": item.get("StatusType", {}).get("Title", "Operacional") if item.get("StatusType") else "Desconhecido",
                "custo_uso": item.get("UsageCost")
            })

        if postos_processados:
            df_postos = pd.DataFrame(postos_processados)
            df_postos.to_csv(caminho_csv_ocm, index=False, encoding="utf-8-sig")
            print(f"-> Open Charge Map concluída ({len(df_postos)} postos salvos em '{caminho_csv_ocm}').")
        else:
            print("Nenhum posto retornado pela Open Charge Map.")

    except requests.exceptions.RequestException as e:
        print(f"Erro na requisição da Open Charge Map: {e}")

print("\nExecução concluída! Verifique a pasta 'dados_limpos/'.")