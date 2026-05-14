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

SECTIONS_ORDER = [
    "introducao",
    "problema",
    "objetivos",
    "metodologia",
    "resultados",
    "conclusao",
]

SECTION_LABELS = {
    "introducao": "Introdução",
    "problema": "Problema",
    "objetivos": "Objetivos",
    "metodologia": "Metodologia",
    "resultados": "Resultados",
    "conclusao": "Conclusão",
}

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
        "introducao": ["introducao", "contextualizacao"],
        "problema": ["problema", "problema de pesquisa", "questao de pesquisa"],
        "objetivos": ["objetivo", "objetivos", "objetivo geral", "objetivos especificos"],
        "metodologia": ["metodologia", "metodo", "procedimentos metodologicos", "materiais e metodos"],
        "resultados": ["resultado", "resultados", "analise dos resultados", "discussao"],
        "conclusao": ["conclusao", "consideracoes finais", "conclusoes"],
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

    for raw_line in full_text.splitlines():
        line = raw_line.strip()
        detected = _section_from_heading(line)
        if detected:
            active_section = detected
            continue

        if active_section and line:
            sections[active_section].append(line)

    finalized = {key: _normalize_spaces("\n".join(value)) for key, value in sections.items()}

    for key in SECTIONS_ORDER:
        if len(finalized[key]) < 80:
            fallback = _fallback_extract_section(full_text, key)
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


def analyze_sections(sections: dict[str, str], config: AnalysisConfig) -> dict[str, Any]:
    model_name = _resolve_model_name(config)
    model = _load_model(model_name)

    warnings: list[str] = []
    for section_key in SECTIONS_ORDER:
        if not sections.get(section_key):
            warnings.append(f"Seção '{SECTION_LABELS[section_key]}' não foi encontrada com clareza no documento.")

    section_texts = [sections.get(key, "") or "" for key in SECTIONS_ORDER]
    embeddings = _to_embeddings(model, section_texts)
    embedding_by_section = {key: embeddings[idx] for idx, key in enumerate(SECTIONS_ORDER)}

    matrix_rows: list[dict[str, Any]] = []
    critical_rows: list[dict[str, Any]] = []

    rigor_cfg = RIGOR_THRESHOLDS.get(config.nivel_rigor, RIGOR_THRESHOLDS["Médio"])

    for left_key, right_key, pair_label in MANDATORY_PAIRS:
        left_text = sections.get(left_key, "")
        right_text = sections.get(right_key, "")

        if not left_text or not right_text:
            score = 0.0
            interpretation, color_label, css_class = "Dados insuficientes", "Vermelho", "coerencia-fraca"
        else:
            score = _cosine_sim(embedding_by_section[left_key], embedding_by_section[right_key])
            interpretation, color_label, css_class = _semantic_band(score, config.nivel_rigor)

        matrix_rows.append(
            {
                "par": pair_label,
                "similaridade": round(score, 4),
                "interpretação": interpretation,
                "faixa": color_label,
                "classe_css": css_class,
            }
        )

        if score < rigor_cfg["critica"] and left_text and right_text:
            excerpt_a, excerpt_b, excerpt_score = _critical_excerpt(model, left_text, right_text)
            suggestion = _build_suggestion(pair_label, excerpt_a, excerpt_b, sections.get(left_key, ""))
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
            "modo_analise": config.modo_analise,
            "modelo_semantico": config.modelo_semantico,
            "nivel_rigor": config.nivel_rigor,
            "modelo_embedding": model_name,
        },
        "matriz_similaridade": matrix_rows,
        "trechos_criticos": critical_rows,
        "secoes_extraidas": sections,
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