from __future__ import annotations

import argparse
import re
import time
from datetime import date
from pathlib import Path
from urllib.parse import urljoin, urlparse

import pandas as pd
import requests
from bs4 import BeautifulSoup

from pipeline_utils import OUTPUT_DIR, ROOT, registrar_coleta

BASE_URL = "https://earn.uber.com"
PASTA_PADRAO = ROOT / "UBER_MATCH"
ARQUIVO_SAIDA = "17_UBER_MATCH_OFERTAS_SP.csv"
ARQUIVO_FALHAS = "17_UBER_MATCH_FALHAS_SP.csv"

TIPOS_CATEGORIA = {
    "rentals_category": "aluguel",
    "rent_to_own_category": "locacao_com_opcao_compra",
    "purchase_category": "compra",
    "services_category": "servicos",
}


def _texto_html(caminho: Path) -> str:
    return caminho.read_text(encoding="utf-8", errors="ignore")


def _url_original_html_salvo(texto: str) -> str:
    cabecalho = texto[:10000]
    achado = re.search(
        r"saved from url=\(\d+\)(https?://[^\s>]+)",
        cabecalho,
        flags=re.IGNORECASE,
    )
    if achado:
        return achado.group(1).replace("&amp;", "&")
    return ""


def _tipo_categoria(url: str) -> str:
    for marcador, tipo in TIPOS_CATEGORIA.items():
        if marcador in url:
            return tipo
    return "desconhecido"


def _links_ofertas(texto: str) -> list[str]:
    soup = BeautifulSoup(texto, "html.parser")
    encontrados: list[str] = []

    def adicionar(href: str) -> None:
        achado = re.search(r"/offer/([A-Za-z0-9_-]+)", href)
        if not achado:
            return
        # A rota localizada /pt-BR/offer/... pode responder 404 para
        # clientes HTTP simples, embora funcione no navegador. A rota
        # canônica sem locale é mais estável para a coleta automatizada.
        absoluto = f"{BASE_URL}/offer/{achado.group(1)}"
        if absoluto not in encontrados:
            encontrados.append(absoluto)

    for link in soup.find_all("a", href=True):
        adicionar(str(link.get("href")))

    for href in re.findall(
        r"(?:https://earn\.uber\.com)?/pt-BR/offer/[A-Za-z0-9_-]+",
        texto,
    ):
        adicionar(href)

    return encontrados


def _periodicidade_card(texto: str, tipo: str) -> str | None:
    base = texto.casefold()
    if "por semana" in base or "weekly" in base:
        return "semanal"
    if "por mês" in base or "por mes" in base or "monthly" in base:
        return "mensal"
    if "por dia" in base or "daily" in base:
        return "diaria"
    if "uma vez" in base or "one time" in base or tipo == "compra":
        return "unico"
    return None


def _metadados_cards(texto: str, tipo: str) -> dict[str, dict]:
    soup = BeautifulSoup(texto, "html.parser")
    saida: dict[str, dict] = {}

    for card in soup.find_all("a", attrs={"data-testid": "offer-card"}, href=True):
        achado = re.search(r"/offer/([A-Za-z0-9_-]+)", str(card.get("href")))
        if not achado:
            continue

        oferta_id = achado.group(1)
        preco = card.find("h6")
        veiculo = card.find(attrs={"data-baseweb": "typo-labelsmall"})
        locadora = card.find("p", attrs={"data-baseweb": "typo-paragraphsmall"})

        preco_texto = preco.get_text(" ", strip=True) if preco else ""
        saida[oferta_id] = {
            "locadora_card": locadora.get_text(" ", strip=True) if locadora else "",
            "veiculo_card": veiculo.get_text(" ", strip=True) if veiculo else "",
            "valor_card_display": preco_texto,
            "periodicidade_card": _periodicidade_card(preco_texto, tipo),
        }

    return saida


def indexar_paginas_categoria(
    arquivos: list[Path],
) -> tuple[pd.DataFrame, list[dict]]:
    linhas: list[dict] = []
    avisos: list[dict] = []

    for caminho in arquivos:
        texto = _texto_html(caminho)
        url_categoria = _url_original_html_salvo(texto)
        tipo = _tipo_categoria(url_categoria)
        links = _links_ofertas(texto)
        cards = _metadados_cards(texto, tipo)

        if tipo == "servicos":
            avisos.append(
                {
                    "arquivo": str(caminho),
                    "motivo": "pagina_servicos_ignorada",
                    "detalhe": (
                        "O HTML salvo corresponde à categoria Serviços, "
                        "não a uma categoria de veículos."
                    ),
                }
            )
            print(
                f"Aviso: '{caminho.name}' é da categoria Serviços; "
                f"{len(links)} links ignorados."
            )
            continue

        if tipo == "desconhecido":
            avisos.append(
                {
                    "arquivo": str(caminho),
                    "motivo": "categoria_nao_identificada",
                    "detalhe": url_categoria,
                }
            )
            print(f"Aviso: categoria não identificada em '{caminho.name}'.")
            continue

        print(
            f"Uber Match/{tipo}: {len(links)} ofertas encontradas em "
            f"'{caminho.name}'."
        )
        for url in links:
            oferta_id = url.rstrip("/").split("/")[-1]
            card = cards.get(oferta_id, {})
            linhas.append(
                {
                    "tipo_oferta_fonte": tipo,
                    "url_categoria_origem": url_categoria,
                    "arquivo_categoria_origem": str(caminho),
                    "url_oferta": url,
                    "id_publico_oferta": oferta_id,
                    "locadora_card": card.get("locadora_card", ""),
                    "veiculo_card": card.get("veiculo_card", ""),
                    "valor_card_display": card.get("valor_card_display", ""),
                    "periodicidade_card": card.get("periodicidade_card"),
                }
            )

        registrar_coleta(
            "UBER_MATCH_CATEGORIA",
            caminho,
            OUTPUT_DIR / ARQUIVO_SAIDA,
            len(links),
            data_referencia=date.today().isoformat(),
            observacao=f"Snapshot local Uber Match: {tipo}",
            extras={"url_categoria": url_categoria},
        )

    indice = pd.DataFrame(linhas)
    if not indice.empty:
        indice = (
            indice.groupby(
                ["url_oferta", "id_publico_oferta"],
                as_index=False,
            )
            .agg(
                {
                    "tipo_oferta_fonte": lambda s: ";".join(sorted(set(s))),
                    "url_categoria_origem": lambda s: ";".join(sorted(set(s))),
                    "arquivo_categoria_origem": lambda s: ";".join(
                        sorted(set(s))
                    ),
                    "locadora_card": lambda s: next(
                        (v for v in s if str(v).strip()), ""
                    ),
                    "veiculo_card": lambda s: next(
                        (v for v in s if str(v).strip()), ""
                    ),
                    "valor_card_display": lambda s: next(
                        (v for v in s if str(v).strip()), ""
                    ),
                    "periodicidade_card": lambda s: next(
                        (v for v in s if str(v).strip()), None
                    ),
                }
            )
        )
    return indice, avisos


def _variantes_url_oferta(url: str) -> list[str]:
    achado = re.search(r"/offer/([A-Za-z0-9_-]+)", url)
    if not achado:
        return [url]

    oferta_id = achado.group(1)
    return [
        f"{BASE_URL}/offer/{oferta_id}",
        f"{BASE_URL}/pt-BR/offer/{oferta_id}",
    ]


class ClienteUberMatch:
    def __init__(self, intervalo: float = 0.4, tentativas: int = 4):
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/140 Safari/537.36"
                ),
                "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.7",
            }
        )
        self.intervalo = intervalo
        self.tentativas = tentativas
        self.ultima_requisicao = 0.0

    def baixar(self, url: str) -> str:
        ultimo_erro: Exception | None = None

        for variante in _variantes_url_oferta(url):
            for tentativa in range(self.tentativas):
                espera = self.intervalo - (
                    time.monotonic() - self.ultima_requisicao
                )
                if espera > 0:
                    time.sleep(espera)

                try:
                    resposta = self.session.get(
                        variante,
                        timeout=30,
                        headers={
                            "Referer": (
                                "https://earn.uber.com/pt-BR/city/"
                                "sao-paulo-BR/458/rentals_category"
                            ),
                            "Accept": (
                                "text/html,application/xhtml+xml,"
                                "application/xml;q=0.9,image/avif,"
                                "image/webp,*/*;q=0.8"
                            ),
                        },
                    )
                    self.ultima_requisicao = time.monotonic()

                    if resposta.status_code == 404:
                        # Tenta a próxima forma da URL. Em especial, a rota
                        # /pt-BR/offer/... pode devolver 404 fora do navegador.
                        ultimo_erro = requests.HTTPError(
                            f"404 em {variante}",
                            response=resposta,
                        )
                        break

                    if resposta.status_code == 429:
                        time.sleep(min(30, 2 ** (tentativa + 1)))
                        continue

                    resposta.raise_for_status()
                    resposta.encoding = (
                        resposta.apparent_encoding or resposta.encoding
                    )
                    return resposta.text
                except requests.RequestException as exc:
                    ultimo_erro = exc
                    if tentativa == self.tentativas - 1:
                        break
                    time.sleep(min(10, 1.5 ** (tentativa + 1)))

        raise RuntimeError(
            f"Não foi possível baixar {url}. Último erro: {ultimo_erro}"
        )


def _linhas_visiveis(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    linhas: list[str] = []
    anterior = None
    for valor in soup.stripped_strings:
        texto = re.sub(r"\s+", " ", str(valor)).strip()
        if not texto or texto == anterior:
            continue
        linhas.append(texto)
        anterior = texto
    return linhas


def _primeiro_indice(
    linhas: list[str],
    alvo: str,
    inicio: int = 0,
) -> int | None:
    alvo_n = alvo.casefold()
    for i in range(inicio, len(linhas)):
        if linhas[i].casefold() == alvo_n:
            return i
    return None


def _secao(
    linhas: list[str],
    inicio: str,
    fins: list[str],
) -> list[str]:
    i = _primeiro_indice(linhas, inicio)
    if i is None:
        return []

    fim = len(linhas)
    for marcador in fins:
        j = _primeiro_indice(linhas, marcador, i + 1)
        if j is not None:
            fim = min(fim, j)

    return linhas[i + 1 : fim]


def _dinheiro_para_float(valor: str | None) -> float | None:
    if not valor:
        return None

    texto = re.sub(r"[^0-9,\.]", "", valor)
    if not texto:
        return None

    if "," in texto and "." in texto:
        if texto.rfind(",") > texto.rfind("."):
            texto = texto.replace(".", "").replace(",", ".")
        else:
            texto = texto.replace(",", "")
    elif "," in texto:
        partes = texto.split(",")
        texto = (
            "".join(partes[:-1]) + "." + partes[-1]
            if len(partes[-1]) == 2
            else "".join(partes)
        )
    elif "." in texto:
        partes = texto.split(".")
        if len(partes) > 2:
            texto = "".join(partes)
        elif len(partes) == 2 and len(partes[-1]) != 2:
            texto = "".join(partes)

    try:
        return float(texto)
    except ValueError:
        return None


def _primeiro_dinheiro(texto: str) -> str | None:
    achado = re.search(
        r"R\$\s*[0-9][0-9\.\,\s]*",
        texto,
        flags=re.IGNORECASE,
    )
    return re.sub(r"\s+", "", achado.group(0)) if achado else None


def _valor_apos(
    linhas: list[str],
    marcador: str,
    max_linhas: int = 5,
) -> str | None:
    i = _primeiro_indice(linhas, marcador)
    if i is None:
        return None

    for linha in linhas[i + 1 : i + 1 + max_linhas]:
        valor = _primeiro_dinheiro(linha)
        if valor:
            return valor
    return None


def _cadencia(
    linhas: list[str],
    tipo_fonte: str,
) -> str | None:
    mapa = [
        ("aluguel semanal", "semanal"),
        ("weekly rental", "semanal"),
        ("aluguel mensal", "mensal"),
        ("monthly rental", "mensal"),
        ("aluguel diário", "diaria"),
        ("daily rental", "diaria"),
        ("semanal", "semanal"),
        ("weekly", "semanal"),
        ("mensal", "mensal"),
        ("monthly", "mensal"),
        ("por dia", "diaria"),
        ("per day", "diaria"),
    ]

    for linha in linhas:
        base = linha.casefold()
        for chave, valor in mapa:
            if chave in base:
                return valor

    if tipo_fonte == "compra":
        return "unico"
    return None


def _equivalentes(
    valor: float | None,
    cadencia: str | None,
) -> tuple[float | None, float | None]:
    if valor is None or not cadencia:
        return None, None

    if cadencia == "semanal":
        return valor, valor * 52 / 12
    if cadencia == "mensal":
        return valor * 12 / 52, valor
    if cadencia == "diaria":
        mensal = valor * 365.25 / 12
        return mensal * 12 / 52, mensal

    return None, None


def _regex_dinheiro_contexto(
    texto: str,
    palavra: str,
    janela: int = 100,
) -> float | None:
    padrao = rf"{palavra}.{{0,{janela}}}?(R\$\s*[0-9][0-9\.\,\s]*)"
    achado = re.search(
        padrao,
        texto,
        flags=re.IGNORECASE | re.DOTALL,
    )
    return (
        _dinheiro_para_float(achado.group(1))
        if achado
        else None
    )


def _extrair_km(
    texto: str,
) -> tuple[float | None, float | None, bool | None]:
    texto_n = texto.casefold()
    sem_limite = (
        True
        if "sem limite de quilometragem" in texto_n
        else None
    )

    km_inclusos = None
    padroes = [
        (
            r"(?:quilometragem|franquia|inclu[íi]d[ao]).{0,60}?"
            r"([0-9][0-9\.\,]*)\s*km"
        ),
        (
            r"([0-9][0-9\.\,]*)\s*km.{0,40}?"
            r"(?:inclu[íi]d|por semana|por m[eê]s)"
        ),
    ]
    for padrao in padroes:
        achado = re.search(
            padrao,
            texto,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if achado:
            valor = re.sub(r"[^0-9]", "", achado.group(1))
            km_inclusos = float(valor) if valor else None
            break

    valor_excedente = None
    padroes_excedente = [
        (
            r"R\$\s*([0-9\.\,]+).{0,25}?"
            r"(?:por|/)?\s*km\s*(?:excedente|adicional)?"
        ),
        (
            r"km\s*(?:excedente|adicional).{0,40}?"
            r"R\$\s*([0-9\.\,]+)"
        ),
    ]
    for padrao in padroes_excedente:
        achado = re.search(
            padrao,
            texto,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if achado:
            valor_excedente = _dinheiro_para_float(
                "R$" + achado.group(1)
            )
            break

    return km_inclusos, valor_excedente, sem_limite


def _bool_texto(
    texto: str,
    termos: list[str],
) -> bool:
    base = texto.casefold()
    return any(termo.casefold() in base for termo in termos)


def _secao_alias(
    linhas: list[str],
    inicios: list[str],
    fins: list[str],
) -> list[str]:
    for inicio in inicios:
        trecho = _secao(linhas, inicio, fins)
        if trecho:
            return trecho
    return []


def _valor_apos_alias(
    linhas: list[str],
    marcadores: list[str],
) -> str | None:
    for marcador in marcadores:
        valor = _valor_apos(linhas, marcador)
        if valor:
            return valor
    return None


def extrair_detalhe(
    html: str,
    url: str,
    tipo_fonte: str,
) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    linhas = _linhas_visiveis(html)

    h1s = [
        tag.get_text(" ", strip=True)
        for tag in soup.find_all("h1")
        if tag.get_text(" ", strip=True)
    ]
    veiculo = next(
        (
            titulo
            for titulo in h1s
            if titulo.casefold() not in {"uber match", "uber"}
        ),
        None,
    )
    if not veiculo:
        veiculo = linhas[0] if linhas else None

    locadora = None
    for linha in linhas:
        base = linha.casefold()
        if base.startswith("listado por "):
            locadora = linha[len("Listado por ") :].strip()
            break
        if base.startswith("listed by "):
            locadora = linha[len("Listed by ") :].strip()
            break

    fins_gerais = [
        "Aluguel semanal",
        "Weekly rental",
        "Aluguel mensal",
        "Monthly rental",
        "Aluguel diário",
        "Daily rental",
        "Inclui",
        "Includes",
        "Descrição",
        "Description",
        "Requisitos",
        "Requirements",
        "Aviso legal",
        "Disclaimer",
    ]

    servicos = _secao_alias(
        linhas,
        ["Serviços elegíveis", "Eligible services"],
        fins_gerais,
    )
    categorias_uber = servicos[0] if servicos else None

    inclusos = _secao_alias(
        linhas,
        ["Inclui", "Includes"],
        [
            "Descrição",
            "Description",
            "Requisitos",
            "Requirements",
            "Aviso legal",
            "Disclaimer",
        ],
    )
    descricao = _secao_alias(
        linhas,
        ["Descrição", "Description"],
        [
            "Requisitos",
            "Requirements",
            "Aviso legal",
            "Disclaimer",
        ],
    )
    requisitos = _secao_alias(
        linhas,
        ["Requisitos", "Requirements"],
        [
            "Falar com a equipe de suporte",
            "Contact support",
            "Aviso legal",
            "Disclaimer",
        ],
    )

    valor_display = _valor_apos_alias(
        linhas,
        ["Custo do aluguel", "Rental cost"],
    )
    if not valor_display:
        candidatos = [_primeiro_dinheiro(linha) for linha in linhas]
        valor_display = next(
            (valor for valor in candidatos if valor),
            None,
        )

    valor = _dinheiro_para_float(valor_display)
    cadencia = _cadencia(linhas, tipo_fonte)
    semanal, mensal = _equivalentes(valor, cadencia)

    texto_sem_duplicatas = "\n".join(dict.fromkeys(linhas))
    caucao = _regex_dinheiro_contexto(
        texto_sem_duplicatas,
        r"cau[cç][aã]o",
        janela=80,
    )
    (
        km_inclusos,
        valor_km_excedente,
        sem_limite_km,
    ) = _extrair_km(texto_sem_duplicatas)

    return {
        "id_publico_oferta": url.rstrip("/").split("/")[-1],
        "url_oferta": url,
        "tipo_oferta_fonte": tipo_fonte,
        "cidade": "São Paulo",
        "territorio_uber_id": 458,
        "locadora": locadora,
        "veiculo": veiculo,
        "categorias_uber": categorias_uber,
        "valor_display": valor_display,
        "valor_reais": valor,
        "periodicidade_valor": cadencia,
        "valor_semanal_equivalente": semanal,
        "valor_mensal_equivalente": mensal,
        "caucao_reais": caucao,
        "km_inclusos": km_inclusos,
        "valor_km_excedente_reais": valor_km_excedente,
        "sem_limite_quilometragem": sem_limite_km,
        "seguro_incluso": _bool_texto(
            "\n".join(inclusos),
            ["seguro", "proteção", "insurance", "vehicle insurance"],
        ),
        "manutencao_inclusa": _bool_texto(
            "\n".join(inclusos),
            ["manutenção", "maintenance"],
        ),
        "ipva_incluso": _bool_texto(
            "\n".join(inclusos + descricao),
            ["ipva por nossa conta", "ipva incluso", "ipva incluído"],
        ),
        "carro_reserva_incluso": _bool_texto(
            "\n".join(inclusos + descricao),
            ["carro reserva", "replacement car"],
        ),
        "opcao_compra": _bool_texto(
            "\n".join(inclusos + descricao),
            [
                "opção de compra",
                "possibilidade de compra",
                "option to purchase",
                "purchase option",
            ],
        ),
        "itens_inclusos": " | ".join(dict.fromkeys(inclusos)),
        "descricao": " ".join(dict.fromkeys(descricao)),
        "requisitos": " | ".join(dict.fromkeys(requisitos)),
        "data_coleta": date.today().isoformat(),
    }


def _nome_cache(url: str) -> str:
    slug = Path(urlparse(url).path).name
    return f"{slug}.html"


def coletar(
    pasta: Path,
    atualizar: bool = False,
    somente_indexar: bool = False,
) -> pd.DataFrame:
    arquivos = sorted(
        caminho
        for caminho in pasta.rglob("*.html")
        if "detalhes" not in {
            parte.casefold()
            for parte in caminho.parts
        }
        and not any(
            parte.casefold().endswith("_files")
            for parte in caminho.parts
        )
    )
    if not arquivos:
        raise FileNotFoundError(
            f"Nenhum HTML encontrado em '{pasta}'. "
            "Salve as páginas gerais do Uber Match nessa pasta."
        )

    indice, avisos = indexar_paginas_categoria(arquivos)
    if indice.empty:
        raise RuntimeError(
            "Nenhuma oferta de veículo foi indexada nos HTMLs fornecidos."
        )

    print(f"Total único indexado: {len(indice)} ofertas.")

    if somente_indexar:
        destino = OUTPUT_DIR / ARQUIVO_SAIDA
        indice.assign(
            data_coleta=date.today().isoformat()
        ).to_csv(
            destino,
            index=False,
            encoding="utf-8-sig",
        )
        return indice

    pasta_detalhes = (
        pasta
        / date.today().isoformat()
        / "detalhes"
    )
    pasta_detalhes.mkdir(
        parents=True,
        exist_ok=True,
    )

    cliente = ClienteUberMatch()
    registros: list[dict] = []
    falhas: list[dict] = list(avisos)

    for pos, row in indice.iterrows():
        url = row["url_oferta"]
        tipos = str(row["tipo_oferta_fonte"])
        tipo_principal = tipos.split(";")[0]
        cache = pasta_detalhes / _nome_cache(url)
        origem_detalhe = "cache"

        try:
            if cache.exists() and not atualizar:
                html = cache.read_text(
                    encoding="utf-8",
                    errors="ignore",
                )
            else:
                html = cliente.baixar(url)
                cache.write_text(
                    html,
                    encoding="utf-8",
                )
                origem_detalhe = "web"

            detalhe = extrair_detalhe(
                html,
                url,
                tipo_principal,
            )

            # Os cards da página geral são a fonte mais estável para
            # locadora, nome exibido, preço de vitrine e periodicidade.
            # As páginas individuais complementam caução, itens inclusos,
            # requisitos e descrição.
            locadora_card = str(row.get("locadora_card") or "").strip()
            veiculo_card = str(row.get("veiculo_card") or "").strip()
            valor_card_display = str(
                row.get("valor_card_display") or ""
            ).strip()
            periodicidade_card = row.get("periodicidade_card")

            if locadora_card:
                detalhe["locadora"] = locadora_card

            veiculo_atual = str(detalhe.get("veiculo") or "").strip()
            if veiculo_card and (
                not veiculo_atual
                or "uber match" in veiculo_atual.casefold()
                or "ganhe com a plataforma" in veiculo_atual.casefold()
            ):
                detalhe["veiculo"] = veiculo_card

            if periodicidade_card:
                detalhe["periodicidade_valor"] = periodicidade_card

            detalhe["valor_card_display"] = valor_card_display

            if detalhe.get("valor_reais") is None and valor_card_display:
                detalhe["valor_reais"] = _dinheiro_para_float(
                    _primeiro_dinheiro(valor_card_display)
                )

            semanal, mensal = _equivalentes(
                detalhe.get("valor_reais"),
                detalhe.get("periodicidade_valor"),
            )
            detalhe["valor_semanal_equivalente"] = semanal
            detalhe["valor_mensal_equivalente"] = mensal

            detalhe["tipos_oferta_fonte"] = tipos
            detalhe["url_categoria_origem"] = row[
                "url_categoria_origem"
            ]
            detalhe["arquivo_categoria_origem"] = row[
                "arquivo_categoria_origem"
            ]
            detalhe["arquivo_html_detalhe"] = str(cache)
            detalhe["origem_detalhe"] = origem_detalhe
            registros.append(detalhe)

            print(
                f"Uber Match [{len(registros)}/{len(indice)}] OK: "
                f"{detalhe.get('locadora')} - "
                f"{detalhe.get('veiculo')}"
            )
        except Exception as exc:
            falhas.append(
                {
                    "url_oferta": url,
                    "motivo": "falha_detalhe",
                    "detalhe": str(exc),
                }
            )
            print(
                f"Uber Match [{pos + 1}/{len(indice)}] FALHA: "
                f"{url} -> {exc}"
            )

    df = pd.DataFrame(registros)
    destino = OUTPUT_DIR / ARQUIVO_SAIDA
    df.to_csv(
        destino,
        index=False,
        encoding="utf-8-sig",
    )

    caminho_falhas = OUTPUT_DIR / ARQUIVO_FALHAS
    if falhas:
        pd.DataFrame(falhas).to_csv(
            caminho_falhas,
            index=False,
            encoding="utf-8-sig",
        )
    elif caminho_falhas.exists():
        caminho_falhas.unlink()

    registrar_coleta(
        "UBER_MATCH",
        "https://earn.uber.com/pt-BR/city/sao-paulo-BR/458",
        destino,
        len(df),
        data_referencia=date.today().isoformat(),
        observacao=(
            "Ofertas de veículos do Uber Match em São Paulo; "
            "páginas de detalhe preservadas localmente."
        ),
        extras={
            "ofertas_indexadas": len(indice),
            "ofertas_processadas": len(df),
            "falhas": len(falhas),
            "pasta_html": str(pasta),
        },
    )

    print(
        f"\nUber Match: {len(df):,} ofertas -> {destino}"
    )
    if falhas:
        print(
            f"Falhas/avisos: {len(falhas)} -> "
            f"{OUTPUT_DIR / ARQUIVO_FALHAS}"
        )

    return df


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Extrai ofertas de veículos do Uber Match (São Paulo)"
        )
    )
    parser.add_argument(
        "--pasta",
        type=Path,
        default=PASTA_PADRAO,
        help="Pasta com os HTMLs gerais salvos do Uber Match",
    )
    parser.add_argument(
        "--atualizar",
        action="store_true",
        help="Baixa novamente detalhes já preservados localmente",
    )
    parser.add_argument(
        "--somente-indexar",
        action="store_true",
        help="Extrai somente os links sem abrir as ofertas individuais",
    )
    args = parser.parse_args()

    coletar(
        args.pasta,
        atualizar=args.atualizar,
        somente_indexar=args.somente_indexar,
    )


if __name__ == "__main__":
    main()
