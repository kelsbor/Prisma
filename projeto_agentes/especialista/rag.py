"""RAG do Especialista: lê os JSONL de base_conhecimento/, divide em pedaços e indexa no Chroma
com embeddings do Gemini. O título e a instituição de cada documento vêm de base_conhecimento/fontes.json.

Manter a base é só mexer na pasta e rodar `python -m especialista indexar`:
- arquivo novo ou alterado: é (re)indexado;
- arquivo apagado: sai do índice;
- arquivo igual ao último indexado: não é tocado (não gasta cota do Gemini).

Ignorados: subpastas, arquivos com "backup" no nome, arquivos de conteúdo idêntico a outro, páginas marcadas com
"incluir_no_chunking": false e páginas com menos de 80 caracteres úteis.
"""

import hashlib
import json
import os
import re
import time
from pathlib import Path

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from comum.config import DATA_DIR, RAIZ, log

PASTA_BASE = Path(os.getenv("PRISMA_BASE") or RAIZ / "base_conhecimento").expanduser()
# Embeddings: "gemini" (padrão, precisa da GOOGLE_API_KEY), "local" (modelo multilíngue rodando na
# própria máquina, sem chave nem cota; baixa ~220 MB na primeira vez), "lexico" (busca por palavras,
# sem modelo nem internet) ou "falso" (vetores aleatórios, só para testes de manutenção do índice).
MODO_EMBEDDINGS = os.getenv("PRISMA_EMBEDDINGS") or "gemini"
MODELO_EMBEDDING = ((os.getenv("PRISMA_MODELO_EMBEDDING_LOCAL") or "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
                    if MODO_EMBEDDINGS == "local"
                    else (os.getenv("PRISMA_MODELO_EMBEDDING") or "models/gemini-embedding-001"))
PASTA_INDICE = DATA_DIR / "rag" / MODO_EMBEDDINGS          # um índice por modo: trocar não apaga o outro
LOTE = 100                       # pedaços por chamada de embedding
MIN_CARACTERES = 80


def _log(msg):
    log("agente-especialista", msg)


# ------------------------------------------------------------------ leitura e limpeza
def limpar(texto: str) -> str:
    t = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", texto or "")   # lixo de extração de PDF
    t = re.sub(r"(?<!\n)\n(?!\n)", " ", t)                              # junta linhas do mesmo parágrafo
    t = re.sub(r"\n{3,}", "\n\n", t)
    return re.sub(r"[ \t]{2,}", " ", t).strip()


def arquivos_da_base() -> dict[str, Path]:
    """{nome: caminho} dos JSONL válidos, sem backups e sem cópias de conteúdo idêntico."""
    vistos, arquivos = {}, {}
    for p in sorted(PASTA_BASE.glob("*.jsonl")):
        if "backup" in p.stem.lower():
            continue
        h = hashlib.sha256(p.read_bytes()).hexdigest()
        if h in vistos:
            _log(f"{p.name} é igual a {vistos[h]}; ignorado")
            continue
        vistos[h] = p.name
        arquivos[p.name] = p
    return arquivos


def catalogo() -> dict:
    """Título e instituição de cada arquivo (base_conhecimento/fontes.json)."""
    f = PASTA_BASE / "fontes.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}


def nome_da_fonte(arquivo: str, cat: dict | None = None) -> str:
    info = (catalogo() if cat is None else cat).get(arquivo)
    return f"{info['instituicao']}, {info['titulo']}" if info else Path(arquivo).stem


def _hash(p: Path) -> str:
    """Muda quando o arquivo ou o título dele em fontes.json mudam."""
    info = json.dumps(catalogo().get(p.name), sort_keys=True, ensure_ascii=False).encode()
    return hashlib.sha256(p.read_bytes() + info).hexdigest()


def pedacos_do_arquivo(p: Path) -> list[Document]:
    docs, fonte = [], nome_da_fonte(p.name)
    for linha in p.read_text(encoding="utf-8", errors="replace").split("\n"):   # não usar splitlines: há \x0c dentro dos textos
        if not linha.strip():
            continue
        pag = json.loads(linha)
        if pag.get("incluir_no_chunking") is False:
            continue
        texto = limpar(pag.get("texto", ""))
        if len(texto) < MIN_CARACTERES:
            continue
        docs.append(Document(page_content=texto, metadata={
            "arquivo": p.name, "fonte": fonte, "pagina": int(pag.get("pagina") or 0)}))
    return RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=150).split_documents(docs)


# ------------------------------------------------------------------ índice
class EmbeddingsLocais:
    """Embeddings no próprio computador com o fastembed (ONNX, sem GPU e sem chave)."""

    def __init__(self, modelo: str):
        self.modelo, self._m = modelo, None

    def _carregar(self):
        if self._m is None:
            from fastembed import TextEmbedding
            _log(f"Carregando o modelo local {self.modelo} (na primeira vez, baixa ~220 MB)...")
            self._m = TextEmbedding(self.modelo, cache_dir=str(DATA_DIR / "modelos"))
        return self._m

    def embed_documents(self, textos):
        return [v.tolist() for v in self._carregar().embed(list(textos), batch_size=64)]

    def embed_query(self, texto):
        return self.embed_documents([texto])[0]


class EmbeddingsLexicos:
    """Busca por palavras, sem modelo e sem internet: cada texto vira um vetor de 2.048 posições com as
    palavras e pares de palavras (sem acento, sem palavras comuns), em peso log. Pega sinônimos mal, mas
    serve para testar a RAG em qualquer máquina e como alternativa quando não dá para baixar o modelo."""

    DIM = 2048
    COMUNS = set("""a o as os um uma uns umas de da do das dos em na no nas nos por para com sem sob que se
    e ou mas como mais menos muito muita muitos muitas ao aos à às pelo pela pelos pelas seu sua seus suas meu
    minha meus minhas eu voce voces ele ela eles elas isso isto esse essa este esta qual quais quando onde ja
    nao sim ser estar ter ha foi sao era tem pode posso devo deve fazer faz qualquer outro outra""".split())

    @classmethod
    def _palavras(cls, texto: str) -> list[str]:
        import unicodedata
        t = unicodedata.normalize("NFKD", texto.lower()).encode("ascii", "ignore").decode()
        return [w for w in re.findall(r"[a-z0-9]+", t) if len(w) > 2 and w not in cls.COMUNS]

    @classmethod
    def _vetor(cls, texto: str) -> list[float]:
        import math
        p = cls._palavras(texto)
        contagem = {}
        for termo in p + [f"{a}_{b}" for a, b in zip(p, p[1:])]:
            contagem[termo] = contagem.get(termo, 0) + 1
        v = [0.0] * cls.DIM
        for termo, n in contagem.items():
            h = int(hashlib.md5(termo.encode()).hexdigest(), 16)
            v[h % cls.DIM] += (1.0 if (h >> 20) % 2 else -1.0) * (1 + math.log(n))
        norma = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / norma for x in v]

    def embed_documents(self, textos):
        return [self._vetor(t) for t in textos]

    def embed_query(self, texto):
        return self._vetor(texto)


def _embeddings():
    if MODO_EMBEDDINGS == "lexico":
        return EmbeddingsLexicos()
    if MODO_EMBEDDINGS == "falso":                          # só para testes sem internet
        from langchain_core.embeddings import DeterministicFakeEmbedding
        return DeterministicFakeEmbedding(size=256)
    if MODO_EMBEDDINGS == "local":
        return EmbeddingsLocais(MODELO_EMBEDDING)
    if not os.getenv("GOOGLE_API_KEY"):
        raise RuntimeError("GOOGLE_API_KEY não definida. Coloque no .env, ou use embeddings locais "
                           "com PRISMA_EMBEDDINGS=local (sem chave).")
    from langchain_google_genai import GoogleGenerativeAIEmbeddings
    return GoogleGenerativeAIEmbeddings(model=MODELO_EMBEDDING)


_db = None


def _sqlite_compativel():
    """O Chroma exige SQLite 3.35+. Ubuntu 20.04 (e Pythons compilados nele) trazem o 3.31; nesse caso
    troca o módulo sqlite3 pelo pysqlite3-binary, que já vem com um SQLite novo."""
    import sqlite3
    if tuple(map(int, sqlite3.sqlite_version.split("."))) >= (3, 35, 0):
        return
    try:
        import pysqlite3
    except ImportError:
        raise RuntimeError(f"O SQLite do sistema ({sqlite3.sqlite_version}) é antigo para o Chroma. "
                           "Rode: pip install pysqlite3-binary") from None
    import sys
    sys.modules["sqlite3"] = pysqlite3


def _abrir():
    global _db
    if _db is None:
        _sqlite_compativel()
        from langchain_chroma import Chroma
        PASTA_INDICE.mkdir(parents=True, exist_ok=True)
        _db = Chroma(collection_name="prisma", embedding_function=_embeddings(),
                     persist_directory=str(PASTA_INDICE), collection_metadata={"hnsw:space": "cosine"})
    return _db


def _manifesto_arquivo() -> Path:
    return PASTA_INDICE / "manifesto.json"


def _manifesto() -> dict:
    f = _manifesto_arquivo()
    m = json.loads(f.read_text()) if f.exists() else {}
    if m.get("_modelo") not in (None, MODELO_EMBEDDING):
        return {}                                        # trocou o modelo: tudo precisa ser refeito
    return m


def _salvar_manifesto(m: dict) -> None:
    m["_modelo"] = MODELO_EMBEDDING
    _manifesto_arquivo().write_text(json.dumps(m, ensure_ascii=False, indent=1))


def _adicionar_com_espera(db, chunks, ids):
    """Envia em lotes; se o Gemini recusar por limite de uso (429), espera e tenta de novo."""
    for i in range(0, len(chunks), LOTE):
        for tentativa in range(6):
            try:
                db.add_documents(chunks[i:i + LOTE], ids=ids[i:i + LOTE])
                break
            except Exception as e:
                if "429" not in str(e) and "RESOURCE_EXHAUSTED" not in str(e) or tentativa == 5:
                    raise
                _log("Limite de uso do Gemini atingido; esperando 60 s...")
                time.sleep(60)


def status() -> dict:
    arquivos = arquivos_da_base()
    m = _manifesto()
    indexados = {n: m[n]["pedacos"] for n in arquivos if n in m and m[n]["hash"] == _hash(arquivos[n])}
    return {
        "pasta": str(PASTA_BASE),
        "arquivos": len(arquivos),
        "indexados": len(indexados),
        "pedacos": sum(indexados.values()),
        "pendentes": sorted(n for n in arquivos if n not in indexados),
        "removidos_da_pasta": sorted(n for n in m if not n.startswith("_") and n not in arquivos),
        "sem_titulo_em_fontes_json": sorted(n for n in arquivos if n not in catalogo()),
    }


def indexar(refazer: bool = False) -> dict:
    """Atualiza o índice com o que mudou na pasta. Pode ser interrompido e rodado de novo."""
    db = _abrir()
    m = {} if refazer else _manifesto()
    if refazer or not m:
        db.reset_collection()
    arquivos = arquivos_da_base()
    feitos = removidos = 0

    for nome in [n for n in m if not n.startswith("_") and n not in arquivos]:
        db.delete(where={"arquivo": nome})
        m.pop(nome)
        removidos += 1

    for nome, p in arquivos.items():
        h = _hash(p)
        if m.get(nome, {}).get("hash") == h:
            continue
        chunks = pedacos_do_arquivo(p)
        _log(f"Indexando {nome}: {len(chunks)} pedaços")
        db.delete(where={"arquivo": nome})                 # versão antiga ou execução interrompida
        _adicionar_com_espera(db, chunks, [f"{h[:12]}-{i}" for i in range(len(chunks))])
        m[nome] = {"hash": h, "pedacos": len(chunks)}
        _salvar_manifesto(m)                               # salva a cada arquivo: dá para retomar
        feitos += 1

    _salvar_manifesto(m)
    return {"indexados_agora": feitos, "removidos": removidos, **status()}


def buscar(pergunta: str, k: int = 4) -> list[dict]:
    """Os k trechos mais parecidos com a pergunta, com fonte, página e nota (0 a 1)."""
    achados = _abrir().similarity_search_with_relevance_scores(pergunta, k=k)
    return [{"fonte": d.metadata["fonte"], "pagina": d.metadata["pagina"], "nota": round(n, 3),
             "arquivo": d.metadata.get("arquivo", ""), "texto": d.page_content} for d, n in achados]
