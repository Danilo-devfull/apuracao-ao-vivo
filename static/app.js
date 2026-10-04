'use strict';
(() => {
  // ================= Utilitários =================
  const $ = id => document.getElementById(id);
  const guardar = (k, v) => { try { localStorage.setItem(k, v); } catch (e) {} };
  const ler = k => { try { return localStorage.getItem(k) || ''; } catch (e) { return ''; } };
  // Tudo que vem da API passa por esc() antes de ir para o HTML (proteção contra XSS)
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const pct = n => Number(n || 0).toLocaleString('pt-BR', {minimumFractionDigits: 2, maximumFractionDigits: 2}) + '%';
  const milhar = n => Number(n || 0).toLocaleString('pt-BR');
  const fotoOk = u => typeof u === 'string' && (u.startsWith('https://resultados.tse.jus.br/') || u.startsWith('https://resultados-sim.tse.jus.br/'));
  const ev = n => { try { navigator.sendBeacon(`/api/evento/${n}/`); } catch (e) {} };
  const UF = /^[a-z]{2}$/;
  const INICIO = Date.parse(document.body.dataset.inicio) || 0;

  // ================= Modais (um por vez, fundo borrado compartilhado) =================
  const fundoModal = $('fundoModal');
  let modalAtual = null, aoFecharModal = null;
  function abrirModal(el, aoFechar) {
    if (modalAtual && modalAtual !== el) fecharModal();
    modalAtual = el; aoFecharModal = aoFechar || null;
    el.hidden = false; fundoModal.hidden = false;
    document.body.classList.add('modal-aberto');
    el.focus();
  }
  function fecharModal(motivo) {
    if (!modalAtual) return;
    const cb = aoFecharModal;
    modalAtual.hidden = true; fundoModal.hidden = true;
    document.body.classList.remove('modal-aberto');
    modalAtual = null; aoFecharModal = null;
    if (cb) cb(motivo);
  }
  fundoModal.addEventListener('click', () => fecharModal('fora'));
  document.addEventListener('keydown', e => { if (e.key === 'Escape') fecharModal('fora'); });

  const entrada = $('entrada'), app = $('app'), alvo = $('conteudo');
  const nomeIn = $('nomeEntrada'), ufIn = $('ufEntrada'), entrar = $('entrar');
  const nomeDoEstado = uf => (ufIn.querySelector(`option[value="${uf}"]`) || {}).textContent || '';
  let ufAtual = '', timer = null, emAndamento = false, ultimoOk = 0;

  // ================= Entrada (nome + estado, salvos só no aparelho) =================
  const limparNome = v => v.replace(/[\u0000-\u001f<>]/g, '').trim().slice(0, 40);
  function atualizarBotao() {
    entrar.disabled = !(limparNome(nomeIn.value) && UF.test(ufIn.value));
    entrar.textContent = UF.test(ufIn.value) ? `Ver a apuração ${artigo(ufIn.value)} ${nomeDoEstado(ufIn.value)}` : 'Ver a apuração';
  }
  // "da Bahia", "do Ceará", "de São Paulo"
  function artigo(uf) {
    if (['ba','pb'].includes(uf)) return 'da';
    if (['df','ac','ap','am','ce','es','ma','pa','pr','pi','rj','rn','rs','to'].includes(uf)) return 'do';
    return 'de';
  }
  nomeIn.addEventListener('input', atualizarBotao);
  ufIn.addEventListener('change', atualizarBotao);
  entrar.addEventListener('click', () => {
    const n = limparNome(nomeIn.value);
    if (!n || !UF.test(ufIn.value)) return;
    guardar('nome', n);
    abrirApp(ufIn.value);
  });
  $('trocarEstado').addEventListener('click', () => {
    clearInterval(timer);
    nomeIn.value = ler('nome'); ufIn.value = ufAtual; atualizarBotao();
    app.hidden = true; entrada.hidden = false; window.scrollTo(0, 0);
  });

  function abrirApp(uf) {
    ufAtual = uf; guardar('uf', uf);
    history.replaceState(null, '', '#' + uf);
    entrada.hidden = true; app.hidden = false; window.scrollTo(0, 0);
    const n = ler('nome');
    $('ola').textContent = n ? `Olá, ${n}` : '';
    $('nomeEstado').textContent = nomeDoEstado(uf);
    alvo.innerHTML = '<section class="cartao"><p class="vazio">Carregando resultados…</p></section>';
    ev('estado');
    clearInterval(timer);
    carregar(); timer = setInterval(carregar, 60000);
    if (typeof agendarConvite === 'function') agendarConvite();
  }

  // ================= Resultados =================
  // Sem foto (ou foto que não carrega): avatar neutro com as iniciais, igual para todos os candidatos
  const iniciais = nome => String(nome || '').split(/\s+/).filter(p => p.length > 2 || /^[A-Z]{2,3}$/.test(p)).slice(0, 2).map(p => p[0]).join('').toUpperCase() || '?';
  const avatar = (c, classe) => `<div class="${classe === 'foto' ? 'foto-sem' : 'mini'} avatar" data-iniciais="${esc(iniciais(c.nome))}" aria-hidden="true"><span>${esc(iniciais(c.nome))}</span></div>`;
  const foto = (c, classe) => fotoOk(c.foto)
    ? `<img class="${classe}" src="${esc(c.foto)}" alt="Foto de ${esc(c.nome)}" loading="lazy" referrerpolicy="no-referrer" data-iniciais="${esc(iniciais(c.nome))}">`
    : avatar(c, classe);
  const selo = c => c.eleito ? `<span class="selo">${esc(c.situacao || 'Eleito')}</span>`
    : (c.situacao && /2º turno/i.test(c.situacao) ? `<span class="selo">2º turno</span>` : '');
  const barra = (v, max) => `<div class="trilho"><i data-w="${Math.max(0, Math.min(100, (Number(v) / (max || 1)) * 100)).toFixed(1)}"></i></div>`;

  function cargoMajoritario(k) {          // presidente e governador
    const [l, ...resto] = k.candidatos;
    const comFoto = k.cargo === 'Presidente';
    const max = Number(l.percentual) || 1;
    return `<section class="cartao">
      <div class="cargo-topo"><h2>${esc(k.cargo)}${k.abrangencia ? ` <span class="abrangencia">${esc(k.abrangencia)}</span>` : ''}</h2><span class="meta">${pct(k.secoes_apuradas)} das seções</span></div>
      <div class="lider">${foto(l, 'foto')}<div>
        <div class="pct">${pct(l.percentual)}</div>
        <div class="nome">${esc(l.nome)}</div>
        <div class="sub">${esc(l.numero)} · ${esc(l.partido)} · ${milhar(l.votos)} votos</div>
        ${selo(l) ? `<div class="selo-lider">${selo(l)}</div>` : ''}
      </div></div>
      ${resto.map(c => `<div class="linha">
        ${comFoto ? foto(c, 'mini') : ''}
        <div class="linha-meio"><div class="nome">${esc(c.nome)} ${selo(c)}</div>${barra(c.percentual, max)}</div>
        <div class="pct">${pct(c.percentual)}</div>
      </div>`).join('')}
    </section>`;
  }

  function cargoLista(k, meta) {          // senador e deputados
    return `<section class="cartao">
      <div class="cargo-topo"><h2>${esc(k.cargo)}</h2><span class="meta">${meta}</span></div>
      <div class="lista">${k.candidatos.map(c => `<div class="item">
        <div><div class="nome">${esc(c.nome)} · ${esc(c.numero)}</div><div class="sub">${milhar(c.votos)} votos</div></div>
        ${selo(c)}
      </div>`).join('')}</div>
      ${k.total_candidatos > k.candidatos.length ? `<p class="mais">Os ${k.candidatos.length} mais votados de ${milhar(k.total_candidatos)} candidatos.</p>` : ''}
    </section>`;
  }

  function cargo(k) {
    if (k.indisponivel || !k.candidatos || !k.candidatos.length) {
      return `<section class="cartao"><div class="cargo-topo"><h2>${esc(k.cargo)}</h2></div><p class="vazio">Os números deste cargo ainda não foram divulgados pelo TSE.</p></section>`;
    }
    if (k.cargo === 'Presidente' || k.cargo === 'Governador') return cargoMajoritario(k);
    if (k.cargo === 'Senador') return cargoLista(k, `${pct(k.secoes_apuradas)} das seções`);
    return cargoLista(k, `${pct(k.secoes_apuradas)} das seções`);
  }

  // ================= Contagem regressiva =================
  function temNumeros(d) { return (d.cargos || []).some(k => !k.indisponivel && Number(k.secoes_apuradas) > 0); }
  function partes() {
    const t = Math.max(0, Math.floor((INICIO - Date.now()) / 1000));
    return {d: Math.floor(t / 86400), h: Math.floor(t % 86400 / 3600), m: Math.floor(t % 3600 / 60), s: t % 60};
  }
  const dd = n => String(n).padStart(2, '0');
  const faltam = () => { const p = partes(); return (p.d ? `${p.d}d ` : '') + `${dd(p.h)}:${dd(p.m)}:${dd(p.s)}`; };
  // Ilustração: urna eletrônica com um anel girando, como se estivesse contando
  const URNA = `<div class="urna-anim" aria-hidden="true">
    <svg viewBox="0 0 200 200" class="anel">
      <g transform="rotate(-90 100 100)">
        <circle cx="100" cy="100" r="88" pathLength="3" class="faixa faixa-verde"/>
        <circle cx="100" cy="100" r="88" pathLength="3" class="faixa faixa-amarela"/>
        <circle cx="100" cy="100" r="88" pathLength="3" class="faixa faixa-azul"/>
      </g>
      <g class="orbita">
        <circle cx="100" cy="12" r="3" class="bola rastro r3" transform="rotate(-21 100 100)"/>
        <circle cx="100" cy="12" r="4.5" class="bola rastro r2" transform="rotate(-14 100 100)"/>
        <circle cx="100" cy="12" r="6" class="bola rastro r1" transform="rotate(-7 100 100)"/>
        <circle cx="100" cy="12" r="9" class="bola principal"/>
        <path d="M100 2 L102 10 L110 12 L102 14 L100 22 L98 14 L90 12 L98 10 Z" class="faisca"/>
      </g>
    </svg>
    <svg viewBox="0 0 120 90" class="urna">
      <rect x="6" y="14" width="108" height="66" rx="8" class="urna-corpo"/>
      <rect x="16" y="24" width="52" height="38" rx="4" class="urna-tela"/>
      <rect x="22" y="32" width="28" height="5" rx="2" class="urna-texto"/><rect x="22" y="42" width="38" height="4" rx="2" class="urna-texto fraco"/><rect x="22" y="50" width="20" height="4" rx="2" class="urna-texto fraco"/>
      <g class="urna-teclas">${[0,1,2,3].map(r => [0,1,2].map(c => `<rect x="${76 + c * 11}" y="${24 + r * 10}" width="8" height="7" rx="1.5"/>`).join('')).join('')}</g>
      <rect x="76" y="66" width="10" height="7" rx="1.5" class="tecla-branco"/><rect x="88" y="66" width="10" height="7" rx="1.5" class="tecla-corrige"/><rect x="100" y="66" width="10" height="7" rx="1.5" class="tecla-confirma"/>
      <rect x="40" y="6" width="40" height="10" rx="3" class="urna-alca"/>
    </svg>
  </div>`;
  const RELOGIO = () => { const p = partes(); return `<div class="relogio" id="relogio">
      ${p.d ? `<div><strong id="rD">${p.d}</strong><span>${p.d === 1 ? 'dia' : 'dias'}</span></div>` : ''}
      <div><strong id="rH">${dd(p.h)}</strong><span>horas</span></div>
      <div><strong id="rM">${dd(p.m)}</strong><span>min</span></div>
      <div><strong id="rS">${dd(p.s)}</strong><span>seg</span></div>
    </div>`; };
  function telaEspera() {
    const antes = Date.now() < INICIO;
    $('progresso').hidden = true;
    $('aoVivo').classList.add('parado');
    $('aoVivoTexto').textContent = antes ? 'Aguardando o início da apuração' : 'Apuração começando';
    // Fundo: "esqueleto" borrado dos cartões, só formas, sem nomes nem números (nada que pareça resultado)
    const linhaEsq = w => `<div class="linha"><div class="mini"></div><div class="linha-meio"><span class="esq" data-largura="55%"></span><div class="trilho"><i data-w="${w}"></i></div></div><span class="esq" data-largura="52px"></span></div>`;
    const cartaoEsq = t => `<section class="cartao"><div class="cargo-topo"><h2>${t}</h2><span class="esq" data-largura="90px"></span></div>
      <div class="lider"><div class="foto-sem"></div><div class="linha-meio"><span class="esq alto" data-largura="70%"></span><span class="esq" data-largura="60%"></span><span class="esq" data-largura="80%"></span></div></div>
      ${linhaEsq(72)}${linhaEsq(40)}${linhaEsq(12)}</section>`;
    const aviso = antes
      ? `${URNA}
         <h2>${Date.now() < INICIO - 86400000 ? 'A apuração começa domingo, às 17h' : 'A apuração começa às 17h'}</h2>
         ${RELOGIO()}
         <p class="meta">horário de Brasília</p>
         <p>Os primeiros números do TSE aparecem aqui automaticamente.</p>
`
      : `<h2 id="apuracaoComecou">A apuração começou</h2>
         <p>As urnas estão enviando os resultados. Os primeiros números do TSE chegam em instantes e aparecem aqui sozinhos.</p>`;
    alvo.innerHTML = `<div class="espera-area">
        <div class="esqueleto" aria-hidden="true">${cartaoEsq('Presidente')}${cartaoEsq('Governador')}</div>
        <div class="espera-coluna">
          <section class="espera" role="status">${aviso}</section>
          ${antes ? botaoCola() + blocoCola() : ''}
        </div>
      </div>`;
    alvo.querySelectorAll('.trilho i').forEach(i => { i.style.width = i.dataset.w + '%'; });
    alvo.querySelectorAll('[data-largura]').forEach(e => { e.style.width = e.dataset.largura; });
    ligarCola();
  }
  function atualizarRelogio() {
    if ($('relogio')) {
      const p = partes();
      if ($('rD')) $('rD').textContent = p.d;
      $('rH').textContent = dd(p.h); $('rM').textContent = dd(p.m); $('rS').textContent = dd(p.s);
      if (Date.now() >= INICIO) carregar();
    }
    const t = $('aoVivoTexto');
    if (ultimoOk && t && !$('aoVivo').classList.contains('parado')) {
      const seg = Math.floor((Date.now() - ultimoOk) / 1000);
      t.textContent = seg < 60 ? `Ao vivo, atualizado há ${seg}s` : `Ao vivo, atualizado há ${Math.floor(seg / 60)} min`;
    }
  }

  // ================= Busca =================
  async function carregar() {
    if (emAndamento || document.hidden || !UF.test(ufAtual)) return;
    emAndamento = true;
    try {
      const r = await fetch(`/api/${ufAtual}/`, {headers: {'Accept': 'application/json'}});
      if (!r.ok) throw new Error(r.status);
      const d = await r.json();
      // Antes do horário da apuração, sempre mostra a urna e o cronômetro,
      // mesmo que o cache tenha dados antigos (simulação ou eleição passada)
      if (Date.now() < INICIO) { if (!$('relogio')) telaEspera(); return; }
      if (!temNumeros(d)) { if (!$('relogio') || (Date.now() >= INICIO && !$('apuracaoComecou'))) telaEspera(); return; }
      const botaoCompartilhar = `<button type="button" class="btn compartilhar" data-compartilhar>
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><path d="M8.6 13.5l6.8 4M15.4 6.5l-6.8 4"/></svg>
        Compartilhar a apuração ${artigo(ufAtual)} ${esc(nomeDoEstado(ufAtual))}</button>`;
      alvo.innerHTML = d.cargos.map((k, i) => cargo(k) + (i === 0 ? botaoCompartilhar : '')).join('');
      alvo.querySelectorAll('.trilho i').forEach(i => { i.style.width = i.dataset.w + '%'; });
      const pres = d.cargos.find(k => k.cargo === 'Governador' && !k.indisponivel) || d.cargos.find(k => !k.indisponivel && !k.abrangencia) || d.cargos.find(k => !k.indisponivel);
      const sec = Number(pres && pres.secoes_apuradas) || 0;
      $('progresso').hidden = false;
      $('progressoValor').textContent = pct(sec);
      $('progressoBarra').style.width = Math.min(100, sec) + '%';
      $('aoVivo').classList.remove('parado');
      ultimoOk = Date.now(); atualizarRelogio();
    } catch (e) {
      // Antes das 17h não há números mesmo: mostra a urna e a colinha (que funcionam sem servidor)
      if (Date.now() < INICIO) { if (!$('relogio')) telaEspera(); return; }
      $('aoVivo').classList.add('parado');
      $('aoVivoTexto').textContent = 'Sem conexão com o servidor';
      if (!alvo.querySelector('.lider, .lista, .espera')) {
        alvo.innerHTML = '<section class="cartao"><p class="vazio">Não foi possível buscar os resultados agora. Nova tentativa em 1 minuto.</p></section>';
      }
    } finally { emAndamento = false; }
  }
  // Foto que não carrega vira um quadro cinza (sem handler inline, compatível com a CSP)
  alvo.addEventListener('error', e => {
    if (e.target.tagName === 'IMG') {
      const d = document.createElement('div'), sp = document.createElement('span');
      d.className = (e.target.className === 'mini' ? 'mini' : 'foto-sem') + ' avatar';
      sp.textContent = e.target.dataset.iniciais || '?'; d.append(sp); e.target.replaceWith(d);
    }
  }, true);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) carregar(); });

  setInterval(atualizarRelogio, 1000);

  // ================= Compartilhar =================
  document.addEventListener('click', e => { if (e.target.closest('[data-compartilhar]')) compartilhar(); });
  async function compartilhar() {
    const url = `${location.origin}/#${ufAtual}`;
    const texto = `Acompanhe a apuração ao vivo: Presidente no Brasil e os cargos ${artigo(ufAtual)} ${nomeDoEstado(ufAtual)}, com os números oficiais do TSE:`;
    ev('compartilhou');
    if (navigator.share) {
      try { await navigator.share({title: 'Apuração 2026', text: texto, url}); } catch (e) {}
    } else {
      window.open(`https://wa.me/?text=${encodeURIComponent(texto + ' ' + url)}`, '_blank', 'noopener');
    }
  }

  // ================= Início =================
  try { if (!sessionStorage.getItem('v')) { sessionStorage.setItem('v', '1'); ev('visita'); } } catch (e) {}
  const doLink = location.hash.slice(1).toLowerCase();
  const ufInicial = UF.test(doLink) && nomeDoEstado(doLink) ? doLink : (UF.test(ler('uf')) ? ler('uf') : '');
  if (ler('nome') && ufInicial) abrirApp(ufInicial);
  else { entrada.hidden = false; nomeIn.value = ler('nome'); if (ufInicial) ufIn.value = ufInicial; atualizarBotao(); }

  // ================= Doação (modal) =================
  // Tempos contam só com o site ABERTO NA TELA, somando as visitas.
  //  - 1º pedido após 30 s; "Agora não" volta após 1 min; copiou o Pix volta após 10 min;
  //  - teto de MAX_POR_DIA pedidos automáticos por dia; o botão "Doar" do topo abre a qualquer momento.
  const PRIMEIRO_PEDIDO = 30, APOS_AGORA_NAO = 60, APOS_COPIAR = 600, MAX_POR_DIA = 8, PASSO = 5;
  const FECHAR_APOS_COPIAR = 4;   // segundos que a confirmação fica na tela
  const doacao = $('doacao');
  if (doacao) {
    const PIX = doacao.dataset.pix;
    const hoje = () => new Date().toLocaleDateString('sv-SE');
    const num = k => Number(ler(k) || 0);
    const titulo = $('tituloDoacao'), texto = doacao.querySelector('.doacao-texto');
    const TEXTO_PADRAO = texto.textContent;
    let fechar = null;
    const adiar = seg => guardar('doacaoProxima', String(num('tempoAtivo') + seg));

    function mostrar(automatico) {
      const n = ler('nome');
      if (ler('copiouPix')) {
        titulo.textContent = n ? `${n}, já fez sua doação?` : 'Já fez sua doação?';
        texto.textContent = 'Se você copiou o código e ainda não concluiu, dá tempo. Qualquer valor ajuda a manter o site no ar e sem propaganda. Obrigado!';
      } else {
        titulo.textContent = n ? `Oi, ${n}! Este site te ajudou?` : 'Este site te ajudou?';
        texto.textContent = TEXTO_PADRAO;
      }
      $('pixOk').hidden = true;
      abrirModal(doacao, motivo => { clearTimeout(fechar); if (motivo !== 'copiou') adiar(APOS_AGORA_NAO); });
      if (automatico) {
        if (ler('doacaoDia') !== hoje()) { guardar('doacaoDia', hoje()); guardar('doacaoVezes', '0'); }
        guardar('doacaoVezes', String(num('doacaoVezes') + 1));
        ev('doacao_vista');
      }
    }

    setInterval(() => {
      if (document.hidden || app.hidden) return;
      guardar('tempoAtivo', String(num('tempoAtivo') + PASSO));
      const limite = ler('doacaoDia') === hoje() && num('doacaoVezes') >= MAX_POR_DIA;
      // Nunca abre por cima de outro modal (atalho ou colinha)
      if (!modalAtual && !limite && num('tempoAtivo') >= (num('doacaoProxima') || PRIMEIRO_PEDIDO)) mostrar(true);
    }, PASSO * 1000);

    $('fecharDoacao').addEventListener('click', () => fecharModal('agora-nao'));
    $('copiarPix').addEventListener('click', async () => {
      ev('pix_copiado');
      try { await navigator.clipboard.writeText(PIX); } catch (e) { window.prompt('Copie o código Pix:', PIX); }
      $('pixOk').hidden = false;
      guardar('copiouPix', '1');
      adiar(APOS_COPIAR);
      clearTimeout(fechar);
      fechar = setTimeout(() => fecharModal('copiou'), FECHAR_APOS_COPIAR * 1000);
    });
    const topo = $('apoiar');
    topo.hidden = false;
    topo.addEventListener('click', () => { ev('doacao_topo'); mostrar(false); });
  }

  // ================= Atalho na tela inicial (modal em conversa) =================
  // Passo 1 pergunta o celular (com o provável já destacado); passo 2 mostra o caminho certo.
  // Nada disso sai do aparelho: a detecção usa só o navegador.
  if ('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js').catch(() => {});
  const modalInst = $('modalInstalar');
  const peloAtalho = matchMedia('(display-mode: standalone)').matches || navigator.standalone;
  const ua = navigator.userAgent;
  const ehIOS = /iphone|ipad|ipod/i.test(ua) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  const ehAndroid = /android/i.test(ua);
  const foraDoSafari = ehIOS && /CriOS|FxiOS|EdgiOS|Instagram|FBAN|FBAV|Line\/|GSA\//i.test(ua);
  let promptInstalar = null;
  if (peloAtalho) guardar('atalhoAdicionado', '1');
  function podeInstalar() { return !ler('atalhoAdicionado') && !peloAtalho; }

  function mostrarPasso(id) {
    ['instPergunta', 'instAndroid', 'instIos'].forEach(p => { $(p).hidden = p !== id; });
    modalInst.scrollTop = 0;
  }
  function passoAndroid() {
    const umClique = !!promptInstalar;
    $('btnInstalar').hidden = !umClique; $('androidFeito').hidden = umClique;
    $('androidPassos').hidden = umClique;
    $('androidTexto').textContent = umClique
      ? 'Toque no botão abaixo e confirme. O ícone da apuração vai aparecer na sua tela inicial, e no domingo é só tocar nele para ver os resultados.'
      : 'Seu navegador pede para fazer pelo menu. São três toques:';
    mostrarPasso('instAndroid');
  }
  function passoIos() { $('iosForaSafari').hidden = !foraDoSafari; mostrarPasso('instIos'); }

  function abrirInstalar() {
    if (!podeInstalar()) return;
    document.querySelectorAll('.opcao-so').forEach(b => {
      const provavel = (b.dataset.so === 'ios' && ehIOS) || (b.dataset.so === 'android' && ehAndroid);
      b.classList.toggle('sugerida', provavel);
      b.querySelector('.detectado').hidden = !provavel;
    });
    mostrarPasso('instPergunta');
    abrirModal(modalInst, motivo => { if (motivo !== 'instalado') guardar('instalarDepois', String(Date.now() + 24 * 3600 * 1000)); });
  }
  const marcarAdicionado = () => {
    guardar('atalhoAdicionado', '1'); ev('instalou');
    document.querySelectorAll('[data-instalar]').forEach(b => b.remove());
    if (modalAtual === modalInst) fecharModal('instalado');
  };
  addEventListener('beforeinstallprompt', e => { e.preventDefault(); promptInstalar = e; });
  addEventListener('appinstalled', marcarAdicionado);
  modalInst.addEventListener('click', e => {
    const so = e.target.closest('[data-so]');
    if (so) { so.dataset.so === 'ios' ? passoIos() : passoAndroid(); return; }
    if (e.target.closest('[data-inst-voltar]')) { mostrarPasso('instPergunta'); return; }
    if (e.target.closest('[data-inst-fechar]')) fecharModal('agora-nao');
  });
  $('btnInstalar').addEventListener('click', async () => {
    if (!promptInstalar) { passoAndroid(); return; }
    promptInstalar.prompt();
    const r = await promptInstalar.userChoice;
    promptInstalar = null;
    if (r.outcome === 'accepted') marcarAdicionado(); else passoAndroid();
  });
  $('androidFeito').addEventListener('click', marcarAdicionado);
  $('iosFeito').addEventListener('click', marcarAdicionado);
  document.addEventListener('click', e => { if (e.target.closest('[data-instalar]')) abrirInstalar(); });

  var convitePendente = null;   // var: pode ser usada antes desta linha (abrirApp roda na inicialização)
  function agendarConvite() {
    clearTimeout(convitePendente);
    convitePendente = setTimeout(() => {
      if (app.hidden) return;
      if (modalAtual) { agendarConvite(); return; }      // espera outro modal fechar
      if (Date.now() > Number(ler('instalarDepois') || 0)) abrirInstalar();
    }, 4000);
  }
  // Botão fixo no cabeçalho: sempre disponível enquanto o atalho não foi adicionado
  const botaoTopo = $('instalarTopo');
  if (podeInstalar()) botaoTopo.hidden = false;
  if (!app.hidden) agendarConvite();

  // ================= Colinha em bloco de notas (fica só no aparelho) =================
  // Ordem da colinha: do cargo mais acompanhado para o menos (a urna pede na ordem inversa)
  function ordemUrna(uf) { return [
    ['pres', 'Presidente', 2],
    ['gov', 'Governador', 2],
    ['sen1', 'Senador (1ª vaga)', 3],
    ['sen2', 'Senador (2ª vaga)', 3],
    ['depest', uf === 'df' ? 'Dep. distrital' : 'Dep. estadual', 5],
    ['depfed', 'Dep. federal', 4],
  ]; }
  function lerCola() { try { return JSON.parse(ler('colinha') || '{}'); } catch (e) { return {}; } }
  function blocoCola() {
    const cola = lerCola();
    return `<section class="bloco" id="blocoCola" aria-labelledby="tituloBloco" hidden>
      <div class="bloco-topo"><h2 id="tituloBloco">Minha colinha</h2><button type="button" class="link-bloco" id="imprimirCola">Imprimir</button></div>
      <div class="bloco-aviso" role="note">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/></svg>
        <p><strong>Sua colinha é só sua.</strong> Fica salva só neste celular. Não enviamos para nenhum site, não é pesquisa e ninguém mais vê.</p>
      </div>
      <div class="bloco-linhas">${ordemUrna(ufAtual).map(([id, rot, dig]) => `<div class="bloco-linha">
          <label for="cola-${id}">${rot}</label>
          <input id="cola-${id}" class="num" inputmode="numeric" maxlength="${dig}" placeholder="${'_'.repeat(dig)}" value="${esc((cola[id] || {}).num)}" autocomplete="off">
          <input id="cola-${id}-nome" class="nome" maxlength="40" placeholder="nome" aria-label="${rot}: nome" value="${esc((cola[id] || {}).nome)}" autocomplete="off">
          <p class="achado" id="achado-${id}" aria-live="polite"></p>
        </div>`).join('')}</div>
      <p class="bloco-celular">Monte aqui e leve no papel: na hora de votar, o celular fica com o mesário.</p>
    </section>`;
  }
  function contarCola() { const c = lerCola(); return Object.values(c).filter(v => v.num).length; }
  function textoBotaoCola(aberta) {
    const n = contarCola(), total = ordemUrna(ufAtual).length;
    return (aberta ? 'Esconder colinha' : 'Minha colinha') + (n ? ` · ${n}/${total}` : '') + (aberta ? ' ▲' : ' ▼');
  }
  function botaoCola() {
    return `<button type="button" class="btn grande btn-icone botao-cola" id="alternarCola" aria-expanded="false" aria-controls="blocoCola">
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M6 2h9l4 4v16H6z"/><path d="M9 11h7M9 15h7M9 19h4"/></svg>
      <span id="alternarColaTexto">${textoBotaoCola(false)}</span></button>`;
  }
  function salvarCola() {
    const cola = {};
    ordemUrna(ufAtual).forEach(([id]) => {
      const n = $('cola-' + id), nm = $('cola-' + id + '-nome');
      if (!n) return;
      const num = n.value.replace(/\D/g, ''), nome = limparNome(nm.value);
      if (num || nome) cola[id] = {num, nome};
    });
    guardar('colinha', JSON.stringify(cola));
    return cola;
  }
  // ---- Busca do candidato: a lista do estado inteiro vem do servidor e o número é procurado
  // aqui no celular. O número digitado nunca sai do aparelho.
  const CHAVE_LISTA = {pres: 'pres', gov: 'gov', sen1: 'sen', sen2: 'sen', depest: 'depest', depfed: 'depfed'};
  let listaCand = null, listaUf = '';
  async function carregarLista() {
    if (listaUf === ufAtual && listaCand) return listaCand;
    try {
      const r = await fetch(`/api/candidatos/${ufAtual}/`, {headers: {'Accept': 'application/json'}});
      listaCand = r.ok ? await r.json() : null; listaUf = ufAtual;
    } catch (e) { listaCand = null; }
    return listaCand;
  }
  function mostrarAchado(id) {
    const campo = $('cola-' + id), saida = $('achado-' + id);
    if (!campo || !saida) return;
    const linha = campo.closest('.bloco-linha'), nomeIn = $('cola-' + id + '-nome');
    const dig = Number(campo.getAttribute('maxlength')), num = campo.value;
    saida.className = 'achado'; saida.replaceChildren();
    linha.classList.remove('com-candidato');
    nomeIn.hidden = false;
    const doCargo = listaCand && listaCand[CHAVE_LISTA[id]];
    if (!doCargo || num.length !== dig) return;
    const c = doCargo[num];
    if (c) {
      // Mostra o nome oficial no lugar do campo "nome" (texto puro, sem HTML)
      const nome = document.createElement('span'); nome.className = 'achado-nome'; nome.textContent = c[0];
      saida.append(nome);
      if (c[1]) { const p = document.createElement('span'); p.className = 'achado-partido'; p.textContent = c[1]; saida.append(p); }
      saida.classList.add('ok');
      linha.classList.add('com-candidato');
      nomeIn.hidden = true;
    } else {
      saida.textContent = 'Número não encontrado para este cargo. Confira.';
      saida.classList.add('erro');
    }
  }

  let colaUsada = false;
  function ligarCola() {
    const bloco = alvo.querySelector('.bloco');
    if (!bloco) return;
    carregarLista().then(() => ordemUrna(ufAtual).forEach(([id]) => mostrarAchado(id)));
    bloco.addEventListener('input', e => {
      if (e.target.classList.contains('num')) {
        e.target.value = e.target.value.replace(/\D/g, '');
        mostrarAchado(e.target.id.replace('cola-', ''));
      }
      salvarCola();                                  // salva sozinho a cada letra
      if (!colaUsada) { colaUsada = true; ev('cola_aberta'); }   // conta só o uso, nunca o conteúdo
    });
    const botao = $('alternarCola');
    if (matchMedia('(min-width: 768px)').matches) {
      bloco.hidden = false; botao.setAttribute('aria-expanded', 'true');
      $('alternarColaTexto').textContent = textoBotaoCola(true);
    }
    botao.addEventListener('click', () => {
      const abrir = bloco.hidden;
      bloco.hidden = !abrir;
      botao.setAttribute('aria-expanded', String(abrir));
      $('alternarColaTexto').textContent = textoBotaoCola(abrir);
      if (abrir) { if (!matchMedia('(min-width: 768px)').matches) bloco.scrollIntoView({behavior: 'smooth', block: 'start'}); if (!colaUsada) { colaUsada = true; ev('cola_aberta'); } }
    });
    bloco.addEventListener('input', () => { $('alternarColaTexto').textContent = textoBotaoCola(!bloco.hidden); });
    $('imprimirCola').addEventListener('click', () => {
      const cola = salvarCola();
      $('colaImpressao').innerHTML = `<h1>Minha colinha · Eleições 2026</h1><table>${ordemUrna(ufAtual).map(([id, rot]) =>
        { const num = (cola[id] || {}).num || '', achado = listaCand && listaCand[CHAVE_LISTA[id]] && listaCand[CHAVE_LISTA[id]][num];
          const nome = (cola[id] && cola[id].nome) || (achado ? achado[0] : '');
          return `<tr><td>${rot}${nome ? '<br>' + esc(nome) : ''}</td><td class="n">${esc(num)}</td></tr>`; }).join('')}</table>`;
      window.print();
    });
  }
})();