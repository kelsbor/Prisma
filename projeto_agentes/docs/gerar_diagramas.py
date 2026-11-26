"""Gera os diagramas SVG do README (docs/*.svg), no mesmo estilo de docs/arquitetura.svg.

    python docs/gerar_diagramas.py

Cada diagrama é uma lista de caixas e setas com coordenadas fixas. Para mudar um diagrama, edite a
função dele e rode o script de novo.
"""

from pathlib import Path
from xml.sax.saxutils import escape

PASTA = Path(__file__).resolve().parent
ESTILO = """
  <defs>
    <marker id="seta" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
      <path d="M2 1L8 5L2 9" fill="none" stroke="#5F5E5A" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>
    </marker>
    <style>
      .t { font-size: 15px; font-weight: 600; }  .s { font-size: 12.5px; }  .l { font-size: 12px; fill: #5F5E5A; }
      .g { font-size: 13px; font-weight: 600; fill: #5F5E5A; }
      .ag rect { fill: #EEEDFE; stroke: #534AB7; } .ag .t { fill: #3C3489; } .ag .s { fill: #534AB7; }
      .dd rect { fill: #E1F5EE; stroke: #0F6E56; } .dd .t { fill: #085041; } .dd .s { fill: #0F6E56; }
      .nt rect { fill: #F1EFE8; stroke: #5F5E5A; } .nt .t { fill: #2C2C2A; } .nt .s { fill: #444441; }
      .rn rect { fill: #FAEEDA; stroke: #854F0B; } .rn .t { fill: #633806; } .rn .s { fill: #854F0B; }
      .ex rect { fill: #FFFFFF; stroke: #5F5E5A; stroke-dasharray: 6 4; } .ex .t { fill: #2C2C2A; } .ex .s { fill: #444441; }
      .seta { stroke: #5F5E5A; stroke-width: 1.4; fill: none; }  .trac { stroke-dasharray: 6 4; }
      .grupo { fill: none; stroke: #B4B2A9; stroke-dasharray: 4 4; }
    </style>
  </defs>"""
LEGENDA = {"ag": ("agente ou ferramenta MCP", "#EEEDFE", "#534AB7", ""),
           "nt": ("etapa em Python", "#F1EFE8", "#5F5E5A", ""),
           "dd": ("dados na máquina", "#E1F5EE", "#0F6E56", ""),
           "rn": ("rede neural", "#FAEEDA", "#854F0B", ""),
           "ex": ("fora da máquina ou opcional", "#FFFFFF", "#5F5E5A", ' stroke-dasharray="4 3"')}


class Diagrama:
    def __init__(self, nome, titulo, descricao, altura, largura=1000):
        self.nome, self.titulo, self.descricao = nome, titulo, descricao
        self.altura, self.largura, self.partes, self.tipos = altura, largura, [], []

    def caixa(self, x, y, w, titulo, sub="", tipo="nt", h=56):
        for texto, px in ((titulo, 8.6), (sub, 7.0)):          # confere se o texto cabe na caixa
            assert len(texto) * px <= w - 12, f"{self.nome}: '{texto}' não cabe em {w}px"
        self.tipos.append(tipo)
        cx = x + w / 2
        ty, sy = (y + h / 2 + 5, None) if not sub else (y + h / 2 - 4, y + h / 2 + 15)
        p = [f'<g class="{tipo}"><rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8"/>',
             f'<text class="t" x="{cx}" y="{ty}" text-anchor="middle">{escape(titulo)}</text>']
        if sub:
            p.append(f'<text class="s" x="{cx}" y="{sy}" text-anchor="middle">{escape(sub)}</text>')
        self.partes.append("".join(p) + "</g>")

    def seta(self, *pontos, tracejada=False):
        d = "M" + " L".join(f"{x} {y}" for x, y in pontos)
        self.partes.append(f'<path class="seta{" trac" if tracejada else ""}" d="{d}" marker-end="url(#seta)"/>')

    def rotulo(self, x, y, texto, ancora="middle", fundo=False):
        if fundo:                                    # fundo branco para o texto não ficar sobre linhas
            w = len(texto) * 6.4 + 8
            x0 = {"middle": x - w / 2, "start": x - 4, "end": x - w + 4}[ancora]
            self.partes.append(f'<rect x="{x0:.0f}" y="{y - 13}" width="{w:.0f}" height="18" fill="#FFFFFF"/>')
        self.partes.append(f'<text class="l" x="{x}" y="{y}" text-anchor="{ancora}">{escape(texto)}</text>')

    def linha(self, x1, y1, x2, y2, tracejada=True, cor="#B4B2A9"):
        tr = ' stroke-dasharray="4 4"' if tracejada else ""
        self.partes.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{cor}" stroke-width="1"{tr}/>')

    def bruto(self, svg):
        self.partes.append(svg)

    def grupo(self, x, y, w, h, titulo):
        self.partes.append(f'<rect class="grupo" x="{x}" y="{y}" width="{w}" height="{h}" rx="10"/>'
                           f'<text class="g" x="{x + 14}" y="{y + 20}">{escape(titulo)}</text>')

    def salvar(self):
        y, x, leg = self.altura - 28, 40, []
        for tipo in dict.fromkeys(self.tipos):
            texto, fill, stroke, extra = LEGENDA[tipo]
            leg.append(f'<rect x="{x}" y="{y - 11}" width="14" height="14" rx="3" fill="{fill}" stroke="{stroke}"{extra}/>'
                       f'<text class="l" x="{x + 20}" y="{y}">{texto}</text>')
            x += 48 + len(texto) * 7.0
        svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.largura}" height="{self.altura}" '
               f'viewBox="0 0 {self.largura} {self.altura}" font-family="Segoe UI, Helvetica, Arial, sans-serif">\n'
               f'  <title>{escape(self.titulo)}</title>\n  <desc>{escape(self.descricao)}</desc>{ESTILO}\n'
               f'  <rect width="{self.largura}" height="{self.altura}" fill="#FFFFFF"/>\n  '
               + "\n  ".join(self.partes + leg) + "\n</svg>\n")
        (PASTA / f"{self.nome}.svg").write_text(svg, encoding="utf-8")
        return PASTA / f"{self.nome}.svg"


def consultas():
    d = Diagrama("agente-consultas", "Agente de Consultas",
                 "Perguntas sobre os gastos respondidas com SQL, com o código do assistente do PrismaAPP: filtro "
                 "de manipulação, Gemini escreve o SQL, validação, execução somente leitura no banco da Pluggy, Gemini "
                 "redige e o guardião confere que todo valor em R$ existe no resultado.", 360)
    d.caixa(40, 40, 200, "Pergunta", "até 300 caracteres", "ag")
    d.caixa(280, 40, 200, "Filtro", "bloqueia manipulação")
    d.caixa(520, 40, 200, "Gemini escreve SQL", "prompt do PrismaAPP", "ex")
    d.caixa(760, 40, 200, "Valida o SQL", "1 SELECT, só a view")
    d.caixa(760, 170, 200, "Executa", "só leitura, até 3 s")
    d.caixa(520, 170, 200, "Banco da Pluggy", "vw_registers", "dd")
    d.caixa(280, 170, 200, "Gemini redige", "com o resultado", "ex")
    d.caixa(40, 170, 200, "Guardião do R$", "todo R$ vem dos dados", "nt")
    d.seta((240, 68), (276, 68))
    d.seta((480, 68), (516, 68))
    d.seta((720, 68), (756, 68))
    d.seta((860, 96), (860, 166))
    d.seta((760, 198), (724, 198))
    d.seta((520, 198), (484, 198))
    d.seta((280, 198), (244, 198))
    d.seta((960, 198), (985, 198), (985, 20), (620, 20), (620, 36), tracejada=True)
    d.rotulo(800, 15, "erro no banco: 1 correção", fundo=True)
    d.grupo(40, 270, 920, 34, "código reaproveitado do PrismaAPP: prompt, exemplos, filtro e validação (PrismaAPP/agent/src)")
    return d.salvar()


def arquitetura():
    d = Diagrama("arquitetura", "Arquitetura do Prisma",
                 "A Pluggy (Open Finance) alimenta, pelo agente-sql, um banco local somente leitura. Três agentes MCP "
                 "locais: Consultas responde com SQL validado sobre esse banco, Especialista explica com RAG e usa o "
                 "resumo do mês e o Agente de Indicadores (Banco Central). O assistente do PrismaAPP atende o app.", 620)
    d.caixa(40, 30, 210, "Pluggy", "Open Finance", "ex")
    d.caixa(395, 30, 210, "Pessoa", "terminal, VS Code ou app")
    d.caixa(750, 30, 210, "Gemini", "texto e SQL · opcional", "ex")
    d.caixa(40, 140, 210, "agente-sql", "./prisma.sh pluggy", "nt")
    d.caixa(750, 140, 210, "PrismaAPP", "app Android", "ex")
    d.grupo(20, 228, 960, 120, "serviços locais")
    d.caixa(40, 270, 200, "Consultas", "8006 · SQL validado", "ag")
    d.caixa(280, 270, 200, "Especialista", "8002 · RAG", "ag")
    d.caixa(520, 270, 200, "Indicadores", "8004 · Banco Central", "ag")
    d.caixa(760, 270, 200, "Assistente do app", "8010 · text-to-SQL", "ag")
    d.caixa(40, 410, 200, "Banco da Pluggy", "~/.prisma/app", "dd")
    d.caixa(280, 410, 200, "Chroma", "índice vetorial", "dd")
    d.caixa(520, 410, 200, "Banco Central", "API pública", "ex")
    d.caixa(280, 510, 200, "base_conhecimento/", "37 materiais", "dd")
    d.seta((145, 86), (145, 136))
    d.seta((40, 168), (26, 168), (26, 438), (36, 438))
    d.rotulo(34, 214, "grava", "start", fundo=True)
    d.seta((420, 86), (420, 266))
    d.seta((460, 270), (460, 118), (855, 118), (855, 90), tracejada=True)
    d.seta((140, 326), (140, 406))
    d.rotulo(148, 372, "só leitura", "start")
    d.seta((300, 326), (300, 370), (220, 370), (220, 406))
    d.seta((420, 326), (420, 406))
    d.seta((480, 298), (516, 298))
    d.rotulo(498, 290, "MCP")
    d.seta((620, 326), (620, 406))
    d.seta((855, 196), (855, 266))
    d.seta((380, 510), (380, 470))
    d.rotulo(388, 494, "indexar", "start")
    d.tipos = ["ag", "nt", "dd", "ex"]
    return d.salvar()


def pluggy():
    d = Diagrama("dados-pluggy", "Dados da Pluggy",
                 "O gerar_banco.py do agente-sql baixa contas, cartões e transações da Pluggy para um banco SQLite "
                 "local, com a mesma vw_registers do PrismaAPP. Especialista, Consultas e agente-sql leem esse banco "
                 "somente para leitura.", 350)
    d.caixa(40, 40, 200, "API da Pluggy", "Open Finance", "ex")
    d.caixa(300, 40, 200, "gerar_banco.py", "./prisma.sh pluggy", "nt")
    d.caixa(560, 40, 220, "Banco da Pluggy", "vw_registers e contas", "dd")
    d.caixa(40, 180, 220, "Especialista", "resumo do mês", "ag")
    d.caixa(300, 180, 220, "Consultas", "SQL validado", "ag")
    d.caixa(560, 180, 220, "agente-sql", "saldo, fatura e limite", "ag")
    d.seta((240, 68), (296, 68))
    d.seta((500, 68), (556, 68))
    d.seta((580, 96), (580, 128), (150, 128), (150, 176))
    d.seta((610, 96), (610, 145), (410, 145), (410, 176))
    d.seta((690, 96), (690, 176))
    d.grupo(40, 256, 740, 34, "arquivo local com permissão 600; os agentes abrem somente para leitura")
    return d.salvar()


def especialista():
    d = Diagrama("agente-especialista", "Agente Especialista",
                 "Indexar: a base é dividida em pedaços, vira vetores e vai para o Chroma. Perguntar: a pergunta vira "
                 "vetor, o Chroma traz os trechos, o filtro de nota mantém os relevantes e, com chave, o Gemini escreve "
                 "a resposta com o resumo do mês (dados da Pluggy) e as taxas do Banco Central.", 640)
    d.grupo(20, 18, 960, 120, "indexar · ./prisma.sh indexar")
    d.caixa(40, 62, 200, "base_conhecimento/", "37 materiais em JSONL", "dd")
    d.caixa(280, 62, 200, "Limpar e dividir", "pedaços de 800 caracteres")
    d.caixa(520, 62, 200, "Embeddings", "local ou Gemini")
    d.caixa(760, 62, 200, "Chroma", "~/.prisma/rag/<modo>", "dd")
    d.seta((240, 90), (276, 90))
    d.seta((480, 90), (516, 90))
    d.seta((720, 90), (756, 90))
    d.grupo(20, 170, 960, 410, "perguntar · ./prisma.sh especialista perguntar")
    d.caixa(40, 214, 200, "Pergunta", "com ou sem --com-dados", "ag")
    d.caixa(280, 214, 200, "Embedding", "o mesmo modelo do índice")
    d.caixa(520, 214, 200, "Busca no Chroma", "4 trechos mais parecidos")
    d.caixa(760, 214, 200, "Filtro de nota", "PRISMA_NOTA_MINIMA")
    d.seta((240, 242), (276, 242))
    d.seta((480, 242), (516, 242))
    d.seta((720, 242), (756, 242))
    d.seta((860, 118), (860, 150), (620, 150), (620, 210))
    d.caixa(40, 340, 200, "Resumo do mês", "banco da Pluggy", "dd")
    d.caixa(520, 340, 200, "Monta o prompt", "regras, dados e trechos")
    d.caixa(760, 340, 200, "GOOGLE_API_KEY?", "chave preenchida no .env")
    d.seta((860, 270), (860, 300), (620, 300), (620, 336))
    d.seta((140, 396), (140, 424), (525, 424), (525, 400))
    d.caixa(40, 480, 200, "Indicadores", "Banco Central, via MCP", "ag")
    d.seta((240, 508), (545, 508), (545, 400))
    d.seta((720, 368), (756, 368))
    d.caixa(580, 480, 190, "Gemini escreve", "resposta com fontes", "ex")
    d.caixa(800, 480, 160, "Só os trechos", "com fonte e página", "ag")
    d.seta((800, 396), (800, 440), (675, 440), (675, 476))
    d.rotulo(690, 460, "sim", "start")
    d.seta((910, 396), (910, 476))
    d.rotulo(918, 444, "não", "start")
    return d.salvar()




def indicadores():
    d = Diagrama("agente-indicadores", "Agente de Indicadores",
                 "O Especialista chama as ferramentas MCP do Agente de Indicadores; as contas são feitas "
                 "em Python sobre dados do Banco Central, guardados em cache por 12 horas. Só os códigos das séries saem "
                 "da máquina.", 380)
    d.caixa(40, 60, 240, "Especialista", "pede por MCP", "ag")
    d.caixa(330, 60, 290, "Ferramentas MCP", "juros, indicador, simular, histórico", "ag")
    d.caixa(670, 60, 290, "Contas em Python", "comparação, simulação, teto legal")
    d.caixa(330, 200, 270, "Cache local", "~/.prisma/indicadores · 12 h", "dd")
    d.caixa(690, 200, 270, "API do Banco Central", "SGS · pública, sem chave", "ex")
    d.seta((280, 88), (326, 88))
    d.seta((620, 88), (666, 88))
    d.seta((815, 116), (815, 160), (475, 160), (475, 196))
    d.seta((600, 228), (686, 228))
    d.rotulo(643, 220, "vencido")
    d.grupo(330, 290, 630, 34, "sai da máquina: só o código da série (ex.: 22022); nenhum dado da pessoa")
    return d.salvar()


def embeddings():
    d = Diagrama("modos-embeddings", "Modos de embeddings",
                 "Com PRISMA_EMBEDDINGS=local, os vetores são calculados na máquina por um modelo multilíngue; com "
                 "lexico, por palavras, sem modelo; com gemini, pela API do Google. Cada modo tem o próprio índice. "
                 "Escrever a resposta depende só da GOOGLE_API_KEY.", 590)
    d.caixa(370, 30, 260, "Texto", "pedaço da base ou pergunta")
    for x, modo in ((30, "local"), (360, "lexico"), (690, "gemini")):
        d.caixa(x, 140, 280, f"PRISMA_EMBEDDINGS={modo}")
        d.caixa(x, 340, 280, "Chroma", f"~/.prisma/rag/{modo}", "dd")
        d.seta((x + 140, 196), (x + 140, 236))
        d.seta((x + 140, 296), (x + 140, 336))
    d.caixa(30, 240, 280, "Modelo local (fastembed)", "MiniLM multilíngue · 384 números")
    d.caixa(360, 240, 280, "Palavras, sem modelo", "2.048 posições · sem internet")
    d.caixa(690, 240, 280, "API do Gemini", "gemini-embedding-001 · 3.072", "ex")
    d.seta((440, 86), (440, 112), (170, 112), (170, 136))
    d.seta((500, 86), (500, 136))
    d.seta((560, 86), (560, 112), (830, 112), (830, 136))
    d.grupo(300, 425, 400, 112, "independente do modo")
    d.caixa(320, 458, 360, "Escrever a resposta", "Gemini só com GOOGLE_API_KEY", "ex", h=56)
    return d.salvar()

if __name__ == "__main__":
    for f in (arquitetura, pluggy, especialista, indicadores, consultas, embeddings):
        print("gerado:", f())
