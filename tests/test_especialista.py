"""Especialista sem internet: manutenção da RAG (com embeddings falsos) e resumo vindo do Armazenamento."""

import asyncio
import json
import os
import tempfile
from pathlib import Path

BASE = Path(tempfile.mkdtemp(prefix="prisma-base-"))
os.environ["PRISMA_BASE"] = str(BASE)

from coletor import pipeline  # noqa: E402
from comum.cliente_armazenamento import conectar  # noqa: E402
from especialista import agente, dados, rag  # noqa: E402

TITULAR = "222.222.222-22"  # fictício


def _escrever(nome, paginas):
    (BASE / nome).write_text("\n".join(json.dumps({"arquivo": nome, "pagina": i + 1, "texto": t}, ensure_ascii=False)
                                       for i, t in enumerate(paginas)), encoding="utf-8")


def test_manutencao_da_rag():
    texto = "O cheque especial é um empréstimo automático da conta corrente, com juros altos e IOF. " * 3
    _escrever("A.jsonl", [texto, "curto", "Reserva de emergência é dinheiro guardado para imprevistos. " * 3])
    _escrever("A.backup.jsonl", [texto])                       # backup: ignorado
    (BASE / "copia.jsonl").write_bytes((BASE / "A.jsonl").read_bytes())    # cópia idêntica: ignorada

    r = rag.indexar()
    assert r["arquivos"] == 1 and r["indexados_agora"] == 1 and r["pedacos"] == 2   # cópia idêntica e página curta fora
    assert rag.indexar()["indexados_agora"] == 0                                    # nada mudou: nada refeito

    _escrever("B.jsonl", ["O rotativo do cartão cobra juros sobre o saldo que não foi pago na fatura. " * 3])
    r = rag.indexar()
    assert r["indexados_agora"] == 1 and r["indexados"] == 2

    (BASE / "A.jsonl").unlink()
    (BASE / "copia.jsonl").unlink()
    r = rag.indexar()
    assert r["removidos"] == 1 and r["pedacos"] == 1
    trechos = rag.buscar("rotativo", k=3)
    assert [t["fonte"] for t in trechos] == ["B"] and trechos[0]["pagina"] == 1


def test_resumo_vem_do_armazenamento():
    async def preparar():
        _, consolidado = pipeline.analisar()
        async with conectar() as cliente:
            await pipeline.enviar(cliente, TITULAR, consolidado)
        return await dados.transacoes(TITULAR)

    resumo = dados.resumo(asyncio.run(preparar()))
    assert resumo["periodo"] == "2026-10" and resumo["saldo"] == round(resumo["entradas"] - resumo["saidas"], 2)
    assert dados.resumo([])["erro"]


def test_perguntar_sem_chave_devolve_trechos():
    r = agente.perguntar("o que é rotativo?")
    assert r["gerado_por"].startswith("sem Gemini") and "trechos" in r
