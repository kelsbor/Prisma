Os nomes de categoria e banco abaixo são exemplos: use sempre o nome EXATO que aparece em CATEGORIAS EXISTENTES ou BANCOS. Se não houver nenhum parecido na lista, a consulta vai voltar vazia; nesse caso prefira buscar pela descrição com LIKE.

- "cartão", "no crédito", "fatura" → tipo_conta = 'cartao' (exceto "pagar a fatura", que é a transferência '05100000' na conta)
- "conta", "no débito", "pix", "na conta corrente" → tipo_conta = 'conta'
- "Nubank", "Nu" → o banco da lista BANCOS que corresponde ao Nubank (normalmente contém 'Nu Pagamentos'); para outros bancos, compare com a lista BANCOS usando LIKE
- "comida", "alimentação" → a categoria-mãe de alimentação em grupo_categoria (normalmente 'Alimentos e bebidas')
- "mercado" → a categoria de supermercado da lista (normalmente 'Supermercado')
- "salário" → a categoria de salário da lista (normalmente 'Salário')
- "estorno", "reembolso", "devolução" → tipo = 'estorno'
- "pendente", "a confirmar" → pendente = 1
- "parcelado", "parcelas" → total_parcelas IS NOT NULL
- "maiores gastos" → ORDER BY valor_gasto DESC
