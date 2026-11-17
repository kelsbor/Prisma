"""Leitura de extratos: normalização de valores e datas e extratores por tipo de arquivo.

Portado do notebook prisma_coletor_docstrange_mcp.ipynb (seções 4 e 5).

| Formato                                      | Como é lido                                   |
|----------------------------------------------|-----------------------------------------------|
| CSV, TSV, TXT delimitado, XLSX/XLS, OFX      | Localmente, de forma determinística           |
| PDF, imagens, DOCX, PPTX, HTML               | DocStrange (OCR + extração com esquema JSON)  |
| PDF com texto, se o DocStrange falhar        | Fallback local com pypdf                      |

PRIVACIDADE / LGPD: no modo "nuvem", o DocStrange envia o arquivo para a API da Nanonets
(fora do Brasil). Use só dados fictícios nesse modo. Para dados reais, use DOCSTRANGE_MODO=gpu
ou formatos lidos localmente.
"""

import csv
import io
import json
import os
import re
import unicodedata
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pandas as pd

DOCSTRANGE_MODO = os.getenv("DOCSTRANGE_MODO", "nuvem")   # "nuvem" (API Nanonets) ou "gpu" (local)
NANONETS_API_KEY = os.getenv("NANONETS_API_KEY")


# ============================== Normalização ==============================
def _sem_acento(s):
    return "".join(c for c in unicodedata.normalize("NFKD", str(s)) if not unicodedata.combining(c))


def parse_valor(x):
    """'-R$ 1.384,62' · '1384.62' · '1.384,62-' · '(32,90)' · '32,90 D' · 3450 → Decimal com 2 casas."""
    if x is None:
        return None
    if isinstance(x, (int, float, Decimal)):
        if isinstance(x, float) and x != x:  # NaN
            return None
        return Decimal(str(x)).quantize(Decimal("0.01"))
    s = str(x).strip().upper().replace("\u2212", "-").replace("\xa0", " ")
    if not s:
        return None
    negativo = (s.startswith("-") or s.endswith("-") or (s.startswith("(") and s.endswith(")"))
                or bool(re.search(r"\s*D$", s)))
    s = re.sub(r"[^\d.,]", "", s)
    if not re.search(r"\d", s):
        return None
    if "," in s and "." in s:                       # o último separador é o decimal
        dec = "," if s.rfind(",") > s.rfind(".") else "."
        s = s.replace("." if dec == "," else ",", "").replace(dec, ".")
    elif "," in s:
        s = s.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(\.\d{3})+", s):    # 1.384 = milhar
        s = s.replace(".", "")
    try:
        v = Decimal(s).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None
    return -v if negativo else v


def parse_data(x, periodo=None):
    """Aceita AAAA-MM-DD, DD/MM/AAAA, DD/MM/AA, DD/MM (ano deduzido do período), AAAAMMDD (OFX)."""
    if x is None:
        return None
    if isinstance(x, datetime):
        return x.date()
    if isinstance(x, date):
        return x
    s = str(x).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y", "%d-%m-%Y", "%d.%m.%Y", "%Y%m%d"):
        try:
            return datetime.strptime(s[:10] if fmt != "%Y%m%d" else s[:8], fmt).date()
        except ValueError:
            pass
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})", s)
    if m:
        d, mes = int(m[1]), int(m[2])
        if periodo:                                  # escolhe o ano que cai dentro do período
            for ano in range(periodo[0].year, periodo[1].year + 1):
                try:
                    cand = date(ano, mes, d)
                except ValueError:
                    continue
                if periodo[0] <= cand <= periodo[1]:
                    return cand
        return None                                  # sem período não dá para saber o ano
    return None


def normalizar_descricao(s):
    return re.sub(r"\s+", " ", str(s or "")).strip().upper()


RE_DATA = r"\d{2}/\d{2}/\d{4}"
RE_DINHEIRO = r"-?\s*\(?-?\s*(?:R\$)?\s*-?\d{1,3}(?:[.\s]?\d{3})*(?:[.,]\d{2})\)?-?(?:\s*[DC]\b)?"


def detectar_periodo(texto):
    m = re.search(rf"({RE_DATA})\s*(?:a|até|ate|-|–)\s*({RE_DATA})", texto or "", re.I)
    if m:
        return parse_data(m[1]), parse_data(m[2])
    return None


def detectar_saldo(texto, rotulo):
    m = re.search(rf"saldo\s+{rotulo}\W{{0,40}}?({RE_DINHEIRO})", _sem_acento(texto or ""), re.I)
    return parse_valor(m[1]) if m else None


# ============================== Leitura local ==============================
APELIDOS = {
    "data":      ["data", "date", "dt", "data lancamento", "data movimento", "data mov"],
    "descricao": ["descricao", "historico", "lancamento", "memo", "description", "detalhe", "estabelecimento"],
    "valor":     ["valor", "amount", "valor r", "montante", "quantia"],
    "debito":    ["debito", "saida", "saidas", "debit"],
    "credito":   ["credito", "entrada", "entradas", "credit"],
    "saldo":     ["saldo", "balance"],
}


def _cab(s):
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", _sem_acento(s).lower()).split())


def mapear_colunas(colunas):
    mapa = {}
    for campo, nomes in APELIDOS.items():
        for col in colunas:
            c = _cab(col) or ""
            if col in mapa.values():
                continue
            if c in nomes or any(c.startswith(n + " ") for n in nomes):
                mapa[campo] = col
                break
    ok = "data" in mapa and "descricao" in mapa and ("valor" in mapa or ("debito" in mapa and "credito" in mapa))
    return mapa if ok else None


def linhas_da_tabela(df, mapa, periodo=None):
    out = []
    for _, r in df.iterrows():
        d = parse_data(r[mapa["data"]], periodo)
        if "valor" in mapa:
            v = parse_valor(r[mapa["valor"]])
        else:
            deb, cre = parse_valor(r[mapa["debito"]]), parse_valor(r[mapa["credito"]])
            v = (cre or 0) - abs(deb or 0) if (deb is not None or cre is not None) else None
        if d is None or v is None:
            continue
        out.append({"data": d, "descricao": normalizar_descricao(r[mapa["descricao"]]), "valor": v,
                    "saldo": parse_valor(r[mapa["saldo"]]) if "saldo" in mapa else None})
    return out


def ler_delimitado(caminho):
    bruto = Path(caminho).read_bytes()
    texto = bruto.decode("latin-1")
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            texto = bruto.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    try:
        sep = csv.Sniffer().sniff(texto[:4000], delimiters=";,\t|").delimiter
    except csv.Error:
        sep = ";"
    df = pd.read_csv(io.StringIO(texto), sep=sep, dtype=str, keep_default_na=False)
    mapa = mapear_colunas(df.columns)
    return (linhas_da_tabela(df, mapa) if mapa else []), texto


def ler_planilha(caminho):
    bruto = pd.read_excel(caminho, header=None, dtype=object)
    for i in range(min(30, len(bruto))):              # bancos costumam pôr cabeçalhos acima da tabela
        mapa = mapear_colunas([str(c) for c in bruto.iloc[i]])
        if mapa:
            df = bruto.iloc[i + 1:].copy()
            df.columns = [str(c) for c in bruto.iloc[i]]
            texto = "\n".join(" ".join(map(str, r)) for r in bruto.iloc[:i].values)
            return linhas_da_tabela(df, mapa, detectar_periodo(texto)), texto
    return [], ""


def ler_ofx(caminho):
    texto = Path(caminho).read_bytes().decode("latin-1")
    out = []
    for bloco in re.findall(r"<STMTTRN>(.*?)(?:</STMTTRN>|(?=<STMTTRN>)|</BANKTRANLIST>)", texto, re.S | re.I):
        def campo(t):
            m = re.search(rf"<{t}>([^<\r\n]*)", bloco, re.I)
            return m[1] if m else None
        d, v = parse_data((campo("DTPOSTED") or "")[:8]), parse_valor(campo("TRNAMT"))
        if d and v is not None:
            out.append({"data": d, "descricao": normalizar_descricao(campo("MEMO") or campo("NAME")),
                        "valor": v, "saldo": None})
    return out, texto


# ============== Texto livre (markdown do DocStrange, texto de PDF, TXT sem cabeçalho) ==============
_RE_LINHA = re.compile(
    rf"^\s*(\d{{4}}-\d{{2}}-\d{{2}}|\d{{2}}/\d{{2}}(?:/\d{{2,4}})?)[\s,;]+(.+?)[\s,;]+({RE_DINHEIRO})"
    rf"(?:[\s,;]+({RE_DINHEIRO}))?\s*$")


def parse_texto(texto, periodo=None):
    periodo = periodo or detectar_periodo(texto)
    out = []
    for linha in (texto or "").splitlines():
        if "|" in linha:                                   # linha de tabela markdown
            cel = [c.strip() for c in linha.strip().strip("|").split("|")]
            idx = next((i for i, c in enumerate(cel) if parse_data(c, periodo)), None)
            if idx is None:
                continue
            resto = cel[idx + 1:]
            din = [i for i, c in enumerate(resto) if re.fullmatch(RE_DINHEIRO, c) and parse_valor(c) is not None]
            if not din:
                continue
            desc = " ".join(resto[:din[0]])
            valor, saldo = parse_valor(resto[din[0]]), (parse_valor(resto[din[1]]) if len(din) > 1 else None)
            d = parse_data(cel[idx], periodo)
        else:
            m = _RE_LINHA.match(linha)
            if not m:
                continue
            d, desc = parse_data(m[1], periodo), m[2].strip(" ,;")
            valor, saldo = parse_valor(m[3]), parse_valor(m[4]) if m[4] else None
        if d and valor is not None and desc:
            out.append({"data": d, "descricao": normalizar_descricao(desc), "valor": valor, "saldo": saldo})
    return out


# ============================== DocStrange ==============================
ESQUEMA_EXTRATO = {
    "banco": "string",
    "periodo_inicio": "string (DD/MM/AAAA)",
    "periodo_fim": "string (DD/MM/AAAA)",
    "saldo_inicial": "number",
    "saldo_final": "number",
    "transacoes": [{"data": "string (DD/MM/AAAA)", "descricao": "string",
                    "valor": "number (negativo = saída)", "saldo": "number"}],
}
_extrator = None


def _docstrange():
    global _extrator
    if _extrator is None:
        try:
            from docstrange import DocumentExtractor
        except ImportError as e:
            raise RuntimeError("DocStrange não instalado (pip install docstrange).") from e
        if DOCSTRANGE_MODO == "gpu":
            _extrator = DocumentExtractor(gpu=True)
        else:
            if not NANONETS_API_KEY:
                raise RuntimeError("Defina a variável NANONETS_API_KEY para usar o DocStrange na nuvem.")
            _extrator = DocumentExtractor(api_key=NANONETS_API_KEY)
    return _extrator


def _achar_transacoes(obj):
    """Procura, em qualquer nível do JSON devolvido, a lista de lançamentos."""
    if isinstance(obj, list) and obj and all(isinstance(i, dict) for i in obj) \
            and any("valor" in i or "amount" in i for i in obj):
        return obj
    if isinstance(obj, dict):
        for v in obj.values():
            achou = _achar_transacoes(v)
            if achou:
                return achou
    return None


def ler_docstrange(caminho):
    res = _docstrange().extract(str(caminho))
    # O DocStrange não lança erro quando a API falha: devolve conteúdo vazio. Por isso checamos tudo.
    dados = res.extract_data(json_schema=ESQUEMA_EXTRATO)
    meta = dados.get("structured_data") if dados.get("format") == "structured_json" else None
    if isinstance(meta, str):
        try:
            meta = json.loads(meta)
        except ValueError:
            meta = None
    meta = meta if isinstance(meta, dict) else {}
    periodo = None
    if meta.get("periodo_inicio") and meta.get("periodo_fim"):
        periodo = (parse_data(meta["periodo_inicio"]), parse_data(meta["periodo_fim"]))
        periodo = periodo if all(periodo) else None
    brutas = _achar_transacoes(meta) or []
    texto = ""
    if not brutas or (periodo is None and any(re.fullmatch(r"\d{1,2}/\d{1,2}", str(t.get("data", "")).strip())
                                              for t in brutas)):
        texto = res.extract_markdown() or ""
        periodo = periodo or detectar_periodo(texto)
    linhas = []
    for t in brutas:
        d, v = parse_data(t.get("data"), periodo), parse_valor(t.get("valor", t.get("amount")))
        if d and v is not None:
            linhas.append({"data": d, "descricao": normalizar_descricao(t.get("descricao", t.get("description"))),
                           "valor": v, "saldo": parse_valor(t.get("saldo"))})
    metodo = "docstrange · json_schema"
    if not linhas and texto:
        linhas, metodo = parse_texto(texto, periodo), "docstrange · markdown"
    extra = {"periodo": periodo,
             "saldo_inicial": parse_valor(meta.get("saldo_inicial")) if meta.get("saldo_inicial") is not None
             else detectar_saldo(texto, "inicial"),
             "saldo_final": parse_valor(meta.get("saldo_final")) if meta.get("saldo_final") is not None
             else detectar_saldo(texto, "final")}
    return linhas, texto, metodo, extra


def ler_pdf_local(caminho):
    from pypdf import PdfReader
    texto = "\n".join(p.extract_text() or "" for p in PdfReader(str(caminho)).pages)
    return parse_texto(texto), texto


# ============================== Roteador ==============================
LOCAIS = {".csv", ".tsv", ".txt", ".xlsx", ".xls", ".ofx"}
VIA_DOCSTRANGE = {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".gif",
                  ".docx", ".doc", ".pptx", ".ppt", ".html", ".htm"}
SUPORTADOS = LOCAIS | VIA_DOCSTRANGE


def extrair(caminho):
    p = Path(caminho)
    ext = p.suffix.lower()
    r = {"arquivo": p.name, "tipo": ext.lstrip("."), "metodo": None, "transacoes": [],
         "periodo": None, "saldo_inicial": None, "saldo_final": None, "avisos": []}
    texto = ""
    try:
        if ext in (".csv", ".tsv", ".txt"):
            r["transacoes"], texto = ler_delimitado(p)
            r["metodo"] = "local · delimitado"
            if not r["transacoes"]:
                r["transacoes"], r["metodo"] = parse_texto(texto), "local · texto livre"
        elif ext in (".xlsx", ".xls"):
            r["transacoes"], texto = ler_planilha(p)
            r["metodo"] = "local · planilha"
        elif ext == ".ofx":
            r["transacoes"], texto = ler_ofx(p)
            r["metodo"] = "local · OFX"

        if not r["transacoes"] and (ext in VIA_DOCSTRANGE or ext in (".txt", ".xlsx", ".xls")):
            try:
                r["transacoes"], texto, r["metodo"], extra = ler_docstrange(p)
                r.update({k: v for k, v in extra.items() if v is not None})
            except Exception as e:
                r["avisos"].append(f"DocStrange falhou: {e}")
            if not r["transacoes"] and ext == ".pdf":
                r["transacoes"], texto = ler_pdf_local(p)
                r["metodo"] = "fallback · texto do PDF (pypdf)"
                r["avisos"].append("PDF lido sem DocStrange; só funciona se o PDF tiver camada de texto.")
        elif ext not in SUPORTADOS:
            r["avisos"].append(f"Tipo {ext} não suportado.")
    except Exception as e:
        r["avisos"].append(f"Erro ao ler: {e}")

    r["periodo"] = r["periodo"] or detectar_periodo(texto)
    r["saldo_inicial"] = r["saldo_inicial"] if r["saldo_inicial"] is not None else detectar_saldo(texto, "inicial")
    r["saldo_final"] = r["saldo_final"] if r["saldo_final"] is not None else detectar_saldo(texto, "final")
    if not r["transacoes"]:
        r["avisos"].append("Nenhuma transação encontrada.")
    return r
