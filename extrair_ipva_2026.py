"""Extrai o Anexo I da Sefaz-SP IPVA 2026 por coordenadas de texto (sem OCR).

Preserva a rastreabilidade da linha, página, código IPVA, complemento,
ano do veículo e valor venal. Não atribui isenção ou alíquota.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import fitz
import pandas as pd

ANOS = list(range(2025, 2005, -1))
CATEGORIAS = {"A": "Automóveis", "B": "Camionetas e Utilitários", "C": "Caminhões", "D": "Ônibus/Microônibus", "E": "Motos e Similares", "F": "Motor - Casa"}
REGEX_VALOR = re.compile(r"\d{1,3}(?:\.\d{3})+|\d+")
COLUNAS = ["exercicio_ipva", "mes_base", "categoria_codigo", "categoria", "linha_tabela", "descricao_marca_modelo", "codigo_ipva", "codigo_complemento", "ano_fabricacao_modelo_tabela", "valor_venal_reais", "pagina_pdf", "arquivo_fonte"]


def agrupar_linhas(words: list[tuple], tolerancia: float = 1.8) -> list[list[tuple]]:
    agrupamentos = []
    for word in sorted(words, key=lambda w: (w[1], w[0])):
        if agrupamentos and abs(word[1] - agrupamentos[-1][0][1]) <= tolerancia:
            agrupamentos[-1].append(word)
        else:
            agrupamentos.append([word])
    return [sorted(group, key=lambda w: w[0]) for group in agrupamentos]


def obter_colunas_anos(page: fitz.Page) -> list[tuple[int, float]]:
    palavras = [w for w in page.get_text("words") if 90 <= w[1] <= 106]
    campos = [(int(w[4]), float(w[0])) for w in palavras if re.fullmatch(r"20(?:0[6-9]|1\d|2[0-5])", w[4])]
    if sorted(a for a, _ in campos) != sorted(ANOS):
        raise ValueError(f"Cabeçalho de anos incompatível na página {page.number + 1}: {campos}")
    return sorted(campos, key=lambda el: el[1])


def extrair(pdf: Path) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    dados = []
    problemas = []
    linhas_documento = []
    with fitz.open(pdf) as doc:
        total_paginas = len(doc)
        for pagina_idx, page in enumerate(doc):
            words = page.get_text("words")
            anos = obter_colunas_anos(page)
            cabecalho = [w[4] for w in words if 70 <= w[1] <= 91 and w[0] < 43]
            categoria_codigo = next((x for x in cabecalho if x in CATEGORIAS), None)
            if not categoria_codigo:
                raise ValueError(f"Categoria não reconhecida na página {pagina_idx+1}")
            for grupo in agrupar_linhas([w for w in words if w[1] >= 108 and w[1] < page.rect.height - 12]):
                indice = [w for w in grupo if w[0] < 41 and re.fullmatch(r"\d{1,5}", w[4])]
                if not indice:
                    continue
                if len(indice) != 1:
                    problemas.append({"pagina_pdf": pagina_idx+1, "linha_tabela": "", "tipo": "indice_ambiguo", "detalhe": " ".join(w[4] for w in indice)})
                    continue
                linha = int(indice[0][4])
                codigo = [w[4] for w in grupo if 183 <= w[0] < 235 and re.fullmatch(r"\d{1,8}", w[4])]
                complemento = [w[4] for w in grupo if 237 <= w[0] < 279 and re.fullmatch(r"\d{4}", w[4])]
                descricao = " ".join(w[4] for w in grupo if 40 <= w[0] < 181)
                if len(codigo) != 1 or len(complemento) != 1 or not descricao:
                    problemas.append({"pagina_pdf": pagina_idx+1, "linha_tabela": linha, "tipo": "cabecalho_registro_incompleto", "detalhe": f"desc={descricao!r} codigo={codigo} complemento={complemento}"})
                    continue
                linhas_documento.append((linha, pagina_idx + 1))
                valores = [w for w in grupo if w[0] >= 280 and re.fullmatch(r"\d{1,3}(?:\.\d{3})*", w[4])]
                if not valores:
                    problemas.append({"pagina_pdf": pagina_idx+1,"linha_tabela": linha,"tipo":"sem_valor", "detalhe": descricao})
                    continue
                anos_usados = set()
                for valor in valores:
                    ano, dist = min(anos, key=lambda a: abs(a[1]-valor[0]))
                    distancia = abs(dist - valor[0])
                    if distancia > 13 or ano in anos_usados:
                        problemas.append({"pagina_pdf": pagina_idx+1,"linha_tabela":linha,"tipo":"valor_desalinhado_ou_duplicado", "detalhe":f"valor={valor[4]} x={valor[0]:.1f} ano={ano} distancia={distancia:.2f}"})
                        continue
                    anos_usados.add(ano)
                    dados.append({"exercicio_ipva":2026,"mes_base":"2025-09","categoria_codigo":categoria_codigo,"categoria":CATEGORIAS[categoria_codigo],"linha_tabela":linha,"descricao_marca_modelo":descricao,"codigo_ipva":codigo[0],"codigo_complemento":complemento[0],"ano_fabricacao_modelo_tabela":ano,"valor_venal_reais":int(valor[4].replace('.','')),"pagina_pdf":pagina_idx+1,"arquivo_fonte":pdf.name})
    df = pd.DataFrame(dados, columns=COLUNAS)
    ocorrencias = pd.DataFrame(problemas, columns=["pagina_pdf","linha_tabela","tipo","detalhe"])
    linhas_df = pd.DataFrame(linhas_documento, columns=["linha_tabela","pagina_pdf"])
    duplicacoes = df.duplicated(["linha_tabela", "ano_fabricacao_modelo_tabela"], keep=False)
    for _, row in df[duplicacoes].iterrows():
        problemas.append({"pagina_pdf":int(row.pagina_pdf), "linha_tabela":int(row.linha_tabela), "tipo":"chave_duplicada", "detalhe":str(row.ano_fabricacao_modelo_tabela)})
    # O documento numera linhas consecutivamente por categoria; detecta qualquer ausência.
    for categoria, sub in df.groupby("categoria_codigo"):
        ids = sorted(sub.linha_tabela.unique())
        for a,b in zip(ids,ids[1:]):
            if b != a+1:
                problemas.append({"pagina_pdf":"", "linha_tabela":f"{a}-{b}", "tipo":"lacuna_sequencial", "detalhe":f"categoria={categoria}; faltam {b-a-1} linhas"})
    if not linhas_df.empty and linhas_df.linha_tabela.duplicated().any():
        problemas.append({"pagina_pdf":"", "linha_tabela":"", "tipo":"indice_repetido", "detalhe":f"{int(linhas_df.linha_tabela.duplicated().sum())} linhas repetidas"})
    if not df.empty:
        df = df.sort_values(["linha_tabela","ano_fabricacao_modelo_tabela"], ascending=[True,False]).reset_index(drop=True)
    return df, pd.DataFrame(problemas, columns=["pagina_pdf","linha_tabela","tipo","detalhe"]), {"paginas":total_paginas,"linhas_unicas_pdf":int(linhas_df.linha_tabela.nunique()),"faixa_linhas":[int(linhas_df.linha_tabela.min()),int(linhas_df.linha_tabela.max())],"registros_extrair":len(df),"categorias":dict(Counter(df.categoria_codigo)),"sha256_pdf":hashlib.sha256(pdf.read_bytes()).hexdigest()}


def main() -> None:
    parser = argparse.ArgumentParser(description="Extrai valores venais do Anexo I IPVA SP 2026")
    parser.add_argument("--pdf", type=Path, default=Path("ANEXO I -Tabela de Valores Venais IPVA 2026.pdf"))
    parser.add_argument("--saida", type=Path, default=Path("dados_padronizados"))
    args=parser.parse_args()
    if not args.pdf.is_file():
        parser.error(f"PDF não encontrado: {args.pdf}")
    dados,pendencias,meta=extrair(args.pdf)
    args.saida.mkdir(parents=True,exist_ok=True)
    csv = args.saida / "18_IPVA_SP_VALORES_VENAIS_2026.csv"
    erros = args.saida / "18_IPVA_SP_PENDENCIAS_EXTRACAO.csv"
    manifesto = args.saida / "18_IPVA_SP_MANIFESTO_2026.json"
    dados.to_csv(csv,index=False,encoding="utf-8-sig")
    pendencias.to_csv(erros,index=False,encoding="utf-8-sig")
    meta.update({"arquivo_csv":csv.name,"pendencias":len(pendencias),"gerado_em_utc":datetime.now(timezone.utc).isoformat(),"metodo":"PyMuPDF palavras com coordenadas; fonte set/2025; PDF original preservado"})
    manifesto.write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(meta,ensure_ascii=False,indent=2))
    print(f"CSV: {csv}\nPendências: {erros}\nManifesto: {manifesto}")

if __name__ == "__main__":
    main()
