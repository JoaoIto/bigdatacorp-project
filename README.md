# ⚽ Processador Batch — Clubes de Futebol (BigDataCorp)

Sistema robusto de processamento em lote (batch processing) construído puramente em Python (Standard Library). Ele transforma arquivos JSONL massivos contendo clubes de futebol e jogadores em arquivos CSV relacionais (1:1 e 1:N), garantindo **complexidade espacial O(1)** e **compliance com RFC 4180**.

---

## 🚀 Como Executar

O programa requer que o caminho do arquivo JSONL de entrada seja passado via parâmetro de linha de comando.

```bash
# Execução básica (CSVs são gerados na mesma pasta do arquivo de entrada)
python src/main.py data/input/sample_clubes.jsonl

# Execução com diretório de saída explícito
python src/main.py data/input/sample_clubes.jsonl data/output
```

**Pré-requisitos:** Python 3.8+ (zero dependências externas para rodar o pipeline principal).

---

## 🧪 Engenharia de Qualidade

Para garantir a qualidade, resiliência e corretude do código, uma suite de testes foi implementada usando `pytest`. 

**Para rodar a suite completa de testes:**
```bash
# Instale o pytest
pip install pytest

# Execute a suite a partir da raiz (/project)
$env:PYTHONPATH="src"
python -m pytest tests/
```

### O que está sendo testado?
- `test_transformer.py`: Testes unitários focados em *edge cases* das funções de regras de negócio (case-insensitivity, nulos, datas malformadas).
- `test_pipeline.py`: Teste de integração end-to-end usando fixtures em memória para garantir contadores corretos e CSVs validados.
- `test_resilience.py`: **Chaos Testing** injetando payloads JSON severamente corrompidos, strings vazias, e tipos errados, para provar que o pipeline falha graciosamente (*fails gracefully*) e não lança exceções não tratadas (não aborta).

---

## 📈 Prova de Performance O(1)

A arquitetura de *Streaming* foi construída para suportar arquivos do tamanho do disco, utilizando pouquíssima memória RAM. Para provar matematicamente essa premissa:

**1. Gere um arquivo JSONL colossal (1 milhão de registros):**
```bash
python scripts/generate_mass_data.py
# Aguarde a geração do arquivo mass_data.jsonl (~260MB)
```

**2. Rode o Profiler de Memória:**
```bash
python scripts/profile_memory.py
```
O script usará a biblioteca nativa `tracemalloc` para medir o **Pico de Memória RAM** do pipeline durante o processamento de 1.000.000 de linhas. O resultado comprovará que o uso da RAM será de poucos Megabytes e constante (O(1)), independentemente do tamanho do arquivo.

---

## 🏗️ Decisões de Arquitetura

O sistema foi desenhado para atuar em ambientes hostis de dados (Big Data). Destaque para as três principais pilares:

### 1. Complexidade de Espaço O(1)
Em vez de carregar listas inteiras na memória, o `src/reader.py` é um **Generator** que aplica lazy evaluation usando `yield`. O arquivo é lido linha a linha e descartado. O uso de memória é limitado estritamente ao tamanho da maior linha do arquivo ($O(M)$), garantindo que um arquivo de 10GB consumirá a mesma memória que um de 10MB.

### 2. Resiliência a Falhas (Fail Gracefully)
Frente a dados de terceiros, a chance de encontrar anomalias é de 100%. O sistema abraça a falha implementando blocos defensivos em múltiplas camadas. Registros com estrutura JSON quebrada, nulos não mapeados ou tipos inesperados são logados como `WARNING` e descartados ou omitidos nos campos finais. **O pipeline nunca aborta no meio.**

### 3. Compliance Estrito RFC 4180
Criar CSVs manualmente via manipulação de string (`",".join()`) é frágil quando dados contêm vírgulas e aspas internas (como `Pedro Lourenço, Filho`). Por isso, usamos o módulo `csv` nativo do Python (bindings em C) configurado com `newline=''` para lidar automaticamente com double quoting, delimiter escaping e quebras de linha `CRLF` (Windows/Unix safety).

> A documentação aprofundada de requisitos, logs da Inteligência Artificial par (Auditoria) e o diário de ADRs (Architecture Decision Records) residem fora do repositório de código, na pasta `/spec`.
