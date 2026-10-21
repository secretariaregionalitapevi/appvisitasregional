document.addEventListener("DOMContentLoaded", () => {
  if (!requireAuth()) return;
  const $ = selector => document.querySelector(selector);
  const state = { context: null, visits: [] };
  const dateInput = $("#route-date");
  dateInput.value = new Intl.DateTimeFormat("en-CA", { timeZone: "America/Sao_Paulo" }).format(new Date());

  const escapeHtml = value => String(value ?? "").replace(/[&<>"']/g, char => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char]));
  const cleanAddress = addr => String(addr || "").replace(/^\[[^\]]+\]\s*/, "").trim();
  const cleanTitle = value => String(value || "Família").replace(/^visita\s*-\s*/i, "").replace(/^visita\s+/i, "").trim();
  const getCategoryBadge = categoria => {
    const raw = String(categoria || "GVI").trim().toUpperCase();
    if (raw.includes("GVM") || raw.includes("MOCIDADE")) return { class: "cat-gvm", label: "GVM: Mocidade" };
    if (raw.includes("GVE") || raw.includes("ENCARREGADO")) return { class: "cat-gve", label: "GVE: Encarregados" };
    if (raw.includes("RF") || raw.includes("FAMILIAR")) return { class: "cat-rf", label: "RF: Reunião Familiar" };
    if (raw.includes("RE") || raw.includes("EVANGELIZA")) return { class: "cat-re", label: "RE: Evangelização" };
    return { class: "cat-gvi", label: "GVI: Irmandade" };
  };
  const time = value => value ? new Date(value).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit", timeZone: "America/Sao_Paulo" }) : "--:--";
  const visitDurationMinutes = visit => {
    if (visit.horario_inicio && visit.horario_fim) {
      const [startHour, startMinute] = visit.horario_inicio.split(":").map(Number);
      const [endHour, endMinute] = visit.horario_fim.split(":").map(Number);
      let durationMinutes = (endHour * 60 + endMinute) - (startHour * 60 + startMinute);
      if (durationMinutes < 0) durationMinutes += 24 * 60;
      if (durationMinutes > 0) return durationMinutes;
    }
    return null;
  };
  const visitTime = (visit, canHighlightExcessDuration = false) => {
    const durationMinutes = visitDurationMinutes(visit);
    if (canHighlightExcessDuration && durationMinutes !== null) return `${durationMinutes} min`;
    return visit.horario_inicio || time(visit.data_inicio);
  };
  const statusClass = value => ({ Realizada: "done", Cancelada: "cancel", "Não realizada": "missed", Marcada: "pending" }[value] || "pending");
  const planningPeriod = visit => {
    const hour = Number(new Intl.DateTimeFormat("pt-BR", {
      timeZone: "America/Sao_Paulo", hour: "2-digit", hourCycle: "h23"
    }).format(new Date(visit.data_inicio)));
    const preference = String(visit.preferencia_periodo_visita || visit.periodo || visit.preferencia_periodo || "")
      .normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
    if (["manha", "tarde", "noite"].includes(visit.periodo_planejado)) return visit.periodo_planejado;
    if (preference.includes("manha")) return "manha";
    if (preference.includes("tarde")) return "tarde";
    if (preference.includes("noite")) return "noite";
    return hour < 12 ? "manha" : hour < 18 ? "tarde" : "noite";
  };
  let toastTimer = null;
  const toast = (message, error = false) => {
    const el = $("#toast");
    const openDialog = document.querySelector("dialog[open]");
    const host = openDialog || document.body;
    if (el.parentElement !== host) host.appendChild(el);
    el.textContent = message;
    el.className = `app-toast show ${error ? "error" : ""}`;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => {
      el.classList.remove("show");
      setTimeout(() => {
        if (!el.classList.contains("show") && el.parentElement !== document.body) document.body.appendChild(el);
      }, 300);
    }, 4500);
  };
  window.toast = toast;
  let successDialogTimer = null;
  const successAlert = (title, message, duration = 2600) => {
    const dialog = $("#success-dialog");
    const progress = $("#success-dialog-progress-bar");
    $("#success-dialog-title").textContent = title;
    $("#success-dialog-message").textContent = message;
    clearTimeout(successDialogTimer);
    dialog.style.setProperty("--success-duration", `${duration}ms`);
    progress.classList.remove("is-running");
    void progress.offsetWidth;
    progress.classList.add("is-running");
    if (!dialog.open) dialog.showModal();
    successDialogTimer = setTimeout(() => {
      if (dialog.open) dialog.close();
    }, duration);
  };
  $("#success-dialog-ok").onclick = () => {
    clearTimeout(successDialogTimer);
    if ($("#success-dialog").open) $("#success-dialog").close();
  };
  const payload = async response => {
    const data = await response.json();
    if (!response.ok) {
      const error = new Error(data.error || "Não foi possível concluir.");
      Object.assign(error, data);
      throw error;
    }
    return data;
  };
  const confirmRecentVisit = warning => new Promise(resolve => {
    const dialog = $("#recent-visit-dialog");
    const recent = warning.visita_recente || {};
    const days = Number(recent.dias_desde_visita || 0);
    const elapsed = days === 0 ? "hoje" : `há ${days} ${days === 1 ? "dia" : "dias"}`;
    const date = recent.data_visita
      ? new Date(recent.data_visita).toLocaleDateString("pt-BR", { timeZone: "America/Sao_Paulo" })
      : "Não informada";
    $("#recent-visit-message").textContent = `Esta família recebeu uma visita ${elapsed}. Deseja realmente incluí-la novamente no roteiro?`;
    $("#recent-visit-team").textContent = recent.equipe || "Equipe não informada";
    $("#recent-visit-date").textContent = date;
    const interval = Number(recent.intervalo_entre_visitas ?? days);
    const recommended = Number(recent.intervalo_recomendado || 35);
    $("#recent-visit-rule").textContent = `Na data escolhida, o intervalo entre as visitas será de ${interval} ${interval === 1 ? "dia" : "dias"}. O recomendado é aguardar ${recommended} dias; o novo agendamento não será bloqueado.`;

    const finish = confirmed => {
      $("#recent-visit-cancel").onclick = null;
      $("#recent-visit-confirm").onclick = null;
      dialog.oncancel = null;
      if (dialog.open) dialog.close();
      resolve(confirmed);
    };
    $("#recent-visit-cancel").onclick = () => finish(false);
    $("#recent-visit-confirm").onclick = () => finish(true);
    dialog.oncancel = event => { event.preventDefault(); finish(false); };
    dialog.showModal();
  });
  const showSameDayVisitConflict = warning => new Promise(resolve => {
    const dialog = $("#duplicate-visit-dialog");
    const existing = warning.visita_existente || {};
    const date = existing.data_visita
      ? new Date(existing.data_visita).toLocaleDateString("pt-BR", { timeZone: "America/Sao_Paulo" })
      : "data selecionada";
    $("#duplicate-visit-name").textContent = existing.titulo || "esta família";
    $("#duplicate-visit-team").textContent = existing.equipe || "Equipe não informada";
    $("#duplicate-visit-date").textContent = date;

    const finish = () => {
      $("#duplicate-visit-close").onclick = null;
      dialog.oncancel = null;
      if (dialog.open) dialog.close();
      resolve();
    };
    $("#duplicate-visit-close").onclick = finish;
    dialog.oncancel = event => { event.preventDefault(); finish(); };
    dialog.showModal();
  });
  const postWithRecentVisitConfirmation = async (url, body) => {
    try {
      return await payload(await authFetch(url, { method: "POST", body: JSON.stringify(body) }));
    } catch (error) {
      if (error.code === "DUPLICATE_FAMILY_VISIT_SAME_DAY") {
        await showSameDayVisitConflict(error);
        return null;
      }
      if (error.code !== "RECENT_FAMILY_VISIT" || body.confirmar_visita_recente) throw error;
      const confirmed = await confirmRecentVisit(error);
      if (!confirmed) return null;
      body.confirmar_visita_recente = true;
      return payload(await authFetch(url, { method: "POST", body: JSON.stringify(body) }));
    }
  };

  const formatAddressHtml = rawAddr => {
    const cleaned = cleanAddress(rawAddr);
    if (!cleaned) return '<div class="visit-address">⌖ Endereço não informado</div>';

    const parts = cleaned.split(/\s+-\s+/);
    if (parts.length >= 3) {
      const mainStreet = parts.slice(0, 2).join(" - ");
      const complement = parts.slice(2).join(" - ");
      return `<div class="visit-address">⌖ ${escapeHtml(mainStreet)}</div>
              <div class="visit-address-extra" style="font-size: 11px; color: #64748b; margin-top: 2px; line-height: 1.3; font-weight: 500;">↳ ${escapeHtml(complement)}</div>`;
    } else if (parts.length === 2 && (parts[1].toLowerCase().includes("próximo") || parts[1].toLowerCase().includes("proximo") || parts[1].toLowerCase().includes("ap") || parts[1].toLowerCase().includes("bloco") || parts[1].toLowerCase().includes("casa"))) {
      return `<div class="visit-address">⌖ ${escapeHtml(parts[0])}</div>
              <div class="visit-address-extra" style="font-size: 11px; color: #64748b; margin-top: 2px; line-height: 1.3; font-weight: 500;">↳ ${escapeHtml(parts[1])}</div>`;
    }

    return `<div class="visit-address">⌖ ${escapeHtml(cleaned)}</div>`;
  };

  function render() {
    const visits = state.visits;
    $("#count-total").textContent = visits.length;
    $("#count-done").textContent = visits.filter(v => v.status === "Realizada").length;
    $("#count-pending").textContent = visits.filter(v => !["Realizada", "Cancelada", "Não realizada"].includes(v.status)).length;
    $("#count-unsuccessful").textContent = visits.filter(v => ["Cancelada", "Não realizada"].includes(v.status)).length;
    $("#state").hidden = visits.length > 0;
    $("#state").textContent = visits.length ? "" : (state.context?.assignmentMissing && !state.context?.isGlobal ? "Seu cadastro está sem vínculo de equipe local ou grupo regional. Solicite a atualização do cadastro." : "Nenhuma visita encontrada para esta seleção e data.");
    const renderCards = laneVisits => laneVisits.map(visit => {
      const index = visits.indexOf(visit);
      const period = planningPeriod(visit);
      const durationMinutes = visitDurationMinutes(visit);
      const canHighlightExcessDuration = Boolean(state.context?.canHighlightExcessDuration);
      const durationClass = canHighlightExcessDuration && durationMinutes !== null
        ? (durationMinutes > 30 ? "visit-duration-exceeded" : "visit-duration")
        : "";
      const phoneNum = visit.celular || visit.telefone || visit.whatsapp || visit.celular_contato || visit.telefone_contato || visit.contato;
      const displayAddress = cleanAddress(visit.endereco_visitado);
      const title = cleanTitle(visit.titulo);
      const cat = getCategoryBadge(visit.categoria);
      const restrictedNote = state.context?.canViewRestrictedNotes && visit.apontamentos_restritos
        ? `<div class="restricted-note visit-card-note"><span class="restricted-note-title">🛡️ Apontamento especial</span><span>${escapeHtml(visit.apontamentos_restritos)}</span></div>`
        : "";
      const preferenceValue = visit.preferencia_periodo_visita || visit.periodo || visit.preferencia_periodo;
      const visitPreference = preferenceValue
        ? `<span class="visit-preference">☀️ Prefere ${escapeHtml(String(preferenceValue).toLowerCase())}</span>`
        : "";
      const additionalCategory = visit.classificacao_adicional
        ? `<span class="additional-category">🏷️ ${escapeHtml(visit.classificacao_adicional)}</span>`
        : "";
      const canSwipeDelete = Boolean(state.context?.canDeleteVisits && visit.status === "Marcada");
      const cardHtml = `<div class="visit-card${visit.status === "Marcada" ? " is-remappable" : " is-locked"}${canSwipeDelete ? " can-swipe-delete" : ""}" data-id="${escapeHtml(visit.id)}" data-period="${period}" tabindex="0" role="button">
      ${visit.status === "Marcada" ? `<button type="button" class="kanban-drag-handle" draggable="true" aria-label="Arrastar ${escapeHtml(title)} para outro período" title="Arraste para Manhã, Tarde ou Noite"><span aria-hidden="true">⠿</span></button>` : ""}
      <span class="route-number">${String(index + 1).padStart(2, "0")}</span>
      
      <div class="visit-info">
        <strong class="visit-title" title="${escapeHtml(title)}">${escapeHtml(title)}</strong>
        ${formatAddressHtml(visit.endereco_visitado)}
        <div class="visit-meta">
          <b class="${durationClass}">${escapeHtml(visitTime(visit, canHighlightExcessDuration))}</b>
          <span>${escapeHtml(visit.setor || "Setor não informado")}</span>
        </div>
        <div class="visit-tags">
          <span class="category-badge ${cat.class}">${escapeHtml(cat.label)}</span>
          <span class="team-badge${visit.equipe_responsavel ? "" : " team-badge-unassigned"}" aria-label="Equipe respons&#225;vel: ${escapeHtml(visit.equipe_responsavel || "Sem equipe")}">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="9" cy="8" r="3"/><path d="M3 20v-2a6 6 0 0 1 12 0v2M16 5a3 3 0 0 1 0 6M21 20v-2a6 6 0 0 0-3-5.2"/></svg>
            ${escapeHtml(visit.equipe_responsavel || "Sem equipe")}
          </span>
          ${visitPreference}
          ${additionalCategory}
        </div>
      </div>

      <div class="visit-actions">
        ${displayAddress ? `
        <a href="https://waze.com/ul?q=${encodeURIComponent(displayAddress)}" target="_blank" class="action-icon waze-btn" onclick="event.stopPropagation()" title="Abrir no Waze">
          <svg width="32" height="32" viewBox="0 0 40 40" fill="none">
            <rect width="40" height="40" rx="6" fill="#1CD1FF"/>
            <path d="M28 20c0-4.42-3.58-8-8-8s-8 3.58-8 8c0 1.8.6 3.45 1.6 4.8L12 28l3.6-1.4c1.3.8 2.8 1.4 4.4 1.4 4.42 0 8-3.58 8-8z" fill="#FFFFFF" stroke="#000000" stroke-width="2" stroke-linejoin="round"/>
            <circle cx="17" cy="19" r="1.5" fill="#000000"/>
            <circle cx="23" cy="19" r="1.5" fill="#000000"/>
            <path d="M17.5 23c1.2 1 2.8 1 4 0" stroke="#000000" stroke-width="2" stroke-linecap="round"/>
            <circle cx="16" cy="28" r="2" fill="#000000"/>
            <circle cx="24" cy="28" r="2" fill="#000000"/>
          </svg>
        </a>
        <a href="https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(displayAddress)}" target="_blank" class="action-icon maps-btn" onclick="event.stopPropagation()" title="Abrir no Google Maps">
          <svg width="32" height="32" viewBox="0 0 40 40" fill="none" aria-hidden="true">
            <path d="M20 3.5c-7.18 0-13 5.68-13 12.69 0 9.52 13 20.31 13 20.31s13-10.79 13-20.31C33 9.18 27.18 3.5 20 3.5Z" fill="#EA4335"/>
            <path d="M8.9 9.6A12.45 12.45 0 0 0 7 16.19c0 4.08 2.39 8.45 5.15 12.12L20 20.65 8.9 9.6Z" fill="#4285F4"/>
            <path d="M12.15 28.31A56.9 56.9 0 0 0 20 36.5s3.35-2.78 6.65-6.55L20 20.65l-7.85 7.66Z" fill="#34A853"/>
            <path d="M31.15 9.63 20 20.65l6.65 9.3C30.03 26.08 33 21.36 33 16.19c0-2.39-.67-4.63-1.85-6.56Z" fill="#FBBC04"/>
            <circle cx="20" cy="16" r="6.1" fill="#FFFFFF"/>
            <circle cx="20" cy="16" r="3.25" fill="#4285F4"/>
          </svg>
        </a>` : ''}
        <a href="${phoneNum ? `https://wa.me/55${String(phoneNum).replace(/\D/g, '')}` : 'javascript:void(0)'}" target="_blank" class="action-icon whatsapp-btn" onclick="event.stopPropagation();${!phoneNum ? "toast('Telefone não cadastrado para esta família.', true);return false;" : ""}" title="WhatsApp">
          <svg width="32" height="32" viewBox="0 0 40 40" fill="none">
            <rect width="40" height="40" rx="6" fill="#25D366"/>
            <path fill="#FFFFFF" d="M20.01 8c-6.07 0-11 4.93-11 11 0 1.94.51 3.83 1.47 5.5L9 31l6.61-1.47c1.61.88 3.43 1.34 5.4 1.34h.01c6.07 0 11-4.93 11-11 0-2.94-1.14-5.7-3.22-7.78A10.94 10.94 0 0 0 20.01 8zm5.99 15.65c-.26.74-1.32 1.41-1.84 1.47-.48.06-1.11.08-1.78-.13-.41-.13-1.04-.33-1.8-.66-3.18-1.37-5.25-4.6-5.41-4.81-.16-.21-1.3-1.73-1.3-3.3 0-1.57.82-2.34 1.11-2.66.29-.32.63-.4.84-.4l.6-.01c.19 0 .45-.07.7.53.26.63.89 2.18.97 2.34.08.16.13.34.03.55-.1.21-.16.34-.32.53-.16.19-.34.42-.48.56-.16.16-.33.33-.14.66.19.33.85 1.4 1.83 2.27 1.26 1.12 2.32 1.47 2.65 1.63.33.16.52.14.71-.08.19-.22.82-.96 1.04-1.29.22-.33.45-.27.75-.16.3.11 1.9.89 2.23 1.06.33.17.55.25.63.39.08.14.08.81-.18 1.55z"/>
          </svg>
        </a>
        <a href="${phoneNum ? `tel:${String(phoneNum).replace(/\D/g, '')}` : 'javascript:void(0)'}" class="action-icon phone-btn" onclick="event.stopPropagation();${!phoneNum ? "toast('Telefone não cadastrado para esta família.', true);return false;" : ""}" title="Ligar (Linha Convencional)">
          <svg width="32" height="32" viewBox="0 0 40 40" fill="none" aria-hidden="true">
            <rect width="40" height="40" rx="6" fill="#0284C7"/>
            <path d="M12.8 10.5h3.65l1.82 5.08-2.25 1.78a16.62 16.62 0 0 0 6.62 6.62l1.78-2.25 5.08 1.82v3.65a2.3 2.3 0 0 1-2.3 2.3c-9.22 0-16.7-7.48-16.7-16.7a2.3 2.3 0 0 1 2.3-2.3Z" fill="#FFFFFF" stroke="#FFFFFF" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
        </a>
      </div>

      <span class="status-pill ${statusClass(visit.status)}">${escapeHtml(visit.status === "Marcada" ? "Agendada" : visit.status || "Agendada")}</span>

      <span class="chevron">›</span>
      ${restrictedNote}
    </div>`;
      if (!canSwipeDelete) return cardHtml;
      return `<div class="visit-swipe-shell" data-id="${escapeHtml(visit.id)}">
        <div class="visit-swipe-delete" aria-hidden="true">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18"/><path d="M8 6V4h8v2"/><path d="m19 6-1 14H6L5 6"/><path d="M10 11v5M14 11v5"/></svg>
          <span>Excluir</span>
        </div>
        ${cardHtml}
      </div>`;
    }).join("");
    const morningVisits = visits.filter(visit => planningPeriod(visit) === "manha");
    const afternoonVisits = visits.filter(visit => planningPeriod(visit) === "tarde");
    const nightVisits = visits.filter(visit => planningPeriod(visit) === "noite");
    const lane = (period, icon, title, items) => `<section class="kanban-lane" data-period="${period}">
      <header class="kanban-lane-header"><span>${icon} ${title}</span><strong>${items.length}</strong></header>
      <div class="kanban-lane-body">${renderCards(items) || `<div class="kanban-empty">Arraste uma visita para ${title.toLowerCase()}</div>`}</div>
    </section>`;
    $("#visit-list").innerHTML = `<div class="visit-kanban">
      ${lane("manha", "☀️", "Manhã", morningVisits)}
      ${lane("tarde", "🌤️", "Tarde", afternoonVisits)}
      ${lane("noite", "🌙", "Noite", nightVisits)}
    </div>`;
  }

  const adminWrap = $("#admin-comum-wrap");
  const cidadeSelect = $("#admin-cidade-select");
  const comumPickerBtn = $("#comum-picker-btn");
  const comumPickerLabel = $("#comum-picker-label");
  const comumPickerPanel = $("#comum-picker-panel");
  const comumPanelSearch = $("#comum-panel-search");
  const comumPanelList = $("#comum-panel-list");

  let allComunsData = [];
  let allCidadesList = [];
  let activeSelectedComum = null;

  async function loadComunsData() {
    try {
      const data = await payload(await authFetch("/api/mobile/comuns"));
      allComunsData = data.comuns || [];
      allCidadesList = data.cidades || [];

      if (cidadeSelect) {
        const userCidade = state.context?.municipio || "";
        cidadeSelect.innerHTML = '<option value="" style="color:#333;">Todos os Municípios</option>' +
          allCidadesList.map(c => `<option value="${escapeHtml(c)}" ${userCidade && userCidade.toLowerCase() === c.toLowerCase() ? 'selected' : ''} style="color:#333;">${escapeHtml(c)}</option>`).join("");
      }
      renderComumPanelList();
    } catch (e) {
      console.error("Erro ao carregar comuns e cidades:", e);
    }
  }

  const normalizeText = str => String(str || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .trim();

  function getFilteredComuns(searchTerm = "") {
    const selCidade = cidadeSelect ? cidadeSelect.value : "";
    let filtered = allComunsData;
    if (selCidade) {
      filtered = allComunsData.filter(item => String(item.cidade || "").toLowerCase() === selCidade.toLowerCase());
    }
    const distinct = Array.from(new Set(filtered.map(i => i.comum))).sort();
    if (!searchTerm) return distinct;
    const normSearch = normalizeText(searchTerm);
    return distinct.filter(c => normalizeText(c).includes(normSearch));
  }

  function renderComumPanelList(searchTerm = "") {
    if (!comumPanelList) return;
    const list = getFilteredComuns(searchTerm);
    let html = `<div class="comum-panel-item ${!activeSelectedComum ? 'active' : ''}" data-val="" style="padding:8px 10px;cursor:pointer;border-bottom:1px solid #f1f5f9;font-size:12.5px;font-weight:600;color:#1e3a8a;border-radius:6px;${!activeSelectedComum ? 'background:#e0f2fe;font-weight:800;' : ''}">Todas as comuns</div>`;
    if (!list.length) {
      html += '<div style="padding:10px 12px;color:#64748b;font-size:12.5px;">Nenhuma comum encontrada</div>';
    } else {
      html += list.map(c => 
        `<div class="comum-panel-item ${activeSelectedComum === c ? 'active' : ''}" data-val="${escapeHtml(c)}" style="padding:8px 10px;cursor:pointer;border-bottom:1px solid #f1f5f9;font-size:12.5px;font-weight:600;color:#1e3a8a;border-radius:6px;${activeSelectedComum === c ? 'background:#e0f2fe;font-weight:800;' : ''}">${escapeHtml(c)}</div>`
      ).join("");
    }
    comumPanelList.innerHTML = html;
  }

  if (comumPickerBtn && comumPickerPanel) {
    comumPickerBtn.onclick = (e) => {
      e.stopPropagation();
      const isVisible = comumPickerPanel.style.display === 'block';
      comumPickerPanel.style.display = isVisible ? 'none' : 'block';
      if (!isVisible && comumPanelSearch) {
        comumPanelSearch.value = "";
        renderComumPanelList("");
        setTimeout(() => comumPanelSearch.focus(), 100);
      }
    };

    document.addEventListener("click", (e) => {
      if (comumPickerPanel && !comumPickerPanel.contains(e.target) && !comumPickerBtn.contains(e.target)) {
        comumPickerPanel.style.display = 'none';
      }
    });

    if (comumPanelSearch) {
      comumPanelSearch.oninput = (e) => {
        renderComumPanelList(e.target.value);
      };
    }

    if (comumPanelList) {
      comumPanelList.onclick = async (e) => {
        const item = e.target.closest('.comum-panel-item');
        if (item) {
          const val = item.dataset.val;
          activeSelectedComum = val;
          if (comumPickerLabel) comumPickerLabel.textContent = val || "Todas as comuns";
          comumPickerPanel.style.display = 'none';
          await loadContext(val);
          await loadVisits();
        }
      };
    }
  }

  if (cidadeSelect) {
    cidadeSelect.onchange = async () => {
      renderComumPanelList(comumPanelSearch ? comumPanelSearch.value : "");
      const filteredComuns = getFilteredComuns();
      const userComum = state.context?.comum || "";
      if (userComum && filteredComuns.includes(userComum)) {
        activeSelectedComum = userComum;
      } else if (activeSelectedComum && !filteredComuns.includes(activeSelectedComum)) {
        activeSelectedComum = filteredComuns.length ? filteredComuns[0] : "";
      }
      if (comumPickerLabel) {
        comumPickerLabel.textContent = activeSelectedComum || "Todas as comuns";
      }
      await loadVisits();
    };
  }

  async function loadContext(selectedComum = null) {
    const targetComum = selectedComum !== null ? selectedComum : activeSelectedComum;
    const activeCidade = cidadeSelect ? cidadeSelect.value : "";
    let params = [];
    if (targetComum) params.push(`comum=${encodeURIComponent(targetComum)}`);
    if (activeCidade) params.push(`municipio=${encodeURIComponent(activeCidade)}`);
    const query = params.length ? `?${params.join("&")}` : "";
    state.context = await payload(await authFetch(`/api/mobile/context${query}`));
    
    $("#welcome").textContent = `Olá, ${String(state.context.usuario || "irmão").split(" ")[0]}!`;
    $("#team-line").textContent = `${state.context.equipe} • ${state.context.comum || "Geral"}`;
    $("#header-comum").textContent = state.context.comum || "Geral";

    const cidadeWrap = $("#admin-cidade-wrap");
    if (adminWrap || cidadeWrap) {
      if (state.context.isGlobal) {
        if (cidadeWrap) cidadeWrap.hidden = false;
        if (adminWrap) adminWrap.hidden = false;
        if (!allComunsData.length) await loadComunsData();

        if (cidadeSelect && !cidadeSelect.value && state.context.municipio) {
          cidadeSelect.value = state.context.municipio;
        }

        if (activeSelectedComum === null && state.context.comum) {
          activeSelectedComum = state.context.comum;
        }

        if (comumPickerLabel) {
          comumPickerLabel.textContent = activeSelectedComum || "Todas as comuns";
        }
      } else {
        if (cidadeWrap) cidadeWrap.hidden = true;
        if (adminWrap) adminWrap.hidden = true;
      }
    }

    // Populate schedule dropdown
    if (state.context.members) {
      const searchInput = $("#schedule-member-search");
      const listDiv = $("#schedule-member-list");
      const idInput = $("#schedule-member-id");

      const renderList = (searchTerm = "") => {
        const norm = normalizeText(searchTerm);
        const filtered = (state.context.members || []).filter(m =>
          normalizeText(m.nome).includes(norm)
        );
        if (!filtered.length) {
          listDiv.innerHTML = '<div style="padding:10px 12px;color:#64748b;font-size:13px;font-weight:500;">Nenhum membro cadastrado nesta comum</div>';
        } else {
          listDiv.innerHTML = filtered.map(m => `<div class="autocomplete-item" data-id="${escapeHtml(m.id)}" data-name="${escapeHtml(m.nome)}">
            <span class="autocomplete-name">${escapeHtml(m.nome)}</span>
            <span class="autocomplete-address">${escapeHtml(cleanAddress(m.endereco) || "Endereço não informado")}</span>
          </div>`).join("");
        }
      };

      searchInput.onfocus = () => { renderList(searchInput.value); listDiv.style.display = 'block'; };
      searchInput.oninput = (e) => { idInput.value = ""; renderList(e.target.value); listDiv.style.display = 'block'; };
      listDiv.onmousedown = (e) => {
        e.preventDefault();
        const item = e.target.closest('.autocomplete-item');
        if (item && item.dataset.name) {
          searchInput.value = item.dataset.name;
          idInput.value = item.dataset.id || "";
          listDiv.style.display = 'none';
        }
      };
      searchInput.onblur = () => {
        setTimeout(() => { listDiv.style.display = 'none'; }, 200);
      };
    }
  }

  async function loadVisits() {
    $("#state").hidden = false; $("#state").textContent = "Carregando seu roteiro..."; $("#visit-list").innerHTML = "";
    try {
      const activeComum = activeSelectedComum !== null ? activeSelectedComum : (state.context?.comum || "");
      const activeCidade = cidadeSelect ? cidadeSelect.value : "";
      let params = [`data=${dateInput.value}`];
      if (activeComum) params.push(`comum=${encodeURIComponent(activeComum)}`);
      if (activeCidade) params.push(`municipio=${encodeURIComponent(activeCidade)}`);
      const query = `?${params.join("&")}`;
      const data = await payload(await authFetch(`/api/mobile/visitas${query}`));
      state.visits = data.visitas || [];
      render();
    }
    catch (error) { $("#state").textContent = error.message; toast(error.message, true); }
  }

  async function moveVisitToPeriod(visitId, period) {
    const visit = state.visits.find(item => String(item.id) === String(visitId));
    if (!visit || visit.status !== "Marcada" || planningPeriod(visit) === period) return;
    try {
      await payload(await authFetch(`/api/mobile/visitas/${visitId}/periodo`, {
        method: "PATCH", body: JSON.stringify({ periodo: period })
      }));
      await loadVisits();
      const periodLabel = period === "manha" ? "manhã" : period === "tarde" ? "tarde" : "noite";
      const firstName = cleanTitle(visit.titulo).trim().split(/\s+/)[0] || "membro";
      toast(`${firstName}: visita classificada para ${periodLabel}.`);
    } catch (error) {
      toast(error.message, true);
      await loadVisits();
    }
  }

  const confirmDeleteVisit = visit => new Promise(resolve => {
    const dialog = $("#delete-visit-dialog");
    $("#delete-visit-name").textContent = cleanTitle(visit.titulo);
    const finish = confirmed => {
      $("#delete-visit-cancel").onclick = null;
      $("#delete-visit-confirm").onclick = null;
      dialog.oncancel = null;
      if (dialog.open) dialog.close();
      resolve(confirmed);
    };
    $("#delete-visit-cancel").onclick = () => finish(false);
    $("#delete-visit-confirm").onclick = () => finish(true);
    dialog.oncancel = event => { event.preventDefault(); finish(false); };
    dialog.showModal();
  });

  async function deleteVisit(visitId) {
    const visit = state.visits.find(item => String(item.id) === String(visitId));
    if (!visit || !state.context?.canDeleteVisits || visit.status !== "Marcada") return;
    if (!await confirmDeleteVisit(visit)) return;
    const shell = document.querySelector(`.visit-swipe-shell[data-id="${CSS.escape(String(visitId))}"]`);
    shell?.classList.add("is-deleting");
    try {
      await payload(await authFetch(`/api/mobile/visitas/${visitId}`, { method: "DELETE" }));
      await loadVisits();
      toast(`${cleanTitle(visit.titulo)}: visita excluída do roteiro.`);
    } catch (error) {
      shell?.classList.remove("is-deleting");
      toast(error.message, true);
    }
  }

  const nextPeriod = period => ({ manha: "tarde", tarde: "noite", noite: "manha" }[period] || "manha");
  const clearDropTargets = () => document.querySelectorAll(".kanban-lane.is-drop-target")
    .forEach(lane => lane.classList.remove("is-drop-target"));

  let dragState = null;
  $("#visit-list").addEventListener("pointerdown", event => {
    const handle = event.target.closest(".kanban-drag-handle");
    if (!handle || event.pointerType === "mouse") return;
    const card = handle.closest(".visit-card");
    if (!card) return;
    event.preventDefault();
    handle.setPointerCapture?.(event.pointerId);
    dragState = {
      pointerId: event.pointerId,
      card,
      origin: card.dataset.period,
      target: null,
      startX: event.clientX,
      startY: event.clientY,
      moved: false
    };
    card.classList.add("is-dragging");
    document.body.classList.add("kanban-drag-active");
    navigator.vibrate?.(30);
  });

  $("#visit-list").addEventListener("pointermove", event => {
    if (!dragState || dragState.pointerId !== event.pointerId) return;
    event.preventDefault();
    if (Math.hypot(event.clientX - dragState.startX, event.clientY - dragState.startY) > 10) dragState.moved = true;
    if (event.clientY < 72) window.scrollBy({ top: -14, behavior: "auto" });
    else if (event.clientY > window.innerHeight - 72) window.scrollBy({ top: 14, behavior: "auto" });
    clearDropTargets();
    const lane = document.elementFromPoint(event.clientX, event.clientY)?.closest(".kanban-lane");
    if (lane) {
      lane.classList.add("is-drop-target");
      dragState.target = lane.dataset.period;
    }
  });

  const finishPeriodDrag = event => {
    if (!dragState || dragState.pointerId !== event.pointerId) return;
    const { card, origin, target, moved } = dragState;
    card.classList.remove("is-dragging");
    document.body.classList.remove("kanban-drag-active");
    clearDropTargets();
    dragState = null;
    if (target && target !== origin) moveVisitToPeriod(card.dataset.id, target);
    else if (!moved) moveVisitToPeriod(card.dataset.id, nextPeriod(origin));
  };
  $("#visit-list").addEventListener("pointerup", finishPeriodDrag);
  $("#visit-list").addEventListener("pointercancel", finishPeriodDrag);
  $("#visit-list").addEventListener("keydown", event => {
    const handle = event.target.closest(".kanban-drag-handle");
    if (!handle || !["Enter", " "].includes(event.key)) return;
    event.preventDefault();
    const card = handle.closest(".visit-card");
    if (card) {
      moveVisitToPeriod(card.dataset.id, nextPeriod(card.dataset.period));
    }
  });

  let nativeDrag = null;
  $("#visit-list").addEventListener("dragstart", event => {
    const handle = event.target.closest(".kanban-drag-handle[draggable=\"true\"]");
    const card = handle?.closest(".visit-card");
    if (!handle || !card) return;
    nativeDrag = { card, origin: card.dataset.period };
    card.classList.add("is-dragging");
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("text/plain", card.dataset.id);
  });
  $("#visit-list").addEventListener("dragover", event => {
    if (!nativeDrag) return;
    const lane = event.target.closest(".kanban-lane");
    if (!lane) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = "move";
    clearDropTargets();
    lane.classList.add("is-drop-target");
  });
  $("#visit-list").addEventListener("drop", event => {
    if (!nativeDrag) return;
    const lane = event.target.closest(".kanban-lane");
    if (!lane) return;
    event.preventDefault();
    const { card, origin } = nativeDrag;
    const target = lane.dataset.period;
    nativeDrag = null;
    card.classList.remove("is-dragging");
    clearDropTargets();
    if (target !== origin) moveVisitToPeriod(card.dataset.id, target);
  });
  $("#visit-list").addEventListener("dragend", () => {
    nativeDrag?.card.classList.remove("is-dragging");
    nativeDrag = null;
    clearDropTargets();
  });

  let swipeState = null;
  let suppressCardClickUntil = 0;
  const resetSwipeCard = card => {
    if (!card) return;
    card.closest(".visit-swipe-shell")?.classList.remove("is-swipe-active");
    card.classList.remove("is-swiping");
    card.style.transform = "";
  };
  $("#visit-list").addEventListener("pointerdown", event => {
    if ((event.pointerType === "mouse" && event.button !== 0) || event.target.closest("a, button, input, select, textarea")) return;
    const card = event.target.closest(".visit-card.can-swipe-delete");
    if (!card) return;
    swipeState = {
      pointerId: event.pointerId, card, startX: event.clientX, startY: event.clientY,
      offsetX: 0, mode: "pending"
    };
  });
  $("#visit-list").addEventListener("pointermove", event => {
    if (!swipeState || swipeState.pointerId !== event.pointerId) return;
    const dx = event.clientX - swipeState.startX;
    const dy = event.clientY - swipeState.startY;
    if (swipeState.mode === "pending") {
      if (Math.hypot(dx, dy) < 8) return;
      if (Math.abs(dy) >= Math.abs(dx) * 0.9 || dx < 0) {
        swipeState = null;
        return;
      }
      swipeState.mode = "horizontal";
      swipeState.card.classList.add("is-swiping");
      swipeState.card.closest(".visit-swipe-shell")?.classList.add("is-swipe-active");
      swipeState.card.setPointerCapture?.(event.pointerId);
      navigator.vibrate?.(15);
    }
    if (swipeState.mode !== "horizontal") return;
    if (event.pointerType === "mouse" && event.buttons === 0) {
      resetSwipeCard(swipeState.card);
      swipeState = null;
      return;
    }
    event.preventDefault();
    swipeState.offsetX = Math.min(Math.max(dx, 0), 124);
    swipeState.card.style.transform = `translateX(${swipeState.offsetX}px)`;
  });
  const finishSwipe = event => {
    if (!swipeState || swipeState.pointerId !== event.pointerId) return;
    const { card, offsetX, mode } = swipeState;
    swipeState = null;
    if (mode !== "horizontal") return;
    event.preventDefault();
    suppressCardClickUntil = Date.now() + 450;
    const shouldDelete = event.type === "pointerup" && offsetX >= 88;
    if (shouldDelete) {
      card.style.transform = "translateX(104px)";
      navigator.vibrate?.(35);
      setTimeout(() => { resetSwipeCard(card); deleteVisit(card.dataset.id); }, 120);
    } else {
      resetSwipeCard(card);
    }
  };
  $("#visit-list").addEventListener("pointerup", finishSwipe);
  $("#visit-list").addEventListener("pointercancel", finishSwipe);

  $("#visit-list").onclick = event => {
    if (Date.now() < suppressCardClickUntil) return;
    if (event.target.closest(".kanban-drag-handle")) return;
    const card = event.target.closest(".visit-card"); if (!card) return;
    const visit = state.visits.find(item => String(item.id) === card.dataset.id); if (!visit) return;
    $("#visit-id").value = visit.id; $("#visit-name").textContent = cleanTitle(visit.titulo); $("#visit-address").textContent = cleanAddress(visit.endereco_visitado) || "Endereço não informado";
    const restrictedWrap = $("#restricted-note-wrap");
    const restrictedText = $("#restricted-note-text");
    const canShowRestricted = Boolean(state.context?.canViewRestrictedNotes && visit.apontamentos_restritos);
    restrictedWrap.hidden = !canShowRestricted;
    restrictedText.textContent = canShowRestricted ? visit.apontamentos_restritos : "";
    $("#visit-notes").value = visit.observacoes || ""; $("#reason").value = visit.motivo_cancelamento || "";
    $("#actual-start-time").value = visit.horario_inicio || "";
    $("#actual-end-time").value = visit.horario_fim || "";
    document.querySelectorAll('[name="status"]').forEach(input => input.checked = input.value === visit.status);
    updateReason(); $("#visit-dialog").showModal();
  };
  const updateReason = () => {
    const status = document.querySelector('#visit-form [name="status"]:checked')?.value;
    const isDone = status === "Realizada";
    $("#reason-wrap").hidden = !status || isDone;
    $("#reason").required = Boolean(status && !isDone);
    $("#actual-time-wrap").hidden = !isDone;
    if (!isDone) {
      $("#actual-start-time").value = "";
      $("#actual-end-time").value = "";
    }
  };
  document.querySelectorAll('#visit-form [name="status"]').forEach(input => input.onchange = updateReason);

  document.querySelectorAll(".close-dialog").forEach(button => button.onclick = () => $("#visit-dialog").close());
  document.querySelectorAll(".close-family").forEach(button => button.onclick = () => $("#family-dialog").close());
  document.querySelectorAll(".close-schedule").forEach(button => button.onclick = () => $("#schedule-dialog").close());

  const familyScheduleToggle = $("#family-schedule-toggle");
  const familyScheduleFields = $("#family-schedule-fields");
  const familyScheduleCard = familyScheduleToggle?.closest(".optional-visit-card");
  const familyScheduleInputs = familyScheduleFields?.querySelectorAll("input, select") || [];
  const updateFamilyScheduleFields = () => {
    const enabled = Boolean(familyScheduleToggle?.checked);
    if (familyScheduleFields) familyScheduleFields.hidden = !enabled;
    if (familyScheduleCard) familyScheduleCard.classList.toggle("is-active", enabled);
    familyScheduleInputs.forEach(input => {
      input.disabled = !enabled;
      input.required = enabled;
    });
    if (enabled && !$("#family-schedule-date").value) {
      $("#family-schedule-date").value = dateInput.value;
    }
  };
  if (familyScheduleToggle) familyScheduleToggle.onchange = updateFamilyScheduleFields;
  updateFamilyScheduleFields();

  $("#visit-form").onsubmit = async event => {
    event.preventDefault(); const button = event.submitter; button.disabled = true;
    try {
      const status = document.querySelector('[name="status"]:checked')?.value;
      const body = {
        status,
        motivo: $("#reason").value,
        observacoes: $("#visit-notes").value,
        horario_inicio: status === "Realizada" ? $("#actual-start-time").value : "",
        horario_fim: status === "Realizada" ? $("#actual-end-time").value : ""
      };
      await payload(await authFetch(`/api/mobile/visitas/${$("#visit-id").value}`, { method: "PATCH", body: JSON.stringify(body) }));
      $("#visit-dialog").close(); await loadVisits(); toast("Visita atualizada com sucesso.");
    }
    catch (error) { toast(error.message, true); } finally { button.disabled = false; }
  };
  const getContextQuery = () => {
    const activeComum = activeSelectedComum !== null ? activeSelectedComum : (state.context?.comum || "");
    const activeCidade = cidadeSelect ? cidadeSelect.value : "";
    let params = [];
    if (activeComum) params.push(`comum=${encodeURIComponent(activeComum)}`);
    if (activeCidade) params.push(`municipio=${encodeURIComponent(activeCidade)}`);
    return params.length ? `?${params.join("&")}` : "";
  };

  $("#new-family").onclick = () => {
    const activeComum = activeSelectedComum !== null ? activeSelectedComum : (state.context?.comum || "");
    const helperEl = document.querySelector("#family-dialog .helper");
    if (helperEl) {
      helperEl.textContent = activeComum
        ? `O cadastro será vinculado à comum ${activeComum}. O agendamento da visita é opcional.`
        : `O cadastro será vinculado à sua comum. O agendamento da visita é opcional.`;
    }
    familyScheduleToggle.checked = false;
    updateFamilyScheduleFields();
    $("#family-dialog").showModal();
  };

  const phoneInput = document.querySelector('input[name="celular"]');
  if (phoneInput) {
    phoneInput.addEventListener('input', e => {
      let v = e.target.value.replace(/\D/g, '');
      if (v.length > 11) v = v.slice(0, 11);
      if (v.length > 10) {
        v = v.replace(/^(\d{2})(\d{5})(\d{4})$/, '($1) $2-$3');
      } else if (v.length > 6) {
        v = v.replace(/^(\d{2})(\d{4})(\d{0,4})/, '($1) $2-$3');
      } else if (v.length > 2) {
        v = v.replace(/^(\d{2})(\d{0,5})/, '($1) $2');
      }
      e.target.value = v;
    });
  }

  const cepInput = document.querySelector('input[name="cep"]');
  if (cepInput) {
    cepInput.addEventListener('input', e => {
      let v = e.target.value.replace(/\D/g, '');
      if (v.length > 8) v = v.slice(0, 8);
      if (v.length > 5) {
        v = v.replace(/^(\d{5})(\d{1,3})/, '$1-$2');
      }
      e.target.value = v;
      const cidadeResidencial = document.querySelector('input[name="cidade_residencial"]');
      if (cidadeResidencial) cidadeResidencial.value = "";
      if (v.length === 9) {
        fetch(`https://viacep.com.br/ws/${v.replace('-','')}/json/`)
          .then(res => res.json())
          .then(data => {
            if (!data.erro) {
              document.querySelector('input[name="endereco"]').value = `${data.logradouro}, `;
              document.querySelector('input[name="setor"]').value = data.bairro;
              if (cidadeResidencial) cidadeResidencial.value = data.localidade || "";
              document.querySelector('input[name="endereco"]').focus();
            }
          })
          .catch(console.error);
      }
    });
  }

  $("#family-form").onsubmit = async event => {
    event.preventDefault();
    const form = event.currentTarget;
    const button = event.submitter;
    button.disabled = true;
    try {
      const body = Object.fromEntries(new FormData(form));
      const activeComum = activeSelectedComum !== null ? activeSelectedComum : (state.context?.comum || "");
      const activeCidade = cidadeSelect ? cidadeSelect.value : "";
      if (activeComum) body.comum = activeComum;
      if (activeCidade) body.cidade = activeCidade;
      const query = getContextQuery();
      const result = await postWithRecentVisitConfirmation(`/api/mobile/irmandade${query}`, body);
      if (!result) return;
      form.reset();
      updateFamilyScheduleFields();
      $("#family-dialog").close();
      await loadVisits();
      const registeredName = String(body.nome || "Pessoa").trim();
      successAlert(
        result.visita ? "Cadastro e visita confirmados!" : "Cadastro realizado!",
        result.visita
          ? `${registeredName} foi cadastrado(a) e a visita foi agendada com sucesso.`
          : `O cadastro de ${registeredName} foi realizado com sucesso.`
      );
    }
    catch (error) { toast(error.message, true); } finally { button.disabled = false; }
  };

  $("#schedule-button").onclick = () => {
    $("#schedule-date").value = dateInput.value;
    const activeComum = activeSelectedComum !== null ? activeSelectedComum : (state.context?.comum || "");
    const helperEl = document.querySelector("#schedule-dialog .helper");
    if (helperEl) {
      helperEl.textContent = activeComum
        ? `Agende uma visita para uma família já cadastrada na comum ${activeComum}.`
        : `Agende uma visita para uma família já cadastrada na sua comum.`;
    }
    $("#schedule-dialog").showModal();
  };
  $("#schedule-form").onsubmit = async event => {
    event.preventDefault();
    const form = event.currentTarget;
    const button = event.submitter;
    button.disabled = true;
    try {
      const body = Object.fromEntries(new FormData(form));
      const searchVal = $("#schedule-member-search")?.value || "";
      if (!body.irmandade_id) {
        throw new Error("Selecione a pessoa correta na lista de resultados antes de agendar.");
      }
      body.nome = searchVal;
      const memberName = searchVal || "família";
      const activeComum = activeSelectedComum !== null ? activeSelectedComum : (state.context?.comum || "");
      const activeCidade = cidadeSelect ? cidadeSelect.value : "";
      if (activeComum) body.comum = activeComum;
      if (activeCidade) body.cidade = activeCidade;
      const query = getContextQuery();
      const result = await postWithRecentVisitConfirmation(`/api/mobile/agendar${query}`, body);
      if (!result) return;
      form.reset();
      if ($("#schedule-member-id")) $("#schedule-member-id").value = "";
      if ($("#schedule-member-search")) $("#schedule-member-search").value = "";
      $("#schedule-dialog").close();
      await loadVisits();
      const scheduledDate = body.data
        ? new Date(`${body.data}T12:00:00`).toLocaleDateString("pt-BR")
        : "a data selecionada";
      const scheduledTime = body.hora ? ` às ${body.hora}` : "";
      successAlert(
        "Visita agendada!",
        `A visita de ${memberName} foi agendada para ${scheduledDate}${scheduledTime}.`
      );
    }
    catch (error) { toast(error.message, true); } finally { button.disabled = false; }
  };
  $("#refresh").onclick = loadVisits; dateInput.onchange = loadVisits; $("#logout").onclick = logoutMobile;
  (async () => { try { await loadContext(); await loadVisits(); } catch (error) { $("#state").textContent = error.message; toast(error.message, true); } })();
});
