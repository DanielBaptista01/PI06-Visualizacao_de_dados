import pandas as pd
import os
import glob

def ver_arquivo(caminho, tipo="excel", sep=";"):
    print("=" * 60)
    print(f"LENDO: {caminho}")
    print("=" * 60)
    
    if not os.path.exists(caminho):
        print(f"Atenção: Arquivo não encontrado no caminho indicado!\n")
        return

    try:
        if tipo == "csv":
            df = pd.read_csv(caminho, sep=sep, encoding="latin1", nrows=5)
        else:
            df = pd.read_excel(caminho, nrows=5)

        print("Colunas encontradas:")
        for i, col in enumerate(df.columns):
            print(f"[{i}] {col}")

        print("\nAmostra (2 primeiras linhas):")
        print(df.head(2))
        print("\n")

    except Exception as e:
        print(f"Erro ao tentar ler o arquivo: {e}\n")

# 1. ANEEL (Excel)
ver_arquivo("ANEEL/data.xlsx", tipo="excel")

# 2. ANP (CSV)
ver_arquivo("ANP/Agosto-26/08-dados-abertos-precos-2026-08-gasolina-etanol.csv", tipo="csv", sep=";")

# 3. IBGE
ver_arquivo("IBGE—mapa_da_RMSP/SP_Municipios_2025.dbf.xlsx", tipo="excel")

# 4. INMETRO
ver_arquivo("INMETRO/dados-inmetro.xlsx", tipo="excel")

# 5. ORIGEM E DESTINO (Lê todos os arquivos da pasta)
arquivos_origem = glob.glob("ORIGEM_E_DESTINO*/**/*.xlsx", recursive=True)
if arquivos_origem:
    print(f"Total de arquivos encontrados em Origem e Destino: {len(arquivos_origem)}")
    for arq in arquivos_origem:
        ver_arquivo(arq, tipo="excel")
else:
    print("Nenhum arquivo encontrado na pasta de Origem e Destino!\n")

# 6. SENATRAN (Lê todos os arquivos, inclusive dentro das subpastas como Julho)
arquivos_senatran = glob.glob("SENATRAN/**/*.xlsx", recursive=True)
if arquivos_senatran:
    print(f"Total de arquivos encontrados em SENATRAN: {len(arquivos_senatran)}")
    for arq in arquivos_senatran:
        ver_arquivo(arq, tipo="excel")
else:
    print("Nenhum arquivo encontrado na pasta SENATRAN!\n")