import os
import glob
import pandas as pd

# ----------------------------------------------------
# 0. CONFIGURAÇÃO DA PASTA DE SAÍDA
# ----------------------------------------------------
pasta_saida = "dados_limpos"
os.makedirs(pasta_saida, exist_ok=True)
print(f"Salvando bases limpas em: ./{pasta_saida}/\n")

# ----------------------------------------------------
# 1. ANEEL (Excel) -> Filtrar SP
# ----------------------------------------------------
caminho_aneel = "ANEEL/data.xlsx"
if os.path.exists(caminho_aneel):
    print("Processando ANEEL...")
    df_aneel = pd.read_excel(caminho_aneel)
    
    # Filtra UF se existir a coluna
    col_uf = [c for c in df_aneel.columns if c.upper() in ['UF', 'SIGLA_UF', 'ESTADO']]
    if col_uf:
        df_aneel = df_aneel[df_aneel[col_uf[0]].astype(str).str.upper() == 'SP']
        
    df_aneel.to_csv(f"{pasta_saida}/02_ANEEL_SP.csv", index=False, encoding="utf-8-sig")
    print(f"-> ANEEL concluída ({len(df_aneel)} registros salvos).")
else:
    print(f"Aviso: {caminho_aneel} não encontrado.")

# ----------------------------------------------------
# 2. ANP (CSV) -> Filtrar SP
# ----------------------------------------------------
caminho_anp = "ANP/Agosto-26/08-dados-abertos-precos-2026-08-gasolina-etanol.csv"
if os.path.exists(caminho_anp):
    print("\nProcessando ANP...")
    df_anp = pd.read_csv(caminho_anp, sep=";", encoding="latin1")
    
    # Filtra UF (Estado - Sigla)
    col_uf_anp = [c for c in df_anp.columns if 'ESTADO' in c.upper() or 'UF' in c.upper()]
    if col_uf_anp:
        df_anp = df_anp[df_anp[col_uf_anp[0]].astype(str).str.upper() == 'SP']
        
    df_anp.to_csv(f"{pasta_saida}/03_ANP_SP.csv", index=False, encoding="utf-8-sig")
    print(f"-> ANP concluída ({len(df_anp)} registros salvos).")
else:
    print(f"Aviso: {caminho_anp} não encontrado.")

# ----------------------------------------------------
# 3. IBGE (Excel extraído do DBF)
# ----------------------------------------------------
caminho_ibge = "IBGE—mapa_da_RMSP/SP_Municipios_2025.dbf.xlsx"
if os.path.exists(caminho_ibge):
    print("\nProcessando IBGE...")
    df_ibge = pd.read_excel(caminho_ibge)
    df_ibge.to_csv(f"{pasta_saida}/04_IBGE_SP.csv", index=False, encoding="utf-8-sig")
    print(f"-> IBGE concluído ({len(df_ibge)} municípios salvos).")
else:
    print(f"Aviso: {caminho_ibge} não encontrado.")

# ----------------------------------------------------
# 4. INMETRO (Excel) -> Não filtra por SP (dados técnicos)
# ----------------------------------------------------
caminho_inmetro = "INMETRO/dados-inmetro.xlsx"
if os.path.exists(caminho_inmetro):
    print("\nProcessando INMETRO...")
    df_inmetro = pd.read_excel(caminho_inmetro)
    df_inmetro.to_csv(f"{pasta_saida}/05_INMETRO.csv", index=False, encoding="utf-8-sig")
    print(f"-> INMETRO concluído ({len(df_inmetro)} modelos salvos).")
else:
    print(f"Aviso: {caminho_inmetro} não encontrado.")

# ----------------------------------------------------
# 5. SENATRAN (Múltiplos Excels na subpasta) -> Filtrar SP
# ----------------------------------------------------
print("\nProcessando SENATRAN...")
arquivos_senatran = glob.glob("SENATRAN/**/*.xlsx", recursive=True)

if arquivos_senatran:
    dfs_senatran = []
    for arq in arquivos_senatran:
        try:
            temp_df = pd.read_excel(arq)
            
            # Filtra por UF se houver coluna correspondente
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
# 6. ORIGEM E DESTINO (Múltiplos Excels)
# ----------------------------------------------------
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

print("\nExtração finalizada com sucesso! Verifique a pasta 'dados_limpos'.")