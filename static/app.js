'use strict';

const SECTIONS = [
  {
    key: 'introducao',
    label: 'Introdução',
    desc: 'Contextualize o trabalho: apresente o tema, a relevância, o cenário atual e como o TCC está organizado.',
  },
  {
    key: 'problema',
    label: 'Problema de Pesquisa',
    desc: 'Defina claramente a lacuna científica ou prática e formule a questão central que o trabalho responde.',
  },
  {
    key: 'objetivos',
    label: 'Objetivos',
    desc: 'Descreva o objetivo geral e os objetivos específicos. Use verbos de ação (analisar, desenvolver, avaliar…).',
  },
  {
    key: 'metodologia',
    label: 'Metodologia',
    desc: 'Explique a abordagem de pesquisa, os métodos, ferramentas, técnicas e procedimentos adotados.',
  },
  {
    key: 'resultados',
    label: 'Resultados',
    desc: 'Apresente os resultados obtidos, análises, tabelas e discussões referentes ao que foi realizado.',
  },
  {
    key: 'conclusao',
    label: 'Conclusão',
    desc: 'Sintetize as contribuições, retome os objetivos atingidos e aponte limitações e trabalhos futuros.',
  },
];

// 0-5  = seções, 6 = config, 7 = carregando, 8 = resultados
const state = {
  step: 0,
  sections: Object.fromEntries(SECTIONS.map(s => [s.key, ''])),
  rigor: 'Médio',
  useGemini: false,
  geminiKey: localStorage.getItem('coerencia_gemini_key') || '',
  results: null,
  error: null,
};

// ── Render ────────────────────────────────────────────────────────────────────

function render() {
  const app = document.getElementById('app');
  if (state.step <= 5)      app.innerHTML = renderStepPage();
  else if (state.step === 6) app.innerHTML = renderConfigPage();
  else if (state.step === 7) app.innerHTML = renderLoadingPage();
  else                       app.innerHTML = renderResultsPage();
  attachHandlers();
}

// ── Header & progress ─────────────────────────────────────────────────────────

function renderHeader() {
  return `
    <div class="header">
      <h1>CoerencIA</h1>
      <p>Análise automatizada de coerência estrutural em TCCs</p>
    </div>`;
}

function renderProgress(currentStep) {
  // currentStep 0-5 = seções, 6 = config
  const total = SECTIONS.length + 1; // +1 para config
  const bars = SECTIONS.map((_, i) => {
    const cls = i < currentStep ? 'done' : i === currentStep ? 'current' : '';
    return `<div class="progress-step ${cls}"></div>`;
  });
  const configCls = currentStep >= 6 ? 'done' : currentStep === 6 ? 'current' : '';
  bars.push(`<div class="progress-step ${configCls}"></div>`);
  const shown = Math.min(currentStep + 1, total);
  return `
    <div class="progress-wrap">
      ${bars.join('')}
      <span class="progress-label">${shown}/${total}</span>
    </div>`;
}

// ── Step page (seções) ────────────────────────────────────────────────────────

function renderStepPage() {
  const sec = SECTIONS[state.step];
  const text = state.sections[sec.key];
  const isLast = state.step === SECTIONS.length - 1;

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
        <div class="nav-row">
          <button class="btn btn-ghost" id="btn-prev" ${state.step === 0 ? 'disabled' : ''}>
            ← Anterior
          </button>
          <button class="btn btn-primary" id="btn-next">
            ${isLast ? 'Configurar análise →' : 'Próxima seção →'}
          </button>
        </div>
      </div>
    </div>`;
}

// ── Config page ───────────────────────────────────────────────────────────────

function renderConfigPage() {
  const chips = SECTIONS.map(s => {
    const ok = state.sections[s.key].trim().length > 0;
    return `<span class="section-chip ${ok ? 'filled' : 'empty'}" data-goto="${SECTIONS.indexOf(s)}">
      ${ok ? '✓' : '!'} ${s.label}
    </span>`;
  }).join('');

  const rigorBtns = ['Baixo', 'Médio', 'Alto'].map(r =>
    `<button class="rigor-btn ${state.rigor === r ? 'active' : ''}" data-rigor="${r}">${r}</button>`
  ).join('');

  const filledCount = SECTIONS.filter(s => state.sections[s.key].trim().length > 0).length;
  const canAnalyze = filledCount >= 2;

  const geminiField = state.useGemini ? `
    <input
      type="password"
      id="gemini-key"
      class="api-key-input"
      placeholder="Cole sua chave Gemini aqui (AIzaSy...)"
      value="${escHtml(state.geminiKey)}"
    >
    <div class="warning">
      🔑 A chave é salva somente no seu navegador (localStorage) e enviada apenas à API do Google.
    </div>` : '';

  const minWarning = !canAnalyze
    ? `<div class="warning">⚠ Preencha pelo menos 2 seções para iniciar a análise.</div>`
    : '';

  return `
    <div class="container">
      ${renderHeader()}
      ${renderProgress(6)}
      <div class="card">
        <div class="step-badge">Configuração</div>
        <div class="step-title">Revisar e analisar</div>
        <div class="step-desc">
          Clique em qualquer seção abaixo para editá-la. Depois ajuste o rigor e inicie.
        </div>

        <div class="sections-summary">${chips}</div>

        <div class="config-label">Nível de rigor</div>
        <div class="rigor-row">${rigorBtns}</div>

        <div class="toggle-row" id="toggle-gemini">
          <div class="toggle-label">
            Análise qualitativa com Gemini
            <small>Gera um diagnóstico em texto usando a API do Google Gemini (requer chave)</small>
          </div>
          <div class="toggle-switch ${state.useGemini ? 'on' : ''}" id="gemini-switch"></div>
        </div>
        ${geminiField}
        ${minWarning}

        <div class="nav-row">
          <button class="btn btn-ghost" id="btn-back-sections">← Voltar à última seção</button>
          <button class="btn btn-primary" id="btn-analyze" ${canAnalyze ? '' : 'disabled'}>
            Analisar coerência
          </button>
        </div>
      </div>
    </div>`;
}

// ── Loading page ──────────────────────────────────────────────────────────────

function renderLoadingPage() {
  const extra = state.useGemini && state.geminiKey
    ? 'Aguardando resposta do Gemini…'
    : 'Calculando vetores semânticos (SBERT)…';
  return `
    <div class="container">
      ${renderHeader()}
      <div class="card loading-wrap">
        <div class="spinner"></div>
        <div>Analisando coerência estrutural…</div>
        <div class="loading-sub">${extra}</div>
      </div>
    </div>`;
}

// ── Results page ──────────────────────────────────────────────────────────────

function renderResultsPage() {
  const r = state.results;
  if (!r) return renderLoadingPage();

  const panel = r.painel_geral;
  const igc   = panel.igc;
  const pct   = Math.round(igc * 100);
  const color = igc >= 0.70 ? '#4ade80' : igc >= 0.50 ? '#facc15' : '#f87171';

  // warnings
  const warningsHtml = (r.avisos || [])
    .map(w => `<div class="warning">⚠ ${w}</div>`)
    .join('');

  // similarity table
  const tableRows = (r.matriz_similaridade || []).map(row => {
    const badgeCls =
      row.faixa === 'Verde'    ? 'badge-green'  :
      row.faixa === 'Amarelo'  ? 'badge-yellow' : 'badge-red';
    const scoreColor =
      row.faixa === 'Verde'    ? '#4ade80' :
      row.faixa === 'Amarelo'  ? '#facc15' : '#f87171';
    return `
      <tr>
        <td>${row.par}</td>
        <td style="font-weight:700;font-variant-numeric:tabular-nums;color:${scoreColor}">
          ${row.similaridade.toFixed(2)}
        </td>
        <td><span class="badge ${badgeCls}">${row['interpretação']}</span></td>
      </tr>`;
  }).join('');

  // critical alerts
  const alertsHtml = (r.trechos_criticos || []).map(c => `
    <div class="alert-card">
      <div class="alert-card-header">⚠ ${c.par} — score: ${c.score_par.toFixed(2)}</div>
      <div class="alert-excerpt"><strong>Trecho A:</strong> "${escHtml(c.trecho_a)}"</div>
      <div class="alert-excerpt"><strong>Trecho B:</strong> "${escHtml(c.trecho_b)}"</div>
      <div class="alert-suggestion">${escHtml(c.sugestao)}</div>
    </div>`).join('');

  // gemini report
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
        <div class="igc-meta">
          Índice Global de Coerência (IGC) &nbsp;·&nbsp; Rigor: ${panel.nivel_rigor}
        </div>
      </div>

      ${warningsHtml}

      <div class="card">
        <div class="section-heading" style="margin-top:0">Matriz de Similaridade</div>
        <table class="sim-table">
          <thead>
            <tr>
              <th>Par Estratégico</th>
              <th>Score</th>
              <th>Interpretação</th>
            </tr>
          </thead>
          <tbody>${tableRows}</tbody>
        </table>
      </div>

      ${alertsHtml ? `<div class="section-heading">Alertas Críticos</div>${alertsHtml}` : ''}

      ${geminiHtml}

      <div class="result-actions">
        <button class="btn btn-ghost"    id="btn-restart">← Nova análise</button>
        <button class="btn btn-primary"  id="btn-reanalyze">Ajustar e reanalisar</button>
      </div>
    </div>`;
}

// ── Attach event handlers ─────────────────────────────────────────────────────

function attachHandlers() {
  // ── Step page ──────────────────────────────────────────
  const input = document.getElementById('section-input');
  if (input) {
    input.addEventListener('input', () => {
      state.sections[SECTIONS[state.step].key] = input.value;
      const cnt = document.getElementById('char-cnt');
      if (cnt) cnt.textContent = input.value.length;
    });
    // Focus the textarea for faster flow
    input.focus({ preventScroll: true });
  }

  on('btn-prev', () => { if (state.step > 0) { state.step--; render(); } });
  on('btn-next', () => {
    if (state.step < SECTIONS.length - 1) { state.step++; render(); }
    else { state.step = 6; render(); }
  });

  // ── Config page ────────────────────────────────────────
  document.querySelectorAll('[data-rigor]').forEach(btn =>
    btn.addEventListener('click', () => { state.rigor = btn.dataset.rigor; render(); })
  );

  document.querySelectorAll('[data-goto]').forEach(chip =>
    chip.addEventListener('click', () => { state.step = parseInt(chip.dataset.goto); render(); })
  );

  on('toggle-gemini', () => { state.useGemini = !state.useGemini; render(); });

  const keyInput = document.getElementById('gemini-key');
  if (keyInput) {
    keyInput.addEventListener('input', () => {
      state.geminiKey = keyInput.value;
      localStorage.setItem('coerencia_gemini_key', state.geminiKey);
    });
  }

  on('btn-back-sections', () => { state.step = SECTIONS.length - 1; render(); });
  on('btn-analyze', runAnalysis);

  // ── Results page ───────────────────────────────────────
  on('btn-restart', () => {
    state.step = 0;
    state.sections = Object.fromEntries(SECTIONS.map(s => [s.key, '']));
    state.results = null;
    state.error = null;
    render();
  });

  on('btn-reanalyze', () => { state.step = 6; render(); });

  // Animate IGC bar after render
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

// ── API call ──────────────────────────────────────────────────────────────────

async function runAnalysis() {
  state.step = 7;
  state.error = null;
  render();

  const useGemini = state.useGemini && state.geminiKey.trim().length > 0;
  const endpoint = useGemini ? '/api/analyze/full' : '/api/analyze';

  try {
    const res = await fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        sections: state.sections,
        rigor: state.rigor,
        gemini_api_key: useGemini ? state.geminiKey.trim() : null,
        use_gemini: useGemini,
      }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || 'Erro desconhecido no servidor.');
    }

    state.results = await res.json();
    state.step = 8;
  } catch (err) {
    state.error = err.message;
    state.step = 6;
    alert('Erro na análise: ' + err.message);
  }

  render();
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function escHtml(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// Minimal Markdown → HTML (for Gemini reports)
function mdToHtml(text) {
  return text
    // escape HTML first
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    // bold
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    // inline code
    .replace(/`(.+?)`/g, '<code>$1</code>')
    // headers (process longest first)
    .replace(/^#### (.+)$/gm, '<h4>$1</h4>')
    .replace(/^### (.+)$/gm,  '<h3>$1</h3>')
    .replace(/^## (.+)$/gm,   '<h2>$1</h2>')
    .replace(/^# (.+)$/gm,    '<h2>$1</h2>')
    // unordered lists
    .replace(/^[-*•] (.+)$/gm, '<li>$1</li>')
    .replace(/(<li>[\s\S]+?<\/li>)\n(?!<li>)/g, '$1</ul>\n')
    .replace(/(<li>)/,         '<ul>$1')
    // paragraphs
    .replace(/\n{2,}/g, '</p><p>')
    .replace(/^(?!<[hH\d]|<ul|<\/p|<p)/, '<p>')
    .replace(/$/, '</p>')
    // clean up empty tags
    .replace(/<p><\/p>/g, '')
    .replace(/<p>(<[hH][2-4]>)/g, '$1')
    .replace(/(<\/[hH][2-4]>)<\/p>/g, '$1')
    .replace(/<p>(<ul>)/g, '$1')
    .replace(/(<\/ul>)<\/p>/g, '$1');
}

// ── Boot ──────────────────────────────────────────────────────────────────────
render();
