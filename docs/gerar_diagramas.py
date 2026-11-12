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


def armazenamento():
    d = Diagrama("agente-armazenamento", "Agente de Armazenamento",
                 "Salvar pseudonimiza o titular com HMAC, criptografa os dados com Fernet e evita duplicatas pela "
                 "chave; consultar busca pelo HMAC e descriptografa; eliminar apaga tudo do titular.", 520)
    d.caixa(40, 40, 240, "Salvar", "salvar_lote · salvar_transacao", "ag")
    d.caixa(40, 310, 240, "Consultar", "consultar_titular", "ag")
    d.caixa(40, 400, 240, "Eliminar", "eliminar_titular", "ag")
    d.caixa(340, 40, 300, "Titular vira HMAC", "ID sem pontuação, nunca em claro")
    d.caixa(340, 130, 300, "Dados viram Fernet", "o JSON inteiro é criptografado")
    d.caixa(340, 220, 300, "Chave vira HMAC", "a mesma transação não entra 2 vezes")
    d.caixa(340, 310, 300, "Fernet vira JSON", "descriptografa só na consulta")
    d.caixa(710, 40, 250, "chaves.json", "~/.prisma · permissão 600", "dd")
    d.caixa(710, 220, 250, "SQLite · registros", "~/.prisma/dados.db", "dd")
    d.seta((280, 68), (336, 68))
    d.seta((490, 96), (490, 126))
    d.seta((490, 186), (490, 216))
    d.seta((640, 248), (706, 248))
    d.rotulo(673, 240, "grava")
    d.seta((710, 68), (644, 68))
    d.rotulo(677, 60, "chaves")
    d.seta((835, 276), (835, 338), (644, 338))
    d.rotulo(740, 330, "busca pelo HMAC")
    d.seta((340, 338), (284, 338))
    d.seta((280, 428), (910, 428), (910, 280))
    d.rotulo(595, 420, "apaga tudo do titular (LGPD, art. 18)")
    return d.salvar()


def coletor():
    d = Diagrama("agente-coletor", "Agente Coletor",
                 "Lê extratos por formato, normaliza, confere a qualidade, consolida os arquivos e, no importar, "
                 "envia em lotes ao Agente de Armazenamento.", 450)
    d.caixa(40, 40, 200, "Extratos", "CSV, TXT, XLSX, OFX, PDF")
    d.caixa(290, 40, 200, "Ler por formato", "estruturados: lidos aqui")
    d.caixa(540, 40, 190, "Normalizar", "datas, valores e sinais")
    d.caixa(780, 40, 190, "Conferir", "alertas e conciliação")
    d.caixa(290, 180, 200, "DocStrange", "PDF escaneado e imagem", "ex")
    d.caixa(540, 180, 190, "analisar", "relatório, nada gravado", "ag")
    d.caixa(780, 180, 190, "Consolidar", "data + valor + ordem")
    d.caixa(540, 320, 190, "importar", "lotes de 200", "ag")
    d.caixa(40, 320, 200, "Armazenamento", "não grava duas vezes", "ag")
    d.seta((240, 68), (286, 68))
    d.seta((490, 68), (536, 68))
    d.seta((730, 68), (776, 68))
    d.seta((875, 96), (875, 176))
    d.seta((390, 96), (390, 176), tracejada=True)
    d.rotulo(398, 140, "opcional", "start")
    d.seta((780, 208), (734, 208))
    d.seta((875, 236), (875, 348), (734, 348))
    d.seta((540, 348), (244, 348))
    d.rotulo(392, 340, "salvar_lote (MCP)")
    return d.salvar()


def especialista():
    d = Diagrama("agente-especialista", "Agente Especialista",
                 "Indexar: a base é dividida em pedaços, vira vetores e vai para o Chroma. Perguntar: a pergunta vira "
                 "vetor, o Chroma traz os trechos, o filtro de nota mantém os relevantes e, com chave, o Gemini escreve "
                 "a resposta com o resumo do mês e o perfil de risco.", 640)
    d.grupo(20, 18, 960, 120, "indexar · ./prisma.sh indexar")
    d.caixa(40, 62, 200, "base_conhecimento/", "37 materiais em JSONL", "dd")
    d.caixa(280, 62, 200, "Limpar e dividir", "pedaços de 800 caracteres")
    d.caixa(520, 62, 200, "Embeddings", "local ou Gemini")
    d.caixa(760, 62, 200, "Chroma", "~/.prisma/rag/<modo>", "dd")
    d.seta((240, 90), (276, 90))
    d.seta((480, 90), (516, 90))
    d.seta((720, 90), (756, 90))
    d.grupo(20, 170, 960, 410, "perguntar · ./prisma.sh especialista perguntar")
    d.caixa(40, 214, 200, "Pergunta", "com ou sem --titular", "ag")
    d.caixa(280, 214, 200, "Embedding", "o mesmo modelo do índice")
    d.caixa(520, 214, 200, "Busca no Chroma", "4 trechos mais parecidos")
    d.caixa(760, 214, 200, "Filtro de nota", "PRISMA_NOTA_MINIMA")
    d.seta((240, 242), (276, 242))
    d.seta((480, 242), (516, 242))
    d.seta((720, 242), (756, 242))
    d.seta((860, 118), (860, 150), (620, 150), (620, 210))
    d.caixa(40, 340, 200, "Resumo do mês", "Armazenamento + Python", "ag")
    d.caixa(280, 340, 200, "Perfil de risco", "Agente de Risco", "ag")
    d.caixa(520, 340, 200, "Monta o prompt", "regras, dados e trechos")
    d.caixa(760, 340, 200, "GOOGLE_API_KEY?", "chave preenchida no .env")
    d.seta((860, 270), (860, 300), (620, 300), (620, 336))
    d.seta((480, 368), (516, 368))
    d.seta((140, 396), (140, 424), (580, 424), (580, 400))
    d.seta((720, 368), (756, 368))
    d.caixa(580, 480, 190, "Gemini escreve", "resposta com fontes", "ex")
    d.caixa(800, 480, 160, "Só os trechos", "com fonte e página", "ag")
    d.seta((800, 396), (800, 440), (675, 440), (675, 476))
    d.rotulo(690, 460, "sim", "start")
    d.seta((910, 396), (910, 476))
    d.rotulo(918, 444, "não", "start")
    return d.salvar()


def risco():
    d = Diagrama("agente-risco", "Agente de Risco",
                 "As transações do titular são categorizadas e seguem por dois caminhos: indicadores em Python e a rede "
                 "neural (autoencoder), que aponta compras atípicas. Os dois somam um score de 0 a 100. O modelo é "
                 "treinado uma vez com dados sintéticos e exportado para .npz.", 720)
    d.caixa(390, 30, 220, "Transações", "consultar_titular (MCP)", "ag")
    d.caixa(390, 130, 220, "Categorizar", "descrição → categoria", "nt")
    d.caixa(60, 240, 300, "Indicadores em Python", "renda, saldo, juros, fatura, reserva")
    d.caixa(480, 240, 200, "27 features", "relativas à própria pessoa", "rn")
    d.caixa(730, 240, 230, "Autoencoder", "27→32→16→6→16→32→27", "rn")
    d.caixa(730, 350, 230, "Erro de reconstrução", "acima do limiar: atípica", "rn")
    d.caixa(480, 350, 200, "Compras atípicas", "com motivos", "rn")
    d.caixa(390, 460, 220, "Score de 0 a 100", "baixo · moderado · alto", "nt")
    d.caixa(700, 460, 260, "perfil_de_risco", "MCP e Especialista", "ag")
    d.seta((500, 86), (500, 126))
    d.seta((440, 186), (440, 212), (210, 212), (210, 236))
    d.seta((560, 186), (560, 212), (580, 212), (580, 236))
    d.seta((680, 268), (726, 268))
    d.seta((845, 296), (845, 346))
    d.seta((730, 378), (684, 378))
    d.seta((580, 406), (580, 456))
    d.rotulo(588, 436, "10 pontos", "start")
    d.seta((210, 296), (210, 488), (386, 488))
    d.rotulo(220, 400, "90 pontos", "start")
    d.seta((610, 488), (696, 488))
    d.grupo(20, 545, 940, 115, "treino, uma vez · ./prisma.sh risco treinar")
    d.caixa(40, 585, 200, "Gerador sintético", "NeuralNetwork/src", "rn")
    d.caixa(280, 585, 200, "Features sem hora", "o extrato só tem a data", "rn")
    d.caixa(520, 585, 200, "Treino", "PyTorch ou scikit-learn", "rn")
    d.caixa(760, 585, 180, "autoencoder.npz", "~/.prisma/modelos", "dd")
    d.seta((240, 613), (276, 613))
    d.seta((480, 613), (516, 613))
    d.seta((720, 613), (756, 613))
    d.seta((940, 613), (980, 613), (980, 268), (964, 268))
    return d.salvar()


def embeddings():
    d = Diagrama("modos-embeddings", "Modos de embeddings",
                 "Com PRISMA_EMBEDDINGS=local, os vetores são calculados na máquina por um modelo multilíngue; com "
                 "gemini, pela API do Google. Cada modo tem o próprio índice. Escrever a resposta depende só da "
                 "GOOGLE_API_KEY.", 590)
    d.caixa(370, 30, 260, "Texto", "pedaço da base ou pergunta")
    d.caixa(110, 140, 280, "PRISMA_EMBEDDINGS=local")
    d.caixa(610, 140, 280, "PRISMA_EMBEDDINGS=gemini")
    d.caixa(110, 240, 280, "Modelo local (fastembed)", "MiniLM multilíngue · 384 números")
    d.caixa(610, 240, 280, "API do Gemini", "gemini-embedding-001 · 3.072", "ex")
    d.caixa(110, 340, 280, "Chroma", "~/.prisma/rag/local", "dd")
    d.caixa(610, 340, 280, "Chroma", "~/.prisma/rag/gemini", "dd")
    d.seta((440, 86), (440, 112), (250, 112), (250, 136))
    d.seta((560, 86), (560, 112), (750, 112), (750, 136))
    d.seta((250, 196), (250, 236))
    d.seta((750, 196), (750, 236))
    d.seta((250, 296), (250, 336))
    d.seta((750, 296), (750, 336))
    d.grupo(300, 425, 400, 112, "independente do modo")
    d.caixa(320, 458, 360, "Escrever a resposta", "Gemini só com GOOGLE_API_KEY", "ex", h=56)
    return d.salvar()


if __name__ == "__main__":
    for f in (armazenamento, coletor, especialista, risco, embeddings):
        print("gerado:", f())
