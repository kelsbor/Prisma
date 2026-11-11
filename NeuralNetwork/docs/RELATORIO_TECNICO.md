# Relatório técnico — arquivos de treinamento das redes neurais

## Resumo executivo

O projeto implementa duas tarefas diferentes:

1. **Previsão de gastos:** uma MLP tenta prever o valor gasto em cada categoria no mês seguinte — ou projetar o fechamento do mês usando o gasto observado até certo dia.
2. **Detecção de anomalias:** um autoencoder aprende a reconstruir transações e usa o erro de reconstrução como pontuação de anomalia.

Há resultados de treinamento registrados no MLflow, mas existe uma divergência importante entre os dados disponíveis e os dados usados nesses experimentos: **os runs de treinamento registrados usaram a base de 200 usuários**, não a base de 1.000 usuários que também está na pasta. Além disso, a organização atual tem cópias duplicadas, um arquivo ZIP com a estrutura errada para o notebook e etapas documentadas que falham por scripts ausentes.

Nos resultados registrados, **a MLP não superou os melhores baselines de previsão**. Para anomalias, o **Isolation Forest teve o melhor resultado geral**; o autoencoder encontrou sinais úteis, mas não foi o melhor método nas métricas globais.

> Os resultados e as observações de execução abaixo foram apurados antes da reorganização do diretório. As bases e os runs legados foram preservados, mas movidos para pastas locais ignoradas pelo Git. As referências de resultados descrevem esses experimentos anteriores e não afirmam que o conjunto maior tenha sido usado no treino.

---

## 1. Estrutura atual do projeto

| Arquivo ou pasta | Função observada |
|---|---|
| `src/` | Fonte Python canônica: geração, features, modelos, calibração e orquestração. |
| `notebooks/executar_no_colab.ipynb` | Recebe o ZIP local diretamente pelo upload do Colab e executa o fluxo rápido ou completo. |
| `tools/build_colab_zip.py` | Cria o `projeto.zip` de distribuição a partir dos arquivos necessários. |
| `docs/RELATORIO_TECNICO.md` | Este relatório de dados, features, arquiteturas e resultados. |
| `data/local/` | Bases e arquivos legados preservados localmente e ignorados pelo Git. |
| `results/local/ml_results/mlflow.db` | Banco legado com os 30 runs finalizados usados na análise deste relatório. |
| `artifacts/models/` | Checkpoints legados preservados localmente; novos modelos também são gravados aqui. |

O diretório `data/generated/` é o destino padrão dos novos dados; `results/` recebe os runs do MLflow. Esses resultados locais, os dados, checkpoints e `projeto.zip` são ignorados pelo Git. O ZIP pode ser recriado a qualquer momento com `python tools/build_colab_zip.py`; ele contém somente código, dependências e README, sem dados, modelos, bancos ou ambiente virtual.

No momento dos experimentos legados, o banco `ml_results/mlflow.db` tinha **30 runs finalizados**. Os arquivos de log preservados com a base pequena registram etapas que falharam por scripts ausentes, não validações bem-sucedidas.

### Divergências entre as duas bases

Há duas bases de transações distintas:

- `data/local/legacy-smoke-200/transactions.csv`: **200 usuários**, 247.134 transações, 13 colunas; `personas.csv` tem 24 campos.
- `data/local/legacy-full-1000/transactions.csv`: **1.000 usuários**, 1.230.667 transações, 12 colunas; `personas.csv` tem 15 campos.

A base da raiz não tem a coluna `balance` e contém quatro tipos de anomalia observados; a base de 200 usuários tem `balance` e inclui os cinco tipos previstos pelo gerador atual. Isso sugere que a base de 1.000 usuários foi produzida por uma versão anterior do gerador ou por uma configuração diferente. Portanto, **não se deve tratar essas bases como intercambiáveis**.

A documentação e o orquestrador antigos mencionavam `validar_dados.py`, `experimento_propensao.py` e `experimento_classificacao.py`, mas esses arquivos não estão presentes. A lista de etapas do orquestrador foi ajustada para incluir somente as etapas executáveis disponíveis; não há resultados de validação automática, propensão ou classificação a relatar.

---

## 2. Como os dados sintéticos são gerados

O gerador cria uma população artificial de pessoas e, para cada uma, produz aproximadamente três anos de movimentações. A configuração usual usa o período de **1º de janeiro de 2023 a 31 de dezembro de 2025**. Com uma seed fixa — `42` por padrão — a geração pode ser repetida de forma determinística.

### 2.1 Personas

Cada persona recebe atributos como perfil de renda, renda mensal, dia de pagamento, cidade, moradia, carro, assinaturas, despesas fixas, propensão latente a gastar e saldo inicial.

Os quatro perfis têm probabilidades diferentes: CLT, autônomo, servidor público e estudante. A renda é amostrada de distribuições lognormais específicas por perfil e limitada a faixas mínimas e máximas. Outras características — como possuir carro, morar de aluguel ou investir — também são sorteadas com probabilidades próprias.

Esses atributos controlam a geração das transações. Por exemplo, possuir carro habilita despesas com combustível; a renda influencia os valores de gastos; e o perfil autônomo gera renda irregular em vez de um pagamento salarial regular.

### 2.2 Transações normais

O gerador combina várias fontes de movimento:

- **Despesas fixas mensais:** aluguel ou financiamento, contas, telecomunicações, assinaturas, saúde e educação.
- **Despesas variáveis:** eventos gerados por taxas Poisson e valores lognormais. A frequência e os valores variam conforme categoria, renda, dia da semana, proximidade do pagamento, sazonalidade e outras características da persona.
- **Renda:** salário, mesada ou recebimentos irregulares de autônomos, conforme o perfil.
- **Créditos que não são renda:** Pix recebidos e estornos.
- **Investimentos e impostos:** gerados com datas e condições específicas.
- **Saldo:** na versão atual, calculado cumulativamente a partir do saldo inicial e do valor assinado das transações.

Os valores seguem uma convenção importante: **débitos são negativos e créditos positivos**. A coluna `type` indica se a transação é `debit` ou `credit`. Algumas etapas posteriores convertem as despesas em valores positivos para calcular gastos.

A geração de despesas variáveis inclui sazonalidade mensal e padrões por dia da semana. O orçamento da persona também influencia a escala final dos gastos variáveis e, quando necessário, dos investimentos. Por isso, os dados não são simples amostras independentes: a rotina de cada usuário condiciona as transações que aparecem em seu histórico.

### 2.3 Anomalias injetadas

O código prevê cinco tipos de anomalia:

1. **Compra atípica:** compra grande em relação à renda.
2. **Cobrança duplicada:** mesmo estabelecimento e valor em intervalo curto.
3. **Fraude:** uma ou mais compras na madrugada, em sequência.
4. **Conta inflada:** conta de consumo com valor multiplicado em comparação com uma conta normal.
5. **Gasto acima do padrão:** compra acima do percentil 95 daquele usuário e categoria.

O rótulo `is_anomaly` é usado para avaliar os métodos. Em alguns modos de treinamento, também determina quais linhas podem entrar no conjunto de treino. As anomalias são artificiais e seguem regras específicas; portanto, bons resultados nessa base **não comprovam desempenho equivalente contra fraudes reais**.

Na base de 200 usuários usada pelos runs do MLflow, foram registrados os cinco tipos. Na base de 1.000 usuários da raiz, a contagem observada não inclui `gasto_acima_do_padrao`, outra indicação de diferença entre versões dos dados.

---

## 3. Features da previsão de gastos

A previsão trabalha com um exemplo por **usuário e mês-alvo**. O histórico é achatado em um vetor: a MLP não é uma rede recorrente; o contexto temporal é construído manualmente no pipeline.

### 3.1 Agregação

`pipeline_features.py` soma os débitos por usuário, mês e categoria, transformando a tabela de transações em uma estrutura equivalente a:

```text
gastos[usuário, mês, categoria]
```

A renda é calculada separadamente usando a categoria `Renda`. A lógica exclui estornos e Pix recebidos da definição de renda.

Por padrão, a etapa de previsão remove as transações rotuladas como anomalias. Isso produz uma avaliação de previsão em dados “limpos”, mas é uma premissa disponível no sintético: em dados reais, normalmente não se conhece antecipadamente o rótulo de uma transação.

### 3.2 Vetor de entrada

Para cada mês-alvo, o pipeline usa os seis meses anteriores (`L = 6`). A renda média da janela serve como escala de normalização. A base usada nos runs registrados tinha **16 categorias de gasto**.

Para a previsão do próximo mês, as 115 features são:

| Grupo de features | Quantidade | Como é calculado |
|---|---:|---|
| Gastos históricos por categoria | 96 | 6 meses × 16 categorias, divididos pela renda média da janela. |
| Renda dos seis meses | 6 | Renda mensal dividida pela renda média da janela. |
| Escala de renda | 1 | Logaritmo da renda média da janela. |
| Mês-alvo | 12 | Codificação one-hot do mês, para representar sazonalidade anual. |
| **Total** | **115** | |

No modo de projeção parcial, entram mais 32 valores:

- gasto já observado no mês corrente até o dia definido, por categoria;
- média histórica do gasto até esse mesmo dia, por categoria.

Assim, o vetor passa a ter **147 features**.

O alvo `y` contém os gastos do mês previsto nas 16 categorias, também divididos pela renda média. Na saída, o pipeline desfaz a padronização, impede valores negativos e reconverte a previsão para reais.

### 3.3 Divisão temporal e padronização

O conjunto é dividido cronologicamente, não por sorteio aleatório. Na base de 36 meses, as janelas de treino, validação e teste correspondem a:

- treino: 18 meses de alvos, de julho de 2023 a dezembro de 2024;
- validação: janeiro a junho de 2025;
- teste: julho a dezembro de 2025.

Com 200 usuários, os runs registram 3.600 exemplos de treino, 1.200 de validação e 1.200 de teste. A média e o desvio-padrão usados na padronização são calculados somente no treino, o que evita usar estatísticas do futuro no pré-processamento.

Esse split mede previsão futura **para usuários já conhecidos no histórico**. Não mede generalização para novos usuários, pois os mesmos usuários aparecem em períodos diferentes.

---

## 4. Features da detecção de anomalias

A tarefa de anomalia trata cada transação de débito como uma observação. O pipeline exclui a categoria `Investimentos` e extrai features relativas ao histórico de cada usuário. Isso é importante: um valor pode ser normal para uma pessoa e atípico para outra.

As features incluem:

- **Valor relativo:** logaritmo do valor absoluto e z-score robusto por usuário/categoria, calculado com mediana e intervalo interquartil. Se há menos de cinco exemplos do usuário naquela categoria, usa-se uma referência da categoria.
- **Relação com renda:** logaritmo da proporção entre valor da transação e renda estimada.
- **Calendário:** dia da semana em seno/cosseno, dia do mês escalado e, quando disponível, hora em seno/cosseno.
- **Familiaridade do estabelecimento:** quantidade de ocorrências anteriores para aquele usuário e indicador de estabelecimento novo. A contagem exclui a própria transação quando apropriado.
- **Intervalo e rajadas:** tempo desde a transação anterior do usuário e número de transações próximas no tempo.
- **Duplicidade e variação:** score para repetição do mesmo usuário, estabelecimento e valor; diferença do logaritmo do valor em relação à compra anterior no mesmo estabelecimento.
- **Categoria:** one-hot das categorias observadas no treino.

Com horário, são **29 features**; sem horário, **27**. Depois, as features são padronizadas com estatísticas do treino e limitadas a uma faixa para reduzir o efeito de valores extremos.

O split dessa tarefa é diferente do de previsão:

- treino: antes de 1º de julho de 2024;
- validação: de 1º de julho a 31 de dezembro de 2024;
- teste: todo o ano de 2025.

Os runs contaminados com hora registram 111.446 exemplos de treino, 37.589 de validação e 73.986 de teste. A taxa de anomalia do teste é aproximadamente 0,98%.

---

## 5. Estrutura e treinamento das redes

### 5.1 MLP de previsão

A MLP é uma rede feedforward de regressão:

```text
115 ou 147 entradas
→ Linear(64) → ReLU → Dropout(0,1)
→ Linear(32) → ReLU → Dropout(0,1)
→ Linear(16)
```

A saída tem uma unidade para cada categoria; não há ativação final, pois a rede prevê números contínuos. A arquitetura tem **10.032 parâmetros** na previsão do próximo mês e **12.080** na projeção parcial.

Configurações padrão: AdamW, taxa de aprendizado `0,001`, weight decay `0,001`, lote de 256 e até 200 épocas. A execução de treino calcula a perda, faz backpropagation e atualiza os pesos. A validação não atualiza os pesos: ela determina o melhor checkpoint e controla o *early stopping*, com paciência de 15 épocas.

Nos runs registrados, a previsão mensal usa MSE e a projeção do dia 15 usa L1. MSE penaliza mais fortemente erros grandes; L1 é menos sensível a esses erros e se relaciona mais diretamente ao erro absoluto usado em WAPE.

### 5.2 Autoencoder de anomalias

Com horário, o autoencoder recebe 29 valores e usa a arquitetura:

```text
29 → 32 → 16 → 6 → 16 → 32 → 29
```

O vetor de 6 valores é o **gargalo**: a rede precisa comprimir a transação e reconstruí-la. As camadas escondidas usam ReLU; a saída é linear, pois reconstrói features padronizadas. A versão sem horário tem 27 entradas e saídas.

O alvo é o próprio vetor de entrada. O treino minimiza o MSE entre a transação original e sua reconstrução, com Adam, taxa de aprendizado `0,001`, weight decay `1e-5`, lote de 1.024 e até 60 épocas. O código também tem uma variante *denoising*: adiciona ruído gaussiano à entrada e pede que a rede reconstrua o vetor original.

Depois, o erro médio quadrático de reconstrução por transação vira um score: quanto maior, mais suspeita a transação. O modelo não classifica diretamente “fraude” ou “normal”. O gargalo pode ajudar a impedir a simples cópia da entrada, mas a escolha de arquitetura e a mistura de anomalias no treino influenciam quais padrões a rede aprende a reconstruir.

### 5.3 Baselines

O pipeline compara a MLP com métodos mais simples:

- último mês;
- média dos últimos três meses;
- média dos últimos seis meses;
- mesmo mês do ano anterior, com fallback para média histórica quando não há um ano de histórico;
- projeção parcial baseada no gasto já realizado e na média histórica do restante;
- regressão Ridge com as mesmas features da MLP.

Para anomalias, os comparadores incluem z-score do valor, Isolation Forest, PCA com erro de reconstrução e um autoencoder MLP do scikit-learn.

---

## 6. Testes e resultados observados

### 6.1 O que está sendo testado

Há três tipos de avaliação:

1. **Teste temporal de previsão:** WAPE no período de teste, no geral e por categoria, comparado aos baselines.
2. **Teste temporal de anomalias:** ROC-AUC, PR-AUC, Recall@1% e AUC por tipo de anomalia.
3. **Calibração descritiva:** comparação de agregados do sintético com números da POF/IBGE.

O README também anuncia 30 testes automáticos de integridade do dataset e experimentos de propensão/classificação. Porém, os scripts correspondentes não estão disponíveis na pasta. Os logs existentes confirmam que essas etapas falharam por arquivo inexistente. Logo, não há resultados válidos dessas validações ou experimentos a relatar.

O notebook do Colab está sem outputs e sem células executadas. Já o banco legado `results/local/ml_results/mlflow.db` contém 30 runs finalizados, mas esses resultados não demonstram que todas as etapas do orquestrador foram concluídas.

### 6.2 Qual base foi realmente usada

Os runs de modelos apontam para a base legada de **200 usuários**, preservada em `data/local/legacy-smoke-200/transactions.csv`; o hash registrado no MLflow corresponde a esse arquivo. Isso também é consistente com os 3.600 exemplos de treino da MLP.

Há um run chamado `dados-n1000-s42`, mas ele aponta para a mesma base de 200 usuários. O resultado registrado não comprova treinamento com a base de 1.000 usuários. A base de 1.000 usuários, agora preservada em `data/local/legacy-full-1000/`, tem hash diferente e não aparece como base dos runs de modelos.

### 6.3 Previsão: WAPE

WAPE é a soma dos erros absolutos dividida pela soma dos gastos reais; menor é melhor.

| Tarefa | MLP: média de 3 seeds | Melhor baseline observado | Interpretação |
|---|---:|---:|---|
| Mês seguinte | **0,4396 ± 0,0041** | Ridge: 0,3954; média de 6 meses: 0,3959 | A MLP teve WAPE cerca de 11% maior que o Ridge. |
| Projeção até o dia 15 | **0,2989 ± 0,0128** | Parcial + restante: 0,2603; Ridge: 0,2641 | A MLP teve WAPE cerca de 15% maior que a projeção parcial. |

Os resultados são relativamente estáveis entre seeds, então a diferença não parece ser apenas uma seed particularmente ruim. A rede aprendeu algum padrão, mas, neste conjunto, não justificou sua complexidade frente aos métodos mais simples.

Os erros variam por categoria. Gastos recorrentes, como telecomunicações e contas, tendem a ser mais previsíveis. Categorias variáveis ou esparsas, como viagens, lazer e compras, são mais difíceis. No teste de uma seed, a MLP mensal teve WAPE de 1,611 em viagens; esse valor pode superar 1 quando o erro absoluto total excede o gasto real total da categoria.

### 6.4 Anomalias: comparação global

| Método ou variante | ROC-AUC | PR-AUC | Recall@1% |
|---|---:|---:|---:|
| Isolation Forest, contaminado com hora | **0,9365** | **0,4450** | 0,4234 |
| Autoencoder MLP scikit-learn | 0,8894 | 0,4334 | **0,4331** |
| Autoencoder PyTorch, com hora — média de 3 seeds | 0,8815 ± 0,0032 | 0,4227 ± 0,0083 | 0,3949 ± 0,0151 |
| Autoencoder PyTorch, sem hora — média de 3 seeds | 0,8825 ± 0,0142 | 0,3789 ± 0,0239 | 0,3825 ± 0,0231 |
| Autoencoder PyTorch, com ruído — média de 3 seeds | 0,8860 ± 0,0056 | 0,4126 ± 0,0183 | 0,4000 ± 0,0326 |
| PCA, contaminado com hora | 0,8623 | 0,1649 | 0,1462 |
| Z-score do valor, contaminado com hora | 0,8273 | 0,1240 | 0,2083 |

Como a prevalência de anomalias no teste é 0,98%, um classificador aleatório teria PR-AUC próxima dessa prevalência. O PR-AUC do autoencoder PyTorch com hora — cerca de 0,423 — é muito superior a esse ponto de referência sintético. Ainda assim, o Isolation Forest obteve ROC-AUC e PR-AUC maiores.

O horário melhora principalmente a PR-AUC do autoencoder em relação à variante sem hora. O ruído de *denoising* não mostrou melhora consistente na média dos três seeds. Isso sugere que a variante pode ajudar em algumas seeds ou tipos de anomalia, mas não há evidência suficiente para considerá-la superior.

Por tipo de anomalia, o autoencoder identificou cobranças duplicadas com AUC próxima de 1,0 e fraudes com AUC média próxima de 0,987. Foi mais fraco para gastos acima do padrão, com AUC média de cerca de 0,589. Esse tipo parece especialmente difícil para o autoencoder, embora o z-score do valor seja muito forte nesse caso. Ou seja, diferentes detectores capturam diferentes formas de desvio.

**Atenção à métrica Recall@1%:** o código calcula essa métrica escolhendo o percentil de 99% dos scores no próprio teste. Ela responde “quantas anomalias aparecem entre o 1% de maiores scores?” e não mede a aplicação de um limiar fixo obtido na validação. Separadamente, o treinador seleciona um limiar no percentil de 99% da validação; nos runs com hora, a precisão média nesse limiar foi aproximadamente 34,5% e o recall, 41,3%. Isso indica que a maioria dos alertas ainda seria falso positivo nessa configuração.

### 6.5 Calibração da base de 1.000 usuários

O relatório de calibração disponível em `src/relatorio_calibracao.py` foi executado sobre a base legada de 1.000 usuários. Os principais resultados foram:

- Composição do consumo: habitação 32,7% contra 36,6% da POF; alimentação 18,8% contra 17,5%; transporte 14,5% contra 18,1%; saúde 8,2% contra 8,0%; educação 4,0% contra 4,7%.
- Alimentação fora de casa: 32,6% contra 33,9%.
- Despesa/renda mensal: mediana 0,96, com percentis 10 e 90 de 0,46 e 1,86; a referência POF usada é uma razão média agregada de 0,86.

Os valores são próximos em alguns grupos, mas não devem ser interpretados como validação estatística: a POF mede famílias em outro período, enquanto o gerador cria personas individuais. Além disso, comparar a mediana sintética com uma média agregada não é uma comparação perfeitamente equivalente.

---

## 7. Interpretação final e prioridades para organização

Os resultados sustentam que o pipeline funciona como **protótipo experimental**: gera dados, extrai features, treina redes e compara métricas com baselines. Eles também indicam duas conclusões práticas:

- Para previsão, os baselines simples superaram a MLP na base avaliada; vale aumentar e reconciliar os dados antes de investir em arquiteturas mais complexas.
- Para anomalias, há sinal útil, mas o Isolation Forest foi mais forte globalmente. A avaliação é sintética e não permite afirmar desempenho equivalente em fraude bancária real.

Antes de interpretar os resultados como avaliação da base de 1.000 usuários, é necessário corrigir a linhagem dos dados: runs registrados com o mesmo hash usam a base de 200 usuários, apesar de existir um run denominado `n1000`. Também é necessário reconciliar os esquemas e versões das duas bases.

A reorganização mantém **uma única cópia canônica do código**, separa documentação, notebook, dados e resultados, e facilita refazer o ZIP sem incluir artefatos locais:

```text
src/                         código Python
notebooks/                   notebook do Colab
tools/build_colab_zip.py     construtor do pacote de upload
docs/                        documentação técnica
data/generated/              novos dados sintéticos
data/local/                  dados locais legados
artifacts/models/             checkpoints locais
results/                     banco e artefatos do MLflow
```

O notebook agora recebe o ZIP pelo upload do próprio Colab, valida sua estrutura e executa o código em `src/`. O pacote inclui apenas os scripts existentes e suas dependências de Python. O número de usuários e o hash dos dados devem continuar sendo conferidos em cada novo experimento.

**Conclusão:** há experimentos úteis e métricas comparáveis no MLflow, mas o resultado atual mais confiável é sobre a base sintética de 200 usuários. A base de 1.000 usuários foi calibrada separadamente, não treinada nos runs registrados, e apresenta esquema e rótulos diferentes. Portanto, os resultados da MLP e do autoencoder devem ser considerados preliminares, não como validação final das redes sobre o conjunto maior.
