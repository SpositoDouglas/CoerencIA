from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from coerencia_engine import (
    SECTION_LABELS,
    AnalysisConfig,
    analyze_document_with_docling,
    analyze_intro_checklist,
    analyze_intro_elements,
    analyze_sections,
    assemble_sections_from_mapping,
    detect_document_segments,
    extract_document_metadata,
    propose_section_mapping_with_ai,
)

BASE_DIR = Path(__file__).parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(title="CoerencIA")


def _get_api_key() -> str | None:
    return os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")


# ── Request models ─────────────────────────────────────────────────────────────

class AnalyzeRequest(BaseModel):
    sections: dict[str, str]
    rigor: str = "Médio"
    use_gemini: bool = False
    additional_info: str = ""


class AnalyzeMappedRequest(BaseModel):
    segments: list[dict[str, Any]]
    user_mapping: dict[str, str]
    rigor: str = "Médio"
    use_gemini: bool = False
    additional_info: str = ""
    metadados: dict[str, Any] = {}
    intro_elementos: list[dict[str, Any]] = []


# ── Static files ───────────────────────────────────────────────────────────────

@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


# ── Utility endpoints ──────────────────────────────────────────────────────────

@app.get("/api/check-ai")
def check_ai():
    """Return whether a Gemini API key is configured on the server."""
    return {"available": bool(_get_api_key())}


# ── Manual analysis endpoints ──────────────────────────────────────────────────

@app.post("/api/analyze")
def analyze(req: AnalyzeRequest):
    config = AnalysisConfig(
        modo_analise="Análise detalhada",
        modelo_semantico="Sentence-BERT padrão",
        nivel_rigor=req.rigor,
    )
    try:
        return analyze_sections(req.sections, config)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/analyze/full")
def analyze_with_gemini(req: AnalyzeRequest):
    api_key = _get_api_key()
    if not api_key:
        raise HTTPException(
            status_code=400,
            detail="Chave de API do Gemini não configurada no servidor. Defina GOOGLE_API_KEY no arquivo .env.",
        )

    config = AnalysisConfig(
        modo_analise="Análise detalhada",
        modelo_semantico="Sentence-BERT padrão",
        nivel_rigor=req.rigor,
    )
    try:
        result = analyze_sections(req.sections, config)
        result["gemini_report"] = _call_gemini_report(
            req.sections, result, req.rigor, api_key, req.additional_info
        )
        return result
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ── Intro checklist endpoint ───────────────────────────────────────────────────

class IntroAnalysisRequest(BaseModel):
    intro_text: str


@app.post("/api/intro-analysis")
def intro_analysis(req: IntroAnalysisRequest):
    api_key = _get_api_key()
    if not api_key:
        raise HTTPException(
            status_code=400,
            detail="Chave de API do Gemini não configurada no servidor.",
        )
    try:
        elementos = analyze_intro_checklist(req.intro_text, api_key)
        return {"elementos": elementos}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ── Document upload: segment extraction ───────────────────────────────────────

@app.post("/api/extract-segments")
async def extract_segments(
    file: UploadFile = File(...),
    propose_mapping: bool = Form(False),
):
    """Extract text and run the document-understanding pipeline for user review.

    Order: convert → clean → detect segments → (optional) propose mapping → extract
    first-page metadata → analyze the Introduction and extract its elements. The AI
    steps are optional; metadata and segments survive even if the AI step fails.
    """
    filename = file.filename or "documento"
    file_bytes = await file.read()
    api_key = _get_api_key()
    use_ai = bool(propose_mapping and api_key)

    try:
        from document_converter import convert_document_to_markdown
        from coerencia_engine import _clean_docling_markdown

        markdown = convert_document_to_markdown(filename, file_bytes)
        cleaned = _clean_docling_markdown(markdown)
        segments = detect_document_segments(cleaned)

        if use_ai:
            segments = propose_section_mapping_with_ai(segments, api_key)

        # Metadados da primeira página (não são seções acadêmicas).
        metadados = extract_document_metadata(cleaned, api_key if use_ai else None)

        # Análise prioritária da Introdução: identifica problema, objetivos, etc.
        intro_text = "\n\n".join(
            seg.get("content", "")
            for seg in segments
            if seg.get("sugerido") == "introducao" and seg.get("content")
        )
        intro_elementos = (
            analyze_intro_elements(intro_text, api_key if use_ai else None)
            if intro_text.strip()
            else []
        )

        return {
            "segments": segments,
            "metadados": metadados,
            "intro_elementos": intro_elementos,
            "markdown": markdown,
        }
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ── Document upload: analysis with user-confirmed mapping ─────────────────────

@app.post("/api/analyze-mapped")
def analyze_mapped(req: AnalyzeMappedRequest):
    config = AnalysisConfig(
        modo_analise="Análise detalhada",
        modelo_semantico="Sentence-BERT padrão",
        nivel_rigor=req.rigor,
    )
    try:
        assembled = assemble_sections_from_mapping(
            req.segments, req.user_mapping, req.intro_elementos
        )
        sections = assembled["sections"]
        result = analyze_sections(
            sections,
            config,
            referencial=assembled["referencial"],
            origem_secoes=assembled["origem_secoes"],
        )
        # Metadados corrigidos pelo usuário têm prioridade sobre a extração automática.
        result["metadados"] = req.metadados or {}

        if req.use_gemini:
            api_key = _get_api_key()
            if api_key:
                result["gemini_report"] = _call_gemini_report(
                    sections, result, req.rigor, api_key, req.additional_info
                )

        return result
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ── Legacy document endpoint (kept for Streamlit / backward compat) ────────────

@app.post("/api/analyze/document")
async def analyze_document_upload(
    file: UploadFile = File(...),
    rigor: str = Form("Médio"),
    use_gemini: bool = Form(False),
):
    filename = file.filename or "documento"
    file_bytes = await file.read()

    config = AnalysisConfig(
        modo_analise="Análise detalhada",
        modelo_semantico="Sentence-BERT padrão",
        nivel_rigor=rigor,
    )
    try:
        result = analyze_document_with_docling(filename, file_bytes, config)
        if use_gemini:
            api_key = _get_api_key()
            if api_key:
                result["gemini_report"] = _call_gemini_report(
                    result["secoes_extraidas"], result, rigor, api_key, ""
                )
        return result
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ── Gemini report helper ───────────────────────────────────────────────────────

def _call_gemini_report(
    sections: dict[str, str],
    analysis: dict,
    rigor: str,
    api_key: str,
    additional_info: str = "",
) -> str:
    from google import genai
    from google.genai import types

    igc = analysis["painel_geral"]["igc"]
    classification = analysis["painel_geral"]["classificacao"]
    evaluated = analysis["painel_geral"].get("pares_avaliados", "—")
    total = analysis["painel_geral"].get("pares_totais", "—")

    pairs_lines = "\n".join(
        f"- {p['par']}: {p['similaridade']:.2f} ({p['interpretação']})"
        for p in analysis["matriz_similaridade"]
    )
    skipped_lines = "\n".join(
        f"- {p['par']}: {p['motivo']}"
        for p in analysis.get("pares_nao_avaliados", [])
    )

    origem = analysis.get("origem_secoes", {}) or {}
    origem_labels = {
        "secao_propria": "seção própria do documento",
        "introducao": "identificado dentro da Introdução (automaticamente, confirmado pelo usuário)",
        "ausente": "ausente (não localizado em seção própria nem na Introdução)",
    }
    origem_lines = "\n".join(
        f"- {SECTION_LABELS.get(key, key)}: {origem_labels.get(value, value)}"
        for key, value in origem.items()
    )

    referencial = (analysis.get("referencial") or "").strip()
    referencial_block = (
        f"\n\nReferencial Teórico (apenas contexto — não entra nos pares nem no IGC):\n{referencial[:1500]}"
        if referencial else ""
    )

    section_order = [
        ("introducao", "Introdução"),
        ("problema", "Problema de Pesquisa"),
        ("objetivos", "Objetivos"),
        ("metodologia", "Metodologia"),
        ("resultados", "Resultados"),
        ("conclusao", "Conclusão"),
    ]
    sections_block = "\n\n".join(
        f"**{label}:**\n{sections.get(key, '').strip()[:1200]}"
        for key, label in section_order
        if sections.get(key, "").strip()
    )

    extra_block = f"\n\nInformações adicionais fornecidas pelo autor:\n{additional_info.strip()}" if additional_info.strip() else ""

    prompt = (
        f"Você é um professor universitário avaliando a coerência estrutural de um trabalho acadêmico "
        f"(TCC ou artigo científico).\n\n"
        f"IGC: {igc:.2f} — {classification} ({evaluated} de {total} pares avaliados)\n"
        f"Nível de rigor: {rigor}\n\n"
        f"Pares avaliados:\n{pairs_lines}\n"
        + (f"\nPares não avaliados (seção ausente):\n{skipped_lines}\n" if skipped_lines else "")
        + (f"\nOrigem dos elementos centrais:\n{origem_lines}\n" if origem_lines else "")
        + f"\nTextos das seções:\n{sections_block}{referencial_block}{extra_block}\n\n"
        f"Gere um diagnóstico em Markdown com:\n"
        f"1. Avaliação geral da coerência\n"
        f"2. Pares com maior e menor alinhamento, explicando o porquê\n"
        f"3. Sugestões acionáveis de melhoria\n"
        f"4. Se houver pares não avaliados, mencione o impacto da ausência dessas seções\n"
        f"5. Quando o problema ou os objetivos tiverem sido identificados dentro da Introdução "
        f"(e não em seção própria), deixe isso explícito no diagnóstico\n"
        f"Use o Referencial Teórico apenas como contexto; ele não compõe o IGC.\n"
        f"Seja direto e prático."
    )

    system = (
        "Você é um professor universitário experiente em bancas de TCC e revisão de artigos. "
        "Analise a coerência estrutural e dê feedback direto e acionável em português do Brasil. "
        "Diferencie claramente baixa coerência de informação insuficiente. "
        "Quando um elemento (problema/objetivos) foi extraído da Introdução por análise automática, "
        "trate-o como identificação automática e indique isso no texto."
    )

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(system_instruction=system),
    )
    return (getattr(response, "text", "") or "").strip()


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
