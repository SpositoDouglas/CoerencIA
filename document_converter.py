from __future__ import annotations

import os
import tempfile
from pathlib import Path

SUPPORTED_EXTENSIONS = {".pdf", ".docx"}


def convert_document_to_markdown(filename: str, file_bytes: bytes) -> str:
    """Convert a PDF or DOCX to Markdown using Docling.

    OCR is disabled — TCCs digitais não precisam de OCR e isso evita o
    download dos modelos RapidOCR do modelscope.cn.
    """
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"Formato não suportado: '{suffix}'. Envie um arquivo PDF ou DOCX."
        )

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(file_bytes)
        tmp_path = tmp.name

    try:
        pipeline_options = PdfPipelineOptions(do_ocr=False)
        converter = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
            }
        )
        result = converter.convert(tmp_path)
        markdown = result.document.export_to_markdown()
        if not markdown.strip():
            raise ValueError(
                "O Docling não extraiu texto do arquivo. "
                "Verifique se o PDF não é um documento escaneado (imagem)."
            )
        return markdown
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
