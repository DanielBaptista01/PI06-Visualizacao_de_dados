import pandas as pd
import os

def verificar_dados_limpos(diretorio="dados_limpos", arquivo_saida="relatorio_tabelas.txt"):
    if not os.path.exists(diretorio):
        print(f"Erro: Pasta '{diretorio}' não encontrada.")
        return

    arquivos = [f for f in os.listdir(diretorio) if f.endswith('.csv')]
    
    print(f"Analisando {len(arquivos)} tabelas... Aguarde.")

    with open(arquivo_saida, 'w', encoding='utf-8') as f:
        f.write("=== RELATÓRIO DE INSPEÇÃO DE TABELAS ===\n\n")

        for arquivo in arquivos:
            caminho = os.path.join(diretorio, arquivo)
            f.write(f"► TABELA: {arquivo}\n")
            f.write("-" * 40 + "\n")
            
            try:
                # low_memory=False evita avisos chatos do Pandas em arquivos grandes
                df = pd.read_csv(caminho, low_memory=False)
                
                f.write(f"Linhas: {df.shape[0]} | Colunas: {df.shape[1]}\n")
                f.write(f"Linhas 100% duplicadas: {df.duplicated().sum()}\n\n")
                f.write("ESTRUTURA DAS COLUNAS (Nome, Tipo e Dados Faltantes):\n")
                
                for col in df.columns:
                    vazios = df[col].isna().sum()
                    f.write(f"  - {col} ({df[col].dtype}): {vazios} vazios\n")
                
            except Exception as e:
                f.write(f"ERRO AO LER O ARQUIVO: {e}\n")
                
            f.write("\n" + "="*50 + "\n\n")

    print(f"Concluído! Abra o arquivo '{arquivo_saida}' e veja o resultado.")

if __name__ == "__main__":
    verificar_dados_limpos()