'use strict';

// ── Constantes de categorias ───────────────────────────────────────────────────

const SECTION_OPTIONS = [
  { value: 'introducao',  label: 'Introdução' },
  { value: 'problema',    label: 'Problema de Pesquisa' },
  { value: 'objetivos',   label: 'Objetivos' },
  { value: 'referencial', label: 'Referencial Teórico' },
  { value: 'metodologia', label: 'Metodologia' },
  { value: 'resultados',  label: 'Resultados' },
  { value: 'conclusao',   label: 'Conclusão' },
  { value: 'ignorar',     label: 'Ignorar este trecho' },
];

const SECTION_LABELS = Object.fromEntries(SECTION_OPTIONS.map(o => [o.value, o.label]));

// Seções acadêmicas que o usuário pode preencher manualmente (além da Introdução
// e do Referencial Teórico, que têm etapas próprias).
const MANUAL_SECTIONS = [
  { key: 'problema',    label: 'Problema de Pesquisa', desc: 'Defina a lacuna e formule a questão central que o trabalho responde.' },
  { key: 'objetivos',   label: 'Objetivos',            desc: 'Objetivo geral e objetivos específicos. Use verbos de ação.' },
  { key: 'metodologia', label: 'Metodologia',          desc: 'Abordagem, métodos, técnicas e procedimentos adotados.' },
  { key: 'resultados',  label: 'Resultados',           desc: 'Resultados obtidos, análises e discussões.' },
  { key: 'conclusao',   label: 'Conclusão',            desc: 'Síntese das contribuições, retomada dos objetivos e limitações.' },
];

// Categorias de elementos da Introdução (para confirmar/alterar a classificação).
const INTRO_ELEMENT_OPTIONS = [
  { value: 'contextualizacao',      label: 'Contextualização do tema' },
  { value: 'problema',              label: 'Problema / questão de pesquisa' },
  { value: 'lacuna',                label: 'Lacuna identificada' },
  { value: 'justificativa',         label: 'Justificativa / relevância' },
  { value: 'objetivo_geral',        label: 'Objetivo geral' },
  { value: 'objetivos_especificos', label: 'Objetivos específicos' },
  { value: 'proposta',              label: 'Proposta do trabalho' },
  { value: 'contribuicao',          label: 'Contribuição esperada' },
  { value: 'metodologia',           label: 'Indicação de metodologia' },
];
const INTRO_ELEMENT_LABELS = Object.fromEntries(INTRO_ELEMENT_OPTIONS.map(o => [o.value, o.label]));

// Tipos de elemento da Introdução que alimentam Problema e Objetivos.
const PROBLEM_TYPES = ['problema', 'lacuna'];
const OBJETIVO_TYPES = ['objetivo_geral', 'objetivos_especificos', 'proposta'];

// ── Estado ──────────────────────────────────────────────────────────────────────
// phase: 'ai-decision' → 'mode-select' → 'manual' | 'upload'
// manual: state.manual.phase = metadata|intro|intro-elements|ask-referencial|
//         referencial|pick-section|section|review|loading|results
// upload: uploadStep 0=file, 1=config, 2=loading-extract, 3=mapping, 4=loading-analyze, 5=results

function freshManual() {
  return {
    phase: 'metadata',
    titulo: '',
    autores: '',
    introducao: '',
    introElementos: [],
    introMetodo: null,
    introErro: null,
    introLoading: false,
    secoes: { problema: '', objetivos: '', metodologia: '', resultados: '', conclusao: '' },
    referencial: { titulo: '', subsecoes: [] },
    preencherReferencial: false,
    outras: [],
    current: null,   // { tipo: 'problema'|...|'outra', outraIdx }
  };
}

const state = {
  phase: 'ai-decision',
  useAI: null,
  aiAvailable: null,

  manual: freshManual(),

  // Upload
  uploadStep: 0,
  uploadFile: null,
  documentSegments: null,
  sectionMapping: {},
  metadados: { titulo: '', autores: [], extraido_por: '' },
  introElementos: [],

  // Shared
  additionalInfo: '',
  rigor: 'Médio',
  results: null,
  error: null,
};

// ── Boot ────────────────────────────────────────────────────────────────────────

async function checkAIAvailability() {
  try {
    const res = await fetch('/api/check-ai');
    if (res.ok) state.aiAvailable = (await res.json()).available;
  } catch (_) {
    state.aiAvailable = false;
  }
  render();
}

// ── Render dispatcher ─────────────────────────────────────────────────────────

function render() {
  const app = document.getElementById('app');
  const html = (() => {
    if (state.phase === 'ai-decision') return renderAIDecisionPage();
    if (state.phase === 'mode-select') return renderModePage();

    if (state.phase === 'manual') {
      switch (state.manual.phase) {
        case 'metadata':        return renderManualMetadata();
        case 'intro':           return renderManualIntro();
        case 'intro-elements':  return renderManualIntroElements();
        case 'ask-referencial': return renderManualAskReferencial();
        case 'referencial':     return renderManualReferencial();
        case 'pick-section':    return renderManualPickSection();
        case 'section':         return renderManualSection();
        case 'review':          return renderManualReview();
        case 'loading':         return renderLoadingPage();
        default:                return renderResultsPage();
      }
    }

    // upload
    switch (state.uploadStep) {
      case 0: return renderUploadFilePage();
      case 1: return renderUploadConfigPage();
      case 2: return renderLoadingPage();
      case 3: return renderMappingReviewPage();
      case 4: return renderLoadingPage();
      default: return renderResultsPage();
    }
  })();
  app.innerHTML = html;
  attachHandlers();
}

// ── Header ────────────────────────────────────────────────────────────────────

function renderHeader() {
  return `
    <div class="header">
      <h1>CoerencIA</h1>
      <p>Análise automatizada de coerência estrutural em trabalhos acadêmicos</p>
    </div>`;
}

// ── AI Decision page ──────────────────────────────────────────────────────────

function renderAIDecisionPage() {
  const canUseAI = state.aiAvailable !== false;
  const aiUnavailableNote = state.aiAvailable === false ? `
    <div class="warning" style="margin-top:1rem">
      Nenhuma chave de API Gemini foi encontrada no servidor (.env). A análise qualitativa com IA não está disponível neste ambiente — a identificação de elementos usará regras locais.
    </div>` : '';

  return `
    <div class="container">
      ${renderHeader()}
      <div class="card">
        <div class="step-badge">Configuração inicial</div>
        <div class="step-title">Análise qualitativa com IA?</div>
        <div class="step-desc">
          Você deseja usar o Gemini para gerar um diagnóstico interpretativo e refinar a identificação de elementos, além da análise semântica com SBERT?
        </div>
        <div class="ai-choice-grid">
          <button class="ai-choice-card ${!canUseAI ? 'disabled' : ''}" id="btn-use-ai" ${!canUseAI ? 'disabled' : ''}>
            <div class="ai-choice-title">Sim, usar IA</div>
            <div class="ai-choice-desc">SBERT + Gemini. Refina a identificação de elementos da Introdução e gera diagnóstico textual por par estratégico.</div>
            ${!canUseAI ? '<div class="ai-choice-unavail">Chave não configurada no servidor</div>' : ''}
          </button>
          <button class="ai-choice-card" id="btn-no-ai">
            <div class="ai-choice-title">Não, apenas SBERT</div>
            <div class="ai-choice-desc">Análise semântica completa com embeddings, IGC, matriz de similaridade e identificação local de elementos. Sem chamadas externas.</div>
          </button>
        </div>
        ${aiUnavailableNote}
      </div>
    </div>`;
}

// ── Mode selection page ───────────────────────────────────────────────────────

function renderModePage() {
  const aiTag = state.useAI ? ' <span class="ai-tag">+ IA</span>' : '';
  return `
    <div class="container">
      ${renderHeader()}
      <div class="mode-grid">
        <button class="mode-card" id="btn-mode-manual">
          <div class="mode-title">Preenchimento Manual${aiTag}</div>
          <div class="mode-desc">Informe metadados, a Introdução (com análise de elementos), o Referencial Teórico e as demais seções na ordem do documento.</div>
        </button>
        <button class="mode-card" id="btn-mode-upload">
          <div class="mode-title">Upload de Documento${aiTag}</div>
          <div class="mode-desc">Envie um PDF ou DOCX para extração automática com Docling e revisão do mapeamento das seções antes da análise.</div>
        </button>
      </div>
      <div style="text-align:center;margin-top:1rem">
        <button class="btn btn-ghost" id="btn-back-ai">← Voltar</button>
      </div>
    </div>`;
}

// ── Manual: metadata ────────────────────────────────────────────────────────────

function renderManualMetadata() {
  const m = state.manual;
  return `
    <div class="container">
      ${renderHeader()}
      <div class="card">
        <div class="step-badge">Metadados do documento</div>
        <div class="step-title">Título e autores</div>
        <div class="step-desc">
          Opcional. Título e autores são apenas metadados — não geram embeddings nem entram no cálculo do IGC.
          Você pode editá-los a qualquer momento na revisão final.
        </div>
        <label class="meta-field">
          <span class="meta-field-label">Título do trabalho</span>
          <input type="text" id="m-titulo" class="meta-input" value="${escHtml(m.titulo)}" placeholder="Título do TCC ou artigo">
        </label>
        <label class="meta-field">
          <span class="meta-field-label">Autor(es) <small>(separe por ponto e vírgula)</small></span>
          <input type="text" id="m-autores" class="meta-input" value="${escHtml(m.autores)}" placeholder="Nome 1; Nome 2">
        </label>
        <div class="nav-row">
          <button class="btn btn-ghost" id="btn-manual-back-mode">← Voltar</button>
          <button class="btn btn-primary" id="btn-manual-to-intro">Continuar para a Introdução →</button>
        </div>
      </div>
    </div>`;
}

// ── Manual: introduction ──────────────────────────────────────────────────────

function renderManualIntro() {
  const m = state.manual;
  const canAnalyze = m.introducao.trim().length >= 40;
  return `
    <div class="container">
      ${renderHeader()}
      <div class="card">
        <div class="step-badge">Seção inicial · Introdução</div>
        <div class="step-title">Introdução</div>
        <div class="step-desc">
          Cole o texto integral da Introdução. Em seguida, o sistema fará uma análise dos elementos presentes
          (contextualização, problema, lacuna, objetivos, justificativa…) para você confirmar.
        </div>
        <textarea id="m-introducao" class="section-textarea" rows="11"
          placeholder="Cole aqui o texto da Introdução...">${escHtml(m.introducao)}</textarea>
        <div class="char-count"><span id="m-intro-cnt">${m.introducao.length}</span> caracteres</div>
        <div class="nav-row">
          <button class="btn btn-ghost" id="btn-manual-back-metadata">← Voltar</button>
          <button class="btn btn-primary" id="btn-manual-analyze-intro" ${canAnalyze ? '' : 'disabled'}>Analisar Introdução →</button>
        </div>
        ${!canAnalyze ? '<div class="char-count" style="text-align:left;margin-top:.5rem">Informe ao menos algumas frases para a análise.</div>' : ''}
      </div>
    </div>`;
}

// ── Manual: intro elements review ─────────────────────────────────────────────

function renderManualIntroElements() {
  const m = state.manual;
  if (m.introLoading) {
    return `
      <div class="container">
        ${renderHeader()}
        <div class="card loading-wrap">
          <div class="spinner"></div>
          <div>Analisando a Introdução…</div>
          <div class="loading-sub">${state.useAI ? 'Identificando elementos com IA…' : 'Identificando elementos por regras locais…'}</div>
        </div>
      </div>`;
  }

  const metodoTag = m.introMetodo === 'ia'
    ? '<span class="ai-suggestion-tag">identificado por IA</span>'
    : '<span class="ai-suggestion-tag">identificado por regras locais</span>';

  const erroBanner = m.introErro ? `<div class="warning">${escHtml(m.introErro)}</div>` : '';

  const items = m.introElementos.map((el, i) => {
    const conf = el.confianca || 'media';
    const confCls = conf === 'alta' ? 'conf-alta' : conf === 'media' ? 'conf-media' : conf === 'baixa' ? 'conf-baixa' : 'conf-manual';
    const catOpts = INTRO_ELEMENT_OPTIONS.map(o =>
      `<option value="${o.value}" ${el.tipo === o.value ? 'selected' : ''}>${o.label}</option>`
    ).join('');
    const trechoHtml = el.manual
      ? `<textarea class="intro-trecho-input" data-el-trecho="${i}" rows="2" placeholder="Cole o trecho original da Introdução…">${escHtml(el.trecho || '')}</textarea>`
      : `<div class="intro-element-trecho">"${escHtml(el.trecho || '')}"</div>`;
    return `
      <div class="intro-element ${el.usar ? '' : 'rejected'}">
        <label class="intro-element-check"><input type="checkbox" data-el-usar="${i}" ${el.usar ? 'checked' : ''}></label>
        <div class="intro-element-body">
          <div class="intro-element-head">
            <select class="intro-cat-select" data-el-cat="${i}">${catOpts}</select>
            <span class="conf-badge ${confCls}">confiança: ${conf}</span>
            <button class="mini-btn-danger" data-el-remove="${i}" title="Remover">remover</button>
          </div>
          ${trechoHtml}
          ${el.localizacao ? `<div class="intro-element-loc">${escHtml(el.localizacao)}</div>` : ''}
        </div>
      </div>`;
  }).join('');

  const emptyMsg = m.introElementos.length === 0
    ? '<p style="color:var(--text-muted);font-size:.88rem">Nenhum elemento identificado automaticamente. Adicione e classifique manualmente os trechos relevantes da Introdução.</p>'
    : '';

  return `
    <div class="container">
      ${renderHeader()}
      <div class="card">
        <div class="step-badge">Análise da Introdução ${metodoTag}</div>
        <div class="step-title">Elementos identificados</div>
        <div class="step-desc">
          Trechos originais da Introdução. Confirme, rejeite (desmarque) ou altere a categoria.
          Um mesmo trecho pode ser adicionado em mais de uma categoria. Quando não houver seção própria
          de Problema ou Objetivos, os elementos confirmados aqui serão usados nos pares correspondentes.
        </div>
        ${erroBanner}
        <div class="intro-elements-block">${items}${emptyMsg}</div>
        <button class="btn btn-ghost btn-sm" id="btn-add-intro-el">+ Adicionar elemento manualmente</button>

        <div class="config-label" style="margin-top:1.5rem">Informações complementares</div>
        <textarea id="m-additional" class="section-textarea additional-textarea" rows="3"
          placeholder="Contexto adicional sobre o tema, problema ou objetivos para apoiar o relatório qualitativo…">${escHtml(state.additionalInfo)}</textarea>

        <div class="nav-row">
          <button class="btn btn-ghost" id="btn-manual-back-intro">← Editar Introdução</button>
          <button class="btn btn-primary" id="btn-manual-after-intro">Continuar →</button>
        </div>
      </div>
    </div>`;
}

// ── Manual: ask referencial ───────────────────────────────────────────────────

function renderManualAskReferencial() {
  return `
    <div class="container">
      ${renderHeader()}
      <div class="card">
        <div class="step-badge">Estrutura do documento</div>
        <div class="step-title">A próxima seção é o Referencial Teórico?</div>
        <div class="step-desc">
          Categorias equivalentes contam como Referencial Teórico: Fundamentação Teórica, Revisão de Literatura,
          Revisão Bibliográfica, Base Teórica, Estado da Arte, Trabalhos Relacionados, Referencial Conceitual,
          Background, Theoretical Framework, Literature Review, Related Work.
        </div>
        <div class="ai-choice-grid">
          <button class="ai-choice-card" id="btn-ref-yes">
            <div class="ai-choice-title">Sim, preencher Referencial Teórico</div>
            <div class="ai-choice-desc">Abre uma etapa para informar o título original usado e uma ou mais subseções.</div>
          </button>
          <button class="ai-choice-card" id="btn-ref-no">
            <div class="ai-choice-title">Não, continuar para outra seção</div>
            <div class="ai-choice-desc">Você escolherá qual seção preencher em seguida.</div>
          </button>
        </div>
        <div class="nav-row">
          <button class="btn btn-ghost" id="btn-manual-back-elements">← Voltar</button>
          <span></span>
        </div>
      </div>
    </div>`;
}

// ── Manual: referencial editor ────────────────────────────────────────────────

function renderManualReferencial() {
  const m = state.manual;
  const subs = m.referencial.subsecoes;

  const subRows = subs.map((s, i) => `
    <div class="subsec-card">
      <div class="subsec-head">
        <span class="subsec-index">Subseção ${i + 1}</span>
        <div class="subsec-actions">
          <button class="mini-btn" data-sub-up="${i}" ${i === 0 ? 'disabled' : ''} title="Subir">↑</button>
          <button class="mini-btn" data-sub-down="${i}" ${i === subs.length - 1 ? 'disabled' : ''} title="Descer">↓</button>
          <button class="mini-btn-danger" data-sub-remove="${i}" title="Remover">remover</button>
        </div>
      </div>
      <div class="subsec-fields">
        <input type="text" class="meta-input subsec-num" data-sub-num="${i}" value="${escHtml(s.numeracao || '')}" placeholder="Nº (ex.: 2.1)">
        <input type="text" class="meta-input subsec-titulo" data-sub-titulo="${i}" value="${escHtml(s.titulo || '')}" placeholder="Título original da subseção">
      </div>
      <textarea class="section-textarea subsec-conteudo" data-sub-conteudo="${i}" rows="4"
        placeholder="Conteúdo desta subseção…">${escHtml(s.conteudo || '')}</textarea>
    </div>`).join('');

  return `
    <div class="container">
      ${renderHeader()}
      <div class="card">
        <div class="step-badge">Referencial Teórico</div>
        <div class="step-title">Preenchimento do Referencial Teórico</div>
        <div class="step-desc">
          A categoria interna é sempre "Referencial Teórico", mas o título original é preservado para apresentação.
          Você pode preencher como uma seção única ou dividir em várias subseções (ex.: "2.1 Inteligência Artificial no Ensino").
        </div>
        <label class="meta-field">
          <span class="meta-field-label">Título original utilizado no documento</span>
          <input type="text" id="m-ref-titulo" class="meta-input" value="${escHtml(m.referencial.titulo)}" placeholder="Ex.: Fundamentação Teórica">
        </label>

        <div class="config-label" style="margin-top:1rem">Subseções</div>
        <div class="subsec-list">${subRows || '<p style="color:var(--text-muted);font-size:.85rem">Nenhuma subseção. Adicione ao menos uma.</p>'}</div>
        <button class="btn btn-ghost btn-sm" id="btn-add-subsec">+ Adicionar subseção</button>

        <div class="nav-row">
          <button class="btn btn-ghost" id="btn-manual-back-ask-ref">← Voltar</button>
          <button class="btn btn-primary" id="btn-manual-ref-continue">Salvar e continuar →</button>
        </div>
      </div>
    </div>`;
}

// ── Manual: pick next section ─────────────────────────────────────────────────

function renderManualPickSection() {
  const m = state.manual;
  const cards = MANUAL_SECTIONS.map(s => {
    const filled = m.secoes[s.key].trim().length > 0;
    return `
      <button class="pick-card ${filled ? 'filled' : ''}" data-pick="${s.key}">
        <span class="pick-title">${s.label}</span>
        <span class="pick-status">${filled ? '✓ preenchida — editar' : 'preencher'}</span>
      </button>`;
  }).join('');

  const refFilled = m.preencherReferencial && m.referencial.subsecoes.some(x => (x.conteudo || '').trim());
  const refCard = `
    <button class="pick-card ${refFilled ? 'filled' : ''}" data-pick="referencial">
      <span class="pick-title">Referencial Teórico</span>
      <span class="pick-status">${refFilled ? `✓ ${m.referencial.subsecoes.length} subseção(ões) — editar` : 'preencher'}</span>
    </button>`;

  const outrasList = m.outras.map((o, i) => `
    <div class="outra-row">
      <span class="outra-title">${escHtml(o.titulo || 'Outra seção')}</span>
      <button class="mini-btn" data-outra-edit="${i}">editar</button>
      <button class="mini-btn-danger" data-outra-remove="${i}">remover</button>
    </div>`).join('');

  return `
    <div class="container">
      ${renderHeader()}
      <div class="card">
        <div class="step-badge">Próxima seção</div>
        <div class="step-title">Qual seção deseja preencher?</div>
        <div class="step-desc">
          Informe as seções na ordem em que aparecem no documento. Você pode adicionar, editar ou pular qualquer seção,
          e finalizar quando quiser.
        </div>
        <div class="pick-grid">
          ${refCard}
          ${cards}
          <button class="pick-card outra" data-pick="outra"><span class="pick-title">Outra seção</span><span class="pick-status">conteúdo de contexto</span></button>
        </div>

        ${m.outras.length ? `<div class="config-label" style="margin-top:1.25rem">Outras seções adicionadas</div><div class="outras-list">${outrasList}</div>` : ''}

        <div class="nav-row" style="margin-top:1.5rem">
          <button class="btn btn-ghost" id="btn-manual-pick-back">← Voltar ao Referencial</button>
          <button class="btn btn-primary" id="btn-manual-to-review">Finalizar preenchimento →</button>
        </div>
      </div>
    </div>`;
}

// ── Manual: fill a section ──────────────────────────────────────────────────────

function renderManualSection() {
  const m = state.manual;
  const cur = m.current || {};
  const isOutra = cur.tipo === 'outra';
  const meta = isOutra ? null : MANUAL_SECTIONS.find(s => s.key === cur.tipo);
  const title = isOutra ? 'Outra seção' : (meta ? meta.label : 'Seção');
  const desc = isOutra
    ? 'Seção que não se enquadra nas categorias do CoerencIA. Será usada como contexto no relatório e não entra no IGC.'
    : (meta ? meta.desc : '');

  let value = '';
  if (isOutra) value = (m.outras[cur.outraIdx]?.conteudo) || '';
  else value = m.secoes[cur.tipo] || '';

  const outraTitleField = isOutra ? `
    <label class="meta-field">
      <span class="meta-field-label">Título original da seção</span>
      <input type="text" id="m-outra-titulo" class="meta-input" value="${escHtml(m.outras[cur.outraIdx]?.titulo || '')}" placeholder="Ex.: Discussão, Trabalhos Futuros…">
    </label>` : '';

  return `
    <div class="container">
      ${renderHeader()}
      <div class="card">
        <div class="step-badge">Preenchimento de seção</div>
        <div class="step-title">${escHtml(title)}</div>
        <div class="step-desc">${escHtml(desc)}</div>
        ${outraTitleField}
        <textarea id="m-section-input" class="section-textarea" rows="10"
          placeholder="Cole aqui o texto desta seção...">${escHtml(value)}</textarea>
        <div class="char-count"><span id="m-section-cnt">${value.length}</span> caracteres</div>
        <div class="nav-row">
          <button class="btn btn-ghost" id="btn-manual-section-cancel">← Voltar</button>
          <div style="display:flex;gap:.6rem">
            <button class="btn btn-ghost" id="btn-manual-section-save">Salvar e adicionar outra</button>
            <button class="btn btn-primary" id="btn-manual-section-finish">Salvar e finalizar</button>
          </div>
        </div>
      </div>
    </div>`;
}

// ── Manual: review ──────────────────────────────────────────────────────────────

function manualResolveOrigin() {
  // Mirror do backend: seção própria tem prioridade; senão trechos confirmados da intro; senão ausente.
  const m = state.manual;
  const confirmed = m.introElementos.filter(e => e.usar && (e.trecho || '').trim());
  const has = (types) => confirmed.some(e => types.includes(e.tipo));
  return {
    problema: m.secoes.problema.trim() ? 'secao_propria' : (has(PROBLEM_TYPES) ? 'introducao' : 'ausente'),
    objetivos: m.secoes.objetivos.trim() ? 'secao_propria' : (has(OBJETIVO_TYPES) ? 'introducao' : 'ausente'),
  };
}

function renderManualReview() {
  const m = state.manual;
  const origem = manualResolveOrigin();
  const autores = splitAutores(m.autores);

  const origemTag = (key) => {
    const o = origem[key];
    if (o === 'secao_propria') return '<span class="origin-tag origin-own">seção própria</span>';
    if (o === 'introducao')    return '<span class="origin-tag origin-intro">identificado na Introdução</span>';
    return '<span class="origin-tag origin-missing">ausente</span>';
  };

  const row = (label, content, extra = '') => {
    const filled = content && content.trim();
    const preview = filled ? escHtml(content.slice(0, 220)) + (content.length > 220 ? '…' : '') : '<em>não preenchida</em>';
    return `
      <div class="review-row ${filled ? '' : 'empty'}">
        <div class="review-row-head"><span class="review-label">${label}</span>${extra}</div>
        <div class="review-content">${preview}</div>
      </div>`;
  };

  // Intro elements confirmed
  const confirmed = m.introElementos.filter(e => e.usar && (e.trecho || '').trim());
  const introElsHtml = confirmed.length ? `
    <div class="review-row">
      <div class="review-row-head"><span class="review-label">Elementos confirmados na Introdução</span></div>
      ${confirmed.map(e => `<div class="review-el"><strong>${escHtml(INTRO_ELEMENT_LABELS[e.tipo] || e.tipo)}:</strong> "${escHtml((e.trecho || '').slice(0, 160))}${(e.trecho || '').length > 160 ? '…' : ''}"</div>`).join('')}
    </div>` : '';

  // Referencial
  const refSubs = m.preencherReferencial ? m.referencial.subsecoes.filter(s => (s.conteudo || '').trim()) : [];
  const refHtml = refSubs.length ? `
    <div class="review-row">
      <div class="review-row-head"><span class="review-label">Referencial Teórico${m.referencial.titulo ? ` — ${escHtml(m.referencial.titulo)}` : ''}</span><span class="origin-tag origin-context">contexto (fora do IGC)</span></div>
      ${refSubs.map(s => `<div class="review-el"><strong>${escHtml([s.numeracao, s.titulo].filter(Boolean).join(' '))}</strong> — ${escHtml((s.conteudo || '').slice(0, 120))}${(s.conteudo || '').length > 120 ? '…' : ''}</div>`).join('')}
    </div>` : '';

  // Outras
  const outrasHtml = m.outras.filter(o => (o.conteudo || '').trim()).length ? `
    <div class="review-row">
      <div class="review-row-head"><span class="review-label">Outras seções</span><span class="origin-tag origin-context">contexto (fora do IGC)</span></div>
      ${m.outras.filter(o => (o.conteudo || '').trim()).map(o => `<div class="review-el"><strong>${escHtml(o.titulo || 'Outra seção')}</strong></div>`).join('')}
    </div>` : '';

  // Missing core sections
  const resolved = {
    introducao: m.introducao.trim().length > 0,
    problema: origem.problema !== 'ausente',
    objetivos: origem.objetivos !== 'ausente',
    metodologia: m.secoes.metodologia.trim().length > 0,
    resultados: m.secoes.resultados.trim().length > 0,
    conclusao: m.secoes.conclusao.trim().length > 0,
  };
  const missing = Object.entries(resolved).filter(([, v]) => !v).map(([k]) => SECTION_LABELS[k]);
  const missingHtml = missing.length ? `
    <div class="partial-notice">
      <strong>Seções sem conteúdo:</strong> ${missing.join(', ')}.
      Pares que dependem delas serão marcados como “não avaliados por informação insuficiente” — não como baixa coerência.
    </div>` : '';

  const resolvedCount = Object.values(resolved).filter(Boolean).length;
  const canAnalyze = resolvedCount >= 2;

  const metaHeader = (m.titulo || autores.length) ? `
    <div class="results-meta" style="margin-bottom:1rem">
      ${m.titulo ? `<div class="results-meta-title">${escHtml(m.titulo)}</div>` : ''}
      ${autores.length ? `<div class="results-meta-authors">${escHtml(autores.join(' · '))}</div>` : ''}
    </div>` : '';

  const rigorBtns = ['Baixo', 'Médio', 'Alto'].map(r =>
    `<button class="rigor-btn ${state.rigor === r ? 'active' : ''}" data-rigor="${r}">${r}</button>`
  ).join('');

  return `
    <div class="container">
      ${renderHeader()}
      ${metaHeader}
      <div class="card">
        <div class="step-badge">Revisão final</div>
        <div class="step-title">Confirme o preenchimento</div>
        <div class="step-desc">Revise os conteúdos e a origem de cada elemento antes da análise. Clique em "Editar" para ajustar qualquer parte.</div>

        <div class="review-list">
          ${row('Introdução', m.introducao, '<button class="mini-btn" data-edit="intro">editar</button>')}
          ${introElsHtml}
          ${row('Problema', origem.problema === 'introducao' ? '(usando trechos confirmados na Introdução)' : m.secoes.problema, origemTag('problema') + '<button class="mini-btn" data-edit="problema">editar</button>')}
          ${row('Objetivos', origem.objetivos === 'introducao' ? '(usando trechos confirmados na Introdução)' : m.secoes.objetivos, origemTag('objetivos') + '<button class="mini-btn" data-edit="objetivos">editar</button>')}
          ${refHtml}
          ${row('Metodologia', m.secoes.metodologia, '<button class="mini-btn" data-edit="metodologia">editar</button>')}
          ${row('Resultados', m.secoes.resultados, '<button class="mini-btn" data-edit="resultados">editar</button>')}
          ${row('Conclusão', m.secoes.conclusao, '<button class="mini-btn" data-edit="conclusao">editar</button>')}
          ${outrasHtml}
        </div>

        ${missingHtml}

        <div class="config-label" style="margin-top:1.25rem">Informações complementares</div>
        <textarea id="m-additional" class="section-textarea additional-textarea" rows="3"
          placeholder="Contexto adicional para o relatório qualitativo…">${escHtml(state.additionalInfo)}</textarea>

        <div class="config-label" style="margin-top:1rem">Nível de rigor</div>
        <div class="rigor-row">${rigorBtns}</div>

        ${!canAnalyze ? '<div class="warning">Preencha ao menos 2 seções estratégicas (ou confirme elementos da Introdução) para iniciar a análise.</div>' : ''}

        <div class="nav-row">
          <button class="btn btn-ghost" id="btn-manual-review-back">← Voltar ao preenchimento</button>
          <button class="btn btn-primary" id="btn-manual-analyze" ${canAnalyze ? '' : 'disabled'}>Confirmar e analisar</button>
        </div>
      </div>
    </div>`;
}

// ── Upload: file selection ────────────────────────────────────────────────────

function renderUploadFilePage() {
  const fileName = state.uploadFile ? state.uploadFile.name : null;
  return `
    <div class="container">
      ${renderHeader()}
      <div class="card">
        <div class="step-badge">Upload de Documento</div>
        <div class="step-title">Envie seu trabalho</div>
        <div class="step-desc">PDF ou DOCX. O Docling extrai o texto; você revisará o mapeamento das seções antes da análise.</div>
        <div class="file-drop-zone ${fileName ? 'has-file' : ''}" id="file-drop-zone">
          <input type="file" id="file-input" accept=".pdf,.docx" style="display:none">
          <div class="file-drop-icon">${fileName ? '&#10003;' : '&#43;'}</div>
          <div class="file-drop-text">${fileName ? `<strong>${escHtml(fileName)}</strong>` : 'Clique para selecionar ou arraste o arquivo aqui'}</div>
          <div class="file-drop-sub">${fileName ? 'Clique para trocar o arquivo' : 'PDF ou DOCX'}</div>
        </div>
        <div class="nav-row">
          <button class="btn btn-ghost" id="btn-back-mode">← Voltar</button>
          <button class="btn btn-primary" id="btn-upload-next" ${state.uploadFile ? '' : 'disabled'}>Configurar análise →</button>
        </div>
      </div>
    </div>`;
}

function renderUploadConfigPage() {
  const rigorBtns = ['Baixo', 'Médio', 'Alto'].map(r =>
    `<button class="rigor-btn ${state.rigor === r ? 'active' : ''}" data-rigor="${r}">${r}</button>`
  ).join('');
  return `
    <div class="container">
      ${renderHeader()}
      <div class="card">
        <div class="step-badge">Configuração</div>
        <div class="step-title">Configurar análise</div>
        <div class="step-desc">Arquivo: <strong>${escHtml(state.uploadFile ? state.uploadFile.name : '')}</strong></div>
        <div class="config-label">Nível de rigor</div>
        <div class="rigor-row">${rigorBtns}</div>
        <div class="nav-row">
          <button class="btn btn-ghost" id="btn-back-upload">← Voltar</button>
          <button class="btn btn-primary" id="btn-extract-segments">Extrair seções →</button>
        </div>
      </div>
    </div>`;
}

// ── Upload: mapping review ────────────────────────────────────────────────────

function renderMappingReviewPage() {
  const segs = state.documentSegments || [];
  const meta = state.metadados || { titulo: '', autores: [] };
  const metaSource = meta.extraido_por === 'ia' ? 'IA' : meta.extraido_por === 'regras' ? 'regras locais' : '';
  const autoresStr = Array.isArray(meta.autores) ? meta.autores.join('; ') : (meta.autores || '');

  const metaBlock = `
    <div class="meta-block">
      <div class="meta-block-header">
        <span>Metadados do documento</span>
        ${metaSource ? `<span class="meta-source">extraído por ${metaSource}</span>` : ''}
      </div>
      <div class="meta-note">Título e autores não são seções acadêmicas e não entram no cálculo do IGC. Corrija se necessário — sua correção tem prioridade.</div>
      <label class="meta-field">
        <span class="meta-field-label">Título</span>
        <input type="text" id="meta-titulo" class="meta-input" value="${escHtml(meta.titulo || '')}" placeholder="Título do trabalho">
      </label>
      <label class="meta-field">
        <span class="meta-field-label">Autores <small>(separe por ponto e vírgula)</small></span>
        <input type="text" id="meta-autores" class="meta-input" value="${escHtml(autoresStr)}" placeholder="Nome 1; Nome 2">
      </label>
    </div>`;

  const introBlock = (state.introElementos && state.introElementos.length) ? `
    <div class="intro-elements-block">
      <div class="section-heading" style="margin-top:0">Elementos identificados na Introdução</div>
      <div class="meta-note">Trechos originais. Quando não houver seção própria de Problema ou Objetivos, os elementos confirmados serão usados nos pares correspondentes. Desmarque para rejeitar.</div>
      ${state.introElementos.map((el, i) => {
        const conf = el.confianca || 'media';
        const confCls = conf === 'alta' ? 'conf-alta' : conf === 'media' ? 'conf-media' : 'conf-baixa';
        return `
        <div class="intro-element ${el.usar ? '' : 'rejected'}">
          <label class="intro-element-check"><input type="checkbox" data-intro-el="${i}" ${el.usar ? 'checked' : ''}></label>
          <div class="intro-element-body">
            <div class="intro-element-head">
              <span class="intro-element-type">${escHtml(el.rotulo || el.tipo)}</span>
              <span class="conf-badge ${confCls}">confiança: ${conf}</span>
            </div>
            <div class="intro-element-trecho">"${escHtml(el.trecho || '')}"</div>
            ${el.localizacao ? `<div class="intro-element-loc">${escHtml(el.localizacao)}</div>` : ''}
          </div>
        </div>`;
      }).join('')}
    </div>` : '';

  const segRows = segs.map((seg, i) => {
    const current = (state.sectionMapping[String(i)] !== undefined) ? state.sectionMapping[String(i)] : (seg.sugerido || '');
    const opts = SECTION_OPTIONS.map(o => `<option value="${o.value}" ${current === o.value ? 'selected' : ''}>${o.label}</option>`).join('');
    const preview = seg.content ? seg.content.slice(0, 160).trim() + (seg.content.length > 160 ? '…' : '') : '';
    const aiTag = seg.sugerido ? `<span class="ai-suggestion-tag">sugestão: ${SECTION_LABELS[seg.sugerido] || seg.sugerido}</span>` : '';
    return `
      <div class="segment-row">
        <div class="segment-header"><span class="segment-title">${escHtml(seg.heading || '(sem título)')}</span>${aiTag}</div>
        <div class="segment-preview">${escHtml(preview)}</div>
        <select class="segment-select" data-seg="${i}"><option value="">— Não classificar —</option>${opts}</select>
      </div>`;
  }).join('');

  const additionalBlock = `
    <div class="config-label" style="margin-top:1.5rem">Informações complementares</div>
    <textarea id="additional-info-input" class="section-textarea additional-textarea" rows="3"
      placeholder="Contexto adicional sobre o tema, problema ou objetivos para apoiar a análise…">${escHtml(state.additionalInfo)}</textarea>`;

  return `
    <div class="container">
      ${renderHeader()}
      <div class="card">
        <div class="step-badge">Revisão do Mapeamento</div>
        <div class="step-title">Confirme metadados e seções</div>
        <div class="step-desc">Revise o mapeamento automático${state.useAI ? ' sugerido pela IA' : ' (baseado em regras locais)'}. Corrija o que estiver incorreto antes de iniciar a análise. Os títulos originais são preservados.</div>
        ${metaBlock}
        ${introBlock}
        <div class="section-heading">Seções e subseções detectadas</div>
        <div class="segments-list">${segRows || '<p style="color:var(--text-muted);font-size:.88rem">Nenhum segmento detectado.</p>'}</div>
        ${additionalBlock}
        <div class="nav-row" style="margin-top:1.5rem">
          <button class="btn btn-ghost" id="btn-back-mapping">← Voltar</button>
          <button class="btn btn-primary" id="btn-analyze-mapped">Analisar coerência</button>
        </div>
      </div>
    </div>`;
}

// ── Loading page ──────────────────────────────────────────────────────────────

function renderLoadingPage() {
  let msg = 'Analisando coerência estrutural…';
  let sub = state.useAI ? 'Calculando SBERT e aguardando Gemini…' : 'Calculando vetores semânticos (SBERT)…';
  if (state.phase === 'upload' && state.uploadStep === 2) {
    msg = 'Extraindo texto do documento…';
    sub = state.useAI ? 'Docling + proposta de mapeamento com IA…' : 'Convertendo com Docling…';
  }
  return `
    <div class="container">
      ${renderHeader()}
      <div class="card loading-wrap">
        <div class="spinner"></div>
        <div>${msg}</div>
        <div class="loading-sub">${sub}</div>
      </div>
    </div>`;
}

// ── Results page ──────────────────────────────────────────────────────────────

function renderResultsPage() {
  const r = state.results;
  if (!r) return renderLoadingPage();

  const panel = r.painel_geral;
  const igc = panel.igc;
  const color = igc >= 0.70 ? '#4ade80' : igc >= 0.50 ? '#facc15' : '#f87171';

  const evaluated = panel.pares_avaliados ?? r.matriz_similaridade?.length ?? '—';
  const total = panel.pares_totais ?? 5;
  const partialHtml = evaluated < total ? `
    <div class="partial-notice">
      <strong>${evaluated} de ${total} pares estratégicos avaliados.</strong>
      O IGC reflete apenas os pares com ambas as seções presentes.
      Pares com seção ausente foram excluídos do cálculo — ausência de seção indica informação insuficiente, não baixa coerência.
    </div>` : '';

  const docInfoHtml = r.arquivo ? `
    <div class="doc-info-card">
      <div class="doc-info-title">Documento analisado</div>
      <div class="doc-info-name">${escHtml(r.arquivo)}</div>
      <div class="doc-info-sections">${Object.values(r.secoes_detectadas || {}).filter(v => v && v.trim()).length} seções detectadas</div>
    </div>` : '';

  const meta = r.metadados || {};
  const autores = Array.isArray(meta.autores) ? meta.autores.filter(Boolean) : [];
  const metaHeaderHtml = (meta.titulo || autores.length) ? `
    <div class="results-meta">
      ${meta.titulo ? `<div class="results-meta-title">${escHtml(meta.titulo)}</div>` : ''}
      ${autores.length ? `<div class="results-meta-authors">${escHtml(autores.join(' · '))}</div>` : ''}
    </div>` : '';

  const origemLabels = {
    secao_propria: 'seção própria, preenchida pelo autor',
    introducao: 'identificado dentro da Introdução (confirmado pelo usuário)',
    ausente: 'não localizado (informação insuficiente)',
  };
  const origem = r.origem_secoes || {};
  const origemEntries = Object.entries(origem);
  const origemHtml = origemEntries.length ? `
    <div class="origem-notice">
      <div class="origem-title">Origem dos elementos centrais</div>
      ${origemEntries.map(([k, v]) => {
        const label = k === 'problema' ? 'Problema' : k === 'objetivos' ? 'Objetivos' : k;
        return `<div>• <strong>${label}:</strong> ${origemLabels[v] || v}.</div>`;
      }).join('')}
    </div>` : '';

  // Confirmed intro elements (evidence)
  const introEls = r.intro_elementos || [];
  const introEvidenceHtml = introEls.length ? `
    <div class="card" style="margin-top:0">
      <div class="section-heading" style="margin-top:0">Elementos confirmados na Introdução</div>
      ${introEls.map(e => `<div class="review-el"><strong>${escHtml(INTRO_ELEMENT_LABELS[e.tipo] || e.tipo)}:</strong> "${escHtml((e.trecho || '').slice(0, 200))}${(e.trecho || '').length > 200 ? '…' : ''}"</div>`).join('')}
    </div>` : '';

  // Referencial notice (+ subsections if manual)
  const refSubs = r.referencial_subsecoes || [];
  const referencialHtml = (r.referencial && r.referencial.trim()) ? `
    <div class="referencial-notice">
      <strong>Referencial Teórico informado.</strong> Usado como contexto da análise e do relatório; não compõe os pares estratégicos nem o IGC.
      ${refSubs.length ? `<div class="ref-subs">${refSubs.map(s => `<span class="ref-sub-chip">${escHtml([s.numeracao, s.titulo].filter(Boolean).join(' ') || 'subseção')}</span>`).join('')}</div>` : ''}
    </div>` : '';

  // Outras seções
  const outras = (r.outras_secoes || []).filter(o => (o.conteudo || '').trim());
  const outrasHtml = outras.length ? `
    <div class="referencial-notice" style="background:rgba(148,163,184,0.06);border-color:rgba(148,163,184,0.2);color:var(--text)">
      <strong>Outras seções informadas:</strong> ${outras.map(o => escHtml(o.titulo || 'Outra seção')).join(', ')}. Contexto apenas; fora do IGC.
    </div>` : '';

  const warningsHtml = (r.avisos || []).map(w => `<div class="warning">${escHtml(w)}</div>`).join('');

  const tableRows = (r.matriz_similaridade || []).map(rw => {
    const badgeCls = rw.faixa === 'Verde' ? 'badge-green' : rw.faixa === 'Amarelo' ? 'badge-yellow' : 'badge-red';
    const scoreColor = rw.faixa === 'Verde' ? '#4ade80' : rw.faixa === 'Amarelo' ? '#facc15' : '#f87171';
    const expl = rw.explicacao ? `<tr><td colspan="3" class="pair-explanation">${escHtml(rw.explicacao)}</td></tr>` : '';
    return `
      <tr>
        <td>${rw.par}</td>
        <td style="font-weight:700;font-variant-numeric:tabular-nums;color:${scoreColor}">${rw.similaridade.toFixed(2)}</td>
        <td><span class="badge ${badgeCls}">${rw['interpretação']}</span></td>
      </tr>${expl}`;
  }).join('');

  const skippedHtml = (r.pares_nao_avaliados || []).length > 0 ? `
    <div class="card" style="margin-top:0">
      <div class="section-heading" style="margin-top:0">Pares não avaliados <span class="insuf-tag">informação insuficiente</span></div>
      ${(r.pares_nao_avaliados).map(p => `
        <div class="skipped-pair"><span class="skipped-par">${p.par}</span><span class="skipped-motivo">${escHtml(p.motivo)}</span></div>`).join('')}
    </div>` : '';

  const alertsHtml = (r.trechos_criticos || []).map(c => `
    <div class="alert-card">
      <div class="alert-card-header">&#9888; ${c.par} — score: ${c.score_par.toFixed(2)}</div>
      <div class="alert-excerpt"><strong>Trecho A:</strong> "${escHtml(c.trecho_a)}"</div>
      <div class="alert-excerpt"><strong>Trecho B:</strong> "${escHtml(c.trecho_b)}"</div>
      <div class="alert-suggestion">${escHtml(c.sugestao)}</div>
    </div>`).join('');

  const geminiHtml = r.gemini_report ? `
    <div class="section-heading">Interpretação Qualitativa (Gemini)</div>
    <div class="gemini-report">${mdToHtml(r.gemini_report)}</div>` : '';

  return `
    <div class="container">
      ${renderHeader()}
      ${metaHeaderHtml}
      <div class="igc-card">
        <div class="igc-number" style="color:${color}">${igc.toFixed(2)}</div>
        <div class="igc-class">${panel.classificacao}</div>
        <div class="igc-bar-track"><div class="igc-bar-fill" id="igc-fill" style="width:0%;background:${color}"></div></div>
        <div class="igc-meta">Índice Global de Coerência (IGC) &nbsp;·&nbsp; Rigor: ${panel.nivel_rigor} &nbsp;·&nbsp; abrangência: ${evaluated}/${total} pares válidos</div>
      </div>

      ${partialHtml}
      ${origemHtml}
      ${referencialHtml}
      ${outrasHtml}
      ${docInfoHtml}
      ${warningsHtml}

      <div class="card">
        <div class="section-heading" style="margin-top:0">Matriz de Similaridade</div>
        <table class="sim-table">
          <thead><tr><th>Par Estratégico</th><th>Score</th><th>Interpretação</th></tr></thead>
          <tbody>${tableRows}</tbody>
        </table>
      </div>

      ${skippedHtml}
      ${introEvidenceHtml}
      ${alertsHtml ? `<div class="section-heading">Alertas Críticos</div>${alertsHtml}` : ''}
      ${geminiHtml}

      <div class="result-actions">
        <button class="btn btn-ghost" id="btn-restart">← Nova análise</button>
        <button class="btn btn-primary" id="btn-reanalyze">Ajustar e reanalisar</button>
      </div>
    </div>`;
}

// ── Attach handlers ───────────────────────────────────────────────────────────

function attachHandlers() {
  // AI decision
  on('btn-use-ai', () => { state.useAI = true;  state.phase = 'mode-select'; render(); });
  on('btn-no-ai',  () => { state.useAI = false; state.phase = 'mode-select'; render(); });

  // Mode select
  on('btn-back-ai',     () => { state.phase = 'ai-decision'; render(); });
  on('btn-mode-manual', () => { state.phase = 'manual'; state.manual = freshManual(); render(); });
  on('btn-mode-upload', () => { state.phase = 'upload'; state.uploadStep = 0; render(); });

  attachManualHandlers();
  attachUploadHandlers();
  attachResultHandlers();

  // Rigor (shared)
  document.querySelectorAll('[data-rigor]').forEach(btn =>
    btn.addEventListener('click', () => { state.rigor = btn.dataset.rigor; render(); })
  );

  // Additional info (shared id)
  const addl = document.getElementById('m-additional') || document.getElementById('additional-info-input');
  if (addl) addl.addEventListener('input', () => { state.additionalInfo = addl.value; });

  // IGC bar animation
  const fill = document.getElementById('igc-fill');
  if (fill && state.results) {
    requestAnimationFrame(() => { fill.style.width = Math.round(state.results.painel_geral.igc * 100) + '%'; });
  }
}

function attachManualHandlers() {
  const m = state.manual;

  // metadata
  bindInput('m-titulo', v => m.titulo = v);
  bindInput('m-autores', v => m.autores = v);
  on('btn-manual-back-mode', () => { state.phase = 'mode-select'; render(); });
  on('btn-manual-to-intro', () => { m.phase = 'intro'; render(); });

  // intro
  const introInput = document.getElementById('m-introducao');
  if (introInput) {
    introInput.addEventListener('input', () => {
      m.introducao = introInput.value;
      const c = document.getElementById('m-intro-cnt');
      if (c) c.textContent = introInput.value.length;
    });
    introInput.focus({ preventScroll: true });
  }
  on('btn-manual-back-metadata', () => { m.phase = 'metadata'; render(); });
  on('btn-manual-analyze-intro', runManualIntroAnalysis);

  // intro elements
  document.querySelectorAll('[data-el-usar]').forEach(chk => chk.addEventListener('change', () => {
    const i = +chk.dataset.elUsar; if (m.introElementos[i]) m.introElementos[i].usar = chk.checked;
    chk.closest('.intro-element').classList.toggle('rejected', !chk.checked);
  }));
  document.querySelectorAll('[data-el-cat]').forEach(sel => sel.addEventListener('change', () => {
    const i = +sel.dataset.elCat; if (m.introElementos[i]) { m.introElementos[i].tipo = sel.value; m.introElementos[i].rotulo = INTRO_ELEMENT_LABELS[sel.value]; }
  }));
  document.querySelectorAll('[data-el-trecho]').forEach(t => t.addEventListener('input', () => {
    const i = +t.dataset.elTrecho; if (m.introElementos[i]) m.introElementos[i].trecho = t.value;
  }));
  document.querySelectorAll('[data-el-remove]').forEach(b => b.addEventListener('click', () => {
    const i = +b.dataset.elRemove; m.introElementos.splice(i, 1); render();
  }));
  on('btn-add-intro-el', () => {
    m.introElementos.push({ tipo: 'problema', rotulo: INTRO_ELEMENT_LABELS['problema'], trecho: '', localizacao: 'Informado manualmente', confianca: 'manual', usar: true, manual: true });
    render();
  });
  on('btn-manual-back-intro', () => { m.phase = 'intro'; render(); });
  on('btn-manual-after-intro', () => { m.phase = 'ask-referencial'; render(); });

  // ask referencial
  on('btn-ref-yes', () => {
    m.preencherReferencial = true;
    if (m.referencial.subsecoes.length === 0) m.referencial.subsecoes.push({ numeracao: '', titulo: '', conteudo: '' });
    m.phase = 'referencial'; render();
  });
  on('btn-ref-no', () => { m.preencherReferencial = m.referencial.subsecoes.some(s => (s.conteudo || '').trim()); m.phase = 'pick-section'; render(); });
  on('btn-manual-back-elements', () => { m.phase = 'intro-elements'; render(); });

  // referencial editor
  bindInput('m-ref-titulo', v => m.referencial.titulo = v);
  document.querySelectorAll('[data-sub-num]').forEach(el => el.addEventListener('input', () => { m.referencial.subsecoes[+el.dataset.subNum].numeracao = el.value; }));
  document.querySelectorAll('[data-sub-titulo]').forEach(el => el.addEventListener('input', () => { m.referencial.subsecoes[+el.dataset.subTitulo].titulo = el.value; }));
  document.querySelectorAll('[data-sub-conteudo]').forEach(el => el.addEventListener('input', () => { m.referencial.subsecoes[+el.dataset.subConteudo].conteudo = el.value; }));
  document.querySelectorAll('[data-sub-remove]').forEach(b => b.addEventListener('click', () => { m.referencial.subsecoes.splice(+b.dataset.subRemove, 1); render(); }));
  document.querySelectorAll('[data-sub-up]').forEach(b => b.addEventListener('click', () => { const i = +b.dataset.subUp; if (i > 0) { const s = m.referencial.subsecoes; [s[i - 1], s[i]] = [s[i], s[i - 1]]; render(); } }));
  document.querySelectorAll('[data-sub-down]').forEach(b => b.addEventListener('click', () => { const i = +b.dataset.subDown; const s = m.referencial.subsecoes; if (i < s.length - 1) { [s[i + 1], s[i]] = [s[i], s[i + 1]]; render(); } }));
  on('btn-add-subsec', () => { m.referencial.subsecoes.push({ numeracao: '', titulo: '', conteudo: '' }); render(); });
  on('btn-manual-back-ask-ref', () => { m.phase = 'ask-referencial'; render(); });
  on('btn-manual-ref-continue', () => { m.preencherReferencial = true; m.phase = 'pick-section'; render(); });

  // pick section
  document.querySelectorAll('[data-pick]').forEach(b => b.addEventListener('click', () => {
    const key = b.dataset.pick;
    if (key === 'referencial') { m.preencherReferencial = true; if (m.referencial.subsecoes.length === 0) m.referencial.subsecoes.push({ numeracao: '', titulo: '', conteudo: '' }); m.phase = 'referencial'; render(); return; }
    if (key === 'outra') { m.outras.push({ titulo: '', conteudo: '' }); m.current = { tipo: 'outra', outraIdx: m.outras.length - 1 }; m.phase = 'section'; render(); return; }
    m.current = { tipo: key }; m.phase = 'section'; render();
  }));
  document.querySelectorAll('[data-outra-edit]').forEach(b => b.addEventListener('click', () => { m.current = { tipo: 'outra', outraIdx: +b.dataset.outraEdit }; m.phase = 'section'; render(); }));
  document.querySelectorAll('[data-outra-remove]').forEach(b => b.addEventListener('click', () => { m.outras.splice(+b.dataset.outraRemove, 1); render(); }));
  on('btn-manual-pick-back', () => { m.phase = 'ask-referencial'; render(); });
  on('btn-manual-to-review', () => { m.phase = 'review'; render(); });

  // section fill
  const secInput = document.getElementById('m-section-input');
  if (secInput) {
    secInput.addEventListener('input', () => {
      const cur = m.current || {};
      if (cur.tipo === 'outra') m.outras[cur.outraIdx].conteudo = secInput.value;
      else m.secoes[cur.tipo] = secInput.value;
      const c = document.getElementById('m-section-cnt'); if (c) c.textContent = secInput.value.length;
    });
    secInput.focus({ preventScroll: true });
  }
  bindInput('m-outra-titulo', v => { const cur = m.current || {}; if (cur.tipo === 'outra') m.outras[cur.outraIdx].titulo = v; });
  on('btn-manual-section-cancel', () => { m.phase = 'pick-section'; render(); });
  on('btn-manual-section-save', () => { m.phase = 'pick-section'; render(); });
  on('btn-manual-section-finish', () => { m.phase = 'review'; render(); });

  // review
  document.querySelectorAll('[data-edit]').forEach(b => b.addEventListener('click', () => {
    const key = b.dataset.edit;
    if (key === 'intro') { m.phase = 'intro'; }
    else { m.current = { tipo: key }; m.phase = 'section'; }
    render();
  }));
  on('btn-manual-review-back', () => { m.phase = 'pick-section'; render(); });
  on('btn-manual-analyze', runManualAnalysis);
}

function attachUploadHandlers() {
  const dropZone = document.getElementById('file-drop-zone');
  const fileInput = document.getElementById('file-input');
  if (dropZone && fileInput) {
    dropZone.addEventListener('click', () => { fileInput.value = ''; fileInput.click(); });
    fileInput.addEventListener('change', () => { if (fileInput.files?.[0]) { state.uploadFile = fileInput.files[0]; render(); } });
    dropZone.addEventListener('dragover', e => { e.preventDefault(); dropZone.classList.add('drag-over'); });
    dropZone.addEventListener('dragleave', () => dropZone.classList.remove('drag-over'));
    dropZone.addEventListener('drop', e => { e.preventDefault(); dropZone.classList.remove('drag-over'); const f = e.dataTransfer?.files[0]; if (f) { state.uploadFile = f; render(); } });
  }
  on('btn-back-mode', () => { state.phase = 'mode-select'; render(); });
  on('btn-upload-next', () => { if (state.uploadFile) { state.uploadStep = 1; render(); } });
  on('btn-back-upload', () => { state.uploadStep = 0; render(); });
  on('btn-extract-segments', runExtractSegments);

  document.querySelectorAll('[data-seg]').forEach(sel => sel.addEventListener('change', () => { state.sectionMapping[sel.dataset.seg] = sel.value; }));

  const metaTitulo = document.getElementById('meta-titulo');
  if (metaTitulo) metaTitulo.addEventListener('input', () => { state.metadados.titulo = metaTitulo.value; state.metadados.extraido_por = 'manual'; });
  const metaAutores = document.getElementById('meta-autores');
  if (metaAutores) metaAutores.addEventListener('input', () => { state.metadados.autores = splitAutores(metaAutores.value); state.metadados.extraido_por = 'manual'; });

  document.querySelectorAll('[data-intro-el]').forEach(chk => chk.addEventListener('change', () => {
    const idx = +chk.dataset.introEl; if (state.introElementos[idx]) state.introElementos[idx].usar = chk.checked;
    chk.closest('.intro-element').classList.toggle('rejected', !chk.checked);
  }));

  on('btn-back-mapping', () => { state.uploadStep = 1; render(); });
  on('btn-analyze-mapped', runMappedAnalysis);
}

function attachResultHandlers() {
  on('btn-restart', () => {
    Object.assign(state, {
      phase: 'ai-decision', useAI: null,
      manual: freshManual(),
      uploadStep: 0, uploadFile: null, documentSegments: null, sectionMapping: {},
      metadados: { titulo: '', autores: [], extraido_por: '' }, introElementos: [],
      additionalInfo: '', results: null, error: null,
    });
    render();
  });
  on('btn-reanalyze', () => {
    if (state.phase === 'upload') state.uploadStep = 3;
    else state.manual.phase = 'review';
    render();
  });
}

function on(id, fn) { const el = document.getElementById(id); if (el) el.addEventListener('click', fn); }
function bindInput(id, fn) { const el = document.getElementById(id); if (el) el.addEventListener('input', () => fn(el.value)); }

// ── API calls ─────────────────────────────────────────────────────────────────

async function runManualIntroAnalysis() {
  const m = state.manual;
  m.phase = 'intro-elements';
  m.introLoading = true;
  m.introErro = null;
  render();
  try {
    const res = await fetch('/api/intro-elements', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ intro_text: m.introducao, use_gemini: state.useAI }),
    });
    if (res.ok) {
      const data = await res.json();
      m.introElementos = data.elementos || [];
      m.introMetodo = data.metodo || 'local';
      m.introErro = data.erro || null;
    } else {
      m.introElementos = [];
      m.introMetodo = 'local';
      m.introErro = 'A identificação automática não pôde ser concluída. Classifique manualmente os elementos.';
    }
  } catch (_) {
    m.introElementos = [];
    m.introMetodo = 'local';
    m.introErro = 'A identificação automática não pôde ser concluída (falha de comunicação). Classifique manualmente os elementos.';
  }
  m.introLoading = false;
  render();
}

async function runManualAnalysis() {
  const m = state.manual;
  m.phase = 'loading';
  state.error = null;
  render();

  const payload = {
    sections: {
      introducao: m.introducao,
      problema: m.secoes.problema,
      objetivos: m.secoes.objetivos,
      metodologia: m.secoes.metodologia,
      resultados: m.secoes.resultados,
      conclusao: m.secoes.conclusao,
    },
    rigor: state.rigor,
    use_gemini: state.useAI,
    additional_info: state.additionalInfo,
    metadados: { titulo: m.titulo.trim(), autores: splitAutores(m.autores), extraido_por: 'manual' },
    intro_elementos: m.introElementos.filter(e => e.usar && (e.trecho || '').trim()),
    referencial_subsecoes: m.preencherReferencial ? m.referencial.subsecoes.filter(s => (s.conteudo || '').trim()) : [],
    outras_secoes: m.outras.filter(o => (o.conteudo || '').trim()),
  };

  const endpoint = state.useAI ? '/api/analyze/full' : '/api/analyze';
  try {
    const res = await fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || res.statusText);
    state.results = await res.json();
    m.phase = 'results';
  } catch (err) {
    state.error = err.message;
    m.phase = 'review';
    alert('Erro na análise: ' + err.message);
  }
  render();
}

async function runExtractSegments() {
  state.uploadStep = 2;
  state.error = null;
  render();
  try {
    const form = new FormData();
    form.append('file', state.uploadFile);
    form.append('propose_mapping', state.useAI ? 'true' : 'false');
    const res = await fetch('/api/extract-segments', { method: 'POST', body: form });
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || res.statusText);
    const data = await res.json();
    state.documentSegments = data.segments || [];
    state.metadados = data.metadados || { titulo: '', autores: [], extraido_por: '' };
    state.introElementos = data.intro_elementos || [];
    state.sectionMapping = {};
    state.documentSegments.forEach((seg, i) => { if (seg.sugerido && seg.sugerido !== 'ignorar') state.sectionMapping[String(i)] = seg.sugerido; });
    state.uploadStep = 3;
  } catch (err) {
    state.error = err.message;
    state.uploadStep = 1;
    alert('Erro na extração: ' + err.message);
  }
  render();
}

async function runMappedAnalysis() {
  state.uploadStep = 4;
  state.error = null;
  render();
  try {
    const res = await fetch('/api/analyze-mapped', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        segments: state.documentSegments,
        user_mapping: state.sectionMapping,
        rigor: state.rigor,
        use_gemini: state.useAI,
        additional_info: state.additionalInfo,
        metadados: state.metadados,
        intro_elementos: state.introElementos,
      }),
    });
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || res.statusText);
    state.results = await res.json();
    state.uploadStep = 5;
  } catch (err) {
    state.error = err.message;
    state.uploadStep = 3;
    alert('Erro na análise: ' + err.message);
  }
  render();
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function splitAutores(str) {
  return String(str || '').split(';').map(s => s.trim()).filter(Boolean);
}

function escHtml(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function mdToHtml(text) {
  return text
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/`(.+?)`/g, '<code>$1</code>')
    .replace(/^#### (.+)$/gm, '<h4>$1</h4>')
    .replace(/^### (.+)$/gm, '<h3>$1</h3>')
    .replace(/^## (.+)$/gm, '<h2>$1</h2>')
    .replace(/^# (.+)$/gm, '<h2>$1</h2>')
    .replace(/^[-*•] (.+)$/gm, '<li>$1</li>')
    .replace(/(<li>[\s\S]+?<\/li>)\n(?!<li>)/g, '$1</ul>\n')
    .replace(/(<li>)/, '<ul>$1')
    .replace(/\n{2,}/g, '</p><p>')
    .replace(/^(?!<[hH\d]|<ul|<\/p|<p)/, '<p>')
    .replace(/$/, '</p>')
    .replace(/<p><\/p>/g, '')
    .replace(/<p>(<[hH][2-4]>)/g, '$1')
    .replace(/(<\/[hH][2-4]>)<\/p>/g, '$1')
    .replace(/<p>(<ul>)/g, '$1')
    .replace(/(<\/ul>)<\/p>/g, '$1');
}

// ── Boot ──────────────────────────────────────────────────────────────────────
checkAIAvailability();
