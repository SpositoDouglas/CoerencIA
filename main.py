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
    AnalysisConfig,
    analyze_document_with_docling,
    analyze_intro_checklist,
    analyze_sections,
    detect_document_segments,
    merge_confirmed_segments,
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
    filename = file.filename or "documento"
    file_bytes = await file.read()

    try:
        from document_converter import convert_document_to_markdown
        from coerencia_engine import _clean_docling_markdown

        markdown = convert_document_to_markdown(filename, file_bytes)
        cleaned = _clean_docling_markdown(markdown)
        segments = detect_document_segments(cleaned)

        if propose_mapping and _get_api_key():
            segments = propose_section_mapping_with_ai(segments, _get_api_key())

        return {"segments": segments, "markdown": markdown}
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
        sections = merge_confirmed_segments(req.segments, req.user_mapping)
        result = analyze_sections(sections, config)

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
        f"Você é um professor universitário avaliando a coerência estrutural de um TCC.\n\n"
        f"IGC: {igc:.2f} — {classification} ({evaluated} de {total} pares avaliados)\n"
        f"Nível de rigor: {rigor}\n\n"
        f"Pares avaliados:\n{pairs_lines}\n"
        + (f"\nPares não avaliados (seção ausente):\n{skipped_lines}\n" if skipped_lines else "")
        + f"\nTextos das seções:\n{sections_block}{extra_block}\n\n"
        f"Gere um diagnóstico em Markdown com:\n"
        f"1. Avaliação geral da coerência\n"
        f"2. Pares com maior e menor alinhamento, explicando o porquê\n"
        f"3. Sugestões acionáveis de melhoria\n"
        f"4. Se houver pares não avaliados, mencione o impacto da ausência dessas seções\n"
        f"Seja direto e prático."
    )

    system = (
        "Você é um professor universitário experiente em bancas de TCC. "
        "Analise a coerência estrutural e dê feedback direto e acionável em português do Brasil. "
        "Diferencie claramente baixa coerência de informação insuficiente."
    )

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(system_instruction=system),
    )
    return (getattr(response, "text", "") or "").strip()


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
