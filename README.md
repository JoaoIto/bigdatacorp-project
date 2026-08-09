# ⚽ Processador Batch — Clubes de Futebol (BigDataCorp)

Processador de dados em lote que transforma um arquivo JSONL de clubes de futebol em arquivos CSV relacionais, com **streaming O(1)**, **tolerância a falhas** e **compliance RFC 4180**.

---

## Visão Geral

O programa lê um arquivo JSONL onde cada linha é um objeto JSON representando um clube de futebol com seus jogadores, e gera dois arquivos CSV:

| Arquivo         | Relação | Descrição                            |
|-----------------|---------|--------------------------------------|
| `clubs.csv`     | 1:1     | Um registro por clube                |
| `players.csv`   | 1:N     | Um registro por jogador de cada clube|

## Pré-requisitos

- **Python 3.8+** (sem dependências externas — usa somente a biblioteca padrão)

## Como Executar

```bash
# Uso básico (CSVs gerados no mesmo diretório do arquivo de entrada)
python src/main.py <caminho_arquivo_entrada.jsonl>

# Com diretório de saída explícito
python src/main.py <caminho_arquivo_entrada.jsonl> <diretório_saída>
```

### Exemplo com o arquivo de amostra

```bash
# A partir do diretório /project
python src/main.py data/input/sample_clubes.jsonl data/output
```

## Estrutura do Projeto

```
project/
├── src/                          # Código-fonte
│   ├── main.py                   # Ponto de entrada CLI + orquestrador
│   ├── reader.py                 # Leitor JSONL em streaming (generator)
│   └── writer.py                 # Escritor CSV (RFC 4180)
├── tests/                        # Testes
│   └── dirty_data.jsonl          # Fixture: dados malformados para teste
├── data/
│   ├── input/                    # Arquivos JSONL de entrada
│   │   └── sample_clubes.jsonl   # Amostra fornecida no desafio
│   └── output/                   # CSVs gerados pelo programa
├── .gitignore
└── README.md                     # Este arquivo
```

## Arquitetura

O sistema segue o padrão **Pipes & Filters** com **Generators** do Python para streaming:

```
JSONL  ──▶  Reader (yield)  ──▶  Transformer  ──▶  Writer (csv)
 O(1)          O(1)                O(1)              O(1)
```

- **Reader** (`reader.py`): Generator que lê o JSONL linha a linha com `json.loads()`. Três níveis de defesa contra dados sujos (linhas vazias, JSON malformado, tipo inesperado).
- **Writer** (`writer.py`): Wrapper sobre `csv.writer` com compliance RFC 4180 nativa (escape de vírgulas, aspas, quebras de linha).
- **Main** (`main.py`): Orquestrador que compõe o pipeline, gerencia ciclo de vida de arquivos e emite relatório final com contadores.

### Decisões Técnicas

| Decisão                        | Escolha                        | Motivo                                    |
|--------------------------------|--------------------------------|-------------------------------------------|
| Dependências                   | Somente stdlib                 | Zero setup, portabilidade máxima          |
| Memória                        | Streaming O(1) via generators  | Suporta milhões de registros              |
| CSV                            | `csv.writer` (C-bindings)      | RFC 4180 nativo, performático             |
| Tolerância a falhas            | `try/except` por registro      | Registros ruins são ignorados, pipeline segue |
| Logging                        | `logging` nativo               | Níveis INFO/WARNING/ERROR sem `print()`   |

> Para documentação detalhada de arquitetura e decisões, consulte o repositório de especificações em `/spec`.

## Regras de Negócio

- **Filtro por campeonato:** Somente clubes da Série A ou Série B
- **Cores:** Lista unida por `|` (pipe). Ex: `["preto","branco"]` → `preto|branco`
- **Datas:** Formato `yyyy-MM-dd`. Data inválida → campo vazio
- **Campos nulos/ausentes:** Viram campo vazio no CSV
- **Robustez:** Registros malformados são ignorados com log — programa nunca aborta

## Saída Esperada (Amostra)

Ao processar `sample_clubes.jsonl`:

- `clubs.csv`: **5 clubes** (SCCP, SEP, SFC, CRU, AVA)
- `players.csv`: **8 jogadores** (3 + 2 + 2 + 1)
- NAC filtrado (campeonato `SEM CAMPEONATO`)
- AVA sem jogadores → aparece em `clubs.csv`, nenhuma linha em `players.csv`
