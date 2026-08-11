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

## 🐳 Como Executar via Docker (Produção)

O projeto está pronto para a nuvem. O container age nativamente como uma CLI (Command-Line Interface).

**1. Construa a Imagem:**
```bash
docker build -t bigdatacorp-processor .
```

**2. Execute passando volumes:**
Como o container tem um File System isolado, é necessário mapear o volume (`-v`) onde seus dados de entrada estão e onde os arquivos de saída devem ser salvos.

```bash
# Mapeia a pasta local /data para o container e passa os parâmetros
docker run --rm -v "$(pwd)/data:/app/data" bigdatacorp-processor data/input/sample_clubes.jsonl data/output
```

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

---

## ⚡ Hyper-Otimização SRE (Escala de Terabytes)

Três técnicas avançadas foram aplicadas para eliminar gargalos ocultos em escala de produção:

### 1. Buffer Tuning (I/O)
Todas as chamadas `open()` (leitura e escrita) utilizam `buffering=262144` (256 KB). Isso reduz em **~32x** as chamadas de sistema `write()` ao kernel, eliminando a contenção de I/O em discos de rede (NFS, EFS, CIFS) onde cada syscall paga latência de rede.

### 2. GC Determinístico (Gen 0)
O GC geracional do CPython é **desativado** antes do processamento (`gc.disable()`). Em vez de deixá-lo pausar a aplicação aleatoriamente a cada 700 alocações, o pipeline força uma coleta limpa apenas da Geração 0 (objetos efêmeros recém-criados) a cada exatas **100.000 linhas processadas** via `gc.collect(generation=0)`. No bloco `finally`, o GC é religado. Isso garante latência de CPU extremamente previsível e alto throughput.

### 3. Micro-otimizações de Bytecode (Local Variable Aliasing)
Para o hot-loop que processa milhões de registros, foi implementado o aliasing de funções globais ou de instância para variáveis locais (ex: `_parse_json = json.loads`). Isso força a máquina virtual do CPython (eval loop) a usar a instrução otimizada `LOAD_FAST` ao invés da custosa `LOAD_ATTR`, removendo a sobrecarga de lookup de atributos de dicionários em cada iteração. Adicionalmente, funções de conversão de dados massivamente repetitivas utilizam `@lru_cache` para evitar recomputação contínua.

### 4. Dead Letter Queue (DLQ) — Auditoria de Dados
Linhas rejeitadas (JSON malformado, tipo inesperado) **não são mais descartadas silenciosamente**. Elas são gravadas no arquivo `dlq_errors.txt` na pasta de saída, com prefixo auditável:
```
[LINHA:4][JSON_MALFORMADO] isto nao e json
[LINHA:7][TIPO_INVALIDO:list] ["lista em vez de dict"]
```
Isso permite que a equipe de Data Quality inspecione, quantifique e reprocesse os dados corrompidos.

> A documentação aprofundada de requisitos, logs da Inteligência Artificial par (Auditoria) e o diário de ADRs (Architecture Decision Records) residem fora do repositório de código, na pasta `/spec`.
