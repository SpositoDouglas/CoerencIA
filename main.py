from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from coerencia_engine import AnalysisConfig, analyze_document_with_docling, analyze_sections

BASE_DIR = Path(__file__).parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(title="CoerencIA")


class AnalyzeRequest(BaseModel):
    sections: dict[str, str]
    rigor: str = "Médio"
    gemini_api_key: Optional[str] = None
    use_gemini: bool = False


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


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
    api_key = req.gemini_api_key or os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=400, detail="Chave de API do Gemini não encontrada.")

    config = AnalysisConfig(
        modo_analise="Análise detalhada",
        modelo_semantico="Sentence-BERT padrão",
        nivel_rigor=req.rigor,
    )
    try:
        result = analyze_sections(req.sections, config)
        result["gemini_report"] = _call_gemini_report(req.sections, result, req.rigor, api_key)
        return result
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def _call_gemini_report(
    sections: dict[str, str],
    analysis: dict,
    rigor: str,
    api_key: str,
) -> str:
    from google import genai
    from google.genai import types

    igc = analysis["painel_geral"]["igc"]
    classification = analysis["painel_geral"]["classificacao"]

    pairs_lines = "\n".join(
        f"- {p['par']}: {p['similaridade']:.2f} ({p['interpretação']})"
        for p in analysis["matriz_similaridade"]
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

    prompt = (
        f"Você é um professor universitário avaliando a coerência estrutural de um TCC.\n\n"
        f"IGC: {igc:.2f} — {classification}\n"
        f"Nível de rigor: {rigor}\n\n"
        f"Similaridade semântica entre pares:\n{pairs_lines}\n\n"
        f"Textos das seções:\n{sections_block}\n\n"
        f"Gere um diagnóstico em português do Brasil em Markdown com:\n"
        f"1. Avaliação geral da coerência do trabalho\n"
        f"2. Pares com maior e menor alinhamento, explicando o porquê\n"
        f"3. Sugestões específicas e acionáveis de melhoria\n"
        f"Seja direto e prático."
    )

    system = (
        "Você é um professor universitário experiente em bancas de TCC. "
        "Analise a coerência estrutural e dê feedback direto e acionável em português do Brasil."
    )

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(system_instruction=system),
    )
    return (getattr(response, "text", "") or "").strip()


@app.post("/api/analyze/document")
async def analyze_document_upload(
    file: UploadFile = File(...),
    rigor: str = Form("Médio"),
    gemini_api_key: Optional[str] = Form(None),
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
            api_key = gemini_api_key or os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
            if api_key:
                result["gemini_report"] = _call_gemini_report(
                    result["secoes_extraidas"], result, rigor, api_key
                )
        return result
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
