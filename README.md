# CoerencIA

**Avaliação Automatizada de TCCs com NLP — Análise de Coerência entre Seções**

O sistema detecta automaticamente desalinhamentos semânticos entre seções de TCCs (Introdução, Problema, Objetivos, Metodologia, Resultados e Conclusão), calculando um **Índice Global de Coerência (IGC)** via embeddings SBERT e gerando sugestões de melhoria.

---

## Como funciona

1. Você cola o texto de cada seção do TCC no wizard passo a passo
2. O sistema gera embeddings com **Sentence-BERT** e calcula a similaridade semântica entre os pares estratégicos (ex: Objetivos ↔ Resultados)
3. O resultado mostra o IGC, uma matriz de similaridade com classificação (Forte / Moderado / Fraco) e alertas para os trechos mais desalinhados
4. Opcionalmente, você pode ativar a **análise qualitativa com Gemini**: o sistema monta um único prompt com todos os textos e envia à API do Google para gerar um diagnóstico em linguagem natural

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
├── coerencia_engine.py      # Motor de análise (SBERT, IGC, métricas)
├── requirements.txt         # Dependências Python
├── .env                     # Chave da API Gemini (não versionar)
│
└── static/
    ├── index.html           # Página principal
    ├── style.css            # Estilo dark theme
    └── app.js               # Lógica do wizard (JavaScript)
```

---

## Endpoints da API

| Método | Rota | Descrição |
|--------|------|-----------|
| `GET`  | `/` | Serve a interface web |
| `POST` | `/api/analyze` | Análise SBERT (somente local, sem IA externa) |
| `POST` | `/api/analyze/full` | Análise SBERT + diagnóstico Gemini |

**Corpo da requisição (`/api/analyze`):**
```json
{
  "sections": {
    "introducao": "Texto da introdução...",
    "problema": "Texto do problema...",
    "objetivos": "Texto dos objetivos...",
    "metodologia": "Texto da metodologia...",
    "resultados": "Texto dos resultados...",
    "conclusao": "Texto da conclusão..."
  },
  "rigor": "Médio"
}
```

Para `/api/analyze/full`, adicione também:
```json
{
  "gemini_api_key": "AIzaSy...",
  "use_gemini": true
}
```

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
- **[Google Gemini API](https://ai.google.dev/)** — análise qualitativa em linguagem natural (opcional)
- **JavaScript (vanilla)** — interface web sem framework
