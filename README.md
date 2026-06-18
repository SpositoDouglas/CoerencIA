# CoerencIA

**Avaliação Automatizada de Trabalhos Acadêmicos com NLP — Análise de Coerência entre Seções**

O sistema detecta automaticamente desalinhamentos semânticos entre seções de TCCs e artigos científicos (Introdução, Problema, Objetivos, Metodologia, Resultados e Conclusão), calculando um **Índice Global de Coerência (IGC)** via embeddings SBERT e gerando sugestões de melhoria.

---

## Como funciona

O CoerencIA oferece dois modos de entrada, e a análise qualitativa por IA é opcional em ambos:

**Preenchimento manual** — você cola o texto de cada seção em um wizard passo a passo.

**Upload de documento (PDF/DOCX)** — o sistema executa um fluxo automático de compreensão do documento antes da análise:

1. Extrai o texto do arquivo
2. Separa e identifica os **metadados da primeira página** (título e autores)
3. Detecta títulos, subtítulos e blocos de texto, preservando os títulos originais
4. Identifica a Introdução e a **analisa prioritariamente**, extraindo possíveis trechos de problema, objetivos, lacuna, justificativa, proposta e demais elementos
5. Usa esses elementos como contexto para classificar as demais seções (incluindo o **Referencial Teórico**)
6. Apresenta todo o mapeamento — metadados, elementos da Introdução e seções — para **revisão e correção do usuário**
7. Somente após a confirmação, calcula as similaridades e o IGC

Em seguida, o motor gera embeddings com **Sentence-BERT**, calcula a similaridade semântica entre os pares estratégicos (ex.: Objetivos ↔ Resultados) e apresenta o IGC, a matriz de similaridade com classificação (Forte / Moderado / Fraco) e alertas para os trechos mais desalinhados.

Opcionalmente, você pode ativar a **análise qualitativa com Gemini**, que gera um diagnóstico interpretativo em linguagem natural. O fluxo nunca depende da IA: sem chave configurada ou em caso de falha da API, a extração de metadados, a análise da Introdução e a classificação das seções continuam funcionando por **regras locais**, e o usuário pode corrigir tudo manualmente.

---

## Metadados, elementos da Introdução e Referencial Teórico

- **Metadados (título e autores):** extraídos da primeira página e exibidos no topo das telas de revisão e de resultados. Não são tratados como seções acadêmicas, não geram embeddings e não influenciam o IGC. A correção manual do usuário tem prioridade sobre a extração automática.
- **Elementos da Introdução:** quando o problema ou os objetivos não existem como seções próprias, mas são identificados e confirmados dentro da Introdução, os trechos correspondentes passam a ser usados nos pares estratégicos aplicáveis, sem serem contabilizados em duplicidade. Se nem a seção própria nem um trecho confiável forem encontrados, o elemento é considerado ausente e os pares dependentes aparecem como **“não avaliados por informação insuficiente”** (nunca recebem similaridade zero).
- **Referencial Teórico:** reconhecido a partir de títulos equivalentes (Fundamentação Teórica, Revisão de Literatura, Estado da Arte, Trabalhos Relacionados, Background, Literature Review, entre outros). É exibido e usado como contexto da análise e do relatório, mas **não altera a fórmula do IGC nem adiciona novos pares estratégicos**. Subseções teóricas têm seus títulos originais preservados e podem ser classificadas individualmente ou agrupadas.

O relatório final indica quando um problema ou objetivo veio de uma seção própria e quando foi identificado dentro da Introdução por análise automática.

---

## Pré-requisitos

- Python 3.11 ou superior
- Conexão com internet apenas na **primeira execução** (para baixar o modelo SBERT, ~120 MB)
- Chave da API do Google Gemini *(opcional — somente para a análise qualitativa)*

---

## Instalação

### 1. Clone ou baixe o projeto

```bash
git clone <url-do-repositorio>
cd CoerencIA
```

Ou simplesmente abra a pasta onde os arquivos estão.

### 2. Crie o ambiente virtual

```bash
python -m venv .venv
```

### 3. Ative o ambiente virtual

**Linux / macOS:**
```bash
source .venv/bin/activate
```

**Windows (PowerShell):**
```powershell
.venv\Scripts\Activate.ps1
```

### 4. Instale as dependências

```bash
pip install -r requirements.txt
```

### 5. Configure a chave Gemini (opcional)

Crie um arquivo `.env` na raiz do projeto com o conteúdo abaixo.  
Sem esse arquivo, o sistema funciona normalmente — apenas sem a análise qualitativa.

```
GOOGLE_API_KEY=sua_chave_gemini_aqui
```


---

## Como iniciar

Com o ambiente virtual ativado, execute:

```bash
uvicorn main:app --reload
```

Depois abra o navegador em:

```
http://localhost:8000
```

> Na **primeira execução**, o servidor fará o download do modelo SBERT (~120 MB).  
> Isso pode levar alguns minutos dependendo da conexão. As execuções seguintes são rápidas.

---

## Estrutura do projeto

```
CoerencIA/
├── main.py                  # Servidor FastAPI (endpoints da API)
├── coerencia_engine.py      # Motor de análise (SBERT, IGC, metadados, segmentação)
├── document_converter.py    # Conversão de PDF/DOCX para Markdown (Docling)
├── requirements.txt         # Dependências Python
├── .env                     # Chave da API Gemini (não versionar)
│
└── static/
    ├── index.html           # Página principal
    ├── style.css            # Estilo dark theme
    └── app.js               # Lógica da interface (JavaScript)
```

---

## Endpoints da API

| Método | Rota | Descrição |
|--------|------|-----------|
| `GET`  | `/` | Serve a interface web |
| `GET`  | `/api/check-ai` | Informa se há chave Gemini configurada no servidor |
| `POST` | `/api/analyze` | Análise SBERT do preenchimento manual (somente local) |
| `POST` | `/api/analyze/full` | Análise SBERT + diagnóstico Gemini (manual) |
| `POST` | `/api/intro-analysis` | Checklist de elementos da Introdução (manual, com IA) |
| `POST` | `/api/extract-segments` | Upload: extrai texto, metadados, segmentos e elementos da Introdução |
| `POST` | `/api/analyze-mapped` | Upload: análise a partir do mapeamento confirmado pelo usuário |

> **Segurança:** a chave da API Gemini é lida exclusivamente do arquivo `.env` pelo backend. Ela **não** é digitada na interface nem enviada no corpo das requisições.

---

## Pares estratégicos avaliados

| Par | Justificativa |
|-----|---------------|
| Introdução ↔ Objetivos | O objetivo deve emergir do contexto apresentado |
| Objetivos ↔ Metodologia | O método deve responder aos objetivos |
| Objetivos ↔ Resultados | Os resultados devem cobrir o que foi proposto |
| Problema ↔ Conclusão | A conclusão deve responder ao problema de pesquisa |
| Resultados ↔ Conclusão | A conclusão deve ser sustentada pelos resultados |

---

## Classificação do IGC

| Faixa | Classificação |
|-------|--------------|
| ≥ 0.70 | Boa coerência estrutural |
| 0.50 – 0.69 | Coerência moderada |
| < 0.50 | Incoerência significativa |

> Os limiares variam conforme o **nível de rigor** selecionado (Baixo / Médio / Alto).

---

## Tecnologias utilizadas

- **[FastAPI](https://fastapi.tiangolo.com/)** — servidor web e API REST
- **[Sentence-Transformers](https://www.sbert.net/)** — modelo `paraphrase-multilingual-MiniLM-L12-v2`
- **[Docling](https://github.com/DS4SD/docling)** — conversão de PDF/DOCX para Markdown no upload (OCR desativado)
- **[Google Gemini API](https://ai.google.dev/)** — análise qualitativa em linguagem natural (opcional)
- **JavaScript (vanilla)** — interface web sem framework
