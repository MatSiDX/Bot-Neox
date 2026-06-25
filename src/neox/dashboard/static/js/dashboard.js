    const pageParams = new URLSearchParams(window.location.search);
    const linkedReportSection = pageParams.get("section") === "report-calculator";

    function createPageState(pageSize = 25) {
      return {
        page: 1,
        page_size: pageSize,
        total_items: 0,
        total_pages: 0,
        status: "",
        record_type: "",
        date_from: "",
        date_to: ""
      };
    }

    const state = {
      data: null,
      section: linkedReportSection ? "report-calculator" : (localStorage.getItem("dashboardSection") || "economy"),
      sidebarCollapsed: localStorage.getItem("dashboardSidebarCollapsed") === "1",
      theme: localStorage.getItem("dashboardTheme") || "light",
      tab: "balances",
      guildId: localStorage.getItem("dashboardGuildId") || "",
      search: "",
      debounceTimers: {},
      pingTemplates: [],
      pingTemplateDrafts: {},
      pingTemplateSavedCount: 0,
      pingTemplateMax: 5,
      currentPingTemplateKey: localStorage.getItem("dashboardPingTemplateKey") || "",
      ticketPanels: [],
      ticketChannels: [],
      ticketCategories: [],
      ticketEmojis: [],
      ticketRoles: [],
      ticketRecords: [],
      ticketRecordsSummary: {},
      ticketRecordSearch: "",
      ticketRecordFilters: createPageState(10),
      selectedTicketRecordId: "",
      selectedLiveTicketId: "",
      ticketLiveMessages: [],
      ticketLiveStatus: "",
      templateStatusMessage: "",
      auditCategories: [],
      auditConfig: { channels: {} },
      auditEvents: [],
      auditSearch: "",
      auditFilters: createPageState(12),
      botPermissions: {},
      botPermissionOptions: [],
      albionRegistrationConfig: null,
      albionRegistrations: [],
      albionRegistrationSearch: "",
      albionRegistrationFilters: createPageState(15),
      reportCalculator: null,
      reportCalculatorOptions: [],
      reportRequestId: "",
      reportContext: linkedReportSection ? {
        guildId: pageParams.get("guild_id") || "",
        callerId: pageParams.get("caller_id") || "",
        ava: pageParams.get("ava") || ""
      } : null,
      fineConfig: null,
      csrfToken: "",
      permissionSearch: "",
      loot: {
        data: null,
        fileName: "",
        format: "",
        iconSize: 60,
        groupByTier: false,
        excludedTiers: new Set(),
        manualHides: new Set(),
        manualShows: new Set()
      },
      currentTicketPanelId: localStorage.getItem("dashboardTicketPanelId") || "",
      ticketEditorSection: localStorage.getItem("dashboardTicketEditorSection") || "identity",
      openRolePicker: "",
      rolePickerSearch: {},
      economyGuildId: "",
      economyPages: {
        balances: createPageState(25),
        operations: createPageState(25),
        avalonians: createPageState(25),
        reports: createPageState(25),
        fines: createPageState(25)
      },
      templateGuildId: "",
      discordMetadataGuildId: "",
      discordMetadataKindsLoaded: {},
      ticketConfigGuildId: "",
      fineConfigGuildId: "",
      auditGuildId: "",
      permissionsGuildId: "",
      albionRegistrationGuildId: "",
      reportCalculatorOptionsGuildId: "",
      ticketPanelsDirty: false,
      userInteracting: false
    };

    applyTheme();

    const columns = {
      balances: [
        ["rank", "#", "number"],
        ["user_name", "Usuario"],
        ["user_id", "ID"],
        ["items", "Items", "number"],
        ["silver", "Silver", "number"],
        ["total", "Total", "number"],
        ["updated_at_display", "Fecha"]
      ],
      operations: [
        ["action", "Accion"],
        ["operator", "Operador"],
        ["player", "Jugador"],
        ["type", "Tipo"],
        ["category", "Categoria"],
        ["amount", "Cantidad", "number"],
        ["previous_balance", "Anterior", "number"],
        ["new_balance", "Nuevo", "number"],
        ["date", "Fecha"],
        ["time", "Hora"]
      ],
      avalonians: [
        ["ava", "Ava"],
        ["action", "Accion"],
        ["user", "Usuario"],
        ["user_id", "ID"],
        ["slot", "Cupo"],
        ["reason", "Justificacion"],
        ["date", "Fecha"],
        ["time", "Hora"]
      ],
      reports: [
        ["ava", "Ava"],
        ["caller", "Caller"],
        ["caller_id", "ID Caller"],
        ["reviewer", "Revisado por"],
        ["decision", "Decision"],
        ["reason", "Motivo"],
        ["date", "Fecha"],
        ["time", "Hora"]
      ],
      fines: [
        ["id", "#", "number"],
        ["report_ava", "Ava"],
        ["fined_user_name", "Usuario"],
        ["amount", "Monto", "number"],
        ["reason", "Motivo"],
        ["status", "Estado"],
        ["created_by_name", "Creado por"],
        ["paid_by_name", "Pagado por"],
        ["created_at", "Creado"],
        ["paid_at", "Pagado"]
      ]
    };

    const numberFields = new Set(["items", "silver", "total", "amount", "previous_balance", "new_balance"]);
    const defaultTicketEmojis = [
      ["", "Sin emoji"],
      ["🎫", "🎫"],
      ["📩", "📩"],
      ["🛡️", "🛡️"],
      ["⚔️", "⚔️"],
      ["💰", "💰"],
      ["❓", "❓"],
      ["✅", "✅"]
    ];

    const globalTicketEmojis = [
      ["", "Sin emoji"],
      ["\uD83C\uDFAB", "\uD83C\uDFAB"],
      ["\uD83D\uDCE9", "\uD83D\uDCE9"],
      ["\uD83D\uDCE8", "\uD83D\uDCE8"],
      ["\u2705", "\u2705"],
      ["\u2753", "\u2753"],
      ["\uD83D\uDEE1\uFE0F", "\uD83D\uDEE1\uFE0F"],
      ["\u2694\uFE0F", "\u2694\uFE0F"],
      ["\uD83D\uDCB0", "\uD83D\uDCB0"],
      ["\uD83D\uDCCC", "\uD83D\uDCCC"],
      ["\uD83D\uDCDD", "\uD83D\uDCDD"],
      ["\uD83D\uDD27", "\uD83D\uDD27"],
      ["\u2B50", "\u2B50"],
      ["\uD83D\uDD25", "\uD83D\uDD25"],
      ["\uD83D\uDC8E", "\uD83D\uDC8E"],
      ["\uD83D\uDCCB", "\uD83D\uDCCB"],
      ["\uD83C\uDFAE", "\uD83C\uDFAE"],
      ["\uD83D\uDC51", "\uD83D\uDC51"],
      ["\uD83D\uDEA8", "\uD83D\uDEA8"],
      ["\uD83D\uDCAC", "\uD83D\uDCAC"],
      ["\uD83D\uDD12", "\uD83D\uDD12"]
    ];

    const ticketChannelPermissionOptions = [
      ["view_channel", "Ver canal"],
      ["send_messages", "Enviar mensajes"],
      ["read_message_history", "Leer historial"],
      ["attach_files", "Adjuntar archivos"],
      ["embed_links", "Insertar enlaces"],
      ["add_reactions", "Agregar reacciones"],
      ["use_external_emojis", "Usar emojis externos"],
      ["use_external_stickers", "Usar stickers externos"],
      ["mention_everyone", "Mencionar everyone/here"],
      ["manage_messages", "Gestionar mensajes"],
      ["manage_channels", "Gestionar canal"],
      ["manage_threads", "Gestionar hilos"],
      ["create_public_threads", "Crear hilos publicos"],
      ["create_private_threads", "Crear hilos privados"],
      ["send_messages_in_threads", "Enviar en hilos"],
      ["use_application_commands", "Usar comandos"]
    ];

    function newTicketPanel(name = "Nuevo panel") {
      const id = crypto.randomUUID ? crypto.randomUUID() : String(Date.now());
      return {
        id,
        name,
        mode: "buttons",
        channel_id: "",
        open_category_id: "",
        message_content: "",
        embed_title: name,
        embed_description: "Selecciona una opcion para abrir un ticket.",
        embed_color: "#22c55e",
        embed_footer: "AvalonBot Tickets",
        image_url: "",
        ticket_open_content: "",
        ticket_open_title: "",
        ticket_open_description: "",
        ticket_open_color: "",
        ticket_open_footer: "",
        ticket_open_image_url: "",
        ticket_open_thumbnail_url: "",
        options: [
          {
            id: crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-option`,
            label: "Abrir ticket",
            emoji: "",
            description: "Crear un ticket privado"
          }
        ],
        permissions: {
          ticket_role_permissions: [],
          claim_roles: "",
          close_roles: "",
          reopen_roles: "",
          delete_roles: ""
        }
      };
    }

    function formatNumber(value) {
      const number = Number(value || 0);
      return Number.isFinite(number) ? number.toLocaleString("es-AR") : value;
    }

    function escapeHtml(value) {
      return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
    }

    const lootTiers = [4, 5, 6, 7, 8];

    function lootItemKey(playerName, itemId) {
      return `${playerName}\u0000${itemId}`;
    }

    function resolveLootTier(itemId) {
      if (itemId === "QUESTITEM_TOKEN_AVALON") return 6;
      if (itemId.startsWith("QUESTITEM_EXP_TOKEN")) return 4;
      const treasure = itemId.match(/^TREASURE_.+_(RARITY[123])$/);
      if (treasure) return { RARITY1: 4, RARITY2: 5, RARITY3: 6 }[treasure[1]] || null;
      const prefix = itemId.match(/^T([4-8])_/);
      return prefix ? Number(prefix[1]) : null;
    }

    function lootTierLabel(tier) {
      return tier == null ? "N/A" : `T${tier}`;
    }

    function lootImageUrl(itemId) {
      return `https://render.albiononline.com/v1/item/${encodeURIComponent(itemId)}.png`;
    }

    function createLootItem(itemId, itemName) {
      return {
        itemId,
        itemName: itemName || itemId || "Objeto desconocido",
        tier: resolveLootTier(itemId),
        totalQuantity: 0,
        price: 0,
        totalPrice: 0,
        imageUrl: lootImageUrl(itemId)
      };
    }

    function addLootEntry(lootMap, playerName, itemId, itemName, quantity, price = 0) {
      const cleanPlayer = String(playerName || "").trim();
      const cleanItemId = String(itemId || "").trim();
      const numericQuantity = Number(quantity);
      const numericPrice = Number(price || 0);
      if (!cleanPlayer || !cleanItemId || !Number.isFinite(numericQuantity) || numericQuantity <= 0) return;
      if (!lootMap[cleanPlayer]) lootMap[cleanPlayer] = {};
      if (!lootMap[cleanPlayer][cleanItemId]) {
        lootMap[cleanPlayer][cleanItemId] = createLootItem(cleanItemId, itemName);
      }
      const item = lootMap[cleanPlayer][cleanItemId];
      item.totalQuantity += numericQuantity;
      if (!item.price && Number.isFinite(numericPrice)) item.price = numericPrice;
      if (Number.isFinite(numericPrice)) item.totalPrice += numericPrice * numericQuantity;
    }

    function detectCsvDelimiter(text) {
      const firstLine = String(text || "").split(/\r?\n/, 1)[0] || "";
      const delimiters = [";", ",", "\t"];
      return delimiters.sort((a, b) => firstLine.split(b).length - firstLine.split(a).length)[0];
    }

    function parseCsvRows(text, delimiter) {
      const rows = [];
      let row = [];
      let field = "";
      let quoted = false;
      for (let index = 0; index < text.length; index += 1) {
        const character = text[index];
        if (quoted) {
          if (character === '"' && text[index + 1] === '"') {
            field += '"';
            index += 1;
          } else if (character === '"') {
            quoted = false;
          } else {
            field += character;
          }
          continue;
        }
        if (character === '"') {
          quoted = true;
        } else if (character === delimiter) {
          row.push(field);
          field = "";
        } else if (character === "\n") {
          row.push(field.replace(/\r$/, ""));
          if (row.some(value => value.trim())) rows.push(row);
          row = [];
          field = "";
        } else {
          field += character;
        }
      }
      row.push(field.replace(/\r$/, ""));
      if (row.some(value => value.trim())) rows.push(row);
      return rows;
    }

    function parseLootCsvText(text) {
      const rows = parseCsvRows(text.replace(/^\uFEFF/, ""), detectCsvDelimiter(text));
      if (rows.length < 2) throw new Error("El CSV no contiene filas de loot.");
      const headers = rows[0].map(value => value.trim().toLowerCase());
      const required = ["looted_by__name", "item_id", "quantity"];
      const missing = required.filter(name => !headers.includes(name));
      if (missing.length) throw new Error(`Faltan columnas requeridas: ${missing.join(", ")}.`);
      const lootMap = {};
      rows.slice(1).forEach(values => {
        const row = Object.fromEntries(headers.map((header, index) => [header, values[index] ?? ""]));
        addLootEntry(
          lootMap,
          row.looted_by__name,
          row.item_id,
          row.item_name,
          Number.parseInt(row.quantity, 10),
          0
        );
      });
      return lootMap;
    }

    function parseLootJsonValue(value) {
      const entries = Array.isArray(value) ? value : value?.entries;
      if (!Array.isArray(entries)) throw new Error('El JSON debe contener una lista "entries" o ser una lista de eventos.');
      const lootMap = {};
      entries.forEach(entry => {
        if (!entry || entry.type !== "loot") return;
        const item = entry.loot?.item || {};
        addLootEntry(
          lootMap,
          entry.loot?.looted_by?.name,
          item.id,
          item.name || item.id,
          item.quantity,
          item.average_est_market_value
        );
      });
      return lootMap;
    }

    function resetLootVisibility() {
      state.loot.excludedTiers = new Set();
      state.loot.manualHides = new Set();
      state.loot.manualShows = new Set();
    }

    function isLootItemIncluded(playerName, item) {
      const key = lootItemKey(playerName, item.itemId);
      if (item.tier == null) return !state.loot.manualHides.has(key);
      if (state.loot.excludedTiers.has(item.tier)) return state.loot.manualShows.has(key);
      return !state.loot.manualHides.has(key);
    }

    function lootItemsForTier(tier) {
      const matches = [];
      Object.entries(state.loot.data || {}).forEach(([playerName, items]) => {
        Object.values(items).forEach(item => {
          if (item.tier === tier) matches.push([playerName, item]);
        });
      });
      return matches;
    }

    function lootTierState(tier) {
      if (!state.loot.excludedTiers.has(tier)) return "all";
      return lootItemsForTier(tier).some(([playerName, item]) =>
        state.loot.manualShows.has(lootItemKey(playerName, item.itemId))
      ) ? "partial" : "none";
    }

    function clearLootTierOverrides(tier) {
      lootItemsForTier(tier).forEach(([playerName, item]) => {
        const key = lootItemKey(playerName, item.itemId);
        state.loot.manualHides.delete(key);
        state.loot.manualShows.delete(key);
      });
    }

    function toggleLootTier(tier) {
      clearLootTierOverrides(tier);
      if (state.loot.excludedTiers.has(tier)) state.loot.excludedTiers.delete(tier);
      else state.loot.excludedTiers.add(tier);
      renderLoot();
    }

    function toggleLootItem(playerName, itemId) {
      const item = state.loot.data?.[playerName]?.[itemId];
      if (!item) return;
      const key = lootItemKey(playerName, itemId);
      const visible = isLootItemIncluded(playerName, item);
      if (item.tier != null && state.loot.excludedTiers.has(item.tier)) {
        if (visible) state.loot.manualShows.delete(key);
        else state.loot.manualShows.add(key);
      } else if (visible) {
        state.loot.manualHides.add(key);
      } else {
        state.loot.manualHides.delete(key);
      }
      renderLoot();
    }

    function sortedLootItems(items) {
      return [...items].sort((a, b) => {
        const tierDifference = (a.tier ?? 99) - (b.tier ?? 99);
        return tierDifference || b.totalQuantity - a.totalQuantity || a.itemName.localeCompare(b.itemName);
      });
    }

    function lootItemHtml(playerName, item) {
      const included = isLootItemIncluded(playerName, item);
      const noPrice = item.price === 0 && item.totalPrice === 0;
      return `
        <div class="loot-item-wrap">
          <button class="loot-item${included ? "" : " excluded"}${noPrice ? " no-price" : ""}" type="button"
            data-loot-player="${escapeHtml(playerName)}" data-loot-item="${escapeHtml(item.itemId)}"
            title="${escapeHtml(item.itemName)} - ${included ? "clic para excluir" : "clic para incluir"}">
            <img src="${escapeHtml(item.imageUrl)}" alt="${escapeHtml(item.itemName)}" loading="lazy">
            <span class="loot-quantity">${formatNumber(item.totalQuantity)}</span>
          </button>
          <button class="loot-info" type="button" data-loot-detail-player="${escapeHtml(playerName)}"
            data-loot-detail-item="${escapeHtml(item.itemId)}" aria-label="Ver detalles de ${escapeHtml(item.itemName)}">i</button>
        </div>
      `;
    }

    function lootPlayerHtml(playerName, items) {
      const itemList = sortedLootItems(Object.values(items));
      const total = itemList.reduce((sum, item) =>
        isLootItemIncluded(playerName, item) ? sum + item.totalPrice : sum, 0
      );
      let content = "";
      if (state.loot.groupByTier) {
        content = [...lootTiers, null].map(tier => {
          const tierItems = itemList.filter(item => item.tier === tier);
          if (!tierItems.length) return "";
          return `<section class="loot-tier-group"><h4>${lootTierLabel(tier)}</h4><div class="loot-grid">${tierItems.map(item => lootItemHtml(playerName, item)).join("")}</div></section>`;
        }).join("");
      } else {
        content = `<div class="loot-grid">${itemList.map(item => lootItemHtml(playerName, item)).join("")}</div>`;
      }
      return `
        <article class="loot-player-card">
          <div class="loot-player-header">
            <h3>${escapeHtml(playerName)}</h3>
            ${state.loot.format === "json" ? `<span class="loot-player-total">${formatNumber(total)} silver</span>` : `<span class="muted">${itemList.length} objetos</span>`}
          </div>
          ${content}
        </article>
      `;
    }

    function renderLoot() {
      const hasData = Boolean(state.loot.data);
      document.getElementById("lootDropzone").hidden = hasData;
      document.getElementById("lootResults").hidden = !hasData;
      document.getElementById("lootReplaceButton").hidden = !hasData;
      document.getElementById("lootClearButton").hidden = !hasData;
      if (!hasData) return;

      const players = Object.entries(state.loot.data);
      const itemKinds = players.reduce((sum, [, items]) => sum + Object.keys(items).length, 0);
      document.getElementById("lootFileName").textContent = state.loot.fileName;
      document.getElementById("lootFileMeta").textContent =
        `${players.length} jugadores - ${itemKinds} objetos agrupados - ${state.loot.format.toUpperCase()}`;
      document.getElementById("lootGrandTotal").textContent = state.loot.format === "json"
        ? `${formatNumber(players.reduce((sum, [playerName, items]) => sum + Object.values(items).reduce((subtotal, item) => isLootItemIncluded(playerName, item) ? subtotal + item.totalPrice : subtotal, 0), 0))} silver total`
        : "";
      document.getElementById("lootTierButtons").innerHTML = lootTiers.map(tier =>
        `<button class="loot-tier-button ${lootTierState(tier)}" type="button" data-loot-tier="${tier}">T${tier}</button>`
      ).join("");
      document.getElementById("lootIconSize").value = state.loot.iconSize;
      document.getElementById("lootIconSizeLabel").textContent = `${state.loot.iconSize}px`;
      document.getElementById("lootGroupToggle").classList.toggle("active", state.loot.groupByTier);
      document.getElementById("lootGroupToggle").textContent = state.loot.groupByTier ? "Si" : "No";
      document.getElementById("lootGroupToggle").setAttribute("aria-pressed", String(state.loot.groupByTier));
      document.getElementById("lootPlayers").style.setProperty("--loot-icon-size", `${state.loot.iconSize}px`);
      document.getElementById("lootPlayers").innerHTML = players.map(([playerName, items]) =>
        lootPlayerHtml(playerName, items)
      ).join("");
    }

    function showLootDetail(playerName, itemId) {
      const item = state.loot.data?.[playerName]?.[itemId];
      if (!item) return;
      const noPrice = item.price === 0 && item.totalPrice === 0;
      document.getElementById("lootModalPanel").innerHTML = `
        <button class="loot-modal-close" type="button" data-loot-modal-close aria-label="Cerrar">x</button>
        <div class="loot-modal-hero">
          <img src="${escapeHtml(item.imageUrl)}" alt="${escapeHtml(item.itemName)}">
          <div><h3 id="lootModalTitle">${escapeHtml(item.itemName)}</h3><p>${escapeHtml(playerName)}</p></div>
        </div>
        <div class="loot-detail-grid">
          <div class="loot-detail"><span>ID</span><strong>${escapeHtml(item.itemId)}</strong></div>
          <div class="loot-detail"><span>Tier</span><strong>${lootTierLabel(item.tier)}</strong></div>
          <div class="loot-detail"><span>Cantidad total</span><strong>${formatNumber(item.totalQuantity)}</strong></div>
          <div class="loot-detail"><span>Precio estimado</span><strong>${noPrice ? "N/A" : `${formatNumber(item.price)} silver`}</strong></div>
          <div class="loot-detail"><span>Valor total</span><strong>${noPrice ? "N/A" : `${formatNumber(item.totalPrice)} silver`}</strong></div>
          <div class="loot-detail"><span>Estado</span><strong>${isLootItemIncluded(playerName, item) ? "Incluido" : "Excluido"}</strong></div>
        </div>
      `;
      document.getElementById("lootModal").hidden = false;
    }

    function closeLootDetail() {
      document.getElementById("lootModal").hidden = true;
    }

    async function loadLootFile(file) {
      if (!file) return;
      const extension = file.name.split(".").pop()?.toLowerCase();
      if (!["csv", "json"].includes(extension)) throw new Error("Formato no soportado. Usa un archivo CSV o JSON.");
      const text = await file.text();
      const data = extension === "csv" ? parseLootCsvText(text) : parseLootJsonValue(JSON.parse(text));
      if (!Object.keys(data).length) throw new Error("No se encontraron eventos de loot validos en el archivo.");
      state.loot.data = data;
      state.loot.fileName = file.name;
      state.loot.format = extension;
      resetLootVisibility();
      document.getElementById("lootError").hidden = true;
      renderLoot();
    }

    function clearLoot() {
      state.loot.data = null;
      state.loot.fileName = "";
      state.loot.format = "";
      resetLootVisibility();
      document.getElementById("lootFileInput").value = "";
      document.getElementById("lootError").hidden = true;
      closeLootDetail();
      renderLoot();
    }

    function showLootError(error) {
      const element = document.getElementById("lootError");
      element.textContent = error instanceof SyntaxError
        ? "El archivo JSON no tiene un formato valido."
        : (error.message || "No pude procesar el archivo.");
      element.hidden = false;
    }

    function badge(value, field) {
      const text = String(value ?? "");
      const lowered = text.toLowerCase();
      let cls = "";
      if (field === "type" || field === "action") {
        if (lowered.includes("add") || lowered.includes("signup")) cls = "add";
        if (lowered.includes("remove") || lowered.includes("leave")) cls = "remove";
      }
      if (field === "category") {
        if (lowered.includes("silver")) cls = "silver";
        if (lowered.includes("items")) cls = "items";
      }
      if (field === "decision") {
        if (lowered.includes("acept")) cls = "accepted";
        if (lowered.includes("rechaz")) cls = "rejected";
      }
      return cls ? `<span class="pill ${cls}">${escapeHtml(text)}</span>` : escapeHtml(text);
    }

    function debounceAction(key, callback, delay = 300) {
      if (state.debounceTimers[key]) window.clearTimeout(state.debounceTimers[key]);
      state.debounceTimers[key] = window.setTimeout(() => {
        delete state.debounceTimers[key];
        callback();
      }, delay);
    }

    function applyPagePayload(target, payload) {
      if (!target || !payload) return;
      target.page = Number(payload.page || 1);
      target.page_size = Number(payload.page_size || target.page_size || 25);
      target.total_items = Number(payload.total_items || 0);
      target.total_pages = Number(payload.total_pages || 0);
    }

    function pageRangeLabel(meta, singularLabel, pluralLabel) {
      const total = Number(meta?.total_items || 0);
      if (!total) return `0 ${pluralLabel}.`;
      const page = Math.max(Number(meta?.page || 1), 1);
      const pageSize = Math.max(Number(meta?.page_size || 1), 1);
      const from = (page - 1) * pageSize + 1;
      const to = Math.min(total, from + pageSize - 1);
      const label = total === 1 ? singularLabel : pluralLabel;
      return `${from}-${to} de ${total} ${label}.`;
    }

    function renderPager(prevButtonId, nextButtonId, labelId, meta, singularLabel, pluralLabel) {
      const label = document.getElementById(labelId);
      if (label) {
        label.textContent = pageRangeLabel(meta, singularLabel, pluralLabel);
      }
      const prev = document.getElementById(prevButtonId);
      const next = document.getElementById(nextButtonId);
      if (prev) prev.disabled = Number(meta?.page || 1) <= 1;
      if (next) next.disabled = !Number(meta?.total_pages || 0) || Number(meta?.page || 1) >= Number(meta?.total_pages || 0);
    }

    function currentEconomyPageState() {
      if (!state.economyPages[state.tab]) {
        state.economyPages[state.tab] = createPageState(25);
      }
      return state.economyPages[state.tab];
    }

    function activeRows() {
      if (!state.data) return [];
      return state.data[state.tab] || [];
    }

    function renderGuilds() {
      const select = document.getElementById("guildSelect");
      const guilds = state.data?.guilds || [];
      if (!guilds.length) {
        select.innerHTML = `<option value="">Sin servidores disponibles</option>`;
        select.disabled = true;
        return;
      }

      select.disabled = false;
      select.innerHTML = guilds.map(guild => {
        const selected = guild.id === state.data.selectedGuildId ? " selected" : "";
        return `<option value="${escapeHtml(guild.id)}"${selected}>${escapeHtml(guild.name)}</option>`;
      }).join("");
    }

    function renderMetrics() {
      const totals = state.data?.totals || {};
      document.getElementById("playersTotal").textContent = formatNumber(totals.players);
      document.getElementById("itemsTotal").textContent = formatNumber(totals.items);
      document.getElementById("silverTotal").textContent = formatNumber(totals.silver);
      document.getElementById("overallTotal").textContent = formatNumber(totals.total);
    }

    function renderEconomyFilters() {
      const filters = currentEconomyPageState();
      const statusFilter = document.getElementById("economyStatusFilter");
      const typeFilter = document.getElementById("economyTypeFilter");
      const dateFrom = document.getElementById("economyDateFrom");
      const dateTo = document.getElementById("economyDateTo");
      const pageSize = document.getElementById("economyPageSize");
      const searchInput = document.getElementById("searchInput");

      statusFilter.value = filters.status || "";
      typeFilter.value = filters.record_type || "";
      dateFrom.value = filters.date_from || "";
      dateTo.value = filters.date_to || "";
      pageSize.value = String(filters.page_size || 25);
      searchInput.value = state.search || "";

      const supportsStatus = state.tab === "fines";
      const supportsType = ["operations", "avalonians", "reports"].includes(state.tab);
      const supportsDates = state.tab !== "balances";

      statusFilter.hidden = !supportsStatus;
      typeFilter.hidden = !supportsType;
      dateFrom.hidden = !supportsDates;
      dateTo.hidden = !supportsDates;

      statusFilter.disabled = !supportsStatus;
      typeFilter.disabled = !supportsType;
      dateFrom.disabled = !supportsDates;
      dateTo.disabled = !supportsDates;

      searchInput.placeholder = state.tab === "balances"
        ? "Buscar usuario o ID"
        : state.tab === "operations"
          ? "Buscar operacion, jugador o operador"
          : "Buscar en el registro";

      renderPager("economyPrevPageButton", "economyNextPageButton", "economyPageInfo", filters, "registro", "registros");
    }

    function renderTable() {
      const head = document.getElementById("tableHead");
      const body = document.getElementById("tableBody");
      const empty = document.getElementById("emptyState");
      const selectedColumns = columns[state.tab];
      const rows = activeRows();

      renderEconomyFilters();
      head.innerHTML = `<tr>${selectedColumns.map(([, label, cls]) => `<th class="${cls || ""}">${label}</th>`).join("")}</tr>`;
      body.innerHTML = rows.map(row => {
        const cells = selectedColumns.map(([field, , cls]) => {
          const raw = row[field] ?? "";
          const value = numberFields.has(field) ? formatNumber(raw) : badge(raw, field);
          return `<td class="${cls || ""}">${value}</td>`;
        });
        return `<tr>${cells.join("")}</tr>`;
      }).join("");
      empty.hidden = rows.length > 0;
      empty.textContent = "No hay datos para mostrar en esta pagina.";
    }

    function renderSection(section = state.section) {
      if (section === "economy") {
        renderMetrics();
        renderTable();
      } else if (section === "templates") {
        renderTemplates();
      } else if (section === "tickets") {
        renderTickets();
      } else if (section === "audit") {
        renderAudit();
      } else if (section === "permissions") {
        renderPermissions();
      } else if (section === "registration") {
        renderAlbionRegistration();
      } else if (section === "report-calculator") {
        renderReportCalculator();
      } else if (section === "loot") {
        renderLoot();
      }
    }

    function renderShell() {
      renderTheme();
      renderGuilds();
      renderSections();
      renderSession();
    }

    function render() {
      renderShell();
      renderSection(state.section);
      document.querySelectorAll(".tab").forEach(button => {
        button.classList.toggle("active", button.dataset.tab === state.tab);
      });
      const status = document.getElementById("status");
      if (state.data?.updatedAt) {
        status.textContent = `Refrescado ${state.data.updatedAt}`;
      } else if (!status.textContent) {
        status.textContent = state.guildId
          ? "Carga inicial ligera lista. Cada seccion cargara sus datos al abrirse."
          : "Sin servidores disponibles";
      }
    }

    function currentTicketPanel() {
      return state.ticketPanels.find(panel => panel.id === state.currentTicketPanelId) || null;
    }

    function currentPingTemplate() {
      return state.pingTemplates.find(template => template.key === state.currentPingTemplateKey) || null;
    }

    function newPingTemplate() {
      return {
        key: "",
        name: "",
        title: "Ava {numero}",
        title_editable: true,
        mention: "",
        join_command: "/join {caller}",
        caller_slot: "MainTank",
        roles: ["MainTank", "Heal", "DPS"],
        slot_format: "> **{index}.{slot}:** {user}",
        content: "# {title} {mention}\\n\\n{join_command}\\n\\n{slots}\\n\\nCupos: {occupied}/{total}{status}",
        loot_link: "",
        report_enabled: true,
        source: "server",
        editable: true,
        deletable: false
      };
    }

    function renderTemplates() {
      document.getElementById("templateSavedTotal").textContent = state.pingTemplateSavedCount;
      document.getElementById("templateLimitTotal").textContent = state.pingTemplateMax;
      document.getElementById("templateAvailableTotal").textContent = state.pingTemplates.length;
      renderTemplateList();
      renderTemplateEditor();
    }

    function renderTemplateList() {
      const list = document.getElementById("templateList");
      if (!state.pingTemplates.length) {
        list.innerHTML = `<button type="button" disabled>No hay plantillas cargadas</button>`;
        return;
      }

      list.innerHTML = state.pingTemplates.map(template => {
        const active = template.key === state.currentPingTemplateKey ? " active" : "";
        const source = template.source === "server"
          ? (template.overrides_global ? "Servidor, reemplaza base" : "Servidor")
          : template.source === "global" ? "Base" : "Temporal";
        return `<button class="template-select${active}" type="button" data-template-key="${escapeHtml(template.key)}">${escapeHtml(template.name || template.key)}<br><span class="muted">${escapeHtml(template.key)} - ${source}</span></button>`;
      }).join("");

      list.querySelectorAll(".template-select").forEach(button => {
        button.addEventListener("click", () => {
          state.currentPingTemplateKey = button.dataset.templateKey;
          localStorage.setItem("dashboardPingTemplateKey", state.currentPingTemplateKey);
          renderTemplates();
        });
      });
    }

    function templateFormData() {
      return {
        key: document.getElementById("templateKey").value.trim(),
        original_key: document.getElementById("templateOriginalKey").value.trim(),
        name: document.getElementById("templateName").value.trim(),
        title: document.getElementById("templateTitle").value,
        mention: document.getElementById("templateMention").value,
        join_command: document.getElementById("templateJoinCommand").value,
        caller_slot: document.getElementById("templateCallerSlot").value,
        roles: document.getElementById("templateRoles").value.replace(/\\n/g, "\n"),
        slot_format: document.getElementById("templateSlotFormat").value,
        content: document.getElementById("templateContent").value.replace(/\\n/g, "\n"),
        loot_link: document.getElementById("templateLootLink").value,
        report_enabled: document.getElementById("templateReportEnabled").checked,
        title_editable: true
      };
    }

    function normalizeTemplateText(value) {
      return String(value || "").replace(/\\n/g, "\n");
    }

    function saveTemplateDraft() {
      const originalKey = document.getElementById("templateOriginalKey").value.trim() || state.currentPingTemplateKey;
      if (!originalKey) return;
      state.pingTemplateDrafts[originalKey] = templateFormData();
    }

    function renderTemplateEditor() {
      const template = currentPingTemplate() || newPingTemplate();
      const draft = state.pingTemplateDrafts[state.currentPingTemplateKey];
      const formTemplate = draft ? { ...template, ...draft } : template;
      const editable = true;
      const isBase = template.source === "global" || template.source === "scratch";
      document.getElementById("templateKey").value = formTemplate.key || "";
      document.getElementById("templateOriginalKey").value = draft?.original_key || template.key || "";
      document.getElementById("templateName").value = formTemplate.name || "";
      document.getElementById("templateTitle").value = formTemplate.title || "";
      document.getElementById("templateMention").value = formTemplate.mention || "";
      document.getElementById("templateJoinCommand").value = formTemplate.join_command || "";
      document.getElementById("templateCallerSlot").value = formTemplate.caller_slot || "";
      document.getElementById("templateRoles").value = Array.isArray(formTemplate.roles) ? formTemplate.roles.join("\n") : normalizeTemplateText(formTemplate.roles);
      document.getElementById("templateSlotFormat").value = formTemplate.slot_format || "";
      document.getElementById("templateContent").value = normalizeTemplateText(formTemplate.content);
      document.getElementById("templateLootLink").value = formTemplate.loot_link || "";
      document.getElementById("templateReportEnabled").checked = formTemplate.report_enabled !== false;

      ["templateKey", "templateName", "templateTitle", "templateMention", "templateJoinCommand", "templateCallerSlot", "templateRoles", "templateSlotFormat", "templateContent", "templateLootLink", "templateReportEnabled"].forEach(id => {
        document.getElementById(id).disabled = !editable;
      });
      document.getElementById("saveTemplateButton").disabled = !editable;
      document.getElementById("deleteTemplateButton").disabled = !template.deletable;
      renderTemplatePreview();
      if (state.templateStatusMessage) {
        document.getElementById("templateStatus").textContent = state.templateStatusMessage;
        state.templateStatusMessage = "";
      } else if (isBase) {
        document.getElementById("templateStatus").textContent = "Estas viendo una plantilla base. Si guardas con esta clave, se crea una version del servidor que reemplaza a la base solo en este servidor.";
      } else {
        document.getElementById("templateStatus").textContent = template.overrides_global
          ? "Plantilla del servidor que reemplaza a una base. Puedes modificarla y guardar los cambios."
          : "Plantilla del servidor. Puedes modificarla y guardar los cambios.";
      }
    }

    function renderTemplatePreview() {
      const data = templateFormData();
      const roles = String(data.roles || "").split(/\\n|,|;/).map(item => item.trim()).filter(Boolean);
      const slots = roles.map((role, index) => `> **${index + 1}.${role}:** ${index === 0 ? "Caller" : "-"}`).join("\\n");
      const values = {
        title: data.title || "Ava 29",
        numero: "29",
        template: data.name || data.key || "Plantilla",
        mention: data.mention || "",
        caller: "Neox",
        join_command: data.join_command || "/join Neox",
        slots,
        loot_link: data.loot_link || "",
        occupied: "1",
        total: String(Math.max(roles.length, 1)),
        status: ""
      };
      const rendered = String(data.content || "").replace(/\\{([a-z_]+)\\}/gi, (match, key) => values[key] ?? match);
      document.getElementById("templatePreview").innerHTML = `
        <div class="discord-preview-title">${escapeHtml(data.name || data.key || "Nueva plantilla")}</div>
        <div class="discord-preview-description">${escapeHtml(rendered || "Completa el mensaje para ver la vista previa.")}</div>
      `;
    }

    function renderTickets() {
      document.getElementById("ticketPanelTotal").textContent = state.ticketPanels.length;
      renderTicketLiveSummary();
      renderFineConfig();
      const hasPanel = Boolean(currentTicketPanel());
      document.getElementById("clonePanelButton").hidden = !hasPanel;
      document.getElementById("deletePanelButton").hidden = !hasPanel;
      renderTicketPanelList();
      renderTicketChannels();
      renderTicketCategories();
      renderTicketEditor();
      renderTicketEditorSections();
      renderTicketRecords();
      renderTicketLiveViewer();
    }

    function renderFineConfig() {
      const config = state.fineConfig || {};
      const channelSelect = document.getElementById("fineChannel");
      const blockedRoleSelect = document.getElementById("fineBlockedRole");
      const resolverRoleSelect = document.getElementById("fineResolverRole");
      const categorySelect = document.getElementById("fineTicketCategory");

      channelSelect.innerHTML = `<option value="">Seleccionar canal</option>${state.ticketChannels.map(channel =>
        `<option value="${escapeHtml(channel.id)}"># ${escapeHtml(channel.name)}</option>`
      ).join("")}`;
      categorySelect.innerHTML = `<option value="">Sin categoria</option>${state.ticketCategories.map(category =>
        `<option value="${escapeHtml(category.id)}">${escapeHtml(category.name)}</option>`
      ).join("")}`;
      const roleOptions = `<option value="">Seleccionar rol</option>${state.ticketRoles.map(role =>
        `<option value="${escapeHtml(role.id)}">${escapeHtml(role.name)}</option>`
      ).join("")}`;
      blockedRoleSelect.innerHTML = roleOptions;
      resolverRoleSelect.innerHTML = roleOptions;

      channelSelect.value = config.channel_id || "";
      blockedRoleSelect.value = config.blocked_role_id || "";
      resolverRoleSelect.value = config.resolver_role_id || "";
      categorySelect.value = config.ticket_category_id || "";
    }

    function renderTicketLiveSummary() {
      const summary = state.ticketRecordsSummary || {};
      document.getElementById("ticketOpenTotal").textContent = summary.open ?? 0;
      document.getElementById("ticketClosedTodayTotal").textContent = summary.closed_today ?? 0;
      document.getElementById("ticketLiveStatus").textContent = summary.updated_at
        ? `En vivo: ${summary.open || 0} abiertos, ${summary.claimed || 0} reclamados, ${summary.transcribed || 0} transcritos. Ultima actualizacion: ${summary.updated_at}`
        : "En vivo: esperando datos.";
    }

    function renderTicketEditorSections() {
      document.querySelectorAll(".editor-tab").forEach(button => {
        button.classList.toggle("active", button.dataset.editorSection === state.ticketEditorSection);
      });
      document.querySelectorAll("[data-editor-panel]").forEach(panel => {
        panel.hidden = panel.dataset.editorPanel !== state.ticketEditorSection;
      });
    }

    function renderAudit() {
      const categories = state.auditCategories || [];
      const channels = state.auditConfig?.channels || {};
      const configured = categories.filter(category => channels[category.key]).length;
      document.getElementById("auditCategoryTotal").textContent = categories.length;
      document.getElementById("auditConfiguredTotal").textContent = configured;
      document.getElementById("auditMissingTotal").textContent = Math.max(categories.length - configured, 0);
      document.getElementById("auditSearch").value = state.auditSearch || "";
      document.getElementById("auditTypeFilter").innerHTML = `<option value="">Todas las categorias</option>${categories.map(category =>
        `<option value="${escapeHtml(category.key)}"${state.auditFilters.record_type === category.key ? " selected" : ""}>${escapeHtml(category.name)}</option>`
      ).join("")}`;
      document.getElementById("auditPageSize").value = String(state.auditFilters.page_size || 12);
      renderPager("auditPrevPageButton", "auditNextPageButton", "auditPageInfo", state.auditFilters, "evento", "eventos");

      const grid = document.getElementById("auditConfigGrid");
      if (!categories.length) {
        grid.innerHTML = `<div class="ticket-empty-editor"><strong>Sin categorias cargadas</strong><p>Inicia sesion y selecciona un servidor.</p></div>`;
        return;
      }

      grid.innerHTML = categories.map(category => `
        <article class="audit-card">
          <div>
            <strong>${escapeHtml(category.name)}</strong>
            <p>${escapeHtml(category.description)}</p>
          </div>
          <select class="audit-channel-select" data-audit-key="${escapeHtml(category.key)}">
            <option value="">Sin canal</option>
            ${state.ticketChannels.map(channel => {
              const selected = channels[category.key] === channel.id ? " selected" : "";
              return `<option value="${escapeHtml(channel.id)}"${selected}>#${escapeHtml(channel.name)}</option>`;
            }).join("")}
          </select>
        </article>
      `).join("");

      grid.querySelectorAll(".audit-channel-select").forEach(select => {
        select.addEventListener("change", () => {
          state.auditConfig.channels[select.dataset.auditKey] = select.value;
          renderAudit();
        });
      });

      const eventsList = document.getElementById("auditEventsList");
      const events = state.auditEvents || [];
      const categoryNames = Object.fromEntries(categories.map(category => [category.key, category.name]));
      const grouped = {};
      for (const event of events) {
        const key = event.category || "otros";
        grouped[key] = grouped[key] || [];
        grouped[key].push(event);
      }

      const orderedGroups = categories.map(category => ({
        key: category.key,
        name: category.name,
        events: grouped[category.key] || []
      }));
      for (const [category, categoryEvents] of Object.entries(grouped)) {
        if (!categoryNames[category]) {
          orderedGroups.push({ key: category, name: category, events: categoryEvents });
        }
      }

      eventsList.innerHTML = orderedGroups.map((group, index) => `
        <details class="audit-event-section"${index === 0 ? " open" : ""}>
          <summary>
            <span>${escapeHtml(group.name)}</span>
            <span class="muted">${group.events.length} eventos</span>
          </summary>
          <div class="audit-event-list">
            ${group.events.length ? group.events.map(event => `
              <article class="ticket-card">
                <div>
                  <h3>${escapeHtml(event.title || "Evento")}</h3>
                  <div class="ticket-meta">
                    <span>${escapeHtml(event.created_at || "")}</span>
                  </div>
                  <div class="muted">${escapeHtml(event.description || "")}</div>
                </div>
              </article>
            `).join("") : `
              <article class="ticket-card">
                <div>
                  <h3>Sin eventos recientes</h3>
                  <div class="ticket-meta"><span>Cuando ocurra algo de esta categoria, aparecera aca.</span></div>
                </div>
              </article>
            `}
          </div>
        </details>
      `).join("");
    }

    function permissionValuesForRole(roleId) {
      const values = state.botPermissions?.[String(roleId)] || [];
      return Array.isArray(values) ? values.map(String) : [];
    }

    function renderPermissions() {
      const grid = document.getElementById("permissionsGrid");
      const roles = state.ticketRoles || [];
      const options = state.botPermissionOptions || [];
      const search = String(state.permissionSearch || "").trim().toLowerCase();
      const visibleRoles = search
        ? roles.filter(role => String(role.name || "").toLowerCase().includes(search) || String(role.id || "").includes(search))
        : roles;
      const configuredRoles = Object.values(state.botPermissions || {}).filter(values => Array.isArray(values) && values.length).length;
      const activeTotal = Object.values(state.botPermissions || {}).reduce((total, values) => total + (Array.isArray(values) ? values.length : 0), 0);

      document.getElementById("permissionRoleTotal").textContent = configuredRoles;
      document.getElementById("permissionActiveTotal").textContent = activeTotal;
      document.getElementById("permissionAvailableTotal").textContent = roles.length;
      document.getElementById("permissionRoleSearch").value = state.permissionSearch;

      if (!roles.length || !options.length) {
        grid.innerHTML = `<div class="ticket-empty-editor"><strong>Sin roles cargados</strong><p>Selecciona un servidor para cargar los roles disponibles.</p></div>`;
        return;
      }

      if (!visibleRoles.length) {
        grid.innerHTML = `<div class="ticket-empty-editor"><strong>No encontre roles</strong><p>Prueba con otro nombre o ID.</p></div>`;
        return;
      }

      grid.innerHTML = `
        <div class="permissions-list">
          <div class="permissions-list-head">
            <span>Rol</span>
            ${options.map(option => `<span title="${escapeHtml(option.description)}">${escapeHtml(option.label)}</span>`).join("")}
          </div>
          ${visibleRoles.map(role => {
        const values = permissionValuesForRole(role.id);
        const hasGlobal = values.includes("global");
        return `
            <article class="permission-row" data-role-id="${escapeHtml(role.id)}">
              <div class="permission-role">
                <strong>@${escapeHtml(role.name)}</strong>
                <span class="muted">${escapeHtml(role.id)}</span>
              </div>
              ${options.map(option => {
                const checked = values.includes(option.key) ? " checked" : "";
                const disabled = hasGlobal && option.key !== "global" ? " disabled" : "";
                const active = checked ? " active" : "";
                const globalClass = option.key === "global" ? " global" : "";
                return `
                  <label class="permission-pill${active}${globalClass}" title="${escapeHtml(option.description)}">
                    <input type="checkbox" data-permission-role="${escapeHtml(role.id)}" data-permission-key="${escapeHtml(option.key)}"${checked}${disabled}>
                    <span>${escapeHtml(option.label)}</span>
                  </label>
                `;
              }).join("")}
            </article>
        `;
          }).join("")}
        </div>
      `;
    }

    function collectBotPermissions() {
      const permissions = { ...(state.botPermissions || {}) };
      document.querySelectorAll(".permission-row").forEach(row => {
        const roleId = String(row.dataset.roleId || "");
        if (roleId) delete permissions[roleId];
      });
      document.querySelectorAll("[data-permission-role]").forEach(input => {
        if (!input.checked) return;
        const roleId = String(input.dataset.permissionRole || "");
        const key = String(input.dataset.permissionKey || "");
        if (!roleId || !key) return;
        permissions[roleId] = permissions[roleId] || [];
        permissions[roleId].push(key);
      });

      for (const [roleId, values] of Object.entries(permissions)) {
        if (values.includes("global")) {
          permissions[roleId] = ["global"];
        }
      }

      return permissions;
    }

    function renderTicketPanelList() {
      const list = document.getElementById("ticketPanelList");
      if (!state.ticketPanels.length) {
        list.innerHTML = `<button type="button" disabled>No hay paneles creados</button>`;
        return;
      }

      list.innerHTML = state.ticketPanels.map(panel => {
        const active = panel.id === state.currentTicketPanelId ? " active" : "";
        return `<button class="ticket-panel-select${active}" type="button" data-panel-id="${escapeHtml(panel.id)}">${escapeHtml(panel.name)}</button>`;
      }).join("");

      list.querySelectorAll(".ticket-panel-select").forEach(button => {
        button.addEventListener("click", () => {
          persistCurrentTicketPanel();
          state.currentTicketPanelId = button.dataset.panelId;
          localStorage.setItem("dashboardTicketPanelId", state.currentTicketPanelId);
          renderTickets();
        });
      });
    }

    function renderTicketChannels() {
      const select = document.getElementById("ticketChannel");
      const panel = currentTicketPanel();
      select.innerHTML = `<option value="">Seleccionar canal</option>` + state.ticketChannels.map(channel => {
        const selected = panel?.channel_id === channel.id ? " selected" : "";
        return `<option value="${escapeHtml(channel.id)}"${selected}>#${escapeHtml(channel.name)}</option>`;
      }).join("");
    }

    function renderTicketCategories() {
      const select = document.getElementById("ticketOpenCategory");
      const panel = currentTicketPanel();
      select.innerHTML = `<option value="">Seleccionar categoria</option>` + state.ticketCategories.map(category => {
        const selected = panel?.open_category_id === category.id ? " selected" : "";
        return `<option value="${escapeHtml(category.id)}"${selected}>${escapeHtml(category.name)}</option>`;
      }).join("");
    }

    function renderTicketRecords() {
      const list = document.getElementById("ticketRecordsList");
      const records = state.ticketRecords || [];
      document.getElementById("ticketRecordSearch").value = state.ticketRecordSearch || "";
      document.getElementById("ticketRecordStatusFilter").value = state.ticketRecordFilters.status || "";
      document.getElementById("ticketRecordPageSize").value = String(state.ticketRecordFilters.page_size || 10);
      document.getElementById("ticketRecordsCount").textContent = pageRangeLabel(state.ticketRecordFilters, "ticket visible", "tickets visibles");
      renderPager("ticketRecordsPrevPageButton", "ticketRecordsNextPageButton", "ticketRecordsPageInfo", state.ticketRecordFilters, "ticket", "tickets");
      if (!records.length) {
        list.innerHTML = `
          <article class="ticket-card">
            <div>
              <h3>No hay tickets para mostrar</h3>
              <div class="ticket-meta"><span>Los tickets abiertos y transcritos apareceran aca.</span></div>
            </div>
          </article>`;
        state.selectedTicketRecordId = "";
        return;
      }

      list.innerHTML = records.map(record => {
        const status = String(record.status || "open").toLowerCase();
        const label = status === "open" ? "Abierto" : status === "closed" ? "Cerrado" : status === "deleted" ? "Eliminado" : status;
        const recordId = record.channel_id || record.number || "";
        const hasTranscript = Boolean(record.transcribed_at || (Array.isArray(record.transcript) && record.transcript.length));
        const metadata = [
          ["Usuario", record.owner_name || record.owner_id || "Desconocido"],
          ["Panel", record.panel_name || "Sin panel"],
          record.option_label ? ["Opcion", record.option_label] : null,
          record.created_at ? ["Creado", record.created_at] : null,
          record.claimed_by_name ? ["Reclamado por", record.claimed_by_name] : null,
          record.closed_at ? ["Cerrado", record.closed_at] : null,
          record.transcribed_at ? ["Transcrito", record.transcribed_at] : null
        ].filter(Boolean);
        return `
          <article class="ticket-card live-ticket ${escapeHtml(status)}">
            <div>
              <div class="ticket-record-title">
                <h3>${escapeHtml(record.channel_name || `ticket-${record.number || ""}`)}</h3>
                <span class="ticket-status">${escapeHtml(label)}</span>
              </div>
              <div class="ticket-record-meta">
                ${metadata.map(([name, value]) => `<span><b>${escapeHtml(name)}</b>${escapeHtml(value)}</span>`).join("")}
              </div>
            </div>
            <div class="ticket-card-actions">
              ${status === "open" && record.channel_id ? `<button class="action-button view-live-ticket-button${String(state.selectedLiveTicketId) === String(record.channel_id) ? " active" : ""}" type="button" data-channel-id="${escapeHtml(record.channel_id)}">Ver ticket</button>` : ""}
              <button class="action-button view-transcript-button${String(state.selectedTicketRecordId) === String(recordId) ? " active" : ""}" type="button" data-record-id="${escapeHtml(recordId)}" title="Ver transcripcion" aria-label="Ver transcripcion"${hasTranscript ? "" : " disabled"}>Ver transcripcion</button>
              ${status !== "open" ? `<button class="action-button danger delete-ticket-record-button" type="button" data-record-id="${escapeHtml(recordId)}" data-channel-id="${escapeHtml(record.channel_id || "")}" data-record-name="${escapeHtml(record.channel_name || `ticket-${record.number || ""}`)}">Eliminar registro</button>` : ""}
            </div>
          </article>
        `;
      }).join("");

      list.querySelectorAll(".view-live-ticket-button").forEach(button => {
        button.addEventListener("click", () => {
          openLiveTicket(button.dataset.channelId).catch(error => {
            document.getElementById("ticketLiveMessageStatus").textContent = error.message;
          });
        });
      });

      list.querySelectorAll(".view-transcript-button").forEach(button => {
        button.addEventListener("click", () => {
          openTicketTranscript(button.dataset.recordId);
        });
      });

      list.querySelectorAll(".delete-ticket-record-button").forEach(button => {
        button.addEventListener("click", () => {
          deleteTicketRecord(
            button.dataset.recordId,
            button.dataset.channelId,
            button.dataset.recordName
          ).catch(error => {
            document.getElementById("ticketStatus").textContent = error.message;
          });
        });
      });
    }

    function openTicketTranscript(recordId) {
      const params = new URLSearchParams({
        guild_id: state.guildId,
        record_id: recordId
      });
      window.location.href = `/ticket-transcript?${params.toString()}`;
    }

    async function deleteTicketRecord(recordId, channelId, recordName) {
      const confirmed = window.confirm(
        `Eliminar definitivamente ${recordName || "este ticket"} de la base de datos? Desaparecera de la lista junto con su transcripcion y archivos guardados.`
      );
      if (!confirmed) return;

      const response = await fetch("/api/ticket-record", {
        method: "DELETE",
        headers: csrfHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({
          guild_id: state.guildId,
          record_id: recordId
        })
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.error || "No pude eliminar el registro del ticket.");
      }

      if (String(state.selectedTicketRecordId) === String(recordId)) {
        state.selectedTicketRecordId = "";
      }
      if (String(state.selectedLiveTicketId) === String(channelId)) {
        closeLiveTicket();
      }
      await loadTicketRecordsLive();
      document.getElementById("ticketStatus").textContent = "Registro del ticket eliminado definitivamente.";
      renderTickets();
    }

    function liveTicketRecord() {
      return (state.ticketRecords || []).find(record => String(record.channel_id || "") === String(state.selectedLiveTicketId || ""));
    }

    async function openLiveTicket(channelId) {
      state.selectedLiveTicketId = String(channelId || "");
      state.ticketLiveMessages = [];
      state.ticketLiveStatus = "Cargando mensajes...";
      renderTickets();
      await loadLiveTicketMessages();
    }

    function closeLiveTicket() {
      state.selectedLiveTicketId = "";
      state.ticketLiveMessages = [];
      state.ticketLiveStatus = "";
      renderTickets();
    }

    async function loadLiveTicketMessages() {
      if (!state.guildId || !state.selectedLiveTicketId) return;
      const params = new URLSearchParams({
        guild_id: state.guildId,
        channel_id: state.selectedLiveTicketId
      });
      const response = await fetch(`/api/ticket-live?${params.toString()}`, { cache: "no-store" });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "No pude cargar el ticket en vivo.");
      state.ticketLiveMessages = payload.messages || [];
      state.ticketLiveStatus = payload.updated_at ? `Actualizado: ${payload.updated_at}` : "";
      renderTicketLiveViewer();
    }

    async function sendLiveTicketMessage() {
      const input = document.getElementById("ticketLiveMessageInput");
      const content = input.value.trim();
      if (!content) return;
      const response = await fetch("/api/ticket-live-message", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          guild_id: state.guildId,
          channel_id: state.selectedLiveTicketId,
          content
        })
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "No pude enviar el mensaje.");
      input.value = "";
      state.ticketLiveStatus = "Mensaje enviado.";
      await loadLiveTicketMessages();
    }

    function renderTicketLiveViewer() {
      const viewer = document.getElementById("ticketLiveViewer");
      const empty = document.getElementById("ticketEmptyEditor");
      const editor = document.getElementById("ticketEditor");
      const record = liveTicketRecord();
      const open = Boolean(state.selectedLiveTicketId && record && String(record.status || "open").toLowerCase() === "open");
      viewer.hidden = !open;
      if (!open) {
        if (!currentTicketPanel()) empty.hidden = false;
        editor.hidden = !currentTicketPanel();
        return;
      }

      empty.hidden = true;
      editor.hidden = true;
      document.getElementById("ticketLiveTitle").textContent = record.channel_name || `ticket-${record.number || ""}`;
      document.getElementById("ticketLiveSubtitle").textContent = `${record.panel_name || "Sin panel"} - ${record.owner_name || record.owner_id || "Usuario desconocido"}`;
      document.getElementById("ticketLiveMessageStatus").textContent = state.ticketLiveStatus || "";
      const box = document.getElementById("ticketLiveMessages");
      box.innerHTML = state.ticketLiveMessages.length
        ? state.ticketLiveMessages.map(renderTranscriptMessage).join("")
        : `<div class="transcript-message"><div></div><div class="muted">Todavia no hay mensajes cargados.</div></div>`;
      box.scrollTop = box.scrollHeight;
    }

    function initialForName(name) {
      const clean = String(name || "U").trim();
      return escapeHtml(clean.slice(0, 1).toUpperCase() || "U");
    }

    function renderTranscriptAvatar(message) {
      const avatar = message.author_avatar || "";
      if (avatar) {
        return `<span class="transcript-avatar"><img src="${escapeHtml(avatar)}" alt=""></span>`;
      }
      return `<span class="transcript-avatar">${initialForName(message.author_name || message.author)}</span>`;
    }

    function renderTranscriptEmbeds(embeds) {
      if (!Array.isArray(embeds) || !embeds.length) return "";
      return embeds.map(embed => {
        const color = embed.color ? `#${Number(embed.color).toString(16).padStart(6, "0").slice(-6)}` : "#5865f2";
        const fields = Array.isArray(embed.fields) ? embed.fields : [];
        const imageUrl = embed.image?.local_url || embed.image?.url || "";
        const thumbnailUrl = embed.thumbnail?.local_url || embed.thumbnail?.url || "";
        return `
          <div class="transcript-embed" style="border-left-color:${escapeHtml(color)}">
            ${embed.author?.name ? `<div class="muted">${escapeHtml(embed.author.name)}</div>` : ""}
            ${embed.title ? `<div class="transcript-embed-title">${escapeHtml(embed.title)}</div>` : ""}
            ${embed.description ? `<div class="transcript-content">${escapeHtml(embed.description)}</div>` : ""}
            ${fields.map(field => `
              <div class="transcript-embed-field">
                <strong>${escapeHtml(field.name || "")}</strong>
                <span>${escapeHtml(field.value || "")}</span>
              </div>
            `).join("")}
            ${thumbnailUrl ? `<img class="transcript-image" src="${escapeHtml(thumbnailUrl)}" alt="Miniatura del embed">` : ""}
            ${imageUrl ? `<img class="transcript-image" src="${escapeHtml(imageUrl)}" alt="Imagen del embed">` : ""}
            ${embed.footer?.text ? `<div class="muted">${escapeHtml(embed.footer.text)}</div>` : ""}
          </div>
        `;
      }).join("");
    }

    function renderTranscriptAttachments(attachments) {
      if (!Array.isArray(attachments) || !attachments.length) return "";
      return `
        <div class="transcript-attachments">
          ${attachments.map(attachment => {
            const url = attachment.local_url || attachment.url || "#";
            const filename = attachment.filename || "Archivo adjunto";
            const contentType = attachment.content_type || "";
            const looksImage = contentType.startsWith("image/") || /\.(png|jpe?g|gif|webp|bmp)$/i.test(filename);
            return looksImage
              ? `<a href="${escapeHtml(url)}" target="_blank" rel="noreferrer"><img class="transcript-image" src="${escapeHtml(url)}" alt="${escapeHtml(filename)}"></a>`
              : `<a class="transcript-attachment" href="${escapeHtml(url)}" target="_blank" rel="noreferrer">${escapeHtml(filename)}</a>`;
          }).join("")}
        </div>
      `;
    }

    function renderTranscriptMessage(message) {
      const authorName = message.author_name || message.author || "Usuario";
      const hasContent = Boolean(message.content);
      const hasEmbeds = Array.isArray(message.embeds) && message.embeds.length;
      const hasAttachments = Array.isArray(message.attachments) && message.attachments.length;
      return `
        <div class="transcript-message">
          ${renderTranscriptAvatar(message)}
          <div class="transcript-body">
            <div class="transcript-author-line">
              <span class="transcript-author">${escapeHtml(authorName)}</span>
              ${message.author_bot ? `<span class="transcript-bot-badge">Bot</span>` : ""}
              <span class="muted">${escapeHtml(message.created_at || "")}</span>
            </div>
            ${hasContent ? `<div class="transcript-content">${escapeHtml(message.content)}</div>` : ""}
            ${renderTranscriptEmbeds(message.embeds)}
            ${renderTranscriptAttachments(message.attachments)}
            ${!hasContent && !hasEmbeds && !hasAttachments ? `<div class="muted">(mensaje sin contenido visible)</div>` : ""}
          </div>
        </div>
      `;
    }

    function permissionValues(value) {
      if (Array.isArray(value)) return value.map(String);
      return String(value || "").split(",").map(item => item.trim()).filter(Boolean);
    }

    function rolePickerValues(inputId) {
      return permissionValues(document.getElementById(inputId)?.value || "");
    }

    function roleById(roleId) {
      return state.ticketRoles.find(role => String(role.id) === String(roleId));
    }

    function setRolePickerValues(inputId, values) {
      document.getElementById(inputId).value = values.map(String).slice(0, 3).join(",");
    }

    function renderRoleSelect(inputId, selectedValues) {
      const values = permissionValues(selectedValues).slice(0, 3);
      const selected = new Set(values);
      const input = document.getElementById(inputId);
      const picker = document.getElementById(`${inputId}Picker`);
      if (!input || !picker) return;

      input.value = values.join(",");
      const search = String(state.rolePickerSearch[inputId] || "").toLowerCase();
      const selectedRoles = values.map(roleById).filter(Boolean);
      const visibleRoles = state.ticketRoles.filter(role => String(role.name || "").toLowerCase().includes(search));
      const open = state.openRolePicker === inputId;
      const disabled = input.disabled ? " disabled" : "";

      picker.classList.toggle("open", open);
      picker.innerHTML = `
        <button id="${inputId}Button" class="role-picker-trigger" type="button" data-role-picker-toggle="${inputId}"${disabled}>
          ${selectedRoles.length ? `${selectedRoles.length} rol${selectedRoles.length === 1 ? "" : "es"} seleccionado${selectedRoles.length === 1 ? "" : "s"}` : "Seleccionar roles"}
        </button>
        <div class="role-picker-selected">
          ${selectedRoles.length ? selectedRoles.map(role => `
            <span class="role-chip">@${escapeHtml(role.name)}
              <button type="button" data-role-picker-remove="${inputId}" data-role-id="${escapeHtml(role.id)}" aria-label="Quitar ${escapeHtml(role.name)}">x</button>
            </span>
          `).join("") : `<span class="muted">Sin roles seleccionados</span>`}
        </div>
        <div class="role-picker-menu">
          <input class="role-picker-search" type="text" placeholder="Buscar rol" value="${escapeHtml(state.rolePickerSearch[inputId] || "")}" data-role-picker-search="${inputId}">
          <div class="role-picker-options">
            ${visibleRoles.length ? visibleRoles.map(role => {
              const active = selected.has(String(role.id));
              const full = !active && selected.size >= 3;
              return `
                <button class="role-picker-option${active ? " active" : ""}" type="button" data-role-picker-option="${inputId}" data-role-id="${escapeHtml(role.id)}"${full ? " disabled" : ""}>
                  <span class="role-picker-check">${active ? "✓" : ""}</span>
                  <span>@${escapeHtml(role.name)}</span>
                </button>
              `;
            }).join("") : `<div class="role-picker-empty">No hay roles para mostrar.</div>`}
          </div>
        </div>
      `;
    }

    function normalizeTicketRolePermissions(entries) {
      if (!Array.isArray(entries)) return [];
      const seen = new Set();
      return entries.map(entry => {
        const roleId = String(entry?.role_id || "").trim();
        const values = Array.isArray(entry?.permissions) ? entry.permissions : [];
        const permissions = values.map(String).filter(value => ticketChannelPermissionOptions.some(([key]) => key === value));
        return { role_id: roleId, permissions };
      }).filter(entry => {
        if (!entry.role_id || seen.has(entry.role_id) || !entry.permissions.length) return false;
        seen.add(entry.role_id);
        return true;
      }).slice(0, 20);
    }

    function roleOptionsHtml(selectedRoleId) {
      return `<option value="">Seleccionar rol</option>` + state.ticketRoles.map(role => {
        const selected = String(role.id) === String(selectedRoleId || "") ? " selected" : "";
        return `<option value="${escapeHtml(role.id)}"${selected}>@${escapeHtml(role.name)}</option>`;
      }).join("");
    }

    function renderTicketRolePermissions(panel) {
      const container = document.getElementById("ticketRolePermissionsList");
      if (!container) return;
      const savedEntries = panel?.permissions?.ticket_role_permissions;
      const entries = Array.isArray(savedEntries)
        ? savedEntries.map(entry => ({
            role_id: String(entry?.role_id || ""),
            permissions: Array.isArray(entry?.permissions) ? entry.permissions.map(String) : []
          }))
        : [];
      container.innerHTML = entries.length ? entries.map((entry, index) => {
        const selected = new Set(entry.permissions || []);
        const selectedLabels = ticketChannelPermissionOptions
          .filter(([key]) => selected.has(key))
          .map(([, label]) => label);
        const permissionCount = selectedLabels.length;
        return `
          <article class="ticket-permission-card" data-ticket-permission-index="${index}">
            <div class="ticket-permission-card-head">
              <div class="field">
                <label>Permisos en ticket para rol</label>
                <select class="ticket-permission-role">${roleOptionsHtml(entry.role_id)}</select>
              </div>
              <div class="ticket-permission-actions">
                <span class="ticket-permission-count">${permissionCount} permiso${permissionCount === 1 ? "" : "s"}</span>
                <button class="action-button danger remove-ticket-permission-role" type="button">Quitar</button>
              </div>
            </div>
            <details class="ticket-permission-details">
              <summary>Editar permisos</summary>
              <div class="ticket-permission-options">
                ${ticketChannelPermissionOptions.map(([key, label]) => `
                  <label class="permission-pill${selected.has(key) ? " active" : ""}">
                    <input class="ticket-permission-checkbox" type="checkbox" value="${escapeHtml(key)}"${selected.has(key) ? " checked" : ""}>
                    ${escapeHtml(label)}
                  </label>
                `).join("")}
              </div>
            </details>
          </article>
        `;
      }).join("") : `<div class="ticket-empty-editor"><strong>Sin roles configurados</strong><p>Agrega un rol para elegir que permisos tendra dentro del canal del ticket.</p></div>`;

      container.querySelectorAll("select, input").forEach(input => {
        input.addEventListener("change", () => {
          persistCurrentTicketPanel();
          renderTicketRolePermissions(currentTicketPanel());
        });
      });
      container.querySelectorAll(".remove-ticket-permission-role").forEach(button => {
        button.addEventListener("click", event => {
          const row = event.target.closest("[data-ticket-permission-index]");
          const index = Number(row?.dataset.ticketPermissionIndex || -1);
          const current = currentTicketPanel();
          if (!current || index < 0) return;
          current.permissions = current.permissions || {};
          current.permissions.ticket_role_permissions = Array.isArray(current.permissions.ticket_role_permissions)
            ? current.permissions.ticket_role_permissions
            : [];
          current.permissions.ticket_role_permissions.splice(index, 1);
          state.ticketPanelsDirty = true;
          renderTicketRolePermissions(current);
        });
      });
    }

    function collectTicketRolePermissions() {
      return Array.from(document.querySelectorAll("[data-ticket-permission-index]")).map(row => {
        const roleId = row.querySelector(".ticket-permission-role")?.value || "";
        const permissions = Array.from(row.querySelectorAll(".ticket-permission-checkbox:checked")).map(input => input.value);
        return { role_id: roleId, permissions };
      }).filter(entry => entry.role_id && entry.permissions.length);
    }

    function renderAllRolePickers(panel) {
      renderRoleSelect("claimRoles", panel.permissions?.claim_roles || []);
      renderRoleSelect("closeRoles", panel.permissions?.close_roles || []);
      renderRoleSelect("reopenRoles", panel.permissions?.reopen_roles || []);
      renderRoleSelect("deleteRoles", panel.permissions?.delete_roles || []);
    }

    function renderRolePickerById(inputId) {
      const panel = currentTicketPanel();
      if (!panel) return;
      const map = {
        claimRoles: "claim_roles",
        closeRoles: "close_roles",
        reopenRoles: "reopen_roles",
        deleteRoles: "delete_roles"
      };
      renderRoleSelect(inputId, panel.permissions?.[map[inputId]] || rolePickerValues(inputId));
    }

    function enforceRoleLimit(input) {
      if (!input) return;
      const values = rolePickerValues(input.id).slice(0, 3);
      setRolePickerValues(input.id, values);
      if (permissionValues(input.value).length > 3) {
        document.getElementById("ticketStatus").textContent = "Puedes seleccionar maximo 3 roles por permiso.";
      }
    }

    function renderTicketEditor() {
      const panel = currentTicketPanel();
      document.getElementById("ticketEmptyEditor").hidden = Boolean(panel);
      document.getElementById("ticketEditor").hidden = !panel;
      const disabled = !panel;
      ["ticketName", "ticketMode", "ticketChannel", "ticketOpenCategory", "ticketColor", "ticketContent", "ticketTitle", "ticketFooter", "ticketDescription", "ticketImage", "ticketOpenContent", "ticketOpenTitle", "ticketOpenColor", "ticketOpenDescription", "ticketOpenFooter", "ticketOpenImage", "ticketOpenThumbnail", "claimRoles", "closeRoles", "reopenRoles", "deleteRoles"].forEach(id => {
        document.getElementById(id).disabled = disabled;
      });

      document.getElementById("savePanelButton").disabled = disabled;
      document.getElementById("publishPanelButton").disabled = disabled;
      document.getElementById("clonePanelButton").disabled = disabled;
      document.getElementById("deletePanelButton").disabled = disabled;
      document.getElementById("addTicketOptionButton").disabled = disabled;
      document.getElementById("addTicketPermissionRoleButton").disabled = disabled;

      if (!panel) {
        document.getElementById("ticketPreview").textContent = "Crea un panel para empezar.";
        document.getElementById("ticketOptions").innerHTML = "";
        document.getElementById("ticketRolePermissionsList").innerHTML = "";
        ["claimRoles", "closeRoles", "reopenRoles", "deleteRoles"].forEach(id => {
          document.getElementById(id).value = "";
          document.getElementById(`${id}Picker`).innerHTML = "";
        });
        return;
      }

      document.getElementById("ticketName").value = panel.name || "";
      document.getElementById("ticketMode").value = panel.mode || "buttons";
      document.getElementById("ticketChannel").value = panel.channel_id || "";
      document.getElementById("ticketOpenCategory").value = panel.open_category_id || "";
      document.getElementById("ticketColor").value = panel.embed_color || "#22c55e";
      document.getElementById("ticketContent").value = panel.message_content || "";
      document.getElementById("ticketTitle").value = panel.embed_title || "";
      document.getElementById("ticketFooter").value = panel.embed_footer || "";
      document.getElementById("ticketDescription").value = panel.embed_description || "";
      document.getElementById("ticketImage").value = panel.image_url || "";
      document.getElementById("ticketOpenContent").value = panel.ticket_open_content || "";
      document.getElementById("ticketOpenTitle").value = panel.ticket_open_title || "";
      document.getElementById("ticketOpenColor").value = panel.ticket_open_color || "";
      document.getElementById("ticketOpenDescription").value = panel.ticket_open_description || "";
      document.getElementById("ticketOpenFooter").value = panel.ticket_open_footer || "";
      document.getElementById("ticketOpenImage").value = panel.ticket_open_image_url || "";
      document.getElementById("ticketOpenThumbnail").value = panel.ticket_open_thumbnail_url || "";
      renderTicketRolePermissions(panel);
      renderAllRolePickers(panel);
      renderTicketOptions(panel);
      renderTicketPreview(panel);
      renderTicketOpenPreview(panel);
    }

    function renderTicketOptions(panel) {
      const container = document.getElementById("ticketOptions");
      const emojiOptions = buildEmojiOptions();
      container.innerHTML = (panel.options || []).map((option, index) => `
        <div class="option-row" data-option-index="${index}">
          <select class="ticket-option-emoji">${emojiOptions(option.emoji || "")}</select>
          <input class="ticket-option-label" type="text" placeholder="Nombre de opcion" value="${escapeHtml(option.label || "")}">
          <input class="ticket-option-description" type="text" placeholder="Descripcion" value="${escapeHtml(option.description || "")}">
          <button class="icon-button remove-ticket-option" type="button" title="Quitar opcion" aria-label="Quitar opcion">x</button>
        </div>
      `).join("");

      container.querySelectorAll("input, select").forEach(input => {
        input.addEventListener("input", () => {
          persistCurrentTicketPanel();
          renderCurrentTicketPreviews();
        });
        input.addEventListener("change", () => {
          persistCurrentTicketPanel();
          renderCurrentTicketPreviews();
        });
      });
      container.querySelectorAll(".remove-ticket-option").forEach(button => {
        button.addEventListener("click", event => {
          const row = event.target.closest(".option-row");
          const index = Number(row.dataset.optionIndex);
          const current = currentTicketPanel();
          if (!current || current.options.length <= 1) return;
          current.options.splice(index, 1);
          state.ticketPanelsDirty = true;
          renderTickets();
        });
      });
    }

    function buildEmojiOptions(selectedValue) {
      return function optionsMarkup(currentValue) {
        const selected = currentValue || selectedValue || "";
        const defaults = globalTicketEmojis.map(([value, label]) => {
          const isSelected = value === selected ? " selected" : "";
          return `<option value="${escapeHtml(value)}"${isSelected}>${escapeHtml(label)}</option>`;
        }).join("");
        return defaults;
      };
    }

    function collectTicketOptions() {
      return Array.from(document.querySelectorAll(".option-row")).map(row => ({
        id: currentTicketPanel()?.options?.[Number(row.dataset.optionIndex)]?.id || (crypto.randomUUID ? crypto.randomUUID() : String(Date.now())),
        emoji: row.querySelector(".ticket-option-emoji").value.trim(),
        label: row.querySelector(".ticket-option-label").value.trim() || "Abrir ticket",
        description: row.querySelector(".ticket-option-description").value.trim()
      }));
    }

    function persistCurrentTicketPanel() {
      const panel = currentTicketPanel();
      if (!panel) return;

      panel.name = document.getElementById("ticketName").value.trim() || "Nuevo panel";
      panel.mode = document.getElementById("ticketMode").value;
      panel.channel_id = document.getElementById("ticketChannel").value;
      panel.open_category_id = document.getElementById("ticketOpenCategory").value;
      panel.embed_color = document.getElementById("ticketColor").value.trim() || "#22c55e";
      panel.message_content = document.getElementById("ticketContent").value;
      panel.embed_title = document.getElementById("ticketTitle").value.trim() || panel.name;
      panel.embed_footer = document.getElementById("ticketFooter").value.trim();
      panel.embed_description = document.getElementById("ticketDescription").value || "Selecciona una opcion para abrir un ticket.";
      panel.image_url = document.getElementById("ticketImage").value.trim();
      panel.ticket_open_content = document.getElementById("ticketOpenContent").value;
      panel.ticket_open_title = document.getElementById("ticketOpenTitle").value.trim();
      panel.ticket_open_color = document.getElementById("ticketOpenColor").value.trim();
      panel.ticket_open_description = document.getElementById("ticketOpenDescription").value;
      panel.ticket_open_footer = document.getElementById("ticketOpenFooter").value.trim();
      panel.ticket_open_image_url = document.getElementById("ticketOpenImage").value.trim();
      panel.ticket_open_thumbnail_url = document.getElementById("ticketOpenThumbnail").value.trim();
      panel.options = collectTicketOptions();
      panel.permissions = {
        ticket_role_permissions: normalizeTicketRolePermissions(collectTicketRolePermissions()),
        claim_roles: rolePickerValues("claimRoles"),
        close_roles: rolePickerValues("closeRoles"),
        reopen_roles: rolePickerValues("reopenRoles"),
        delete_roles: rolePickerValues("deleteRoles")
      };
      state.ticketPanelsDirty = true;
    }

    function renderCurrentTicketPreviews() {
      const panel = currentTicketPanel();
      renderTicketPreview(panel);
      renderTicketOpenPreview(panel);
    }

    function renderTicketPreview(panel) {
      if (!panel) return;
      const mode = panel.mode === "select" ? "Lista desplegable" : "Botones";
      const actions = (panel.options || []).map(option => `
        <span class="discord-preview-action">${escapeHtml(option.emoji || "")}${option.emoji ? " " : ""}${escapeHtml(option.label)}</span>
      `).join("");
      document.getElementById("ticketPreview").innerHTML = `
        <div class="discord-preview" style="border-left-color:${escapeHtml(panel.embed_color || "#22c55e")}">
          ${panel.message_content ? `<div class="muted">${escapeHtml(panel.message_content)}</div>` : ""}
          <div class="discord-preview-title">${escapeHtml(panel.embed_title || panel.name)}</div>
          <div class="discord-preview-description">${escapeHtml(panel.embed_description || "")}</div>
          <div class="muted">Modo: ${escapeHtml(mode)}</div>
          <div class="discord-preview-actions">${actions || `<span class="muted">Sin opciones</span>`}</div>
          ${panel.embed_footer ? `<div class="muted">${escapeHtml(panel.embed_footer)}</div>` : ""}
        </div>
      `;
    }

    function renderTicketOpenPreview(panel) {
      if (!panel) return;
      const hasEmbed = Boolean(
        panel.ticket_open_title ||
        panel.ticket_open_description ||
        panel.ticket_open_footer ||
        panel.ticket_open_image_url ||
        panel.ticket_open_thumbnail_url
      );
      const embed = hasEmbed ? `
        <div class="discord-preview" style="${panel.ticket_open_color ? `border-left-color:${escapeHtml(panel.ticket_open_color)}` : ""}">
          ${panel.ticket_open_title ? `<div class="discord-preview-title">${escapeHtml(panel.ticket_open_title)}</div>` : ""}
          ${panel.ticket_open_description ? `<div class="discord-preview-description">${escapeHtml(panel.ticket_open_description)}</div>` : ""}
          ${panel.ticket_open_thumbnail_url ? `<div class="muted">Miniatura: ${escapeHtml(panel.ticket_open_thumbnail_url)}</div>` : ""}
          ${panel.ticket_open_image_url ? `<div class="muted">Imagen: ${escapeHtml(panel.ticket_open_image_url)}</div>` : ""}
          ${panel.ticket_open_footer ? `<div class="muted">${escapeHtml(panel.ticket_open_footer)}</div>` : ""}
        </div>
      ` : `<div class="muted">Sin embed configurado.</div>`;
      document.getElementById("ticketOpenPreview").innerHTML = `
        ${panel.ticket_open_content ? `<div class="discord-preview-description">${escapeHtml(panel.ticket_open_content)}</div>` : `<div class="muted">Sin mensaje superior.</div>`}
        ${embed}
        <div class="discord-preview-actions">
          <span class="discord-preview-action">Reclamar ticket</span>
          <span class="discord-preview-action">Cerrar ticket</span>
        </div>
      `;
    }

    function renderAlbionRegistration() {
      const config = state.albionRegistrationConfig || {};
      const roleSelect = document.getElementById("albionRole");
      const channelSelect = document.getElementById("albionLogChannel");
      roleSelect.innerHTML = `<option value="">Seleccionar rol</option>${state.ticketRoles.map(role =>
        `<option value="${escapeHtml(role.id)}">${escapeHtml(role.name)}</option>`
      ).join("")}`;
      channelSelect.innerHTML = `<option value="">Sin canal de registros</option>${state.ticketChannels.map(channel =>
        `<option value="${escapeHtml(channel.id)}"># ${escapeHtml(channel.name)}</option>`
      ).join("")}`;

      document.getElementById("albionGuildName").value = config.albion_guild_name || "";
      roleSelect.value = config.role_id || "";
      document.getElementById("albionLeaveAction").value = config.leave_action || "remove_roles";
      channelSelect.value = config.log_channel_id || "";
      document.getElementById("albionSyncNickname").checked = Boolean(config.sync_nickname);

      const active = state.albionRegistrations.filter(item => item.status === "active").length;
      document.getElementById("albionRegistrationSearch").value = state.albionRegistrationSearch || "";
      document.getElementById("albionRegistrationStatusFilter").value = state.albionRegistrationFilters.status || "";
      document.getElementById("albionRegistrationPageSize").value = String(state.albionRegistrationFilters.page_size || 15);
      document.getElementById("albionRegistrationTotal").textContent = state.albionRegistrationFilters.total_items || state.albionRegistrations.length;
      document.getElementById("albionRegistrationActiveTotal").textContent = active;
      renderPager(
        "albionRegistrationPrevPageButton",
        "albionRegistrationNextPageButton",
        "albionRegistrationPageInfo",
        state.albionRegistrationFilters,
        "registro",
        "registros"
      );
      const body = document.getElementById("albionRegistrationsBody");
      body.innerHTML = state.albionRegistrations.map(item => `
        <tr>
          <td>${escapeHtml(item.discord_user_name || item.discord_user_id || "")}</td>
          <td>${escapeHtml(item.player_name || "")}</td>
          <td>${escapeHtml(item.albion_guild_name || "Sin gremio")}</td>
          <td>${escapeHtml(item.status === "active" ? "Activo" : item.status === "kicked" ? "Expulsado" : "Fuera del gremio")}</td>
          <td>${escapeHtml(item.last_checked_at || "")}</td>
        </tr>
      `).join("");
      document.getElementById("albionRegistrationsEmpty").hidden = state.albionRegistrations.length > 0;
    }

    function parseReportAmount(value) {
      const text = String(value || "").trim().toLowerCase().replace(",", ".");
      const suffixMatch = text.match(/(k|m|b|mil|millon|millones)\b/);
      const multipliers = {
        k: 1000,
        mil: 1000,
        m: 1000000,
        millon: 1000000,
        millones: 1000000,
        b: 1000000000
      };
      if (suffixMatch) {
        const amountMatch = text.match(/\d+(?:\.\d+)?/);
        if (!amountMatch) return 0;
        return Math.floor(Number(amountMatch[0]) * (multipliers[suffixMatch[1]] || 1));
      }
      const digits = text.replace(/\D/g, "");
      return digits ? Number(digits) : 0;
    }

    function reportCalculatorModeConfig(mode) {
      return {
        showItems: mode !== "silver",
        showSilver: mode !== "items",
        showCosts: mode !== "items",
        showBothExtras: mode === "items_silver"
      };
    }

    function parseReportPercentage(value) {
      const text = String(value || "").trim().replace(",", ".");
      const match = text.match(/\d+(?:\.\d+)?/);
      if (!match) return 0;
      return Math.max(0, Math.min(Number(match[0]), 100));
    }

    function setReportFieldVisible(fieldId, visible) {
      const field = document.getElementById(fieldId);
      if (field) field.hidden = !visible;
    }

    function applyReportModeVisibility(mode) {
      const config = reportCalculatorModeConfig(mode);
      setReportFieldVisible("reportItemsField", config.showItems);
      setReportFieldVisible("reportSilverField", config.showSilver);
      setReportFieldVisible("reportMapCostField", config.showCosts);
      setReportFieldVisible("reportRepairCostField", config.showCosts);
      setReportFieldVisible("reportCallerPercentField", config.showBothExtras);
      setReportFieldVisible("reportLooterPaymentField", config.showBothExtras);
      const looterPayment = config.showBothExtras ? parseReportAmount(document.getElementById("reportLooterPayment").value) : 0;
      setReportFieldVisible("reportLooterUserField", config.showBothExtras && looterPayment > 0);
      setReportFieldVisible("reportTabSaleField", config.showBothExtras);
      return config;
    }

    function populateReportLooterOptions(participants) {
      const select = document.getElementById("reportLooterUser");
      const selectedValue = select.value;
      select.innerHTML = `<option value="">Selecciona un integrante</option>` + participants.map(participant => (
        `<option value="${escapeHtml(participant.user_id)}">${escapeHtml(participant.display_name || participant.user_id)} - ${escapeHtml(participant.slot)}</option>`
      )).join("");
      if (participants.some(participant => participant.user_id === selectedValue)) {
        select.value = selectedValue;
      }
    }

    function reportParticipantOptionsMarkup(participants, selectedValue = "") {
      return `<option value="">Selecciona un integrante</option>` + participants.map(participant => {
        const selected = participant.user_id === selectedValue ? " selected" : "";
        return `<option value="${escapeHtml(participant.user_id)}"${selected}>${escapeHtml(participant.display_name || participant.user_id)} - ${escapeHtml(participant.slot)}</option>`;
      }).join("");
    }

    function syncReportFineParticipantOptions(participants) {
      document.querySelectorAll(".report-fine-user").forEach(select => {
        const previous = select.value;
        select.innerHTML = reportParticipantOptionsMarkup(participants, previous);
      });
    }

    async function fileToDataUrl(file) {
      return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result || ""));
        reader.onerror = () => reject(new Error("No pude leer la prueba adjunta."));
        reader.readAsDataURL(file);
      });
    }

    function bindReportFineRow(row) {
      row.querySelectorAll("select, input").forEach(element => {
        element.addEventListener("input", () => renderReportCalculator());
        element.addEventListener("change", () => renderReportCalculator());
      });
      row.querySelector(".report-fine-remove").addEventListener("click", () => {
        row.remove();
        renderReportCalculator();
      });
      row.querySelector(".report-fine-proof").addEventListener("change", async event => {
        const file = event.target.files?.[0];
        const label = row.querySelector(".report-fine-proof-name");
        if (!file) {
          event.target.dataset.proofDataUrl = "";
          event.target.dataset.proofName = "";
          label.textContent = "";
          return;
        }
        try {
          event.target.dataset.proofDataUrl = await fileToDataUrl(file);
          event.target.dataset.proofName = file.name;
          label.textContent = file.name;
        } catch (error) {
          event.target.value = "";
          event.target.dataset.proofDataUrl = "";
          event.target.dataset.proofName = "";
          label.textContent = error.message;
        }
      });
    }

    function appendReportFineRow(fine = {}) {
      const container = document.getElementById("reportFinesList");
      const participants = state.reportCalculator?.participants || [];
      const row = document.createElement("div");
      row.className = "report-fine-row";
      row.innerHTML = `
        <div class="field report-fine-user-field">
          <label>Jugador</label>
          <select class="report-fine-user">${reportParticipantOptionsMarkup(participants, fine.user_id || "")}</select>
        </div>
        <div class="field report-fine-amount-field">
          <label>Monto</label>
          <input class="report-fine-amount" type="text" placeholder="Ej: 1m" value="${escapeHtml(fine.amount || "")}">
        </div>
        <div class="field report-fine-reason-field">
          <label>Motivo</label>
          <input class="report-fine-reason" type="text" placeholder="Describe el motivo" value="${escapeHtml(fine.reason || "")}">
        </div>
        <div class="field report-fine-proof-field">
          <label>Prueba</label>
          <input class="report-fine-proof" type="file" accept="image/*">
          <div class="report-fine-proof-name">${escapeHtml(fine.proof_name || "")}</div>
        </div>
        <button class="action-button danger report-fine-remove" type="button">Quitar</button>
      `;
      const proofInput = row.querySelector(".report-fine-proof");
      if (fine.proof_data_url) proofInput.dataset.proofDataUrl = fine.proof_data_url;
      if (fine.proof_name) proofInput.dataset.proofName = fine.proof_name;
      bindReportFineRow(row);
      container.appendChild(row);
    }

    function collectReportFines() {
      return [...document.querySelectorAll(".report-fine-row")].map(row => {
        const userSelect = row.querySelector(".report-fine-user");
        const selectedOption = userSelect.options[userSelect.selectedIndex];
        const proofInput = row.querySelector(".report-fine-proof");
        return {
          user_id: userSelect.value,
          user_name: selectedOption?.textContent?.split(" - ")[0] || "",
          slot: selectedOption?.textContent?.split(" - ").slice(1).join(" - ") || "",
          amount: row.querySelector(".report-fine-amount").value,
          reason: row.querySelector(".report-fine-reason").value,
          proof_data_url: proofInput.dataset.proofDataUrl || "",
          proof_name: proofInput.dataset.proofName || "",
        };
      }).filter(fine => fine.user_id && fine.amount && fine.reason);
    }

    async function loadReportCalculatorOptions({ force = false } = {}) {
      if (!state.guildId || !state.data?.viewer?.id) {
        state.reportCalculatorOptions = [];
        state.reportCalculatorOptionsGuildId = "";
        return;
      }
      if (!force && state.reportCalculatorOptionsGuildId === state.guildId) {
        return;
      }
      const params = new URLSearchParams({ guild_id: state.guildId, list: "1" });
      const response = await fetch(`/api/report-calculator?${params.toString()}`, { cache: "no-store" });
      const payload = await readJsonResponse(response);
      if (!response.ok) throw new Error(payload.error || "No pude cargar los pings activos.");
      state.reportCalculatorOptions = payload.calculators || [];
      state.reportCalculatorOptionsGuildId = state.guildId;
      const currentAva = state.reportContext?.ava || "";
      if (!state.reportCalculatorOptions.length) {
        state.reportContext = null;
        state.reportCalculator = null;
        return;
      }
      const selected = state.reportCalculatorOptions.find(item => item.numero_ava === currentAva) || state.reportCalculatorOptions[0];
      state.reportContext = {
        guildId: state.guildId,
        callerId: state.data.viewer.id,
        ava: selected.numero_ava,
      };
    }

    function renderReportCalculatorOptions() {
      const select = document.getElementById("reportCalculatorSelect");
      const options = state.reportCalculatorOptions || [];
      const currentAva = state.reportContext?.ava || "";
      select.innerHTML = `<option value="">Selecciona una Ava</option>` + options.map(option => {
        const selected = option.numero_ava === currentAva ? " selected" : "";
        const suffix = option.report_rejected ? " - Rechazado" : option.report_sent ? " - Enviado" : "";
        return `<option value="${escapeHtml(option.numero_ava)}"${selected}>${escapeHtml(option.title)}${escapeHtml(suffix)}</option>`;
      }).join("");
      select.disabled = options.length === 0;
    }

    function reportCalculatorValues() {
      const participants = state.reportCalculator?.participants || [];
      const participantCount = participants.length;
      const mode = document.getElementById("reportSplitMode").value;
      const config = applyReportModeVisibility(mode);
      const items = config.showItems ? parseReportAmount(document.getElementById("reportItems").value) : 0;
      const silver = config.showSilver ? parseReportAmount(document.getElementById("reportSilver").value) : 0;
      const mapCost = config.showCosts ? parseReportAmount(document.getElementById("reportMapCost").value) : 0;
      const repairCost = config.showCosts ? parseReportAmount(document.getElementById("reportRepairCost").value) : 0;
      const callerPercent = config.showBothExtras ? parseReportPercentage(document.getElementById("reportCallerPercent").value) : 0;
      const callerPayment = config.showBothExtras ? Math.floor(silver * callerPercent / 100) : 0;
      const looterPayment = config.showBothExtras ? parseReportAmount(document.getElementById("reportLooterPayment").value) : 0;
      const looterUserId = config.showBothExtras && looterPayment > 0 ? document.getElementById("reportLooterUser").value : "";
      const tabSalePercent = config.showBothExtras ? parseReportPercentage(document.getElementById("reportTabSalePercent").value) : 0;
      const netSilver = Math.max(silver - callerPayment - looterPayment - mapCost - repairCost, 0);
      const soldTabValue = config.showBothExtras && tabSalePercent > 0
        ? Math.floor(items * ((100 - tabSalePercent) / 100))
        : 0;
      const splitParticipantCount = participantCount - (looterPayment > 0 && looterUserId ? 1 : 0);
      let itemPool = 0;
      let silverPool = 0;
      if (mode === "items") itemPool = items;
      else if (mode === "silver") silverPool = netSilver;
      else if (tabSalePercent > 0) silverPool = Math.max(netSilver - callerPayment, 0) + soldTabValue;
      else {
        itemPool = items;
        silverPool = netSilver;
      }
      return {
        mode,
        config,
        items,
        silver,
        mapCost,
        repairCost,
        callerPercent,
        callerPayment,
        looterPayment,
        looterUserId,
        tabSalePercent,
        soldTabValue,
        splitParticipantCount: Math.max(splitParticipantCount, 0),
        itemPool,
        silverPool,
        total: itemPool + silverPool,
        itemPerUser: splitParticipantCount > 0 ? Math.floor(itemPool / splitParticipantCount) : 0,
        silverPerUser: splitParticipantCount > 0 ? Math.floor(silverPool / splitParticipantCount) : 0
      };
    }

    function renderReportCalculator() {
      const calculator = state.reportCalculator;
      const participants = calculator?.participants || [];
      renderReportCalculatorOptions();
      populateReportLooterOptions(participants);
      syncReportFineParticipantOptions(participants);
      const selectedLooterId = document.getElementById("reportLooterUser").value;
      document.getElementById("reportCalculatorParticipantsTotal").textContent = participants.length;
      document.getElementById("reportCalculatorSubtitle").textContent = calculator
        ? `${calculator.title} - Caller: ${calculator.caller_name || calculator.caller_id}`
        : "Abre esta seccion desde el boton Enviar informe de una Ava finalizada.";
      document.getElementById("reportParticipantsList").innerHTML = participants.length
        ? participants.map(participant => `
            <article class="report-participant-card">
              <div class="report-participant-head">
                <strong>${escapeHtml(`${participant.index}. ${participant.slot}`)}</strong>
                ${participant.user_id === selectedLooterId ? '<span class="report-participant-role">Looter</span>' : ''}
              </div>
              <span class="report-participant-name">${escapeHtml(participant.display_name || participant.user_id)}</span>
            </article>
          `).join("")
        : `<article class="report-participant-card">
              <div class="report-participant-head">
                <strong>Sin integrantes cargados</strong>
              </div>
              <span class="muted">Abre una Ava finalizada desde Discord.</span>
            </article>
          `;

      const values = reportCalculatorValues();
      document.getElementById("reportSplitParticipantsTotal").textContent = formatNumber(values.splitParticipantCount);
      document.getElementById("reportItemsPerUserStat").hidden = values.itemPool <= 0;
      document.getElementById("reportSilverPerUserStat").hidden = values.silverPool <= 0;
      document.getElementById("reportItemsPerUser").textContent = formatNumber(values.itemPerUser);
      document.getElementById("reportSilverPerUser").textContent = formatNumber(values.silverPerUser);
      document.getElementById("reportNetTotal").textContent = formatNumber(values.total);
      const breakdown = [];
      if (values.itemPool) {
        breakdown.push({
          label: "Items netos",
          value: formatNumber(values.itemPool),
          tone: "accent"
        });
      }
      if (values.silverPool) {
        breakdown.push({
          label: "Silver neto",
          value: formatNumber(values.silverPool),
          tone: "accent"
        });
      }
      if (values.config.showCosts) {
        if (values.callerPayment) {
          breakdown.push({
            label: `Caller (${values.callerPercent}%)`,
            value: `-${formatNumber(values.callerPayment)}`,
            tone: "negative"
          });
        }
        if (values.looterPayment) {
          breakdown.push({
            label: "Pago looter",
            value: `-${formatNumber(values.looterPayment)}`,
            tone: "negative"
          });
        }
        if (values.mapCost) {
          breakdown.push({
            label: "Mapa",
            value: `-${formatNumber(values.mapCost)}`,
            tone: "negative"
          });
        }
        if (values.repairCost) {
          breakdown.push({
            label: "Reparaciones",
            value: `-${formatNumber(values.repairCost)}`,
            tone: "negative"
          });
        }
      }
      document.getElementById("reportCalculatorBreakdown").innerHTML = breakdown.length
        ? breakdown.map(item => `
            <div class="report-breakdown-item ${item.tone ? escapeHtml(item.tone) : ""}">
              <span class="report-breakdown-label">${escapeHtml(item.label)}</span>
              <strong class="report-breakdown-value">${escapeHtml(item.value)}</strong>
            </div>
          `).join("")
        : `<div class="report-breakdown-empty">Completa los datos para calcular el reparto.</div>`;
      if (values.looterPayment && !values.looterUserId) {
        document.getElementById("reportCalculatorBreakdown").innerHTML += `
          <div class="report-breakdown-empty">Selecciona quien fue el looter para excluirlo del split.</div>
        `;
      }
      document.getElementById("submitReportCalculatorButton").disabled = !calculator || calculator.report_sent || calculator.cancelled || !calculator.finalized || (values.looterPayment > 0 && !values.looterUserId);
    }

    function resetReportCalculator() {
      ["reportEstimated", "reportItems", "reportSilver", "reportMapCost", "reportRepairCost", "reportCallerPercent", "reportLooterPayment", "reportLooterUser", "reportTabSalePercent"].forEach(id => {
        document.getElementById(id).value = "";
      });
      document.getElementById("reportFinesList").innerHTML = "";
      document.getElementById("reportCalculatorStatus").textContent = "";
      renderReportCalculator();
    }

    async function loadReportCalculator() {
      renderReportCalculatorOptions();
      if (!state.reportContext) {
        state.reportCalculator = null;
        renderReportCalculator();
        return;
      }
      const params = new URLSearchParams({
        guild_id: state.reportContext.guildId,
        caller_id: state.reportContext.callerId,
        ava: state.reportContext.ava
      });
      const response = await fetch(`/api/report-calculator?${params.toString()}`, { cache: "no-store" });
      const payload = await response.json();
      if (!response.ok) {
        state.reportCalculator = null;
        renderReportCalculator();
        if (response.status === 404) {
          throw new Error("Esta Ava ya no esta activa o ya fue cerrada. Abrela de nuevo desde Discord.");
        }
        throw new Error(payload.error || "No pude cargar la calculadora.");
      }
      state.reportCalculator = payload.calculator;
      document.getElementById("reportFinesList").innerHTML = "";
      state.guildId = payload.calculator.guild_id;
      renderReportCalculator();
    }

    async function submitReportCalculator() {
      if (!state.reportCalculator) throw new Error("No hay una Ava cargada.");
      const status = document.getElementById("reportCalculatorStatus");
      const mode = document.getElementById("reportSplitMode").value;
      const config = reportCalculatorModeConfig(mode);
      status.textContent = "Enviando informe al bot...";
      const response = await fetch("/api/report-calculator", {
        method: "POST",
        headers: csrfHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({
          guild_id: state.reportCalculator.guild_id,
          caller_id: state.reportCalculator.caller_id,
          numero_ava: state.reportCalculator.numero_ava,
          split_mode: mode,
          estimated: document.getElementById("reportEstimated").value,
          items: config.showItems ? document.getElementById("reportItems").value : "",
          silver: config.showSilver ? document.getElementById("reportSilver").value : "",
          costs: config.showCosts ? `mapa=${document.getElementById("reportMapCost").value}; repa=${document.getElementById("reportRepairCost").value}` : "",
          caller_percentage: config.showBothExtras ? document.getElementById("reportCallerPercent").value : "",
          looter_payment: config.showBothExtras ? document.getElementById("reportLooterPayment").value : "",
          looter_user_id: config.showBothExtras ? document.getElementById("reportLooterUser").value : "",
          tab_sale_percentage: config.showBothExtras ? document.getElementById("reportTabSalePercent").value : "",
          adjustments: "",
          fines: collectReportFines(),
        })
      });
      const payload = await response.json();
      if (!response.ok) {
        if (response.status === 404) {
          state.reportCalculator = null;
          renderReportCalculator();
          throw new Error("Esta Ava ya no esta activa o ya fue cerrada. Abrela de nuevo desde Discord.");
        }
        throw new Error(payload.error || "No pude enviar el informe.");
      }
      state.reportRequestId = payload.request.id;
      status.textContent = "El bot esta procesando el informe...";
      await pollReportRequest();
    }

    async function pollReportRequest() {
      if (!state.reportRequestId) return;
      const params = new URLSearchParams({ request_id: state.reportRequestId });
      const response = await fetch(`/api/report-calculator?${params.toString()}`, { cache: "no-store" });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "No pude consultar el envio.");
      const request = payload.request;
      if (request.status === "completed") {
        document.getElementById("reportCalculatorStatus").textContent = "Informe enviado a evaluacion.";
        state.reportCalculator.report_sent = true;
        renderReportCalculator();
        return;
      }
      if (request.status === "error") {
        throw new Error(request.error || "El bot no pudo enviar el informe.");
      }
      setTimeout(() => pollReportRequest().catch(error => {
        document.getElementById("reportCalculatorStatus").textContent = error.message;
      }), 1500);
    }

    function applyTheme() {
      document.body.classList.toggle("theme-dark", state.theme === "dark");
    }

    function renderTheme() {
      applyTheme();
      const button = document.getElementById("themeToggle");
      button.innerHTML = state.theme === "dark"
        ? `<svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="4"></circle><path d="M12 2v2"></path><path d="M12 20v2"></path><path d="m4.93 4.93 1.41 1.41"></path><path d="m17.66 17.66 1.41 1.41"></path><path d="M2 12h2"></path><path d="M20 12h2"></path><path d="m6.34 17.66-1.41 1.41"></path><path d="m19.07 4.93-1.41 1.41"></path></svg>`
        : `<svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20.99 12.35A8.5 8.5 0 1 1 11.65 3a6.5 6.5 0 0 0 9.34 9.35Z"></path></svg>`;
      button.title = state.theme === "dark" ? "Cambiar a tema claro" : "Cambiar a tema oscuro";
      button.setAttribute("aria-label", button.title);
    }

    function renderSections() {
      document.getElementById("appShell").classList.toggle("sidebar-collapsed", state.sidebarCollapsed);
      const sidebarToggle = document.getElementById("sidebarToggle");
      const sidebarToggleLabel = state.sidebarCollapsed ? "Expandir secciones" : "Minimizar secciones";
      sidebarToggle.setAttribute("aria-label", sidebarToggleLabel);
      sidebarToggle.title = sidebarToggleLabel;
      sidebarToggle.setAttribute("aria-expanded", String(!state.sidebarCollapsed));
      if (!canUseSection(state.section)) {
        const firstAllowed = [...document.querySelectorAll(".section-button")]
          .find(button => canUseSection(button.dataset.section));
        state.section = firstAllowed?.dataset.section || "tickets";
        localStorage.setItem("dashboardSection", state.section);
      }
      document.getElementById("economySection").hidden = state.section !== "economy";
      document.getElementById("templatesSection").hidden = state.section !== "templates";
      document.getElementById("lootSection").hidden = state.section !== "loot";
      document.getElementById("ticketsSection").hidden = state.section !== "tickets";
      document.getElementById("reportCalculatorSection").hidden = state.section !== "report-calculator";
      document.getElementById("registrationSection").hidden = state.section !== "registration";
      document.getElementById("welcomeSection").hidden = state.section !== "welcome";
      document.getElementById("auditSection").hidden = state.section !== "audit";
      document.getElementById("permissionsSection").hidden = state.section !== "permissions";
      document.getElementById("searchInput").hidden = state.section !== "economy";
      document.querySelectorAll(".section-button").forEach(button => {
        button.hidden = !canUseSection(button.dataset.section);
        const active = button.dataset.section === state.section;
        button.classList.toggle("active", active);
        if (active) button.setAttribute("aria-current", "page");
        else button.removeAttribute("aria-current");
      });
    }

    function canUseSection(section) {
      const access = state.data?.access || {};
      if (access.admin) return true;
      const sectionAccess = {
        economy: "economy",
        templates: "templates",
        tickets: "tickets",
        audit: "audit",
        permissions: "permissions",
        registration: "registration"
      };
      if (sectionAccess[section]) return Boolean(access[sectionAccess[section]]);
      if (section === "report-calculator") return Boolean(state.guildId);
      return false;
    }

    function renderSession() {
      const viewer = state.data?.viewer || null;
      const authenticated = Boolean(viewer?.id);
      document.getElementById("userLabel").textContent = authenticated ? viewer.username : "No conectado";
      document.getElementById("logoutButton").hidden = !authenticated;
    }

    function createEmptyDashboardData(overrides = {}) {
      return {
        guilds: [],
        selectedGuildId: "",
        balances: [],
        operations: [],
        avalonians: [],
        reports: [],
        fines: [],
        totals: { players: 0, items: 0, silver: 0, total: 0 },
        updatedAt: "",
        viewer: {},
        access: {},
        ...overrides
      };
    }

    function resetGuildScopedData() {
      state.data = createEmptyDashboardData({
        guilds: state.data?.guilds || [],
        selectedGuildId: state.guildId || "",
        viewer: state.data?.viewer || {},
        access: {}
      });
      state.pingTemplates = [];
      state.pingTemplateSavedCount = 0;
      state.pingTemplateMax = 5;
      state.ticketPanels = [];
      state.ticketChannels = [];
      state.ticketCategories = [];
      state.ticketEmojis = [];
      state.ticketRoles = [];
      state.ticketRecords = [];
      state.ticketRecordsSummary = {};
      state.ticketRecordSearch = "";
      state.ticketRecordFilters = createPageState(10);
      state.selectedTicketRecordId = "";
      state.selectedLiveTicketId = "";
      state.ticketLiveMessages = [];
      state.auditCategories = [];
      state.auditConfig = { channels: {} };
      state.auditEvents = [];
      state.auditSearch = "";
      state.auditFilters = createPageState(12);
      state.botPermissions = {};
      state.botPermissionOptions = [];
      state.albionRegistrationConfig = null;
      state.albionRegistrations = [];
      state.albionRegistrationSearch = "";
      state.albionRegistrationFilters = createPageState(15);
      state.reportCalculator = null;
      state.reportCalculatorOptions = [];
      state.reportRequestId = "";
      state.fineConfig = null;
      state.economyGuildId = "";
      state.search = "";
      state.economyPages = {
        balances: createPageState(25),
        operations: createPageState(25),
        avalonians: createPageState(25),
        reports: createPageState(25),
        fines: createPageState(25)
      };
      state.templateGuildId = "";
      state.discordMetadataGuildId = "";
      state.discordMetadataKindsLoaded = {};
      state.ticketConfigGuildId = "";
      state.fineConfigGuildId = "";
      state.auditGuildId = "";
      state.permissionsGuildId = "";
      state.albionRegistrationGuildId = "";
      state.reportCalculatorOptionsGuildId = "";
      state.ticketPanelsDirty = false;
      if (state.reportContext && state.reportContext.guildId !== state.guildId) {
        state.reportContext = null;
      }
    }

    function setSectionMessage(section, message) {
      const ids = {
        economy: ["status"],
        templates: ["templateStatus"],
        tickets: ["ticketStatus"],
        audit: ["auditStatus"],
        permissions: ["permissionsStatus"],
        registration: ["albionRegistrationStatus"],
        "report-calculator": ["reportCalculatorStatus"]
      }[section] || [];
      ids.forEach(id => {
        const element = document.getElementById(id);
        if (element) element.textContent = message;
      });
    }

    function clearSectionMessage(section) {
      setSectionMessage(section, "");
    }

    function renderBlocked(message) {
      state.data = createEmptyDashboardData();
      render();
      document.getElementById("status").textContent = message;
    }

    async function loadBootstrapData() {
      const params = new URLSearchParams();
      const requestedGuildId = state.reportContext?.guildId || state.guildId;
      if (requestedGuildId) params.set("guild_id", requestedGuildId);
      const [meResponse, guildsResponse] = await Promise.all([
        fetch("/api/me", { cache: "no-store" }),
        fetch(`/api/guilds?${params.toString()}`, { cache: "no-store" })
      ]);
      if (
        meResponse.status === 401 || meResponse.status === 503 ||
        guildsResponse.status === 401 || guildsResponse.status === 503
      ) {
        window.location.href = "/";
        return;
      }
      const mePayload = await readJsonResponse(meResponse);
      const guildsPayload = await readJsonResponse(guildsResponse);
      if (!meResponse.ok) throw new Error(mePayload.error || "No se pudo cargar la sesion.");
      if (!guildsResponse.ok) throw new Error(guildsPayload.error || "No se pudo cargar la lista de servidores.");

      state.data = createEmptyDashboardData({
        viewer: mePayload.viewer || {},
        guilds: guildsPayload.guilds || [],
        selectedGuildId: guildsPayload.selectedGuildId || ""
      });
      state.csrfToken = mePayload.csrf_token || "";
      state.guildId = state.data.selectedGuildId || "";
      if (state.guildId) localStorage.setItem("dashboardGuildId", state.guildId);
      else localStorage.removeItem("dashboardGuildId");
      await loadDashboardAccess();
      render();
    }

    async function loadDashboardAccess() {
      const params = new URLSearchParams();
      if (state.guildId) params.set("guild_id", state.guildId);
      const response = await fetch(`/api/dashboard/access?${params.toString()}`, { cache: "no-store" });
      if (response.status === 401 || response.status === 503) {
        window.location.href = "/";
        return;
      }
      const payload = await readJsonResponse(response);
      if (!response.ok) throw new Error(payload.error || "No se pudieron cargar los permisos del dashboard.");

      const selectedGuildId = payload.selectedGuildId || "";
      if (selectedGuildId && selectedGuildId !== state.guildId) {
        state.guildId = selectedGuildId;
        localStorage.setItem("dashboardGuildId", state.guildId);
      }
      state.data = createEmptyDashboardData({
        ...state.data,
        selectedGuildId: state.guildId || selectedGuildId,
        access: payload.access || {}
      });
    }

    async function loadDiscordMetadata({ force = false, kinds = ["channels", "categories", "emojis", "roles"] } = {}) {
      if (!state.guildId) return;
      const requestedKinds = Array.isArray(kinds) ? kinds : ["channels", "categories", "emojis", "roles"];
      const missingKinds = requestedKinds.filter(kind => force || !state.discordMetadataKindsLoaded[kind]);
      if (!missingKinds.length && state.discordMetadataGuildId === state.guildId) return;

      const params = new URLSearchParams({
        guild_id: state.guildId,
        kinds: missingKinds.join(",")
      });
      if (force) params.set("refresh", "1");
      const response = await fetch(`/api/discord-metadata?${params.toString()}`, { cache: "no-store" });
      const payload = await readJsonResponse(response);
      if (!response.ok) throw new Error(payload.error || "No pude cargar la metadata de Discord.");

      if (payload.channels) {
        state.ticketChannels = payload.channels || [];
        state.discordMetadataKindsLoaded.channels = true;
      }
      if (payload.categories) {
        state.ticketCategories = payload.categories || [];
        state.discordMetadataKindsLoaded.categories = true;
      }
      if (payload.emojis) {
        state.ticketEmojis = payload.emojis || [];
        state.discordMetadataKindsLoaded.emojis = true;
      }
      if (payload.roles) {
        state.ticketRoles = payload.roles || [];
        state.discordMetadataKindsLoaded.roles = true;
      }
      state.discordMetadataGuildId = state.guildId;
    }

    function createDashboardContext() {
      return {
        state,
        createEmptyDashboardData,
        createPageState,
        currentEconomyPageState,
        applyPagePayload,
        setSectionMessage,
        clearSectionMessage,
        readJsonResponse,
        applyPingTemplatesPayload,
        ensureDiscordMetadata: loadDiscordMetadata,
        renderShell,
        renderSection,
        render,
        loadReportCalculatorOptions,
        loadReportCalculator,
      };
    }

    function loadEconomyData(options = {}) {
      return window.NeoxDashboardRouter.load("economy", createDashboardContext(), options);
    }

    function loadTemplatesData(options = {}) {
      return window.NeoxDashboardRouter.load("templates", createDashboardContext(), options);
    }

    function loadTicketsData(options = {}) {
      return window.NeoxDashboardRouter.load("tickets", createDashboardContext(), options);
    }

    function loadAuditData(options = {}) {
      return window.NeoxDashboardRouter.load("audit", createDashboardContext(), options);
    }

    function loadPermissionsData(options = {}) {
      return window.NeoxDashboardRouter.load("permissions", createDashboardContext(), options);
    }

    function loadAlbionRegistrationData(options = {}) {
      return window.NeoxDashboardRouter.load("registration", createDashboardContext(), options);
    }

    async function loadCurrentSectionData(options = {}) {
      const force = Boolean(options?.force);
      if (state.section === "loot" || state.section === "welcome") {
        renderSection(state.section);
        return;
      }
      if (state.section === "report-calculator") {
        return window.NeoxDashboardRouter.load("report-calculator", createDashboardContext(), { force });
      }
      return window.NeoxDashboardRouter.load(state.section, createDashboardContext(), { force });
    }

    function csrfHeaders(extra = {}) {
      const headers = { ...extra };
      if (state.csrfToken) headers["X-CSRF-Token"] = state.csrfToken;
      return headers;
    }

    async function loadTicketRecordsLive() {
      if (!state.guildId) return;
      const filters = state.ticketRecordFilters;
      const params = new URLSearchParams({
        guild_id: state.guildId,
        page: String(filters.page || 1),
        page_size: String(filters.page_size || 10),
        q: state.ticketRecordSearch || ""
      });
      if (filters.status) params.set("status", filters.status);
      if (filters.date_from) params.set("date_from", filters.date_from);
      if (filters.date_to) params.set("date_to", filters.date_to);
      const response = await fetch(`/api/ticket-records?${params.toString()}`, { cache: "no-store" });
      const payload = await readJsonResponse(response);
      if (!response.ok) throw new Error(payload.error || "No pude cargar tickets en vivo.");
      applyPagePayload(state.ticketRecordFilters, payload);
      state.ticketRecords = payload.records || [];
      state.ticketRecordsSummary = payload.summary || {};
      renderTicketLiveSummary();
      renderTicketRecords();
    }

    async function saveTicketPanels() {
      persistCurrentTicketPanel();
      const response = await fetch("/api/ticket-panels", {
        method: "POST",
        headers: csrfHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({
          guild_id: state.guildId,
          panels: state.ticketPanels
        })
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "No pude guardar los paneles.");
      state.ticketPanels = payload.panels || [];
      state.ticketPanelsDirty = false;
      document.getElementById("ticketStatus").textContent = "Configuracion guardada.";
      renderTickets();
    }

    async function readJsonResponse(response) {
      const text = await response.text();
      if (!text) return {};
      try {
        return JSON.parse(text);
      } catch (error) {
        throw new Error(text.slice(0, 180) || "Respuesta invalida del dashboard.");
      }
    }

    function applyPingTemplatesPayload(payload) {
      state.pingTemplates = payload.templates || [];
      state.pingTemplateSavedCount = payload.saved_count || 0;
      state.pingTemplateMax = payload.max_templates || 5;
      if (!state.pingTemplates.some(template => template.key === state.currentPingTemplateKey)) {
        state.currentPingTemplateKey = state.pingTemplates[0]?.key || "";
      }
      localStorage.setItem("dashboardPingTemplateKey", state.currentPingTemplateKey);
    }

    async function savePingTemplate() {
      const data = templateFormData();
      if (!state.guildId) {
        throw new Error("Selecciona un servidor antes de guardar la plantilla.");
      }
      document.getElementById("templateStatus").textContent = "Guardando plantilla...";
      const response = await fetch("/api/ping-templates", {
        method: "POST",
        headers: csrfHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({
          guild_id: state.guildId,
          template: data
        })
      });
      const payload = await readJsonResponse(response);
      if (!response.ok) throw new Error(payload.error || "No pude guardar la plantilla.");
      delete state.pingTemplateDrafts[data.original_key];
      delete state.pingTemplateDrafts[data.key];
      applyPingTemplatesPayload(payload);
      state.currentPingTemplateKey = payload.template?.key || state.currentPingTemplateKey;
      localStorage.setItem("dashboardPingTemplateKey", state.currentPingTemplateKey);
      state.templateStatusMessage = "Plantilla guardada. Los comandos /ping y /plantilla ya usan esta configuracion.";
      renderTemplates();
    }

    async function deletePingTemplate() {
      const template = currentPingTemplate();
      const key = document.getElementById("templateOriginalKey").value.trim() || template?.key || "";
      if (!state.guildId) {
        throw new Error("Selecciona un servidor antes de eliminar la plantilla.");
      }
      if (!template || !template.deletable || !key) {
        throw new Error("Esta plantilla todavia no se puede eliminar. Guarda una version del servidor primero.");
      }
      document.getElementById("templateStatus").textContent = "Eliminando plantilla...";
      const response = await fetch("/api/ping-templates", {
        method: "DELETE",
        headers: csrfHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({
          guild_id: state.guildId,
          key
        })
      });
      const payload = await readJsonResponse(response);
      if (!response.ok) throw new Error(payload.error || "No pude eliminar la plantilla.");
      delete state.pingTemplateDrafts[key];
      applyPingTemplatesPayload(payload);
      state.templateStatusMessage = "Plantilla eliminada.";
      renderTemplates();
    }

    async function saveAuditConfig() {
      const response = await fetch("/api/audit-config", {
        method: "POST",
        headers: csrfHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({
          guild_id: state.guildId,
          config: state.auditConfig
        })
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "No pude guardar auditoria.");
      state.auditConfig = payload.config || { channels: {} };
      document.getElementById("auditStatus").textContent = "Auditoria guardada.";
      renderAudit();
    }

    async function saveBotPermissions() {
      const response = await fetch("/api/bot-permissions", {
        method: "POST",
        headers: csrfHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({
          guild_id: state.guildId,
          permissions: collectBotPermissions()
        })
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "No pude guardar los permisos.");
      state.botPermissions = payload.permissions || {};
      state.botPermissionOptions = payload.options || state.botPermissionOptions;
      document.getElementById("permissionsStatus").textContent = "Permisos guardados. Los comandos de Discord ya usan esta configuracion.";
      renderPermissions();
    }

    async function saveAlbionRegistration() {
      const status = document.getElementById("albionRegistrationStatus");
      status.textContent = "Validando el gremio en Albion Online...";
      const response = await fetch("/api/albion-registration", {
        method: "POST",
        headers: csrfHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({
          guild_id: state.guildId,
          albion_guild_name: document.getElementById("albionGuildName").value.trim(),
          role_id: document.getElementById("albionRole").value,
          leave_action: document.getElementById("albionLeaveAction").value,
          log_channel_id: document.getElementById("albionLogChannel").value,
          sync_nickname: document.getElementById("albionSyncNickname").checked
        })
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "No pude guardar el registro de Albion.");
      state.albionRegistrationConfig = payload.config || null;
      state.albionRegistrationGuildId = "";
      await loadAlbionRegistrationData({ force: true });
      renderAlbionRegistration();
      status.textContent = `Configuracion guardada para ${payload.config?.albion_guild_name || "el gremio"}.`;
    }

    async function saveFineConfig() {
      const response = await fetch("/api/fine-config", {
        method: "POST",
        headers: csrfHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({
          guild_id: state.guildId,
          channel_id: document.getElementById("fineChannel").value,
          blocked_role_id: document.getElementById("fineBlockedRole").value,
          resolver_role_id: document.getElementById("fineResolverRole").value,
          ticket_category_id: document.getElementById("fineTicketCategory").value,
        })
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "No pude guardar la configuracion de multas.");
      state.fineConfig = payload;
      document.getElementById("fineConfigStatus").textContent = "Configuracion de multas guardada.";
      renderFineConfig();
    }

    async function publishCurrentTicketPanel() {
      persistCurrentTicketPanel();
      if (state.ticketPanelsDirty) {
        await saveTicketPanels();
      }
      const panel = currentTicketPanel();
      if (!panel) return;
      const response = await fetch("/api/publish-ticket-panel", {
        method: "POST",
        headers: csrfHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({
          guild_id: state.guildId,
          channel_id: panel.channel_id,
          panel
        })
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "No pude publicar el panel.");
      document.getElementById("ticketStatus").textContent = `Publicado en Discord. Mensaje ${payload.message_id || ""}`;
    }

    document.getElementById("guildSelect").addEventListener("change", event => {
      state.guildId = event.target.value;
      state.data = createEmptyDashboardData({
        ...state.data,
        selectedGuildId: state.guildId
      });
      if (state.guildId) localStorage.setItem("dashboardGuildId", state.guildId);
      else localStorage.removeItem("dashboardGuildId");
      resetGuildScopedData();
      render();
      loadDashboardAccess()
        .then(() => {
          render();
          return loadCurrentSectionData({ force: true });
        })
        .catch(showError);
    });

    document.getElementById("searchInput").addEventListener("input", event => {
      state.search = event.target.value;
      currentEconomyPageState().page = 1;
      debounceAction("economy-search", () => {
        loadEconomyData({ force: true }).catch(showError);
      });
    });

    document.getElementById("economyStatusFilter").addEventListener("change", event => {
      const filters = currentEconomyPageState();
      filters.status = event.target.value;
      filters.page = 1;
      loadEconomyData({ force: true }).catch(showError);
    });

    document.getElementById("economyTypeFilter").addEventListener("change", event => {
      const filters = currentEconomyPageState();
      filters.record_type = event.target.value;
      filters.page = 1;
      loadEconomyData({ force: true }).catch(showError);
    });

    document.getElementById("economyDateFrom").addEventListener("change", event => {
      const filters = currentEconomyPageState();
      filters.date_from = event.target.value;
      filters.page = 1;
      loadEconomyData({ force: true }).catch(showError);
    });

    document.getElementById("economyDateTo").addEventListener("change", event => {
      const filters = currentEconomyPageState();
      filters.date_to = event.target.value;
      filters.page = 1;
      loadEconomyData({ force: true }).catch(showError);
    });

    document.getElementById("economyPageSize").addEventListener("change", event => {
      const filters = currentEconomyPageState();
      filters.page_size = Number(event.target.value || 25);
      filters.page = 1;
      loadEconomyData({ force: true }).catch(showError);
    });

    document.getElementById("economyPrevPageButton").addEventListener("click", () => {
      const filters = currentEconomyPageState();
      if (filters.page <= 1) return;
      filters.page -= 1;
      loadEconomyData({ force: true }).catch(showError);
    });

    document.getElementById("economyNextPageButton").addEventListener("click", () => {
      const filters = currentEconomyPageState();
      if (filters.total_pages && filters.page >= filters.total_pages) return;
      filters.page += 1;
      loadEconomyData({ force: true }).catch(showError);
    });

    document.getElementById("logoutButton").addEventListener("click", () => {
      window.location.href = "/logout";
    });

    document.getElementById("themeToggle").addEventListener("click", () => {
      state.theme = state.theme === "dark" ? "light" : "dark";
      localStorage.setItem("dashboardTheme", state.theme);
      renderTheme();
    });

    document.getElementById("sidebarToggle").addEventListener("click", () => {
      state.sidebarCollapsed = !state.sidebarCollapsed;
      localStorage.setItem("dashboardSidebarCollapsed", state.sidebarCollapsed ? "1" : "0");
      renderSections();
    });

    document.querySelectorAll(".section-button").forEach(button => {
      button.addEventListener("click", () => {
        if (!canUseSection(button.dataset.section)) return;
        state.section = button.dataset.section;
        localStorage.setItem("dashboardSection", state.section);
        render();
        loadCurrentSectionData().catch(showError);
      });
    });

    document.getElementById("lootFileInput").addEventListener("change", event => {
      const file = event.target.files?.[0];
      loadLootFile(file)
        .catch(showLootError)
        .finally(() => {
          event.target.value = "";
        });
    });

    document.getElementById("lootReplaceButton").addEventListener("click", () => {
      document.getElementById("lootFileInput").value = "";
      document.getElementById("lootFileInput").click();
    });

    document.getElementById("lootClearButton").addEventListener("click", clearLoot);

    document.getElementById("lootIconSize").addEventListener("input", event => {
      state.loot.iconSize = Number(event.target.value);
      renderLoot();
    });

    document.getElementById("lootGroupToggle").addEventListener("click", () => {
      state.loot.groupByTier = !state.loot.groupByTier;
      renderLoot();
    });

    const lootDropzone = document.getElementById("lootDropzone");
    ["dragenter", "dragover"].forEach(eventName => {
      lootDropzone.addEventListener(eventName, event => {
        event.preventDefault();
        lootDropzone.classList.add("dragging");
      });
    });
    ["dragleave", "drop"].forEach(eventName => {
      lootDropzone.addEventListener(eventName, event => {
        event.preventDefault();
        lootDropzone.classList.remove("dragging");
      });
    });
    lootDropzone.addEventListener("drop", event => {
      loadLootFile(event.dataTransfer?.files?.[0]).catch(showLootError);
    });

    document.getElementById("lootTierButtons").addEventListener("click", event => {
      const button = event.target.closest("[data-loot-tier]");
      if (button) toggleLootTier(Number(button.dataset.lootTier));
    });

    document.getElementById("lootPlayers").addEventListener("click", event => {
      const detail = event.target.closest("[data-loot-detail-item]");
      if (detail) {
        showLootDetail(detail.dataset.lootDetailPlayer, detail.dataset.lootDetailItem);
        return;
      }
      const item = event.target.closest("[data-loot-item]");
      if (item) toggleLootItem(item.dataset.lootPlayer, item.dataset.lootItem);
    });

    document.getElementById("lootModal").addEventListener("click", event => {
      if (event.target.id === "lootModal" || event.target.closest("[data-loot-modal-close]")) {
        closeLootDetail();
      }
    });

    document.addEventListener("keydown", event => {
      if (event.key === "Escape" && !document.getElementById("lootModal").hidden) closeLootDetail();
    });

    document.querySelectorAll(".editor-tab").forEach(button => {
      button.addEventListener("click", () => {
        state.ticketEditorSection = button.dataset.editorSection;
        localStorage.setItem("dashboardTicketEditorSection", state.ticketEditorSection);
        renderTicketEditorSections();
      });
    });

    ["ticketName", "ticketMode", "ticketChannel", "ticketOpenCategory", "ticketColor", "ticketContent", "ticketTitle", "ticketFooter", "ticketDescription", "ticketImage", "ticketOpenContent", "ticketOpenTitle", "ticketOpenColor", "ticketOpenDescription", "ticketOpenFooter", "ticketOpenImage", "ticketOpenThumbnail", "claimRoles", "closeRoles", "reopenRoles", "deleteRoles"].forEach(id => {
      document.getElementById(id).addEventListener("input", () => {
        if (id.endsWith("Roles")) enforceRoleLimit(document.getElementById(id));
        persistCurrentTicketPanel();
        renderCurrentTicketPreviews();
      });
      document.getElementById(id).addEventListener("change", () => {
        if (id.endsWith("Roles")) enforceRoleLimit(document.getElementById(id));
        persistCurrentTicketPanel();
        renderCurrentTicketPreviews();
      });
    });

    document.addEventListener("click", event => {
      const toggle = event.target.closest("[data-role-picker-toggle]");
      const option = event.target.closest("[data-role-picker-option]");
      const remove = event.target.closest("[data-role-picker-remove]");
      const insidePicker = event.target.closest(".role-picker");

      if (toggle) {
        const inputId = toggle.dataset.rolePickerToggle;
        state.openRolePicker = state.openRolePicker === inputId ? "" : inputId;
        renderRolePickerById(inputId);
        return;
      }

      if (option) {
        const inputId = option.dataset.rolePickerOption;
        const roleId = String(option.dataset.roleId || "");
        const values = rolePickerValues(inputId);
        const exists = values.includes(roleId);
        if (exists) {
          setRolePickerValues(inputId, values.filter(value => value !== roleId));
        } else if (values.length < 3) {
          setRolePickerValues(inputId, [...values, roleId]);
        } else {
          document.getElementById("ticketStatus").textContent = "Puedes seleccionar maximo 3 roles por permiso.";
        }
        state.openRolePicker = inputId;
        persistCurrentTicketPanel();
        renderRolePickerById(inputId);
        return;
      }

      if (remove) {
        const inputId = remove.dataset.rolePickerRemove;
        const roleId = String(remove.dataset.roleId || "");
        setRolePickerValues(inputId, rolePickerValues(inputId).filter(value => value !== roleId));
        state.openRolePicker = inputId;
        persistCurrentTicketPanel();
        renderRolePickerById(inputId);
        return;
      }

      if (!insidePicker && state.openRolePicker) {
        const inputId = state.openRolePicker;
        state.openRolePicker = "";
        renderRolePickerById(inputId);
      }
    });

    document.addEventListener("input", event => {
      const search = event.target.closest("[data-role-picker-search]");
      if (!search) return;
      const inputId = search.dataset.rolePickerSearch;
      state.rolePickerSearch[inputId] = search.value;
      state.openRolePicker = inputId;
      renderRolePickerById(inputId);
      setTimeout(() => {
        const refreshed = document.querySelector(`[data-role-picker-search="${inputId}"]`);
        if (refreshed) {
          refreshed.focus();
          refreshed.setSelectionRange(refreshed.value.length, refreshed.value.length);
        }
      }, 0);
    });

    document.getElementById("ticketRecordSearch").addEventListener("input", event => {
      state.ticketRecordSearch = event.target.value;
      state.ticketRecordFilters.page = 1;
      debounceAction("ticket-record-search", () => {
        loadTicketRecordsLive().catch(error => {
          document.getElementById("ticketLiveStatus").textContent = error.message;
        });
      });
    });

    document.getElementById("ticketRecordStatusFilter").addEventListener("change", event => {
      state.ticketRecordFilters.status = event.target.value;
      state.ticketRecordFilters.page = 1;
      loadTicketRecordsLive().catch(error => {
        document.getElementById("ticketLiveStatus").textContent = error.message;
      });
    });

    document.getElementById("ticketRecordPageSize").addEventListener("change", event => {
      state.ticketRecordFilters.page_size = Number(event.target.value || 10);
      state.ticketRecordFilters.page = 1;
      loadTicketRecordsLive().catch(error => {
        document.getElementById("ticketLiveStatus").textContent = error.message;
      });
    });

    document.getElementById("ticketRecordsPrevPageButton").addEventListener("click", () => {
      if (state.ticketRecordFilters.page <= 1) return;
      state.ticketRecordFilters.page -= 1;
      loadTicketRecordsLive().catch(error => {
        document.getElementById("ticketLiveStatus").textContent = error.message;
      });
    });

    document.getElementById("ticketRecordsNextPageButton").addEventListener("click", () => {
      if (state.ticketRecordFilters.total_pages && state.ticketRecordFilters.page >= state.ticketRecordFilters.total_pages) return;
      state.ticketRecordFilters.page += 1;
      loadTicketRecordsLive().catch(error => {
        document.getElementById("ticketLiveStatus").textContent = error.message;
      });
    });

    document.getElementById("refreshTicketRecordsButton").addEventListener("click", () => {
      loadTicketRecordsLive().catch(error => {
        document.getElementById("ticketLiveStatus").textContent = error.message;
      });
    });

    document.getElementById("newTemplateButton").addEventListener("click", () => {
      const template = newPingTemplate();
      template.key = `plantilla-${Date.now().toString().slice(-4)}`;
      template.name = "Nueva plantilla";
      state.pingTemplates = [template, ...state.pingTemplates.filter(item => item.key !== template.key)];
      state.currentPingTemplateKey = template.key;
      localStorage.setItem("dashboardPingTemplateKey", state.currentPingTemplateKey);
      renderTemplates();
    });

    document.getElementById("saveTemplateButton").addEventListener("click", () => {
      savePingTemplate().catch(error => {
        document.getElementById("templateStatus").textContent = error.message;
      });
    });

    document.getElementById("deleteTemplateButton").addEventListener("click", () => {
      deletePingTemplate().catch(error => {
        document.getElementById("templateStatus").textContent = error.message;
      });
    });

    ["templateKey", "templateName", "templateTitle", "templateMention", "templateJoinCommand", "templateCallerSlot", "templateRoles", "templateSlotFormat", "templateContent", "templateLootLink", "templateReportEnabled"].forEach(id => {
      document.getElementById(id).addEventListener("input", () => {
        saveTemplateDraft();
        renderTemplatePreview();
      });
      document.getElementById(id).addEventListener("change", () => {
        saveTemplateDraft();
        renderTemplatePreview();
      });
    });

    document.getElementById("closeLiveTicketButton").addEventListener("click", () => {
      closeLiveTicket();
    });

    document.getElementById("ticketLiveForm").addEventListener("submit", event => {
      event.preventDefault();
      sendLiveTicketMessage().catch(error => {
        document.getElementById("ticketLiveMessageStatus").textContent = error.message;
      });
    });

    document.getElementById("createPanelButton").addEventListener("click", () => {
      persistCurrentTicketPanel();
      const panel = newTicketPanel("Nuevo panel");
      state.ticketPanels.push(panel);
      state.currentTicketPanelId = panel.id;
      state.ticketPanelsDirty = true;
      localStorage.setItem("dashboardTicketPanelId", panel.id);
      renderTickets();
    });

    document.getElementById("clonePanelButton").addEventListener("click", () => {
      persistCurrentTicketPanel();
      const panel = currentTicketPanel();
      if (!panel) return;
      const clone = JSON.parse(JSON.stringify(panel));
      clone.id = crypto.randomUUID ? crypto.randomUUID() : String(Date.now());
      clone.name = `${panel.name} copia`;
      clone.options = (clone.options || []).map(option => ({
        ...option,
        id: crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`
      }));
      state.ticketPanels.push(clone);
      state.currentTicketPanelId = clone.id;
      state.ticketPanelsDirty = true;
      localStorage.setItem("dashboardTicketPanelId", clone.id);
      renderTickets();
      document.getElementById("ticketStatus").textContent = "Panel clonado. Guarda la configuracion y envia este panel a Discord para que tenga numeracion propia.";
    });

    document.getElementById("deletePanelButton").addEventListener("click", () => {
      const panel = currentTicketPanel();
      if (!panel) return;
      state.ticketPanels = state.ticketPanels.filter(item => item.id !== panel.id);
      state.currentTicketPanelId = state.ticketPanels[0]?.id || "";
      state.ticketPanelsDirty = true;
      localStorage.setItem("dashboardTicketPanelId", state.currentTicketPanelId);
      renderTickets();
    });

    document.getElementById("addTicketOptionButton").addEventListener("click", () => {
      persistCurrentTicketPanel();
      const panel = currentTicketPanel();
      if (!panel) return;
      panel.options.push({
        id: crypto.randomUUID ? crypto.randomUUID() : String(Date.now()),
        emoji: "",
        label: `Opcion ${panel.options.length + 1}`,
        description: ""
      });
      state.ticketPanelsDirty = true;
      renderTickets();
    });

    document.getElementById("addTicketPermissionRoleButton").addEventListener("click", () => {
      persistCurrentTicketPanel();
      const panel = currentTicketPanel();
      if (!panel) return;
      panel.permissions = panel.permissions || {};
      const entries = Array.isArray(panel.permissions.ticket_role_permissions)
        ? panel.permissions.ticket_role_permissions
        : [];
      if (entries.length >= 20) {
        document.getElementById("ticketStatus").textContent = "Puedes configurar maximo 20 roles con permisos de canal.";
        return;
      }
      entries.push({
        role_id: "",
        permissions: ["view_channel", "read_message_history"]
      });
      panel.permissions.ticket_role_permissions = entries;
      state.ticketPanelsDirty = true;
      renderTicketRolePermissions(panel);
    });

    document.getElementById("savePanelButton").addEventListener("click", () => {
      saveTicketPanels().catch(error => {
        document.getElementById("ticketStatus").textContent = error.message;
      });
    });

    document.getElementById("publishPanelButton").addEventListener("click", () => {
      publishCurrentTicketPanel().catch(error => {
        document.getElementById("ticketStatus").textContent = error.message;
      });
    });

    document.getElementById("saveAuditConfigButton").addEventListener("click", () => {
      saveAuditConfig().catch(error => {
        document.getElementById("auditStatus").textContent = error.message;
      });
    });

    document.getElementById("auditSearch").addEventListener("input", event => {
      state.auditSearch = event.target.value;
      state.auditFilters.page = 1;
      debounceAction("audit-search", () => {
        loadAuditData({ force: true }).catch(showError);
      });
    });

    document.getElementById("auditTypeFilter").addEventListener("change", event => {
      state.auditFilters.record_type = event.target.value;
      state.auditFilters.page = 1;
      loadAuditData({ force: true }).catch(showError);
    });

    document.getElementById("auditPageSize").addEventListener("change", event => {
      state.auditFilters.page_size = Number(event.target.value || 12);
      state.auditFilters.page = 1;
      loadAuditData({ force: true }).catch(showError);
    });

    document.getElementById("auditPrevPageButton").addEventListener("click", () => {
      if (state.auditFilters.page <= 1) return;
      state.auditFilters.page -= 1;
      loadAuditData({ force: true }).catch(showError);
    });

    document.getElementById("auditNextPageButton").addEventListener("click", () => {
      if (state.auditFilters.total_pages && state.auditFilters.page >= state.auditFilters.total_pages) return;
      state.auditFilters.page += 1;
      loadAuditData({ force: true }).catch(showError);
    });

    document.getElementById("saveFineConfigButton").addEventListener("click", () => {
      saveFineConfig().catch(error => {
        document.getElementById("fineConfigStatus").textContent = error.message;
      });
    });

    document.getElementById("savePermissionsButton").addEventListener("click", () => {
      state.botPermissions = collectBotPermissions();
      saveBotPermissions().catch(error => {
        document.getElementById("permissionsStatus").textContent = error.message;
      });
    });

    document.getElementById("exportEconomyButton").addEventListener("click", () => {
      if (!state.guildId) return;
      window.location.href = `/api/export/economy?${new URLSearchParams({ guild_id: state.guildId }).toString()}`;
    });

    document.getElementById("exportTemplatesButton").addEventListener("click", () => {
      if (!state.guildId) return;
      window.location.href = `/api/export/templates?${new URLSearchParams({ guild_id: state.guildId }).toString()}`;
    });

    document.getElementById("exportTicketsButton").addEventListener("click", () => {
      if (!state.guildId) return;
      window.location.href = `/api/export/tickets?${new URLSearchParams({ guild_id: state.guildId }).toString()}`;
    });

    document.getElementById("saveAlbionRegistrationButton").addEventListener("click", () => {
      saveAlbionRegistration().catch(error => {
        document.getElementById("albionRegistrationStatus").textContent = error.message;
      });
    });

    document.getElementById("albionRegistrationSearch").addEventListener("input", event => {
      state.albionRegistrationSearch = event.target.value;
      state.albionRegistrationFilters.page = 1;
      debounceAction("albion-search", () => {
        loadAlbionRegistrationData({ force: true }).catch(error => {
          document.getElementById("albionRegistrationStatus").textContent = error.message;
        });
      });
    });

    document.getElementById("albionRegistrationStatusFilter").addEventListener("change", event => {
      state.albionRegistrationFilters.status = event.target.value;
      state.albionRegistrationFilters.page = 1;
      loadAlbionRegistrationData({ force: true }).catch(error => {
        document.getElementById("albionRegistrationStatus").textContent = error.message;
      });
    });

    document.getElementById("albionRegistrationPageSize").addEventListener("change", event => {
      state.albionRegistrationFilters.page_size = Number(event.target.value || 15);
      state.albionRegistrationFilters.page = 1;
      loadAlbionRegistrationData({ force: true }).catch(error => {
        document.getElementById("albionRegistrationStatus").textContent = error.message;
      });
    });

    document.getElementById("albionRegistrationPrevPageButton").addEventListener("click", () => {
      if (state.albionRegistrationFilters.page <= 1) return;
      state.albionRegistrationFilters.page -= 1;
      loadAlbionRegistrationData({ force: true }).catch(error => {
        document.getElementById("albionRegistrationStatus").textContent = error.message;
      });
    });

    document.getElementById("albionRegistrationNextPageButton").addEventListener("click", () => {
      if (state.albionRegistrationFilters.total_pages && state.albionRegistrationFilters.page >= state.albionRegistrationFilters.total_pages) return;
      state.albionRegistrationFilters.page += 1;
      loadAlbionRegistrationData({ force: true }).catch(error => {
        document.getElementById("albionRegistrationStatus").textContent = error.message;
      });
    });

    ["reportSplitMode", "reportEstimated", "reportItems", "reportSilver", "reportMapCost", "reportRepairCost", "reportCallerPercent", "reportLooterPayment", "reportLooterUser", "reportTabSalePercent"].forEach(id => {
      document.getElementById(id).addEventListener("input", renderReportCalculator);
      document.getElementById(id).addEventListener("change", renderReportCalculator);
    });

    document.getElementById("addReportFineButton").addEventListener("click", () => {
      appendReportFineRow();
      renderReportCalculator();
    });

    document.getElementById("reportCalculatorSelect").addEventListener("change", event => {
      const ava = event.target.value;
      if (!ava) {
        state.reportContext = null;
        state.reportCalculator = null;
        renderReportCalculator();
        return;
      }
      state.reportContext = {
        guildId: state.guildId,
        callerId: state.data?.viewer?.id || "",
        ava,
      };
      loadReportCalculator().catch(error => {
        document.getElementById("reportCalculatorStatus").textContent = error.message;
      });
    });

    document.getElementById("submitReportCalculatorButton").addEventListener("click", () => {
      submitReportCalculator().catch(error => {
        document.getElementById("reportCalculatorStatus").textContent = error.message;
      });
    });

    document.getElementById("resetReportCalculatorButton").addEventListener("click", resetReportCalculator);

    document.getElementById("refreshAlbionRegistrationButton").addEventListener("click", () => {
      state.albionRegistrationGuildId = "";
      loadAlbionRegistrationData({ force: true }).then(() => {
        renderAlbionRegistration();
        document.getElementById("albionRegistrationStatus").textContent = "Registro recargado.";
      }).catch(error => {
        document.getElementById("albionRegistrationStatus").textContent = error.message;
      });
    });

    document.getElementById("refreshPermissionsButton").addEventListener("click", () => {
      state.permissionsGuildId = "";
      loadPermissionsData({ force: true }).then(() => {
        document.getElementById("permissionsStatus").textContent = "Permisos recargados.";
        renderPermissions();
      }).catch(error => {
        document.getElementById("permissionsStatus").textContent = error.message;
      });
    });

    document.getElementById("permissionsGrid").addEventListener("change", event => {
      if (!event.target.matches("[data-permission-role]")) return;
      state.botPermissions = collectBotPermissions();
      document.getElementById("permissionsStatus").textContent = "Cambios sin guardar.";
      renderPermissions();
    });

    document.getElementById("permissionRoleSearch").addEventListener("input", event => {
      state.botPermissions = collectBotPermissions();
      state.permissionSearch = event.target.value;
      renderPermissions();
    });

    document.querySelectorAll(".tab").forEach(button => {
      button.addEventListener("click", () => {
        state.tab = button.dataset.tab;
        currentEconomyPageState().page = 1;
        render();
        loadEconomyData({ force: true }).catch(showError);
      });
    });

    function showError(error) {
      setSectionMessage(state.section, error.message);
      document.getElementById("status").textContent = error.message;
    }

    loadBootstrapData()
      .then(() => loadCurrentSectionData())
      .catch(showError);
    document.addEventListener("focusin", event => {
      if (event.target.matches("select, input, textarea, button")) state.userInteracting = true;
    });

    document.addEventListener("focusout", () => {
      setTimeout(() => {
        state.userInteracting = Boolean(document.activeElement?.matches("select, input, textarea, button"));
      }, 250);
    });

    setInterval(() => {
      if (state.userInteracting || state.section !== "economy") return;
      loadEconomyData({ force: true }).catch(showError);
    }, 3000);

    setInterval(() => {
      if (state.section !== "tickets") return;
      loadTicketRecordsLive().catch(error => {
        document.getElementById("ticketLiveStatus").textContent = error.message;
      });
      if (state.selectedLiveTicketId) {
        loadLiveTicketMessages().catch(error => {
          document.getElementById("ticketLiveMessageStatus").textContent = error.message;
        });
      }
    }, 5000);
