# Finanças pessoais com redes neurais

Projeto didático de geração de transações financeiras sintéticas, previsão de gastos por categoria e detecção de anomalias.

## Estrutura

```text
src/                         Código Python (fonte única)
notebooks/                   Notebook de execução no Google Colab
tools/build_colab_zip.py     Empacota só o código necessário para o Colab
docs/RELATORIO_TECNICO.md    Relatório detalhado dos dados, features e resultados
data/generated/              Dados gerados ao executar os scripts (ignorado pelo Git)
data/local/                  Bases antigas preservadas localmente (ignorado pelo Git)
artifacts/models/             Checkpoints dos modelos (ignorado pelo Git)
results/                     Banco e artefatos do MLflow (ignorado pelo Git)
```

O código não depende de cópias em outras pastas. Dados, modelos, bancos de resultados e o ZIP de distribuição não são incluídos no commit.

## Executar localmente

Crie um ambiente virtual e instale as dependências:

```bash
python -m venv .venv
source .venv/bin/activate              # Linux/macOS
# .venv\Scripts\Activate.ps1           # Windows PowerShell
pip install -r requirements.txt
pip install torch --index-url https://download.pytorch.org/whl/cpu
```

O PyTorch é opcional para geração, calibração e baselines. Os modelos são pequenos; CPU basta.

```bash
python src/rodar_tudo.py --rapido --pular-torch
python src/rodar_tudo.py --mlflow
python src/rodar_tudo.py --mlflow --seeds 0 1 2
python src/rodar_tudo.py --so gerar calibrar
```

`--rapido` gera 200 usuários e limita as épocas para um teste de fumaça. A execução normal gera 1.000 usuários. Os dados ficam em `data/generated/`, os modelos em `artifacts/models/` e os resultados do MLflow em `results/`. Para mudar o local dos dados, use `--dados CAMINHO`.

Também é possível executar os scripts individualmente. Por exemplo:

```bash
python src/gerar_dados_sinteticos.py --n-users 200 --out data/generated
python src/treinar_mlp.py data/generated/transactions.csv
python src/treinar_autoencoder.py data/generated/transactions.csv --contaminado
```

As etapas de validação automática, propensão e classificação não estão incluídas: os scripts mencionados em versões anteriores da documentação não fazem parte deste projeto. `rodar_tudo.py` lista apenas etapas executáveis presentes na pasta.

## Executar no Google Colab usando o ZIP

1. Na raiz do projeto, gere o pacote:

   ```bash
   python tools/build_colab_zip.py
   ```

   Isso cria `projeto.zip`, contendo `src/`, `requirements.txt` e `README.md`. Bases, modelos, ambientes virtuais, bancos e resultados locais ficam de fora.

2. Abra `notebooks/executar_no_colab.ipynb` no Google Colab.
3. Execute as células em ordem e, quando solicitado, selecione o `projeto.zip` gerado.
4. O notebook instala as dependências, executa o cenário rápido e mostra as métricas registradas no MLflow.
5. Para executar o experimento completo, use a célula opcional do notebook. Ela gera 1.000 usuários e treina com três seeds.
6. Ao final, baixe o ZIP de resultados antes de encerrar o runtime; o disco da sessão do Colab é temporário.

Não é necessário montar o Google Drive nem mover os arquivos para um caminho específico. O ZIP pode ser enviado do computador diretamente no formulário de upload do Colab.

## MLflow e reprodutibilidade

Com `--mlflow`, o banco local fica em `results/mlflow.db` e os artefatos em `results/mlartifacts/`. Os runs registram parâmetros, métricas, versões das bibliotecas e hash do arquivo CSV usado. A interface local pode ser aberta com:

```bash
mlflow ui --backend-store-uri sqlite:///results/mlflow.db
```

Use o hash dos dados e a seed para identificar execuções comparáveis. Os resultados antigos em `results/local/` e os dados legados em `data/local/` são apenas referências locais; eles não fazem parte do conjunto versionado nem do ZIP do Colab.

## Dependências

As dependências Python estão em `requirements.txt`. Ele não instala o PyTorch, pois o comando adequado depende do ambiente e da disponibilidade de CPU/GPU.
