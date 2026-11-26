"""Especialista sem internet: manutenção da RAG (com embeddings falsos) e resumo do banco da Pluggy."""

import json
from datetime import date
import os
import tempfile
from pathlib import Path

BASE = Path(tempfile.mkdtemp(prefix="prisma-base-"))
os.environ["PRISMA_BASE"] = str(BASE)

import pytest  # noqa: E402

from especialista import agente, dados, rag  # noqa: E402


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


def test_resumo_do_banco_da_pluggy(banco_app):
    r = dados.resumo("2026-10", hoje=date(2026, 11, 18))
    assert r["entradas"] == 5000.0 and r["gastos"] == 349.5          # a fatura (transferência) não conta como gasto
    assert r["saldo_do_mes"] == 4650.5 and r["maiores_gastos_por_categoria"][0]["categoria"] == "Supermercado"
    assert r["meses_com_dados"] == ["2026-10"]                          # a parcela futura fica de fora
    assert {c["tipo"] for c in r["contas"]} == {"conta", "cartão"} and r["contas"][0]["conta"] == "Conta"


def test_sem_banco_da_pluggy(tmp_path, monkeypatch):
    monkeypatch.setattr(dados, "BANCO_APP", tmp_path / "nao-existe.db")
    with pytest.raises(dados.SemDados, match="prisma.sh pluggy"):
        dados.resumo()


def test_perguntar_sem_chave_devolve_trechos():
    r = agente.perguntar("o que é rotativo?")
    assert r["gerado_por"].startswith("sem Gemini") and "trechos" in r


def test_prompt_fica_registrado(monkeypatch):
    from especialista import log_prompts
    antes = len(log_prompts.ultimos(1000))
    agente.perguntar("o que é cheque especial?", {"saldo": -10.0})
    reg = log_prompts.ultimos(1)[0]
    assert len(log_prompts.ultimos(1000)) == antes + 1
    assert reg["pergunta"] == "o que é cheque especial?"
    assert "## PERGUNTA\no que é cheque especial?" in reg["prompt"] and "'saldo': -10.0" in reg["prompt"]
    assert reg["enviado_ao_gemini"] is False and reg["gerado_por"].startswith("sem Gemini")

    monkeypatch.setenv("PRISMA_LOG_PROMPTS", "0")              # desligado: nada é gravado
    agente.perguntar("outra pergunta")
    assert len(log_prompts.ultimos(1000)) == antes + 1


def test_embeddings_lexicos_aproximam_textos_do_mesmo_assunto():
    e = rag.EmbeddingsLexicos()
    q = e.embed_query("Como funciona o cheque especial?")
    perto = e.embed_query("O cheque especial é um limite de crédito ligado à conta corrente.")
    longe = e.embed_query("Receita de bolo de chocolate com cobertura.")
    cos = lambda a, b: sum(x * y for x, y in zip(a, b))
    assert cos(q, perto) > 0.2 > cos(q, longe)


def test_avaliacao_da_busca(monkeypatch):
    from especialista import avaliacao
    respostas = {
        "rotativo?": [{"fonte": "F", "pagina": 1, "nota": 0.8, "arquivo": "outro.jsonl"},
                      {"fonte": "F", "pagina": 2, "nota": 0.7, "arquivo": "cartao.jsonl"}],
        "cheque?": [{"fonte": "F", "pagina": 1, "nota": 0.9, "arquivo": "cheque.jsonl"}],
        "futebol?": [{"fonte": "F", "pagina": 1, "nota": 0.3, "arquivo": "outro.jsonl"}],
    }
    monkeypatch.setattr(rag, "buscar", lambda p, k=4: respostas[p])
    r = avaliacao.avaliar(4, [{"pergunta": "rotativo?", "esperado": ["cartao"]},
                              {"pergunta": "cheque?", "esperado": ["cheque"]},
                              {"pergunta": "futebol?", "esperado": []}])
    assert r["acerto@1"] == 0.5 and r["acerto@4"] == 1.0 and r["mrr"] == 0.75
    assert r["notas_acertos"] == [0.7, 0.9] and r["notas_fora_do_tema"] == [0.3, 0.3]
    assert 0.3 < r["nota_minima_sugerida"] <= 0.7                      # separa acertos de fora do tema
    assert len(avaliacao.carregar()) >= 20                               # o conjunto de perguntas do projeto
