import importlib
import os
from typing import Any

import pandas as pd

os.environ.setdefault("STREAMLIT_SERVER_FILE_WATCHER_TYPE", "none")

import streamlit as st
from dotenv import load_dotenv

from coerencia_engine import AnalysisConfig, analyze_mode, generate_gemini_report, report_to_markdown

google_genai: Any = importlib.import_module("google.genai")
genai_types: Any = importlib.import_module("google.genai.types")


load_dotenv()


st.set_page_config(
    page_title="CoerencIA Chat",
    page_icon="💬",
    layout="wide",
    initial_sidebar_state="expanded",
)


CSS = """
<style>
    /* Base visual system for the entire app */
    .stApp {
        background:
            radial-gradient(circle at top left, rgba(59, 130, 246, 0.12), transparent 30%),
            radial-gradient(circle at top right, rgba(16, 185, 129, 0.10), transparent 24%),
            linear-gradient(180deg, #07111f 0%, #0b1220 100%);
        color: #e5eefb;
        font-family: "Inter", "Segoe UI", sans-serif;
    }

    .block-container {
        padding-top: 1.1rem;
        padding-bottom: 5.5rem;
        max-width: 1080px;
    }

    footer, #MainMenu {
        visibility: hidden;
    }

    .chat-title {
        font-size: 2rem;
        font-weight: 800;
        letter-spacing: -0.03em;
        color: #f8fbff;
        margin-bottom: 0.15rem;
    }

    .chat-subtitle {
        color: rgba(229, 238, 251, 0.72);
        margin-bottom: 1.4rem;
        line-height: 1.5;
    }

    /* Chat transcript readability for long academic content */
    div[data-testid="stChatMessage"] {
        border: 1px solid rgba(148, 163, 184, 0.10);
        border-radius: 20px;
        background: rgba(8, 15, 28, 0.52);
        backdrop-filter: blur(14px);
        box-shadow: 0 18px 42px rgba(2, 8, 20, 0.22);
        margin-bottom: 0.8rem;
    }

    div[data-testid="stChatMessage"] div[data-testid="stMarkdownContainer"] {
        font-size: 0.98rem;
        line-height: 1.72;
        color: rgba(233, 240, 250, 0.95);
    }

    div[data-testid="stChatMessage"] p,
    div[data-testid="stChatMessage"] li {
        margin-bottom: 0.55rem;
    }

    div[data-testid="stChatMessage"] code {
        background: rgba(15, 23, 42, 0.82);
        color: #d7ecff;
        border: 1px solid rgba(96, 165, 250, 0.18);
        border-radius: 8px;
        padding: 0.16rem 0.38rem;
        font-size: 0.92em;
    }

    div[data-testid="stChatMessage"] pre {
        background: linear-gradient(180deg, rgba(15, 23, 42, 0.96), rgba(9, 14, 26, 0.98));
        border: 1px solid rgba(96, 165, 250, 0.16);
        border-radius: 14px;
        padding: 1rem 1.1rem;
        overflow: auto;
    }

    div[data-testid="stChatMessage"] pre code {
        background: transparent;
        border: 0;
        padding: 0;
        font-size: 0.9rem;
        line-height: 1.65;
    }

    /* Stronger visual distinction for assistant-style analysis blocks */
    .coerencia-bot,
    div[data-testid="stChatMessage"]:has(svg[aria-label="assistant"]) {
        border-left: 4px solid rgba(56, 189, 248, 0.72);
        background: linear-gradient(180deg, rgba(8, 18, 34, 0.72), rgba(8, 15, 28, 0.56));
    }

    .coerencia-user,
    div[data-testid="stChatMessage"]:has(svg[aria-label="user"]) {
        border-left: 4px solid rgba(148, 163, 184, 0.56);
        background: linear-gradient(180deg, rgba(10, 17, 31, 0.70), rgba(8, 15, 28, 0.50));
    }

    .stChatMessage {
        border-radius: 18px;
    }

    /* Keep the input docked and visually separated from the transcript */
    .stChatInput {
        border-top: 1px solid rgba(148, 163, 184, 0.18);
        background: rgba(7, 17, 31, 0.88);
        backdrop-filter: blur(10px);
    }

    .stChatInput textarea {
        color: #f3f7ff !important;
        caret-color: #60a5fa;
        line-height: 1.55;
        font-size: 0.98rem;
    }

    .stChatInput textarea::placeholder {
        color: rgba(203, 213, 225, 0.62);
    }

    /* Glassmorphism for sidebar and native controls */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, rgba(8, 15, 28, 0.95), rgba(10, 17, 31, 0.98));
        border-right: 1px solid rgba(148, 163, 184, 0.10);
    }

    .sidebar-note {
        color: rgba(229, 238, 251, 0.7);
        font-size: 0.92rem;
        line-height: 1.5;
    }

    /* File uploader styling for PDF/DOCX intake */
    section[data-testid="stFileUploaderDropzone"] {
        background: rgba(10, 17, 31, 0.74);
        border: 1px solid rgba(148, 163, 184, 0.18);
        border-radius: 18px;
        padding: 0.9rem 1rem;
        backdrop-filter: blur(12px);
    }

    section[data-testid="stFileUploaderDropzone"]:hover {
        border-color: rgba(96, 165, 250, 0.45);
        box-shadow: 0 0 0 1px rgba(96, 165, 250, 0.15);
    }

    section[data-testid="stFileUploaderDropzone"] button {
        background: linear-gradient(135deg, rgba(37, 99, 235, 0.92), rgba(14, 165, 233, 0.88));
        color: #f8fbff;
        border: 0;
        border-radius: 999px;
        font-weight: 700;
    }

    /* Buttons, radios and sliders should share the same premium tone */
    .stButton > button {
        background: linear-gradient(135deg, rgba(37, 99, 235, 0.92), rgba(14, 165, 233, 0.88));
        color: #f8fbff;
        border: 1px solid rgba(96, 165, 250, 0.24);
        border-radius: 14px;
        padding: 0.62rem 1rem;
        font-weight: 700;
        box-shadow: 0 10px 30px rgba(37, 99, 235, 0.18);
    }

    .stButton > button:hover {
        transform: translateY(-1px);
        border-color: rgba(125, 211, 252, 0.42);
    }

    div[data-baseweb="radio"] {
        background: rgba(10, 17, 31, 0.60);
        border: 1px solid rgba(148, 163, 184, 0.14);
        border-radius: 16px;
        padding: 0.4rem 0.65rem;
    }

    div[data-baseweb="radio"] label {
        color: rgba(233, 240, 250, 0.92);
    }

    div[data-baseweb="slider"] [role="slider"] {
        background: #dbeafe;
        border: 2px solid rgba(96, 165, 250, 0.65);
        box-shadow: 0 0 0 4px rgba(59, 130, 246, 0.14);
    }

    div[data-baseweb="slider"] div[aria-hidden="true"] {
        background: linear-gradient(90deg, rgba(34, 197, 94, 0.95), rgba(59, 130, 246, 0.95));
    }

    /* Dataframe styling for similarity matrices and diagnostics */
    [data-testid="stDataFrame"] {
        background: rgba(8, 15, 28, 0.62);
        border: 1px solid rgba(148, 163, 184, 0.14);
        border-radius: 18px;
        overflow: hidden;
        backdrop-filter: blur(12px);
    }

    [data-testid="stDataFrame"] * {
        font-size: 0.92rem;
    }

    [data-testid="stDataFrame"] thead tr th {
        background: rgba(15, 23, 42, 0.95);
        color: #eaf2ff;
        border-bottom: 1px solid rgba(148, 163, 184, 0.16);
    }

    [data-testid="stDataFrame"] tbody tr {
        color: rgba(233, 240, 250, 0.94);
    }

    [data-testid="stDataFrame"] tbody tr:hover {
        background: rgba(37, 99, 235, 0.10);
    }

    /* Semantic coherence tokens for similarity highlights */
    .coerencia-forte {
        color: #4ade80;
        background: rgba(34, 197, 94, 0.12);
        border: 1px solid rgba(34, 197, 94, 0.24);
        border-radius: 999px;
        padding: 0.16rem 0.55rem;
        font-weight: 700;
    }

    .coerencia-moderada {
        color: #facc15;
        background: rgba(250, 204, 21, 0.12);
        border: 1px solid rgba(250, 204, 21, 0.24);
        border-radius: 999px;
        padding: 0.16rem 0.55rem;
        font-weight: 700;
    }

    .coerencia-fraca {
        color: #f87171;
        background: rgba(248, 113, 113, 0.12);
        border: 1px solid rgba(248, 113, 113, 0.24);
        border-radius: 999px;
        padding: 0.16rem 0.55rem;
        font-weight: 700;
    }

    /* Subtle, modern scrollbars for dark mode */
    * {
        scrollbar-width: thin;
        scrollbar-color: rgba(148, 163, 184, 0.42) rgba(7, 17, 31, 0.28);
    }

    *::-webkit-scrollbar {
        width: 10px;
        height: 10px;
    }

    *::-webkit-scrollbar-track {
        background: rgba(7, 17, 31, 0.28);
    }

    *::-webkit-scrollbar-thumb {
        background: linear-gradient(180deg, rgba(71, 85, 105, 0.92), rgba(100, 116, 139, 0.82));
        border: 2px solid rgba(7, 17, 31, 0.28);
        border-radius: 999px;
    }

    *::-webkit-scrollbar-thumb:hover {
        background: linear-gradient(180deg, rgba(96, 165, 250, 0.95), rgba(56, 189, 248, 0.92));
    }
</style>
"""


st.markdown(CSS, unsafe_allow_html=True)


def init_state() -> None:
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "analysis_payload" not in st.session_state:
        st.session_state.analysis_payload = None
    if "analysis_report" not in st.session_state:
        st.session_state.analysis_report = ""
    if "analysis_pair_reports" not in st.session_state:
        st.session_state.analysis_pair_reports = []


def get_api_key() -> str:
    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not api_key:
        st.error("Defina GOOGLE_API_KEY ou GEMINI_API_KEY no arquivo .env antes de iniciar a aplicação.")
        st.stop()
    assert api_key is not None
    return api_key


def to_gemini_history(messages: list[dict[str, str]]) -> list[dict[str, Any]]:
    history: list[dict[str, Any]] = []
    for message in messages:
        if message["role"] == "user":
            history.append({"role": "user", "parts": [{"text": message["content"]}]})
        elif message["role"] == "assistant":
            history.append({"role": "model", "parts": [{"text": message["content"]}]})
    return history


def render_messages() -> None:
    for message in st.session_state.messages:
        avatar = "🧑" if message["role"] == "user" else "✨"
        with st.chat_message(message["role"], avatar=avatar):
            st.markdown(message["content"])


def render_single_analysis(analysis: dict[str, Any]) -> None:
    panel = analysis["painel_geral"]
    col1, col2, col3 = st.columns(3)
    col1.metric("IGC", f"{panel['igc']:.2f}")
    col2.metric("Similaridade Média", f"{panel['similaridade_media']:.2f}")
    col3.metric("Classificação", panel["classificacao"])

    if analysis["avisos"]:
        for warning in analysis["avisos"]:
            st.warning(warning)

    st.markdown("### Matriz de Similaridade")
    matrix_df = pd.DataFrame(analysis["matriz_similaridade"])
    matrix_df = matrix_df.rename(
        columns={
            "par": "Par Estratégico",
            "similaridade": "Similaridade",
            "interpretação": "Interpretação",
            "faixa": "Faixa",
            "classe_css": "Classe CSS",
        }
    )
    st.dataframe(matrix_df, use_container_width=True, hide_index=True)

    st.markdown("### Trechos Críticos e Sugestões")
    if not analysis["trechos_criticos"]:
        st.markdown("<span class='coerencia-forte'>Sem desalinhamentos críticos detectados.</span>", unsafe_allow_html=True)
        return

    for idx, critical in enumerate(analysis["trechos_criticos"], start=1):
        with st.expander(f"{idx}. {critical['par']} | score do par: {critical['score_par']:.2f}", expanded=idx == 1):
            st.markdown(f"**Trecho A:** {critical['trecho_a']}")
            st.markdown(f"**Trecho B:** {critical['trecho_b']}")
            st.markdown(critical["sugestao"])


def render_analysis_panels(payload: dict[str, Any]) -> None:
    st.markdown("## Painel Geral de Coerência")
    if payload["tipo_resultado"] == "single":
        render_single_analysis(payload["analise"])
        return

    st.markdown("### Comparação entre Versões")
    base = payload["analise_base"]["painel_geral"]
    revised = payload["analise_revisada"]["painel_geral"]
    comparativo = payload["comparativo"]

    col1, col2, col3 = st.columns(3)
    col1.metric("IGC Versão Base", f"{base['igc']:.2f}")
    col2.metric("IGC Versão Revisada", f"{revised['igc']:.2f}")
    col3.metric("Delta IGC", f"{comparativo['delta_igc']:+.2f}")

    deltas_df = pd.DataFrame(comparativo["deltas_por_par"]).rename(columns={"par": "Par Estratégico", "delta": "Delta"})
    st.markdown("### Delta de Similaridade por Par")
    st.dataframe(deltas_df, use_container_width=True, hide_index=True)

    st.markdown("### Matriz e Alertas da Versão Revisada")
    render_single_analysis(payload["analise_revisada"])


def render_pair_reports() -> None:
    if not st.session_state.analysis_pair_reports:
        return
    st.markdown("### Interpretação Qualitativa (Gemini)")
    for item in st.session_state.analysis_pair_reports:
        with st.expander(item["par"]):
            st.markdown(item["diagnostico"])


def stream_answer(prompt: str) -> str:
    client = google_genai.Client(api_key=get_api_key())

    history = to_gemini_history(st.session_state.messages[:-1])
    contents = [
        *history,
        {"role": "user", "parts": [{"text": prompt}]},
    ]
    config = genai_types.GenerateContentConfig(
        system_instruction=(
            "Você é um assistente de IA útil, direto e claro. "
            "Responda em português do Brasil, use Markdown quando fizer sentido e preserve blocos de código."
        )
    )

    full_response = ""
    response_placeholder = st.empty()

    try:
        for chunk in client.models.generate_content_stream(
            model="gemini-2.5-flash",
            contents=contents,
            config=config,
        ):
            text = getattr(chunk, "text", "") or ""
            if text:
                full_response += text
                response_placeholder.markdown(full_response + "▌")
        response_placeholder.markdown(full_response if full_response else "Não consegui gerar uma resposta agora.")
    except Exception as exc:
        response_placeholder.error(f"Erro ao consultar o Gemini: {exc}")
        return ""

    return full_response.strip()


init_state()


with st.sidebar:
    st.markdown("### CoerencIA")
    st.markdown(
        "<p class='sidebar-note'>Motor de diagnóstico acadêmico com SBERT, IGC e detecção de desalinhamentos estruturais.</p>",
        unsafe_allow_html=True,
    )

    modo_analise = st.radio(
        "Modo de Análise",
        ["Análise básica", "Análise detalhada", "Comparação entre versões"],
        index=1,
    )
    modelo_semantico = st.radio(
        "Modelo Semântico",
        ["Sentence-BERT padrão", "Modelo Customizado"],
        index=0,
    )
    nivel_rigor = st.select_slider("Nível de Rigor", options=["Baixo", "Médio", "Alto"], value="Médio")

    modelo_customizado = None
    if modelo_semantico == "Modelo Customizado":
        modelo_customizado = st.text_input(
            "Nome/caminho do modelo customizado",
            value=os.getenv("COERENCIA_CUSTOM_MODEL", ""),
            placeholder="ex: sentence-transformers/all-MiniLM-L6-v2",
        )

    arquivo_principal = st.file_uploader("Versão principal do TCC (PDF ou DOCX)", type=["pdf", "docx"])

    arquivo_secundario = None
    if modo_analise == "Comparação entre versões":
        arquivo_secundario = st.file_uploader("Versão revisada para comparação", type=["pdf", "docx"])

    diagnosticar = st.button("Executar diagnóstico CoerencIA", use_container_width=True, type="primary")

    if diagnosticar:
        if arquivo_principal is None:
            st.error("Envie o arquivo principal para iniciar a análise.")
        elif modo_analise == "Comparação entre versões" and arquivo_secundario is None:
            st.error("No modo de comparação, envie também a versão revisada.")
        else:
            config = AnalysisConfig(
                modo_analise=modo_analise,
                modelo_semantico=modelo_semantico,
                nivel_rigor=nivel_rigor,
                modelo_customizado=modelo_customizado or None,
            )
            try:
                with st.spinner("Processando documento, gerando embeddings e calculando similaridade..."):
                    payload = analyze_mode(
                        config=config,
                        primary_file_name=arquivo_principal.name,
                        primary_file_bytes=arquivo_principal.getvalue(),
                        secondary_file_name=arquivo_secundario.name if arquivo_secundario else None,
                        secondary_file_bytes=arquivo_secundario.getvalue() if arquivo_secundario else None,
                    )
                with st.spinner("Gerando relatório qualitativo com Gemini 2.5 Flash..."):
                    gemini_pack = generate_gemini_report(payload=payload, config=config, api_key=get_api_key())
                st.session_state.analysis_payload = payload
                st.session_state.analysis_report = gemini_pack.get("relatorio_markdown") or report_to_markdown(payload)
                st.session_state.analysis_pair_reports = gemini_pack.get("diagnosticos_por_par", [])
                st.session_state.messages.append(
                    {
                        "role": "assistant",
                        "content": st.session_state.analysis_report,
                    }
                )
                st.success("Diagnóstico concluído e enviado para o chat.")
            except Exception as exc:
                st.error(f"Erro no motor de análise: {exc}")

    if st.button("Limpar conversa", use_container_width=True):
        st.session_state.messages = []
        st.session_state.analysis_payload = None
        st.session_state.analysis_report = ""
        st.session_state.analysis_pair_reports = []
        st.rerun()


st.markdown("<div class='chat-title'>CoerencIA Chat</div>", unsafe_allow_html=True)
st.markdown(
    "<div class='chat-subtitle'>Interface estilo ChatGPT com streaming real do Gemini, memória da sessão e renderização Markdown.</div>",
    unsafe_allow_html=True,
)


if st.session_state.analysis_payload is not None:
    render_analysis_panels(st.session_state.analysis_payload)
    render_pair_reports()
    st.markdown("---")


if not st.session_state.messages:
    with st.chat_message("assistant", avatar="✨"):
        st.markdown("Olá. Posso ajudar com código, arquitetura, debugging ou qualquer tarefa de IA.")


render_messages()


prompt = st.chat_input("Digite sua mensagem...", max_chars=8000)

if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})

    with st.chat_message("user", avatar="🧑"):
        st.markdown(prompt)

    with st.chat_message("assistant", avatar="✨"):
        answer = stream_answer(prompt)

    if answer:
        st.session_state.messages.append({"role": "assistant", "content": answer})