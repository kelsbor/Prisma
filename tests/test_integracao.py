"""Teste de ponta a ponta: Coletor lê os extratos fictícios de extratos_ficticios/ e grava no Armazenamento.

    python -m pytest
"""

import asyncio

from coletor import pipeline
from comum.cliente_armazenamento import conectar

TITULAR = "000.000.000-00"  # fictício


def test_analise_dos_extratos_ficticios():
    relatorio, consolidado = pipeline.analisar()
    assert len(consolidado) == 79
    assert relatorio["liquido_consolidado"] == -341.44            # 503,68 − 845,12
    assert len({d["chave"] for d in consolidado}) == 79
    alertas = {a for d in consolidado for a in d.get("alertas", [])}
    assert {"repetido_no_mesmo_dia", "valor_irrisorio", "descricao_parecida_com:PAG*IFOOD",
            "estorna:2026-09-03", "estorna:2026-09-10"} <= alertas


def test_coletor_grava_no_armazenamento_sem_duplicar():
    async def fluxo():
        _, consolidado = pipeline.analisar()
        async with conectar() as cliente:
            primeiro = await pipeline.enviar(cliente, TITULAR, consolidado)
            segundo = await pipeline.enviar(cliente, "00000000000", consolidado)  # mesmo CPF, sem pontuação
            base = await cliente.chamar("consultar_titular", {"titular_id": TITULAR})
            apagados = await cliente.chamar("eliminar_titular", {"titular_id": TITULAR})
        return primeiro, segundo, base, apagados

    primeiro, segundo, base, apagados = asyncio.run(fluxo())
    assert primeiro == {"gravadas": 79, "ja_existiam": 0}
    assert segundo == {"gravadas": 0, "ja_existiam": 79}
    assert len(base["registros"]) == 79
    assert round(sum(r["dados"]["valor"] for r in base["registros"]), 2) == -341.44
    assert apagados["apagados"] == 79

