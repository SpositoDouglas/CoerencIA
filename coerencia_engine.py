from __future__ import annotations

import io
import importlib
import json
import os
import re
import time
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import numpy as np

docx_module: Any = importlib.import_module("docx")
pypdf_module: Any = importlib.import_module("pypdf")
sentence_transformers_module: Any = importlib.import_module("sentence_transformers")
google_genai: Any = importlib.import_module("google.genai")
genai_types: Any = importlib.import_module("google.genai.types")

Document = docx_module.Document
PdfReader = pypdf_module.PdfReader
SentenceTransformer = sentence_transformers_module.SentenceTransformer

GEMINI_SYSTEM_INSTRUCTION = (
    "Você é um professor de universidade altamente qualificado, membro experiente de bancas avaliadoras "
    "de Trabalhos de Conclusão de Curso (TCCs). Sua capacidade principal é identificar automaticamente "
    "desalinhamentos semânticos e estruturais entre diferentes seções de textos acadêmicos digitais. "
    "Você receberá textos de pares de seções de um TCC (ex.: Introdução vs. Objetivos, Objetivos vs. Resultados) "
    "juntamente com uma nota de similaridade semântica já calculada pelo motor do modelo Sentence-BERT. "
    "Seu objetivo é interpretar esse score de similaridade e o conteúdo dos textos para avaliar a coesão lógica. "
    "Caso a similaridade seja baixa, você deve apontar os trechos com menor alinhamento, explicar o motivo "
    "do desalinhamento e fornecer sugestões claras e automatizadas de reescrita para corrigir a inconsistência metodológica."
)

MODEL_PROMPT_BLOCKS = {
    "Sentence-BERT padrão": (
        "Modelo Sentence-BERT padrão. Foque na coerência semântica geral, "
        "comparando os embeddings habituais da linguagem estruturada acadêmica."
    ),
    "Modelo Customizado": (
        "Modelo customizado com fine-tuning específico. A avaliação deve dar peso redobrado "
        "a jargões técnicos da área de pesquisa e à coerência estrutural muito específica desta linha de estudo."
    ),
}

RIGOR_PROMPT_BLOCKS = {
    "Baixo": (
        "Nível Baixo: Forneça apenas alertas leves. Indique apenas inconsistências e desalinhamentos "
        "graves e muito óbvios. Tolere pequenas variações argumentativas."
    ),
    "Médio": (
        "Nível Médio (Padrão): Faça uma avaliação equilibrada. Destaque possíveis desalinhamentos estruturais "
        "(ex.: objetivos específicos não contemplados na metodologia ou resultados que não respondem à pergunta central). "
        "Indique o alinhamento como Forte, Moderado ou Fraco."
    ),
    "Alto": (
        "Nível Alto: Seja extremamente sensível e rigoroso. Reduza o limiar de tolerância. "
        "Identifique desalinhamentos muito sutis e incoerências conceituais leves, marcando qualquer falha "
        "na dependência lógica rigorosa entre problema, método e conclusão."
    ),
}

MODE_PROMPT_BLOCKS = {
    "Análise básica": (
        "Forneça um painel geral e direto. Indique se os textos parecem coerentes, "
        "apresente a interpretação do grau de similaridade em uma única frase e diga se a estrutura está satisfatória."
    ),
    "Análise detalhada": (
        "Gere um Relatório Detalhado com: 1) A interpretação do nível de alinhamento; "
        "2) Citações dos trechos específicos com menor alinhamento; 3) O motivo exato de um elemento não conversar com o outro; "
        "4) Pontos fortes e pontos de atenção; 5) Uma recomendação explícita de como o aluno deve reescrever o texto para corrigir a falha."
    ),
    "Comparação entre versões": (
        "Exiba uma matriz comparativa. Avalie se o Índice Global e o alinhamento entre as seções "
        "(ex.: Objetivos vs. Resultados) apresentaram evolução. Gere uma mensagem automática indicando se houve melhora significativa "
        "no alinhamento ou se os novos ajustes prejudicaram a coesão."
    ),
}

# Seções centrais — participam dos embeddings, dos pares estratégicos e do IGC.
SECTIONS_ORDER = [
    "introducao",
    "problema",
    "objetivos",
    "metodologia",
    "resultados",
    "conclusao",
]

# Seções extras — reconhecidas, exibidas e usadas como contexto da análise/relatório,
# mas que NÃO entram nos pares estratégicos nem alteram a fórmula do IGC.
EXTRA_SECTIONS = ["referencial"]

SECTION_LABELS = {
    "introducao": "Introdução",
    "problema": "Problema",
    "objetivos": "Objetivos",
    "metodologia": "Metodologia",
    "resultados": "Resultados",
    "conclusao": "Conclusão",
    "referencial": "Referencial Teórico",
}

# Todas as categorias acadêmicas válidas para mapeamento/seleção do usuário.
MAPPABLE_SECTIONS = [*SECTIONS_ORDER, *EXTRA_SECTIONS]

MANDATORY_PAIRS = [
    ("introducao", "objetivos", "Introdução ↔ Objetivos"),
    ("objetivos", "metodologia", "Objetivos ↔ Metodologia"),
    ("objetivos", "resultados", "Objetivos ↔ Resultados"),
    ("problema", "conclusao", "Problema ↔ Conclusão"),
    ("resultados", "conclusao", "Resultados ↔ Conclusão"),
]

RIGOR_THRESHOLDS = {
    "Baixo": {"forte": 0.62, "moderada": 0.44, "critica": 0.42},
    "Médio": {"forte": 0.68, "moderada": 0.50, "critica": 0.50},
    "Alto": {"forte": 0.74, "moderada": 0.56, "critica": 0.58},
}

PAIR_CONTEXT: dict[str, dict[str, str]] = {
    "Introdução ↔ Objetivos": {
        "forte": "Os objetivos estão diretamente ancorados no contexto e na justificativa apresentada na introdução.",
        "moderada": "Os objetivos atendem parcialmente ao cenário introduzido, mas alguns aspectos contextualizados não se refletem claramente nos objetivos declarados.",
        "fraca": "Os objetivos parecem desconectados do contexto e da problemática levantada na introdução. Verifique se os objetivos respondem diretamente ao que foi apresentado.",
    },
    "Objetivos ↔ Metodologia": {
        "forte": "A metodologia cobre os procedimentos necessários para atingir todos os objetivos declarados.",
        "moderada": "A metodologia responde a parte dos objetivos, mas alguns procedimentos podem ser vagos ou ausentes para objetivos específicos.",
        "fraca": "A metodologia não reflete claramente os objetivos. Os procedimentos adotados parecem insuficientes ou desalinhados com o que foi proposto.",
    },
    "Objetivos ↔ Resultados": {
        "forte": "Os resultados demonstram cumprimento dos objetivos, com boa correspondência entre o que foi proposto e o que foi alcançado.",
        "moderada": "Os resultados respondem parcialmente aos objetivos. Alguns objetivos específicos não possuem evidências claras nos resultados apresentados.",
        "fraca": "Os resultados apresentam baixa correspondência com os objetivos. O trabalho pode não ter respondido adequadamente ao que se propôs.",
    },
    "Problema ↔ Conclusão": {
        "forte": "A conclusão responde com clareza ao problema de pesquisa formulado, demonstrando fechamento lógico do trabalho.",
        "moderada": "A conclusão aborda o problema de pesquisa de forma parcial. Aspectos centrais da questão podem não ter resposta explícita nas considerações finais.",
        "fraca": "A conclusão não responde adequadamente ao problema de pesquisa. O fechamento do trabalho parece desconectado da questão central formulada.",
    },
    "Resultados ↔ Conclusão": {
        "forte": "As conclusões são sustentadas pelos resultados apresentados, com boa coerência entre evidências e inferências finais.",
        "moderada": "As conclusões refletem parcialmente os resultados. Algumas inferências podem extrapolar ou subutilizar as evidências apresentadas.",
        "fraca": "As conclusões têm baixa correspondência com os resultados. As inferências finais não estão suficientemente sustentadas pelas evidências do trabalho.",
    },
}

STOPWORDS_PT = {
    "a",
    "o",
    "os",
    "as",
    "de",
    "do",
    "da",
    "dos",
    "das",
    "e",
    "em",
    "no",
    "na",
    "nos",
    "nas",
    "um",
    "uma",
    "para",
    "por",
    "com",
    "sobre",
    "que",
    "se",
    "ao",
    "aos",
    "como",
    "ser",
    "foi",
    "sao",
    "são",
    "dos",
    "das",
    "este",
    "esta",
    "esse",
    "essa",
    "mais",
    "menos",
    "entre",
    "tambem",
    "também",
    "pois",
    "quando",
    "onde",
    "qual",
    "quais",
}

GEMINI_BACKOFF_DELAYS = (5, 15, 30)

# Regex patterns for cleaning Docling Markdown output
_RE_DOCLING_TABLE_SEP = re.compile(r'^[\|\-\+\=\:\s]+$')
_RE_DOCLING_IMAGE = re.compile(r'^\s*!\[')
_RE_DOCLING_FILE_LINK = re.compile(
    r'^\s*\[.*?\]\([^)]*\.(pdf|png|jpg|jpeg|gif|svg|tiff|webp|bmp)[^)]*\)\s*$',
    re.IGNORECASE,
)


@dataclass
class AnalysisConfig:
    modo_analise: str
    modelo_semantico: str
    nivel_rigor: str
    modelo_customizado: str | None = None


def _normalize_spaces(text: str) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r"\r", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def _strip_accents(text: str) -> str:
    return "".join(char for char in unicodedata.normalize("NFD", text) if unicodedata.category(char) != "Mn")


def _normalize_heading(line: str) -> str:
    lowered = _strip_accents(line.lower())
    lowered = re.sub(r"[^a-z0-9\s]", " ", lowered)
    lowered = re.sub(r"\s+", " ", lowered).strip()
    return lowered


def _section_from_heading(line: str) -> str | None:
    normalized = _normalize_heading(line)
    if not normalized or len(normalized) > 120:
        return None

    mapping = {
        "introducao": [
            "introducao", "contextualizacao", "contexto", "apresentacao",
            "introducao ao tema", "contextualizacao do tema", "contexto e problema",
            "contexto geral", "apresentacao do tema",
        ],
        "problema": [
            "problema", "problema de pesquisa", "questao de pesquisa",
            "questao norteadora", "problematica", "delimitacao do problema",
            "formulacao do problema", "identificacao do problema",
            "questao central", "hipotese", "lacuna", "justificativa",
        ],
        "objetivos": [
            "objetivo", "objetivos", "objetivo geral", "objetivos especificos",
            "objetivos do trabalho", "objetivo da pesquisa", "objetivos da pesquisa",
            "objetivos gerais e especificos", "metas da pesquisa", "finalidade",
            "proposito", "objetivos gerais",
        ],
        "referencial": [
            "referencial teorico", "referencial conceitual", "fundamentacao teorica",
            "revisao de literatura", "revisao da literatura", "revisao bibliografica",
            "base teorica", "embasamento teorico", "marco teorico", "estado da arte",
            "trabalhos relacionados", "trabalhos correlatos", "background",
            "theoretical framework", "literature review", "related work",
            "fundamentacao", "referencial",
        ],
        "metodologia": [
            "metodologia", "metodo", "procedimentos metodologicos", "materiais e metodos",
            "materiais e metodologia", "metodos e tecnicas", "abordagem metodologica",
            "procedimentos", "metodologia de pesquisa", "delineamento metodologico",
            "tipo de pesquisa", "metodologia e tecnicas", "caminho metodologico",
            "percurso metodologico", "estrategia metodologica", "design da pesquisa",
            "tecnicas de pesquisa", "abordagem", "metodos", "metodologia e metodos",
        ],
        "resultados": [
            "resultado", "resultados", "analise dos resultados", "discussao",
            "analise e discussao", "discussao dos resultados", "apresentacao dos resultados",
            "resultados e discussao", "analise de dados", "achados",
            "analise e interpretacao", "dados e resultados", "analise dos dados",
            "resultados obtidos", "resultados e analise", "resultados e discussao",
        ],
        "conclusao": [
            "conclusao", "consideracoes finais", "conclusoes",
            "conclusao e consideracoes finais", "reflexoes finais",
            "consideracoes", "encerramento", "sintese",
            "contribuicoes", "conclusoes e recomendacoes",
            "conclusoes finais", "fechamento", "ultimas consideracoes",
            "consideracoes e conclusoes",
        ],
        "ignorar": [
            "resumo", "abstract", "resumen", "sumario", "sumario executivo",
            "summary", "palavras chave", "keywords", "palavras-chave",
            "referencias", "referencias bibliograficas", "bibliografia",
            "lista de referencias", "agradecimentos", "dedicatoria",
            "anexo", "anexos", "apendice", "apendices",
            "lista de figuras", "lista de tabelas", "lista de abreviaturas",
            "lista de siglas", "epigrafe", "folha de aprovacao",
        ],
    }

    for key, aliases in mapping.items():
        if any(alias in normalized for alias in aliases):
            return key
    return None


def _fallback_extract_section(full_text: str, section_key: str) -> str:
    keywords = {
        "introducao": ["introdução", "introducao", "contexto"],
        "problema": ["problema", "questão", "questao"],
        "objetivos": ["objetivo", "objetivos"],
        "metodologia": ["metodologia", "método", "metodo"],
        "resultados": ["resultado", "resultados", "discussão", "discussao"],
        "conclusao": ["conclusão", "conclusao", "considerações finais", "consideracoes finais"],
    }
    lowered = full_text.lower()
    for kw in keywords[section_key]:
        pos = lowered.find(kw)
        if pos != -1:
            start = max(0, pos - 350)
            end = min(len(full_text), pos + 1450)
            return full_text[start:end].strip()
    return ""


def segment_sections(full_text: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {key: [] for key in SECTIONS_ORDER}
    active_section: str | None = None
    ignoring = False
    filtered_lines: list[str] = []

    for raw_line in full_text.splitlines():
        line = raw_line.strip()
        detected = _section_from_heading(line)
        if detected:
            ignoring = detected == "ignorar"
            active_section = detected if detected in SECTIONS_ORDER else None
            continue

        if ignoring:
            continue

        if active_section and line:
            sections[active_section].append(line)
        filtered_lines.append(line)

    finalized = {key: _normalize_spaces("\n".join(value)) for key, value in sections.items()}
    filtered_text = "\n".join(filtered_lines)

    for key in SECTIONS_ORDER:
        if len(finalized[key]) < 80:
            fallback = _fallback_extract_section(filtered_text, key)
            if len(fallback) > len(finalized[key]):
                finalized[key] = _normalize_spaces(fallback)

    return finalized


def extract_text_from_pdf(file_bytes: bytes) -> str:
    reader = PdfReader(io.BytesIO(file_bytes))
    pages = [page.extract_text() or "" for page in reader.pages]
    return _normalize_spaces("\n\n".join(pages))


def extract_text_from_docx(file_bytes: bytes) -> str:
    document = Document(io.BytesIO(file_bytes))
    paragraphs = [paragraph.text for paragraph in document.paragraphs]
    return _normalize_spaces("\n".join(paragraphs))


def extract_document_text(filename: str, file_bytes: bytes) -> str:
    lowered = filename.lower()
    if lowered.endswith(".pdf"):
        return extract_text_from_pdf(file_bytes)
    if lowered.endswith(".docx"):
        return extract_text_from_docx(file_bytes)
    raise ValueError("Formato não suportado. Envie um arquivo PDF ou DOCX.")


def _clean_docling_markdown(text: str) -> str:
    """Remove non-textual Markdown artifacts produced by Docling before segmentation.

    Removes: table separator rows (|---|---), image syntax, standalone binary-file
    links, and lines where less than 15 % of characters are alphanumeric.
    """
    output: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            output.append("")
            continue
        if _RE_DOCLING_TABLE_SEP.match(stripped):
            continue
        if _RE_DOCLING_IMAGE.match(stripped):
            continue
        if _RE_DOCLING_FILE_LINK.match(stripped):
            continue
        if len(stripped) > 8 and sum(c.isalnum() for c in stripped) / len(stripped) < 0.15:
            continue
        output.append(line)
    return _normalize_spaces("\n".join(output))


def _resolve_model_name(config: AnalysisConfig) -> str:
    if config.modelo_semantico == "Modelo Customizado" and config.modelo_customizado:
        return config.modelo_customizado
    return "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


@lru_cache(maxsize=3)
def _load_model(model_name: str) -> Any:
    return SentenceTransformer(model_name)


def _to_embeddings(model: Any, texts: list[str]) -> np.ndarray:
    return model.encode(texts, normalize_embeddings=True, convert_to_numpy=True)


def _cosine_sim(vec_a: np.ndarray, vec_b: np.ndarray) -> float:
    return float(np.dot(vec_a, vec_b))


def _split_sentences(text: str) -> list[str]:
    candidates = re.split(r"(?<=[\.!?])\s+|\n+", text)
    cleaned = [item.strip() for item in candidates if len(item.strip()) > 35]
    return cleaned[:40]


def _extract_keywords(text: str, top_k: int = 8) -> list[str]:
    normalized = _strip_accents(text.lower())
    words = re.findall(r"[a-z]{4,}", normalized)
    freq: dict[str, int] = {}
    for word in words:
        if word in STOPWORDS_PT:
            continue
        freq[word] = freq.get(word, 0) + 1
    sorted_words = sorted(freq.items(), key=lambda item: item[1], reverse=True)
    return [word for word, _ in sorted_words[:top_k]]


def _semantic_band(score: float, rigor: str) -> tuple[str, str, str]:
    thresholds = RIGOR_THRESHOLDS.get(rigor, RIGOR_THRESHOLDS["Médio"])
    if score >= thresholds["forte"]:
        return "Forte alinhamento", "Verde", "coerencia-forte"
    if score >= thresholds["moderada"]:
        return "Alinhamento moderado", "Amarelo", "coerencia-moderada"
    return "Alinhamento fraco", "Vermelho", "coerencia-fraca"


def _igc_classification(igc: float) -> str:
    if igc < 0.50:
        return "Incoerência significativa"
    if igc <= 0.70:
        return "Coerência moderada"
    return "Boa coerência estrutural"


def _generate_pair_explanation(pair_label: str, score: float, rigor: str) -> str:
    thresholds = RIGOR_THRESHOLDS.get(rigor, RIGOR_THRESHOLDS["Médio"])
    if score >= thresholds["forte"]:
        band = "forte"
    elif score >= thresholds["moderada"]:
        band = "moderada"
    else:
        band = "fraca"
    return PAIR_CONTEXT.get(pair_label, {}).get(band, "")


def _critical_excerpt(
    model: Any,
    section_a: str,
    section_b: str,
) -> tuple[str, str, float]:
    sentences_a = _split_sentences(section_a)
    sentences_b = _split_sentences(section_b)
    if not sentences_a or not sentences_b:
        return section_a[:240], section_b[:240], 0.0

    embeddings_a = _to_embeddings(model, sentences_a)
    embeddings_b = _to_embeddings(model, sentences_b)
    similarity_matrix = np.matmul(embeddings_a, embeddings_b.T)

    best_matches = similarity_matrix.max(axis=1)
    lowest_idx = int(np.argmin(best_matches))
    best_b_idx = int(np.argmax(similarity_matrix[lowest_idx]))

    return sentences_a[lowest_idx], sentences_b[best_b_idx], float(best_matches[lowest_idx])


def _build_suggestion(pair_label: str, excerpt_a: str, excerpt_b: str, section_anchor: str) -> str:
    keywords = _extract_keywords(section_anchor)
    missing = [kw for kw in keywords[:5] if kw not in _strip_accents(excerpt_b.lower())]
    missing_text = ", ".join(missing[:3]) if missing else "termos-chave do problema/objetivo"
    return (
        f"⚠ No par {pair_label}, o trecho analisado não cobre com clareza {missing_text}. "
        f"Sugestão: reescreva a seção para conectar explicitamente causa, método e evidência com esses elementos."
    )


def analyze_sections(
    sections: dict[str, str],
    config: AnalysisConfig,
    *,
    referencial: str = "",
    origem_secoes: dict[str, str] | None = None,
) -> dict[str, Any]:
    model_name = _resolve_model_name(config)
    model = _load_model(model_name)

    origem_secoes = origem_secoes or {}

    warnings: list[str] = []
    for section_key in SECTIONS_ORDER:
        if not sections.get(section_key):
            warnings.append(f"Seção '{SECTION_LABELS[section_key]}' não foi encontrada com clareza no documento.")

    section_texts = [sections.get(key, "") or "" for key in SECTIONS_ORDER]
    embeddings = _to_embeddings(model, section_texts)
    embedding_by_section = {key: embeddings[idx] for idx, key in enumerate(SECTIONS_ORDER)}

    matrix_rows: list[dict[str, Any]] = []
    skipped_pairs: list[dict[str, str]] = []
    critical_rows: list[dict[str, Any]] = []

    rigor_cfg = RIGOR_THRESHOLDS.get(config.nivel_rigor, RIGOR_THRESHOLDS["Médio"])

    for left_key, right_key, pair_label in MANDATORY_PAIRS:
        left_text = sections.get(left_key, "")
        right_text = sections.get(right_key, "")

        if not left_text or not right_text:
            ausentes = [SECTION_LABELS[k] for k, t in ((left_key, left_text), (right_key, right_text)) if not t]
            skipped_pairs.append({
                "par": pair_label,
                "motivo": f"Seção ausente: {', '.join(ausentes)}",
            })
            continue

        score = _cosine_sim(embedding_by_section[left_key], embedding_by_section[right_key])
        interpretation, color_label, css_class = _semantic_band(score, config.nivel_rigor)

        matrix_rows.append(
            {
                "par": pair_label,
                "similaridade": round(score, 4),
                "interpretação": interpretation,
                "faixa": color_label,
                "classe_css": css_class,
                "explicacao": _generate_pair_explanation(pair_label, score, config.nivel_rigor),
            }
        )

        if score < rigor_cfg["critica"]:
            excerpt_a, excerpt_b, excerpt_score = _critical_excerpt(model, left_text, right_text)
            suggestion = _build_suggestion(pair_label, excerpt_a, excerpt_b, left_text)
            critical_rows.append(
                {
                    "par": pair_label,
                    "score_par": round(score, 4),
                    "score_trecho": round(excerpt_score, 4),
                    "trecho_a": excerpt_a,
                    "trecho_b": excerpt_b,
                    "sugestao": suggestion,
                    "classe_css": "coerencia-fraca",
                }
            )

    scores = [row["similaridade"] for row in matrix_rows]
    similarity_mean = float(np.mean(scores)) if scores else 0.0
    igc = similarity_mean
    classification = _igc_classification(igc)

    return {
        "painel_geral": {
            "igc": round(igc, 4),
            "similaridade_media": round(similarity_mean, 4),
            "classificacao": classification,
            "pares_avaliados": len(matrix_rows),
            "pares_ignorados": len(skipped_pairs),
            "pares_totais": len(MANDATORY_PAIRS),
            "modo_analise": config.modo_analise,
            "modelo_semantico": config.modelo_semantico,
            "nivel_rigor": config.nivel_rigor,
            "modelo_embedding": model_name,
        },
        "matriz_similaridade": matrix_rows,
        "pares_nao_avaliados": skipped_pairs,
        "trechos_criticos": critical_rows,
        "secoes_extraidas": sections,
        "referencial": referencial,
        "origem_secoes": origem_secoes,
        "avisos": warnings,
    }


def analyze_document_bytes(file_name: str, file_bytes: bytes, config: AnalysisConfig) -> dict[str, Any]:
    text = extract_document_text(file_name, file_bytes)
    if len(text) < 600:
        raise ValueError("Não foi possível extrair texto suficiente do arquivo para análise estrutural.")
    sections = segment_sections(text)
    result = analyze_sections(sections, config)
    result["arquivo"] = file_name
    return result


def analyze_mode(
    config: AnalysisConfig,
    primary_file_name: str,
    primary_file_bytes: bytes,
    secondary_file_name: str | None = None,
    secondary_file_bytes: bytes | None = None,
) -> dict[str, Any]:
    if config.modo_analise != "Comparação entre versões":
        return {
            "tipo_resultado": "single",
            "analise": analyze_document_bytes(primary_file_name, primary_file_bytes, config),
        }

    if not secondary_file_name or not secondary_file_bytes:
        raise ValueError("No modo de comparação entre versões, envie dois arquivos (versão base e versão revisada).")

    base = analyze_document_bytes(primary_file_name, primary_file_bytes, config)
    revised = analyze_document_bytes(secondary_file_name, secondary_file_bytes, config)

    delta_igc = round(revised["painel_geral"]["igc"] - base["painel_geral"]["igc"], 4)

    base_scores = {item["par"]: item["similaridade"] for item in base["matriz_similaridade"]}
    revised_scores = {item["par"]: item["similaridade"] for item in revised["matriz_similaridade"]}
    deltas = []
    for _, _, pair_label in MANDATORY_PAIRS:
        delta = round(revised_scores.get(pair_label, 0.0) - base_scores.get(pair_label, 0.0), 4)
        deltas.append({"par": pair_label, "delta": delta})

    return {
        "tipo_resultado": "comparacao",
        "analise_base": base,
        "analise_revisada": revised,
        "comparativo": {
            "delta_igc": delta_igc,
            "deltas_por_par": deltas,
        },
    }


def _truncate_for_prompt(text: str, max_chars: int = 2400) -> str:
    cleaned = _normalize_spaces(text)
    if len(cleaned) <= max_chars:
        return cleaned
    return f"{cleaned[:max_chars]}..."


def _build_pair_prompt(
    section_a_name: str,
    section_a_text: str,
    section_b_name: str,
    section_b_text: str,
    score: float,
    config: AnalysisConfig,
) -> str:
    model_block = MODEL_PROMPT_BLOCKS.get(config.modelo_semantico, MODEL_PROMPT_BLOCKS["Sentence-BERT padrão"])
    rigor_block = RIGOR_PROMPT_BLOCKS.get(config.nivel_rigor, RIGOR_PROMPT_BLOCKS["Médio"])
    mode_block = MODE_PROMPT_BLOCKS.get(config.modo_analise, MODE_PROMPT_BLOCKS["Análise detalhada"])

    return (
        "Professor, analise o seguinte par de seções extraídas de um TCC.\n\n"
        f"Seção A ({section_a_name}):\n'{_truncate_for_prompt(section_a_text)}'\n\n"
        f"Seção B ({section_b_name}):\n'{_truncate_for_prompt(section_b_text)}'\n\n"
        f"Similaridade Semântica (Calculada via {config.modelo_semantico}): {score:.4f}\n"
        f"Modo de Análise Solicitado: {config.modo_analise}\n"
        f"Nível de Rigor Solicitado: {config.nivel_rigor}\n\n"
        f"Diretriz de Modelo: {model_block}\n"
        f"Diretriz de Rigor: {rigor_block}\n"
        f"Diretriz de Modo: {mode_block}\n\n"
        "Com base nestas configurações, gere o seu diagnóstico e relatório para este par específico "
        "em Markdown, com linguagem objetiva e orientada a ação."
    )


def _build_comparison_prompt(payload: dict[str, Any], config: AnalysisConfig) -> str:
    model_block = MODEL_PROMPT_BLOCKS.get(config.modelo_semantico, MODEL_PROMPT_BLOCKS["Sentence-BERT padrão"])
    rigor_block = RIGOR_PROMPT_BLOCKS.get(config.nivel_rigor, RIGOR_PROMPT_BLOCKS["Médio"])
    mode_block = MODE_PROMPT_BLOCKS.get(config.modo_analise, MODE_PROMPT_BLOCKS["Comparação entre versões"])

    base = payload["analise_base"]["painel_geral"]
    revised = payload["analise_revisada"]["painel_geral"]
    comparison_data = {
        "igc_base": base["igc"],
        "igc_revisada": revised["igc"],
        "delta_igc": payload["comparativo"]["delta_igc"],
        "deltas_por_par": payload["comparativo"]["deltas_por_par"],
        "matriz_base": payload["analise_base"]["matriz_similaridade"],
        "matriz_revisada": payload["analise_revisada"]["matriz_similaridade"],
    }

    return (
        "Professor, analise a comparação entre duas versões de um TCC.\n\n"
        f"Dados quantitativos (Sentence-BERT):\n{json.dumps(comparison_data, ensure_ascii=False, indent=2)}\n\n"
        f"Modo de Análise Solicitado: {config.modo_analise}\n"
        f"Nível de Rigor Solicitado: {config.nivel_rigor}\n"
        f"Tipo de Modelo: {config.modelo_semantico}\n\n"
        f"Diretriz de Modelo: {model_block}\n"
        f"Diretriz de Rigor: {rigor_block}\n"
        f"Diretriz de Modo: {mode_block}\n\n"
        "Gere um relatório em Markdown com: diagnóstico comparativo, evolução ou regressão do IGC, "
        "pares que melhoraram/pioraram, impacto acadêmico e recomendações de reescrita prioritárias."
    )


def _gemini_model(api_key: str) -> Any:
    return google_genai.Client(api_key=api_key)


def _call_gemini(client: Any, prompt: str) -> str:
    last_error: Exception | None = None
    for attempt, delay_seconds in enumerate((0, *GEMINI_BACKOFF_DELAYS), start=1):
        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=genai_types.GenerateContentConfig(system_instruction=GEMINI_SYSTEM_INSTRUCTION),
            )
            text = getattr(response, "text", "") or ""
            return text.strip()
        except Exception as exc:  # noqa: BLE001 - handle SDK/network errors uniformly
            last_error = exc
            error_text = str(exc)
            status_code = getattr(exc, "status_code", None)
            if status_code not in {429, 503} and "429" not in error_text and "503" not in error_text and "UNAVAILABLE" not in error_text:
                raise
            if attempt >= 4:
                break
            time.sleep(delay_seconds)

    raise RuntimeError(
        "A API do Gemini está indisponível no momento após 3 tentativas com backoff exponencial. "
        "Tente novamente mais tarde."
    ) from last_error


def _local_report_header(analysis: dict[str, Any]) -> list[str]:
    panel = analysis["painel_geral"]
    lines = [
        "## Diagnóstico CoerencIA",
        f"- IGC: **{panel['igc']:.2f}** - {panel['classificacao']}",
        f"- Similaridade média: **{panel['similaridade_media']:.2f}**",
        f"- Modo: **{panel['modo_analise']}**",
        f"- Modelo: **{panel['modelo_semantico']}**",
        f"- Rigor: **{panel['nivel_rigor']}**",
        "",
        "### Pares avaliados",
    ]
    for row in analysis["matriz_similaridade"]:
        lines.append(f"- {row['par']}: **{row['similaridade']:.2f}** ({row['interpretação']})")
    return lines


def _local_pair_summary(pair: str, score: float, gemini_text: str, config: AnalysisConfig) -> str:
    band, _, css_class = _semantic_band(score, config.nivel_rigor)
    return (
        f"### {pair}\n"
        f"- Similaridade SBERT: **{score:.2f}**\n"
        f"- Interpretação: **{band}**\n"
        f"- Classe visual: `{css_class}`\n\n"
        f"{gemini_text if gemini_text else 'Sem retorno textual da Gemini para este par.'}"
    )


def generate_gemini_report(payload: dict[str, Any], config: AnalysisConfig, api_key: str | None = None) -> dict[str, Any]:
    resolved_key = api_key or os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not resolved_key:
        raise ValueError("A chave da API Gemini não foi encontrada. Defina GOOGLE_API_KEY ou GEMINI_API_KEY.")

    model = _gemini_model(resolved_key)

    if payload["tipo_resultado"] == "comparacao":
        base = payload["analise_base"]
        revised = payload["analise_revisada"]

        base_by_label = {item["par"]: item for item in base["matriz_similaridade"]}
        revised_by_label = {item["par"]: item for item in revised["matriz_similaridade"]}

        diagnostics: list[dict[str, str]] = []
        for section_a_key, section_b_key, pair_label in MANDATORY_PAIRS:
            base_score = base_by_label.get(pair_label, {}).get("similaridade", 0.0)
            revised_score = revised_by_label.get(pair_label, {}).get("similaridade", 0.0)
            pair_prompt = _build_pair_prompt(
                section_a_name=f"{SECTION_LABELS[section_a_key]} (Versão Base)",
                section_a_text=base["secoes_extraidas"].get(section_a_key, ""),
                section_b_name=f"{SECTION_LABELS[section_b_key]} (Versão Base)",
                section_b_text=base["secoes_extraidas"].get(section_b_key, ""),
                score=base_score,
                config=config,
            )
            pair_report_base = _call_gemini(model, pair_prompt)

            revised_prompt = _build_pair_prompt(
                section_a_name=f"{SECTION_LABELS[section_a_key]} (Versão Revisada)",
                section_a_text=revised["secoes_extraidas"].get(section_a_key, ""),
                section_b_name=f"{SECTION_LABELS[section_b_key]} (Versão Revisada)",
                section_b_text=revised["secoes_extraidas"].get(section_b_key, ""),
                score=revised_score,
                config=config,
            )
            pair_report_revised = _call_gemini(model, revised_prompt)

            diagnostics.append(
                {
                    "par": pair_label,
                    "diagnostico": (
                        f"**Versão Base**\n\n{pair_report_base}\n\n"
                        f"**Versão Revisada**\n\n{pair_report_revised}"
                    ),
                }
            )

        final_report = _local_report_header(revised)
        final_report.extend(
            [
                "",
                "### Evolução entre versões",
                f"- IGC base: **{base['painel_geral']['igc']:.2f}**",
                f"- IGC revisada: **{revised['painel_geral']['igc']:.2f}**",
                f"- Delta de IGC: **{payload['comparativo']['delta_igc']:+.2f}**",
                "",
                "### Interpretação qualitativa por par",
            ]
        )
        for item in diagnostics:
            final_report.append(f"- {item['par']}: diagnóstico gerado com comparação base vs. revisada.")

        return {
            "relatorio_markdown": "\n".join(final_report),
            "diagnosticos_por_par": diagnostics,
        }

    analysis = payload["analise"]
    by_label = {item["par"]: item for item in analysis["matriz_similaridade"]}

    diagnostics: list[dict[str, str]] = []
    for section_a_key, section_b_key, pair_label in MANDATORY_PAIRS:
        score = by_label.get(pair_label, {}).get("similaridade", 0.0)
        prompt = _build_pair_prompt(
            section_a_name=SECTION_LABELS[section_a_key],
            section_a_text=analysis["secoes_extraidas"].get(section_a_key, ""),
            section_b_name=SECTION_LABELS[section_b_key],
            section_b_text=analysis["secoes_extraidas"].get(section_b_key, ""),
            score=score,
            config=config,
        )
        pair_report = _call_gemini(model, prompt)
        diagnostics.append({"par": pair_label, "diagnostico": pair_report})

    final_report = _local_report_header(analysis)
    final_report.extend([
        "",
        "### Interpretação qualitativa por par",
    ])
    for item in diagnostics:
        final_report.extend([
            f"#### {item['par']}",
            item["diagnostico"],
            "",
        ])

    if analysis["trechos_criticos"]:
        final_report.extend(["### Alertas críticos"])
        for critical in analysis["trechos_criticos"][:3]:
            final_report.append(f"- {critical['sugestao']}")

    return {
        "relatorio_markdown": "\n".join(final_report),
        "diagnosticos_por_par": diagnostics,
    }


def analyze_document_with_docling(file_name: str, file_bytes: bytes, config: AnalysisConfig) -> dict[str, Any]:
    """Extract text via Docling, segment sections, and run coherence analysis."""
    from document_converter import convert_document_to_markdown

    markdown = convert_document_to_markdown(file_name, file_bytes)
    if len(markdown) < 200:
        raise ValueError("Não foi possível extrair texto suficiente do arquivo para análise estrutural.")
    cleaned = _clean_docling_markdown(markdown)
    sections = segment_sections(cleaned)
    result = analyze_sections(sections, config)
    result["arquivo"] = file_name
    result["markdown_extraido"] = markdown
    result["secoes_detectadas"] = {k: v for k, v in sections.items() if v}
    return result


def detect_document_segments(text: str) -> list[dict[str, Any]]:
    """Split Markdown text into heading+content pairs for user review."""
    segments: list[dict[str, Any]] = []
    current_heading = ""
    current_lines: list[str] = []

    def _flush() -> None:
        content = _normalize_spaces(" ".join(current_lines))
        if current_heading or content:
            auto = _section_from_heading(current_heading) if current_heading else None
            segments.append({
                "heading": current_heading,
                "content": content,
                "sugerido": auto,
            })

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("#"):
            _flush()
            current_heading = re.sub(r"^#+\s*", "", line).strip()
            current_lines = []
        elif line:
            current_lines.append(line)

    _flush()
    return segments


def merge_confirmed_segments(
    segments: list[dict], user_mapping: dict[str, str]
) -> dict[str, str]:
    """Merge document segments into section dict using user-confirmed mapping."""
    buckets: dict[str, list[str]] = {key: [] for key in SECTIONS_ORDER}
    for i, seg in enumerate(segments):
        role = user_mapping.get(str(i)) or seg.get("sugerido")
        if not role or role not in SECTIONS_ORDER:
            continue
        text = seg.get("content", "").strip()
        if text:
            buckets[role].append(text)
    return {
        key: _normalize_spaces("\n".join(texts))
        for key, texts in buckets.items()
    }


def propose_section_mapping_with_ai(
    segments: list[dict], api_key: str | None = None
) -> list[dict]:
    """Use Gemini to propose section classification for each detected segment."""
    resolved_key = api_key or os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not resolved_key or not segments:
        return segments

    headings_block = "\n".join(
        f"{i}. [{seg['heading'] or '(sem título)'}] {seg['content'][:180].strip()}"
        for i, seg in enumerate(segments)
    )
    prompt = (
        "Você está analisando a estrutura de um TCC. Classifique cada trecho numerado "
        "em exatamente uma das categorias: introducao, problema, objetivos, metodologia, "
        "resultados, conclusao, ignorar.\n\n"
        "Classifique como 'ignorar' trechos que sejam Resumo, Abstract, Sumário, "
        "Palavras-chave/Keywords, Referências (ou Referências Bibliográficas/Bibliografia), "
        "Agradecimentos, Dedicatória, Epígrafe, Anexos ou Apêndices — esses trechos não "
        "fazem parte do corpo estrutural do trabalho e não devem ser usados na análise.\n\n"
        f"Trechos:\n{headings_block}\n\n"
        "Responda apenas com JSON:\n"
        '{"mapeamento": {"0": "categoria", "1": "categoria"}}'
    )

    try:
        client = google_genai.Client(api_key=resolved_key)
        response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
        raw = getattr(response, "text", "") or ""
        json_match = re.search(r"\{.*\}", raw, re.DOTALL)
        if json_match:
            import json as _json
            data = _json.loads(json_match.group())
            mapping = data.get("mapeamento", {})
            for i, seg in enumerate(segments):
                candidate = mapping.get(str(i))
                if candidate and candidate in (*SECTIONS_ORDER, "ignorar"):
                    seg["sugerido"] = candidate
    except Exception:
        pass

    return segments


def analyze_intro_checklist(
    intro_text: str, api_key: str | None = None
) -> list[dict]:
    """Return a checklist of academic elements found in the Introduction text."""
    resolved_key = api_key or os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not resolved_key or not intro_text.strip():
        return []

    prompt = (
        "Analise o trecho de Introdução de um TCC abaixo. Identifique se cada elemento "
        "acadêmico está presente, parcialmente presente ou ausente.\n"
        "Elementos: Contextualização do tema, Problema de pesquisa ou lacuna, "
        "Justificativa/relevância, Objetivo geral, Objetivos específicos, "
        "Metodologia mencionada, Estrutura do trabalho.\n\n"
        "Responda apenas com JSON:\n"
        '{"elementos": [{"nome": "...", "status": "presente|parcial|ausente", "observacao": "..."}]}\n\n'
        f"Introdução:\n{intro_text[:3000]}"
    )

    try:
        client = google_genai.Client(api_key=resolved_key)
        response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
        raw = getattr(response, "text", "") or ""
        json_match = re.search(r"\{.*\}", raw, re.DOTALL)
        if json_match:
            import json as _json
            data = _json.loads(json_match.group())
            return data.get("elementos", [])
    except Exception:
        pass

    return []


# ── Metadados do documento (título e autores) ───────────────────────────────────

_INSTITUTION_HINTS = (
    "universidade", "faculdade", "instituto", "centro universitario", "fundacao",
    "escola", "departamento", "curso", "graduacao", "bacharelado", "licenciatura",
    "tecnologo", "campus", "ministerio", "secretaria", "colegiado",
    "programa de pos", "centro de", "pontificia",
)
_ROLE_HINTS = (
    "orientador", "orientadora", "coorientador", "coorientadora", "professor",
    "professora", "prof.", "prof ", "dr.", "dra.", "msc", "m.sc", "ph.d", "phd",
    "banca", "examinador", "examinadora", "mestre", "doutor", "doutora",
)
_META_NOISE = (
    "resumo", "abstract", "resumen", "palavras-chave", "palavras chave",
    "keywords", "sumario", "trabalho de conclusao", "monografia", "dissertacao",
    "tese de", "como requisito", "requisito parcial", "obtencao do",
    "titulo de", "grau de", "submetido", "apresentad",
)


def _document_preamble(text: str) -> list[str]:
    """Return the non-empty lines that appear before the Introduction heading."""
    preamble: list[str] = []
    for raw_line in text.splitlines():
        line = re.sub(r"^#+\s*", "", raw_line).strip()
        if not line:
            continue
        if len(line) < 60 and _section_from_heading(line) == "introducao":
            break
        preamble.append(line)
        if len(preamble) >= 45 or sum(len(item) for item in preamble) > 2200:
            break
    return preamble


def _classify_preamble_line(line: str) -> str:
    norm = _strip_accents(line.lower())
    if any(hint in norm for hint in _INSTITUTION_HINTS):
        return "inst"
    if any(hint in norm for hint in _ROLE_HINTS):
        return "role"
    if any(hint in norm for hint in _META_NOISE):
        return "noise"
    letters = sum(c.isalpha() for c in line)
    digits = sum(c.isdigit() for c in line)
    if letters == 0 or digits > letters:
        return "noise"
    return "text"


def _looks_like_person_name(fragment: str) -> bool:
    fragment = fragment.strip()
    if not fragment or any(c.isdigit() for c in fragment):
        return False
    tokens = fragment.split()
    if not (2 <= len(tokens) <= 6) or len(fragment) > 60:
        return False
    capitalized = sum(1 for tok in tokens if tok[:1].isupper())
    return capitalized >= len(tokens) - 1


def _metadata_heuristic(text: str) -> dict[str, Any]:
    preamble = _document_preamble(text)

    # Agrupa linhas "de texto" consecutivas em blocos candidatos a título.
    blocks: list[list[str]] = []
    current: list[str] = []
    for line in preamble:
        if _classify_preamble_line(line) == "text":
            current.append(line)
        elif current:
            blocks.append(current)
            current = []
    if current:
        blocks.append(current)

    authors: list[str] = []

    def _collect_authors(line: str) -> None:
        for fragment in re.split(r"[;,/]|\s+e\s+", line):
            fragment = fragment.strip()
            if _looks_like_person_name(fragment) and fragment not in authors:
                authors.append(fragment)

    title = ""
    title_block: list[str] = []
    if blocks:
        # O bloco de título tende a ser o de maior extensão textual.
        title_block = max(blocks, key=lambda b: sum(len(item) for item in b))
        # Dentro do bloco, separa linhas com cara de nome (autores) das de título.
        title_lines: list[str] = []
        for line in title_block:
            if _looks_like_person_name(line):
                _collect_authors(line)
            else:
                title_lines.append(line)
        title = _normalize_spaces(" ".join(title_lines))

    # Autores adicionais em linhas de texto fora do bloco de título.
    for line in preamble:
        if line in title_block or _classify_preamble_line(line) != "text":
            continue
        _collect_authors(line)

    return {"titulo": title, "autores": authors[:8], "extraido_por": "regras"}


def extract_document_metadata(text: str, api_key: str | None = None) -> dict[str, Any]:
    """Extract title and authors from the document preamble.

    Uses local heuristics by default; when a Gemini key is available, refines the
    extraction with the model. Always returns a usable structure even on failure,
    so the user can correct it manually afterwards.
    """
    heuristic = _metadata_heuristic(text)

    resolved_key = api_key or os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not resolved_key:
        return heuristic

    preamble_text = "\n".join(_document_preamble(text))[:2200]
    if not preamble_text.strip():
        return heuristic

    prompt = (
        "Extraia os metadados acadêmicos do trecho inicial de um documento (TCC ou artigo científico).\n"
        "Identifique o título completo do trabalho e os nomes dos autores. "
        "NÃO inclua orientadores, coorientadores, membros de banca, instituições, "
        "cursos, datas ou cidades na lista de autores.\n\n"
        "Responda apenas com JSON no formato:\n"
        '{"titulo": "...", "autores": ["..."]}\n\n'
        f"Trecho inicial:\n{preamble_text}"
    )

    try:
        client = google_genai.Client(api_key=resolved_key)
        response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
        raw = getattr(response, "text", "") or ""
        json_match = re.search(r"\{.*\}", raw, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group())
            titulo = _normalize_spaces(str(data.get("titulo", ""))) or heuristic["titulo"]
            autores_raw = data.get("autores", [])
            autores = [
                _normalize_spaces(str(a)) for a in autores_raw
                if isinstance(a, str) and a.strip()
            ]
            return {
                "titulo": titulo,
                "autores": autores or heuristic["autores"],
                "extraido_por": "ia",
            }
    except Exception:
        pass

    return heuristic


# ── Elementos da Introdução ─────────────────────────────────────────────────────

INTRO_ELEMENT_LABELS = {
    "contextualizacao": "Contextualização do tema",
    "problema": "Problema / questão de pesquisa",
    "lacuna": "Lacuna identificada",
    "justificativa": "Justificativa / relevância",
    "objetivo_geral": "Objetivo geral",
    "objetivos_especificos": "Objetivos específicos",
    "proposta": "Proposta do trabalho",
    "contribuicao": "Contribuição esperada",
    "metodologia": "Indicação de metodologia",
}

# Cada regra: (tipo, pistas fortes, pistas fracas). Pistas comparadas sem acento.
_INTRO_ELEMENT_RULES: list[tuple[str, tuple[str, ...], tuple[str, ...]]] = [
    ("objetivo_geral",
     ("objetivo geral", "tem como objetivo", "tem por objetivo", "este trabalho objetiva",
      "o objetivo deste", "objetivo deste estudo", "objetivo desta pesquisa", "tem o objetivo de"),
     ("objetivo", "visa ", "pretende", "busca ", "propoe-se a")),
    ("objetivos_especificos",
     ("objetivos especificos",),
     ("especificamente", "dentre os objetivos")),
    ("problema",
     ("problema de pesquisa", "questao de pesquisa", "questao norteadora",
      "pergunta de pesquisa", "problematica", "questao central"),
     ("o problema", "de que forma", "como garantir", "como pode", "como resolver")),
    ("lacuna",
     ("lacuna",),
     ("ainda nao", "pouco explorado", "carencia", "escassez", "falta de",
      "nao ha consenso", "poucos estudos", "pouca atencao")),
    ("justificativa",
     ("justifica-se", "se justifica", "justificativa"),
     ("relevancia", "importancia", "torna-se relevante", "necessidade de", "motiva")),
    ("proposta",
     ("este trabalho propoe", "propoe-se", "propomos", "apresenta-se uma proposta",
      "este artigo propoe"),
     ("proposta", "este trabalho apresenta", "desenvolve-se")),
    ("contribuicao",
     ("contribuicao deste", "as contribuicoes deste"),
     ("contribuir", "espera-se que", "beneficio", "impacto esperado")),
    ("metodologia",
     ("abordagem metodologica", "metodologia adotada"),
     ("metodologia", "por meio de", "utilizou-se", "foi realizada", "aplicou-se")),
    ("contextualizacao",
     (),
     ("atualmente", "nos ultimos anos", "cada vez mais", "cenario", "panorama", "contexto")),
]


def _intro_paragraphs(intro_text: str) -> list[str]:
    paras = [p.strip() for p in re.split(r"\n\s*\n", intro_text) if p.strip()]
    if len(paras) <= 1:
        sentences = _split_sentences(intro_text)
        if len(sentences) > 1:
            return sentences
    return paras or [intro_text.strip()]


def _intro_elements_heuristic(intro_text: str) -> list[dict[str, Any]]:
    paragraphs = _intro_paragraphs(intro_text)
    total = len(paragraphs)
    found: list[dict[str, Any]] = []
    per_type_count: dict[str, int] = {}

    for p_idx, paragraph in enumerate(paragraphs):
        sentences = _split_sentences(paragraph) or [paragraph]
        norm_para = _strip_accents(paragraph.lower())
        for tipo, strong, weak in _INTRO_ELEMENT_RULES:
            if per_type_count.get(tipo, 0) >= 2:
                continue
            hit_strong = any(cue in norm_para for cue in strong)
            hit_weak = hit_strong or any(cue in norm_para for cue in weak)
            if not hit_weak:
                continue
            # Escolhe a frase do parágrafo que contém a pista.
            cues = strong if hit_strong else weak
            excerpt = paragraph
            for sentence in sentences:
                norm_sentence = _strip_accents(sentence.lower())
                if any(cue in norm_sentence for cue in cues):
                    excerpt = sentence
                    break
            excerpt = _normalize_spaces(excerpt)[:600]
            if any(e["trecho"] == excerpt and e["tipo"] == tipo for e in found):
                continue
            ratio = p_idx / max(total - 1, 1)
            posicao = "início" if ratio < 0.34 else "meio" if ratio < 0.67 else "final"
            confianca = "media" if hit_strong else "baixa"
            found.append({
                "tipo": tipo,
                "rotulo": INTRO_ELEMENT_LABELS[tipo],
                "trecho": excerpt,
                "localizacao": f"Parágrafo {p_idx + 1} ({posicao} da introdução)",
                "confianca": confianca,
                "usar": confianca != "baixa",
            })
            per_type_count[tipo] = per_type_count.get(tipo, 0) + 1

    return found[:14]


def _intro_elements_ai(intro_text: str, api_key: str) -> list[dict[str, Any]]:
    """Call Gemini to identify Introduction elements. Raises on API/parse failure.

    Kept separate from the public function so callers that need to detect an AI
    failure (e.g. to inform the user) can do so without the silent fallback.
    """
    tipos = ", ".join(INTRO_ELEMENT_LABELS.keys())
    prompt = (
        "Analise o texto da Introdução de um trabalho acadêmico (TCC ou artigo).\n"
        "Localize trechos que representem os seguintes tipos de elemento: "
        f"{tipos}.\n"
        "Regras importantes:\n"
        "- Use SEMPRE o texto original do documento no campo 'trecho', sem reescrever ou parafrasear.\n"
        "- Um mesmo trecho pode conter mais de um elemento; nesse caso, gere um item para cada elemento.\n"
        "- Indique a localização aproximada (ex.: 'início da introdução', 'parágrafo 2').\n"
        "- Indique o grau de confiança como 'alta', 'media' ou 'baixa'.\n\n"
        "Responda apenas com JSON:\n"
        '{"elementos": [{"tipo": "...", "trecho": "...", "localizacao": "...", "confianca": "alta|media|baixa"}]}\n\n'
        f"Introdução:\n{intro_text[:4000]}"
    )

    client = google_genai.Client(api_key=api_key)
    response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
    raw = getattr(response, "text", "") or ""
    json_match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not json_match:
        raise ValueError("Resposta da IA sem JSON reconhecível.")

    data = json.loads(json_match.group())
    elementos: list[dict[str, Any]] = []
    for item in data.get("elementos", []):
        tipo = str(item.get("tipo", "")).strip().lower()
        trecho = _normalize_spaces(str(item.get("trecho", "")))
        if tipo not in INTRO_ELEMENT_LABELS or not trecho:
            continue
        confianca = str(item.get("confianca", "media")).strip().lower()
        if confianca not in {"alta", "media", "baixa"}:
            confianca = "media"
        elementos.append({
            "tipo": tipo,
            "rotulo": INTRO_ELEMENT_LABELS[tipo],
            "trecho": trecho[:600],
            "localizacao": _normalize_spaces(str(item.get("localizacao", ""))) or "Introdução",
            "confianca": confianca,
            "usar": confianca != "baixa",
        })
    return elementos


def analyze_intro_elements(intro_text: str, api_key: str | None = None) -> list[dict[str, Any]]:
    """Identify academic elements (problem, objectives, gap, etc.) inside the Introduction.

    Returns excerpts preserving the document's original text. Uses local rules by
    default and refines with Gemini when a key is available; on AI failure, the
    rule-based result is preserved so the flow never breaks.
    """
    intro_text = (intro_text or "").strip()
    if not intro_text:
        return []

    heuristic = _intro_elements_heuristic(intro_text)

    resolved_key = api_key or os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not resolved_key:
        return heuristic

    try:
        elementos = _intro_elements_ai(intro_text, resolved_key)
        return elementos or heuristic
    except Exception:
        return heuristic


# ── Montagem das seções a partir do mapeamento confirmado ───────────────────────

# Quais elementos da Introdução podem suprir cada seção central ausente.
_INTRO_ELEMENT_TO_SECTION = {
    "problema": ("problema", "lacuna"),
    "objetivos": ("objetivo_geral", "objetivos_especificos", "proposta"),
}


def apply_intro_elements(
    sections: dict[str, str],
    intro_elements: list[dict] | None = None,
) -> tuple[dict[str, str], dict[str, str]]:
    """Resolve the origin of Problem/Objectives and inject confirmed intro excerpts.

    Shared by the automatic and the manual flows. A dedicated section always has
    priority ('secao_propria'). When it is empty, the confirmed excerpts identified
    inside the Introduction are used as an internal representation ('introducao') —
    only the excerpts, never the whole Introduction, so nothing is double-counted.
    When neither exists, the section stays 'ausente'. Returns (sections, origem).
    """
    confirmed = [e for e in (intro_elements or []) if e.get("usar")]
    origem: dict[str, str] = {}

    for section_key, tipos in _INTRO_ELEMENT_TO_SECTION.items():
        if sections.get(section_key):
            origem[section_key] = "secao_propria"
            continue
        trechos = [
            e["trecho"] for e in confirmed
            if e.get("tipo") in tipos and e.get("trecho")
        ]
        if trechos:
            sections[section_key] = _normalize_spaces("\n".join(trechos))
            origem[section_key] = "introducao"
        else:
            origem[section_key] = "ausente"

    return sections, origem


def assemble_sections_from_mapping(
    segments: list[dict],
    user_mapping: dict[str, str],
    intro_elements: list[dict] | None = None,
) -> dict[str, Any]:
    """Build the analysis input from the user-confirmed segment mapping.

    Returns the core sections dict, the Referencial Teórico text (context only),
    and the origin of each strategic section ('secao_propria', 'introducao' or
    'ausente').
    """
    buckets: dict[str, list[str]] = {key: [] for key in MAPPABLE_SECTIONS}
    for idx, seg in enumerate(segments):
        role = user_mapping.get(str(idx)) or seg.get("sugerido")
        if role not in MAPPABLE_SECTIONS:
            continue
        text = (seg.get("content") or "").strip()
        if text:
            buckets[role].append(text)

    sections = {
        key: _normalize_spaces("\n".join(buckets[key])) for key in SECTIONS_ORDER
    }
    referencial = _normalize_spaces("\n".join(buckets["referencial"]))
    sections, origem = apply_intro_elements(sections, intro_elements)

    return {
        "sections": sections,
        "referencial": referencial,
        "origem_secoes": origem,
    }


def report_to_markdown(payload: dict[str, Any]) -> str:
    if payload["tipo_resultado"] == "comparacao":
        base = payload["analise_base"]["painel_geral"]
        revised = payload["analise_revisada"]["painel_geral"]
        comparativo = payload["comparativo"]
        direction = "evolução" if comparativo["delta_igc"] >= 0 else "queda"

        lines = [
            "## Diagnóstico CoerencIA (Comparação entre versões)",
            f"- IGC base: **{base['igc']:.2f}** ({base['classificacao']})",
            f"- IGC revisada: **{revised['igc']:.2f}** ({revised['classificacao']})",
            f"- Delta de IGC: **{comparativo['delta_igc']:+.2f}** ({direction})",
            "",
            "### Variação por par estratégico",
        ]
        for delta in comparativo["deltas_por_par"]:
            lines.append(f"- {delta['par']}: **{delta['delta']:+.2f}**")
        return "\n".join(lines)

    analysis = payload["analise"]
    panel = analysis["painel_geral"]
    lines = [
        "## Diagnóstico CoerencIA",
        f"- IGC: **{panel['igc']:.2f}** - {panel['classificacao']}",
        f"- Similaridade média: **{panel['similaridade_media']:.2f}**",
        f"- Rigor: **{panel['nivel_rigor']}**",
        "",
        "### Pares avaliados",
    ]
    for row in analysis["matriz_similaridade"]:
        lines.append(f"- {row['par']}: **{row['similaridade']:.2f}** ({row['interpretação']})")

    if analysis["trechos_criticos"]:
        lines.append("")
        lines.append("### Alertas críticos")
        for critical in analysis["trechos_criticos"][:3]:
            lines.append(f"- {critical['sugestao']}")

    return "\n".join(lines)