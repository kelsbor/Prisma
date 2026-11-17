Banco SQLite. Você só pode consultar a view `vw_registers`: uma linha por transação do usuário.

| coluna | tipo | significado |
|---|---|---|
| transacao_id | texto | identificador da transação |
| data | texto 'YYYY-MM-DD' | dia da transação (fuso de Brasília) |
| ano | inteiro | ano da data (ex.: 2026) |
| mes | inteiro | mês da data, 1 a 12 |
| descricao | texto | descrição como veio do banco (ex.: "IFOOD *RESTAURANTE") |
| estabelecimento | texto ou NULL | nome do estabelecimento, quando o banco informa |
| valor_centavos | inteiro | valor exato em centavos; saída de dinheiro é negativa |
| valor | real | o mesmo valor em reais; saída negativa, entrada positiva |
| categoria_id | texto ou NULL | código da categoria (8 dígitos) |
| categoria | texto | nome da categoria em português (a escolhida pelo usuário, senão a do banco); 'Sem categoria' quando não há |
| categoria_manual | 0/1 | 1 se o usuário trocou a categoria manualmente |
| grupo_categoria | texto ou NULL | categoria "mãe" (ex.: 'Alimentos e bebidas' agrupa 'Restaurantes', 'Delivery de alimentos'…) |
| tipo | texto | 'gasto', 'entrada', 'estorno', 'transferencia' ou 'neutro' |
| valor_gasto | real (reais) | quanto a linha soma no total de GASTOS: positivo para gasto, negativo para estorno, 0 nos demais |
| valor_entrada | real (reais) | quanto a linha soma no total de ENTRADAS (dinheiro recebido na conta); 0 nos demais |
| conta | texto | nome da conta ou do cartão |
| tipo_conta | texto | 'conta' (conta bancária) ou 'cartao' (cartão de crédito) |
| banco | texto | nome do banco/instituição |
| pendente | 0/1 | 1 se a transação ainda não foi confirmada |
| parcela | inteiro ou NULL | número da parcela (compras parceladas no cartão) |
| total_parcelas | inteiro ou NULL | total de parcelas |

NÃO existem neste banco: saldo das contas, limite do cartão, valor da fatura atual, investimentos, metas, orçamento, dados de outras pessoas.
