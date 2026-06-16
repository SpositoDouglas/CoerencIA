'use strict';

const SECTIONS = [
  { key: 'introducao', label: 'Introdução',        desc: 'Contextualize o trabalho: apresente o tema, a relevância, o cenário atual e como o TCC está organizado.' },
  { key: 'problema',   label: 'Problema de Pesquisa', desc: 'Defina claramente a lacuna científica ou prática e formule a questão central que o trabalho responde.' },
  { key: 'objetivos',  label: 'Objetivos',          desc: 'Descreva o objetivo geral e os objetivos específicos. Use verbos de ação (analisar, desenvolver, avaliar…).' },
  { key: 'metodologia',label: 'Metodologia',        desc: 'Explique a abordagem de pesquisa, os métodos, ferramentas, técnicas e procedimentos adotados.' },
  { key: 'resultados', label: 'Resultados',         desc: 'Apresente os resultados obtidos, análises, tabelas e discussões referentes ao que foi realizado.' },
  { key: 'conclusao',  label: 'Conclusão',          desc: 'Sintetize as contribuições, retome os objetivos atingidos e aponte limitações e trabalhos futuros.' },
];

const SECTION_OPTIONS = [
  { value: 'introducao',  label: 'Introdução' },
  { value: 'problema',    label: 'Problema de Pesquisa' },
  { value: 'objetivos',   label: 'Objetivos' },
  { value: 'metodologia', label: 'Metodologia' },
  { value: 'resultados',  label: 'Resultados' },
  { value: 'conclusao',   label: 'Conclusão' },
  { value: 'ignorar',     label: 'Ignorar este trecho' },
];

// ── State ─────────────────────────────────────────────────────────────────────
// phase: 'ai-decision' → 'mode-select' → 'manual' | 'upload'
// manual: step 0-5=sections, 6=config, 7=loading, 8=results
// upload: uploadStep 0=file, 1=config, 2=loading-extract, 3=mapping, 4=loading-analyze, 5=results

const state = {
  phase: 'ai-decision',
  useAI: null,
  aiAvailable: null,   // populated on first load via /api/check-ai

  // Manual
  step: 0,
  sections: Object.fromEntries(SECTIONS.map(s => [s.key, ''])),
  introChecklist: null,
  showingChecklist: false,
  checklistLoading: false,
  additionalInfo: '',

  // Upload
  uploadStep: 0,
  uploadFile: null,
  documentSegments: null,
  sectionMapping: {},

  // Shared
  rigor: 'Médio',
  results: null,
  error: null,
};

// ── Boot: check if AI is available on server ──────────────────────────────────

async function checkAIAvailability() {
  try {
    const res = await fetch('/api/check-ai');
    if (res.ok) {
      const data = await res.json();
      state.aiAvailable = data.available;
    }
  } catch (_) {
    state.aiAvailable = false;
  }
  render();
}

// ── Render ────────────────────────────────────────────────────────────────────

function render() {
  const app = document.getElementById('app');
  const html = (() => {
    if (state.phase === 'ai-decision')  return renderAIDecisionPage();
    if (state.phase === 'mode-select')  return renderModePage();

    if (state.phase === 'manual') {
      if (state.showingChecklist)       return renderIntroChecklistPage();
      if (state.step <= 5)              return renderStepPage();
      if (state.step === 6)             return renderConfigPage();
      if (state.step === 7)             return renderLoadingPage();
      return renderResultsPage();
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

// ── Header ─────────────────────────────────────────────────────────────────────

function renderHeader() {
  return `
    <div class="header">
      <h1>CoerencIA</h1>
      <p>Análise automatizada de coerência estrutural em TCCs</p>
    </div>`;
}

// ── Progress bar (manual mode) ────────────────────────────────────────────────

function renderProgress(currentStep) {
  const total = SECTIONS.length + 1;
  const bars = SECTIONS.map((_, i) => {
    const cls = i < currentStep ? 'done' : i === currentStep ? 'current' : '';
    return `<div class="progress-step ${cls}"></div>`;
  });
  const configCls = currentStep >= 6 ? 'done' : currentStep === 6 ? 'current' : '';
  bars.push(`<div class="progress-step ${configCls}"></div>`);
  return `
    <div class="progress-wrap">
      ${bars.join('')}
      <span class="progress-label">${Math.min(currentStep + 1, total)}/${total}</span>
    </div>`;
}

// ── AI Decision page ──────────────────────────────────────────────────────────

function renderAIDecisionPage() {
  const aiUnavailableNote = state.aiAvailable === false ? `
    <div class="warning" style="margin-top:1rem">
      Nenhuma chave de API Gemini foi encontrada no servidor (.env). A análise qualitativa com IA não está disponível neste ambiente.
    </div>` : '';

  const canUseAI = state.aiAvailable !== false;

  return `
    <div class="container">
      ${renderHeader()}
      <div class="card">
        <div class="step-badge">Configuração inicial</div>
        <div class="step-title">Análise qualitativa com IA?</div>
        <div class="step-desc">
          Você deseja usar o Gemini para gerar um diagnóstico interpretativo além da análise semântica com SBERT?
        </div>

        <div class="ai-choice-grid">
          <button class="ai-choice-card ${!canUseAI ? 'disabled' : ''}" id="btn-use-ai" ${!canUseAI ? 'disabled' : ''}>
            <div class="ai-choice-title">Sim, usar IA</div>
            <div class="ai-choice-desc">SBERT + Gemini. Gera diagnóstico textual interpretativo por par estratégico, além do IGC e da matriz de similaridade.</div>
            ${!canUseAI ? '<div class="ai-choice-unavail">Chave não configurada no servidor</div>' : ''}
          </button>
          <button class="ai-choice-card" id="btn-no-ai">
            <div class="ai-choice-title">Não, apenas SBERT</div>
            <div class="ai-choice-desc">Análise semântica completa com embeddings, IGC, matriz de similaridade e explicações automáticas por par. Sem chamadas externas.</div>
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
          <div class="mode-desc">Cole o texto de cada seção do TCC nos campos correspondentes. A Introdução pode incluir uma análise dos elementos presentes.</div>
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

// ── Manual: section step ──────────────────────────────────────────────────────

function renderStepPage() {
  const sec = SECTIONS[state.step];
  const text = state.sections[sec.key];
  const isLast = state.step === SECTIONS.length - 1;
  const isIntro = state.step === 0;

  const additionalBlock = isIntro ? `
    <div class="additional-info-toggle" id="toggle-additional">
      <span>Adicionar contexto complementar ao tema ou problema</span>
      <span class="toggle-chevron">${state.additionalInfo ? '&#9650;' : '&#9660;'}</span>
    </div>
    ${state.additionalInfo !== null ? `
    <textarea
      id="additional-info-input"
      class="section-textarea additional-textarea"
      placeholder="Descreva aqui informações adicionais sobre o tema, problema, objetivos ou contexto do TCC que a IA deve considerar na análise qualitativa…"
      rows="4"
    >${escHtml(state.additionalInfo)}</textarea>` : ''}` : '';

  const nextLabel = isLast
    ? 'Configurar análise →'
    : (isIntro && state.useAI && text.trim().length > 100
        ? 'Analisar introdução →'
        : 'Próxima seção →');

  return `
    <div class="container">
      ${renderHeader()}
      ${renderProgress(state.step)}
      <div class="card">
        <div class="step-badge">Seção ${state.step + 1} de ${SECTIONS.length}</div>
        <div class="step-title">${sec.label}</div>
        <div class="step-desc">${sec.desc}</div>
        <textarea
          id="section-input"
          class="section-textarea"
          placeholder="Cole aqui o texto desta seção..."
          rows="10"
        >${escHtml(text)}</textarea>
        <div class="char-count"><span id="char-cnt">${text.length}</span> caracteres</div>
        ${additionalBlock}
        <div class="nav-row">
          <button class="btn btn-ghost" id="btn-prev" ${state.step === 0 ? 'disabled' : ''}>← Anterior</button>
          <button class="btn btn-primary" id="btn-next">${nextLabel}</button>
        </div>
      </div>
    </div>`;
}

// ── Manual: intro checklist page ──────────────────────────────────────────────

function renderIntroChecklistPage() {
  if (state.checklistLoading) {
    return `
      <div class="container">
        ${renderHeader()}
        <div class="card loading-wrap">
          <div class="spinner"></div>
          <div>Analisando a Introdução com IA…</div>
          <div class="loading-sub">Identificando elementos acadêmicos presentes</div>
        </div>
      </div>`;
  }

  const items = (state.introChecklist || []).map(el => {
    const cls = el.status === 'presente' ? 'check-present' : el.status === 'parcial' ? 'check-partial' : 'check-absent';
    const icon = el.status === 'presente' ? '&#10003;' : el.status === 'parcial' ? '~' : '&#10007;';
    return `
      <div class="checklist-item ${cls}">
        <span class="checklist-icon">${icon}</span>
        <div>
          <div class="checklist-name">${escHtml(el.nome)}</div>
          ${el.observacao ? `<div class="checklist-obs">${escHtml(el.observacao)}</div>` : ''}
        </div>
      </div>`;
  }).join('');

  return `
    <div class="container">
      ${renderHeader()}
      <div class="card">
        <div class="step-badge">Análise da Introdução</div>
        <div class="step-title">Elementos identificados pela IA</div>
        <div class="step-desc">Esta é uma leitura interpretativa, não uma decisão definitiva. Corrija ou complemente nas próximas seções.</div>
        <div class="checklist-wrap">${items || '<p style="color:var(--text-muted);font-size:.88rem">Nenhum elemento identificado.</p>'}</div>

        <div class="config-label" style="margin-top:1.25rem">Contexto complementar</div>
        <textarea
          id="additional-info-input"
          class="section-textarea additional-textarea"
          placeholder="Adicione aqui informações sobre o tema, problema ou objetivos que a IA deve considerar na análise qualitativa…"
          rows="4"
        >${escHtml(state.additionalInfo)}</textarea>

        <div class="nav-row">
          <button class="btn btn-ghost" id="btn-back-checklist">← Editar introdução</button>
          <button class="btn btn-primary" id="btn-continue-checklist">Continuar →</button>
        </div>
      </div>
    </div>`;
}

// ── Manual: config page ───────────────────────────────────────────────────────

function renderConfigPage() {
  const chips = SECTIONS.map(s => {
    const ok = state.sections[s.key].trim().length > 0;
    return `<span class="section-chip ${ok ? 'filled' : 'empty'}" data-goto="${SECTIONS.indexOf(s)}">
      ${ok ? '&#10003;' : '!'} ${s.label}
    </span>`;
  }).join('');

  const rigorBtns = ['Baixo', 'Médio', 'Alto'].map(r =>
    `<button class="rigor-btn ${state.rigor === r ? 'active' : ''}" data-rigor="${r}">${r}</button>`
  ).join('');

  const filledCount = SECTIONS.filter(s => state.sections[s.key].trim().length > 0).length;
  const canAnalyze = filledCount >= 2;

  return `
    <div class="container">
      ${renderHeader()}
      ${renderProgress(6)}
      <div class="card">
        <div class="step-badge">Configuração</div>
        <div class="step-title">Revisar e analisar</div>
        <div class="step-desc">Clique em qualquer seção para editá-la. Ajuste o rigor e inicie.</div>

        <div class="sections-summary">${chips}</div>

        <div class="config-label">Nível de rigor</div>
        <div class="rigor-row">${rigorBtns}</div>

        ${!canAnalyze ? `<div class="warning">Preencha pelo menos 2 seções para iniciar a análise.</div>` : ''}

        <div class="nav-row">
          <button class="btn btn-ghost" id="btn-back-sections">← Voltar à última seção</button>
          <button class="btn btn-primary" id="btn-analyze" ${canAnalyze ? '' : 'disabled'}>Analisar coerência</button>
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
        <div class="step-title">Envie seu TCC</div>
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

// ── Upload: config ────────────────────────────────────────────────────────────

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

  const segRows = segs.map((seg, i) => {
    const current = state.sectionMapping[String(i)] || seg.sugerido || '';
    const opts = SECTION_OPTIONS.map(o =>
      `<option value="${o.value}" ${current === o.value ? 'selected' : ''}>${o.label}</option>`
    ).join('');
    const preview = seg.content ? seg.content.slice(0, 140).trim() + (seg.content.length > 140 ? '…' : '') : '';
    const aiTag = seg.sugerido ? `<span class="ai-suggestion-tag">IA: ${SECTION_OPTIONS.find(o => o.value === seg.sugerido)?.label || seg.sugerido}</span>` : '';

    return `
      <div class="segment-row">
        <div class="segment-header">
          <span class="segment-title">${escHtml(seg.heading || '(sem título)')}</span>
          ${aiTag}
        </div>
        <div class="segment-preview">${escHtml(preview)}</div>
        <select class="segment-select" data-seg="${i}">
          <option value="">— Não classificar —</option>
          ${opts}
        </select>
      </div>`;
  }).join('');

  const additionalBlock = state.useAI ? `
    <div class="config-label" style="margin-top:1.5rem">Contexto complementar para a IA</div>
    <textarea
      id="additional-info-input"
      class="section-textarea additional-textarea"
      placeholder="Informações adicionais sobre o tema, problema ou objetivos que a IA deve considerar…"
      rows="3"
    >${escHtml(state.additionalInfo)}</textarea>` : '';

  return `
    <div class="container">
      ${renderHeader()}
      <div class="card">
        <div class="step-badge">Mapeamento de Seções</div>
        <div class="step-title">Confirme as seções detectadas</div>
        <div class="step-desc">
          Revise o mapeamento automático${state.useAI ? ' sugerido pela IA' : ''}. Corrija os papéis incorretos antes de iniciar a análise.
        </div>

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
  let msg, sub;
  if (state.phase === 'upload') {
    if (state.uploadStep === 2) {
      msg = 'Extraindo texto do documento…';
      sub = state.useAI ? 'Docling + proposta de mapeamento com IA…' : 'Convertendo com Docling…';
    } else {
      msg = 'Analisando coerência estrutural…';
      sub = state.useAI ? 'Calculando SBERT e aguardando Gemini…' : 'Calculando vetores semânticos (SBERT)…';
    }
  } else {
    msg = 'Analisando coerência estrutural…';
    sub = state.useAI ? 'Calculando SBERT e aguardando Gemini…' : 'Calculando vetores semânticos (SBERT)…';
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
  const igc   = panel.igc;
  const color = igc >= 0.70 ? '#4ade80' : igc >= 0.50 ? '#facc15' : '#f87171';

  // Partial evaluation notice
  const evaluated = panel.pares_avaliados ?? r.matriz_similaridade?.length ?? '—';
  const total      = panel.pares_totais ?? 5;
  const partialHtml = evaluated < total ? `
    <div class="partial-notice">
      <strong>${evaluated} de ${total} pares estratégicos avaliados.</strong>
      O IGC reflete apenas os pares com ambas as seções presentes.
      Pares com seção ausente foram excluídos do cálculo — ausência de seção indica informação insuficiente, não baixa coerência.
    </div>` : '';

  // Document info (upload mode)
  const docInfoHtml = r.arquivo ? `
    <div class="doc-info-card">
      <div class="doc-info-title">Documento analisado</div>
      <div class="doc-info-name">${escHtml(r.arquivo)}</div>
      <div class="doc-info-sections">${Object.values(r.secoes_detectadas || {}).filter(v => v && v.trim()).length} seções detectadas</div>
    </div>` : '';

  // Warnings
  const warningsHtml = (r.avisos || []).map(w => `<div class="warning">${escHtml(w)}</div>`).join('');

  // Similarity table
  const tableRows = (r.matriz_similaridade || []).map(row => {
    const badgeCls   = row.faixa === 'Verde' ? 'badge-green' : row.faixa === 'Amarelo' ? 'badge-yellow' : 'badge-red';
    const scoreColor = row.faixa === 'Verde' ? '#4ade80'    : row.faixa === 'Amarelo' ? '#facc15'      : '#f87171';
    const expl = row.explicacao ? `<tr><td colspan="3" class="pair-explanation">${escHtml(row.explicacao)}</td></tr>` : '';
    return `
      <tr>
        <td>${row.par}</td>
        <td style="font-weight:700;font-variant-numeric:tabular-nums;color:${scoreColor}">${row.similaridade.toFixed(2)}</td>
        <td><span class="badge ${badgeCls}">${row['interpretação']}</span></td>
      </tr>${expl}`;
  }).join('');

  // Skipped pairs
  const skippedHtml = (r.pares_nao_avaliados || []).length > 0 ? `
    <div class="card" style="margin-top:0">
      <div class="section-heading" style="margin-top:0">Pares não avaliados</div>
      ${(r.pares_nao_avaliados).map(p => `
        <div class="skipped-pair">
          <span class="skipped-par">${p.par}</span>
          <span class="skipped-motivo">${escHtml(p.motivo)}</span>
        </div>`).join('')}
    </div>` : '';

  // Critical alerts
  const alertsHtml = (r.trechos_criticos || []).map(c => `
    <div class="alert-card">
      <div class="alert-card-header">&#9888; ${c.par} — score: ${c.score_par.toFixed(2)}</div>
      <div class="alert-excerpt"><strong>Trecho A:</strong> "${escHtml(c.trecho_a)}"</div>
      <div class="alert-excerpt"><strong>Trecho B:</strong> "${escHtml(c.trecho_b)}"</div>
      <div class="alert-suggestion">${escHtml(c.sugestao)}</div>
    </div>`).join('');

  // Gemini report
  const geminiHtml = r.gemini_report ? `
    <div class="section-heading">Interpretação Qualitativa (Gemini)</div>
    <div class="gemini-report">${mdToHtml(r.gemini_report)}</div>` : '';

  return `
    <div class="container">
      ${renderHeader()}

      <div class="igc-card">
        <div class="igc-number" style="color:${color}">${igc.toFixed(2)}</div>
        <div class="igc-class">${panel.classificacao}</div>
        <div class="igc-bar-track">
          <div class="igc-bar-fill" id="igc-fill" style="width:0%;background:${color}"></div>
        </div>
        <div class="igc-meta">Índice Global de Coerência (IGC) &nbsp;·&nbsp; Rigor: ${panel.nivel_rigor} &nbsp;·&nbsp; ${evaluated}/${total} pares</div>
      </div>

      ${partialHtml}
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
      ${alertsHtml ? `<div class="section-heading">Alertas Críticos</div>${alertsHtml}` : ''}
      ${geminiHtml}

      <div class="result-actions">
        <button class="btn btn-ghost"   id="btn-restart">← Nova análise</button>
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
  on('btn-mode-manual', () => { state.phase = 'manual'; state.step = 0; render(); });
  on('btn-mode-upload', () => { state.phase = 'upload'; state.uploadStep = 0; render(); });

  // Manual: section step
  const input = document.getElementById('section-input');
  if (input) {
    input.addEventListener('input', () => {
      state.sections[SECTIONS[state.step].key] = input.value;
      document.getElementById('char-cnt').textContent = input.value.length;
    });
    input.focus({ preventScroll: true });
  }

  const addlInput = document.getElementById('additional-info-input');
  if (addlInput) {
    addlInput.addEventListener('input', () => { state.additionalInfo = addlInput.value; });
  }

  on('btn-prev', () => { if (state.step > 0) { state.step--; render(); } });
  on('btn-next', async () => {
    const isIntro = state.step === 0;
    const introText = state.sections['introducao'];
    if (isIntro && state.useAI && introText.trim().length > 100) {
      state.showingChecklist = true;
      state.checklistLoading = true;
      render();
      try {
        const res = await fetch('/api/intro-analysis', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ intro_text: introText }),
        });
        if (res.ok) state.introChecklist = (await res.json()).elementos;
      } catch (_) {}
      state.checklistLoading = false;
      render();
    } else if (state.step < SECTIONS.length - 1) {
      state.step++;
      render();
    } else {
      state.step = 6;
      render();
    }
  });

  // Manual: intro checklist
  on('btn-back-checklist', () => {
    state.showingChecklist = false;
    render();
  });
  on('btn-continue-checklist', () => {
    state.showingChecklist = false;
    state.step = 1;
    render();
  });

  // Manual: config
  on('btn-back-sections', () => { state.step = SECTIONS.length - 1; render(); });
  on('btn-analyze', runManualAnalysis);

  document.querySelectorAll('[data-rigor]').forEach(btn =>
    btn.addEventListener('click', () => { state.rigor = btn.dataset.rigor; render(); })
  );
  document.querySelectorAll('[data-goto]').forEach(chip =>
    chip.addEventListener('click', () => { state.step = parseInt(chip.dataset.goto); render(); })
  );

  // Upload: file
  const dropZone  = document.getElementById('file-drop-zone');
  const fileInput = document.getElementById('file-input');
  if (dropZone && fileInput) {
    dropZone.addEventListener('click', () => { fileInput.value = ''; fileInput.click(); });
    fileInput.addEventListener('change', () => {
      if (fileInput.files?.[0]) { state.uploadFile = fileInput.files[0]; render(); }
    });
    dropZone.addEventListener('dragover',  e => { e.preventDefault(); dropZone.classList.add('drag-over'); });
    dropZone.addEventListener('dragleave', () => dropZone.classList.remove('drag-over'));
    dropZone.addEventListener('drop', e => {
      e.preventDefault(); dropZone.classList.remove('drag-over');
      const f = e.dataTransfer?.files[0];
      if (f) { state.uploadFile = f; render(); }
    });
  }

  on('btn-back-mode',   () => { state.phase = 'mode-select'; render(); });
  on('btn-upload-next', () => { if (state.uploadFile) { state.uploadStep = 1; render(); } });
  on('btn-back-upload', () => { state.uploadStep = 0; render(); });
  on('btn-extract-segments', runExtractSegments);

  // Upload: mapping
  document.querySelectorAll('[data-seg]').forEach(sel => {
    sel.addEventListener('change', () => {
      state.sectionMapping[sel.dataset.seg] = sel.value;
    });
  });
  on('btn-back-mapping', () => { state.uploadStep = 1; render(); });
  on('btn-analyze-mapped', runMappedAnalysis);

  // Results
  on('btn-restart', () => {
    Object.assign(state, {
      phase: 'ai-decision', useAI: null,
      step: 0, sections: Object.fromEntries(SECTIONS.map(s => [s.key, ''])),
      introChecklist: null, showingChecklist: false, additionalInfo: '',
      uploadStep: 0, uploadFile: null, documentSegments: null, sectionMapping: {},
      results: null, error: null,
    });
    render();
  });
  on('btn-reanalyze', () => {
    if (state.phase === 'upload') state.uploadStep = 3;
    else state.step = 6;
    render();
  });

  // IGC bar animation
  const fill = document.getElementById('igc-fill');
  if (fill && state.results) {
    requestAnimationFrame(() => {
      fill.style.width = Math.round(state.results.painel_geral.igc * 100) + '%';
    });
  }
}

function on(id, fn) {
  const el = document.getElementById(id);
  if (el) el.addEventListener('click', fn);
}

// ── API calls ─────────────────────────────────────────────────────────────────

async function runManualAnalysis() {
  state.step = 7;
  state.error = null;
  render();

  const endpoint = state.useAI ? '/api/analyze/full' : '/api/analyze';
  try {
    const res = await fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        sections: state.sections,
        rigor: state.rigor,
        use_gemini: state.useAI,
        additional_info: state.additionalInfo,
      }),
    });
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || res.statusText);
    state.results = await res.json();
    state.step = 8;
  } catch (err) {
    state.error = err.message;
    state.step = 6;
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
    // Pre-fill mapping with AI suggestions
    state.sectionMapping = {};
    state.documentSegments.forEach((seg, i) => {
      if (seg.sugerido && seg.sugerido !== 'ignorar') state.sectionMapping[String(i)] = seg.sugerido;
    });
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

function escHtml(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function mdToHtml(text) {
  return text
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/\*\*(.+?)\*\*/g,'<strong>$1</strong>')
    .replace(/`(.+?)`/g,'<code>$1</code>')
    .replace(/^#### (.+)$/gm,'<h4>$1</h4>')
    .replace(/^### (.+)$/gm,'<h3>$1</h3>')
    .replace(/^## (.+)$/gm,'<h2>$1</h2>')
    .replace(/^# (.+)$/gm,'<h2>$1</h2>')
    .replace(/^[-*•] (.+)$/gm,'<li>$1</li>')
    .replace(/(<li>[\s\S]+?<\/li>)\n(?!<li>)/g,'$1</ul>\n')
    .replace(/(<li>)/,'<ul>$1')
    .replace(/\n{2,}/g,'</p><p>')
    .replace(/^(?!<[hH\d]|<ul|<\/p|<p)/,'<p>')
    .replace(/$/, '</p>')
    .replace(/<p><\/p>/g,'')
    .replace(/<p>(<[hH][2-4]>)/g,'$1')
    .replace(/(<\/[hH][2-4]>)<\/p>/g,'$1')
    .replace(/<p>(<ul>)/g,'$1')
    .replace(/(<\/ul>)<\/p>/g,'$1');
}

// ── Boot ──────────────────────────────────────────────────────────────────────
checkAIAvailability();
