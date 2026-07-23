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
        sort: "newest",
        date_from: "",
        date_to: ""
      };
    }

    const savedSection = localStorage.getItem("dashboardSection") || "economy";
    const initialSection = savedSection === "ticket-records" ? "tickets" : savedSection;
    if (savedSection === "ticket-records") {
      localStorage.setItem("dashboardSection", "tickets");
    }
    const savedSidebarCollapsed = localStorage.getItem("dashboardSidebarCollapsed");
    const startsInMobileLayout = window.matchMedia?.("(max-width: 760px)")?.matches || false;

    const state = {
      data: null,
      section: linkedReportSection ? "report-calculator" : initialSection,
      sidebarCollapsed: startsInMobileLayout ? true : savedSidebarCollapsed === "1",
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
      selectedTicketTranscriptMessages: [],
      selectedTicketTranscriptRecord: null,
      selectedLiveTicketId: "",
      ticketLiveMessages: [],
      ticketLiveStatus: "",
      ticketFocusView: "",
      templateStatusMessage: "",
      auditCategories: [],
      auditConfig: { channels: {} },
      auditEvents: [],
      auditSearch: "",
      auditFilters: createPageState(12),
      botPermissions: {},
      botPermissionOptions: [],
      adminGuilds: [],
      adminOverview: null,
      adminElevation: null,
      adminElevationGuildId: "",
      adminElevationSubmitting: false,
      adminElevationUiMessage: "",
      adminMessageChannels: [],
      adminMessageChannelsCache: {},
      adminMessageChannelsStatus: "idle",
      adminMessageChannelsError: "",
      adminBotMessageRequestId: "",
      adminServerBackups: [],
      adminServerBackupsMax: 2,
      adminServerBackupsStatus: "idle",
      adminServerBackupsError: "",
      selectedAdminBackupId: "",
      selectedAdminBackupDetail: null,
      adminBackupReplaceMode: false,
      adminTemplateTargetGuildId: "",
      adminTemplateUpdateExisting: false,
      adminTemplateIncludeBotConfig: true,
      adminTemplateClearTarget: false,
      adminTemplatePreview: null,
      adminTemplateRequestId: "",
      adminTemplateStatus: "",
      albionRegistrationConfig: null,
      albionRegistrations: [],
      albionRegistrationSearch: "",
      albionRegistrationFilters: createPageState(15),
      reportCalculator: null,
      reportCalculatorOptions: [],
      reportFinalPreviewText: "",
      reportRequestId: "",
      reportSubmitting: false,
      chestTables: [],
      chestTable: null,
      chestTableStatus: "",
      chestTableDirty: false,
      chestTableLoading: false,
      reportBuildLoanProofReads: new Set(),
      reportContext: linkedReportSection ? {
        guildId: pageParams.get("guild_id") || "",
        callerId: pageParams.get("caller_id") || "",
        ava: pageParams.get("ava") || ""
      } : null,
      fineConfig: null,
      csrfToken: "",
      permissionSearch: "",
      permissionCategoryFilter: "",
      permissionStatusFilter: "",
      botPermissions: {},
      botSystemPermissions: {},
      botPermissionOptions: [],
      manageablePermissions: [],
      permissionReadOnlyRoleIds: [],
      canEditPermissions: false,
      loot: {
        data: null,
        fileName: "",
        format: "",
        loadToken: 0,
        pricing: null,
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
      adminPanelGuildId: "",
      albionRegistrationGuildId: "",
      reportCalculatorOptionsGuildId: "",
      chestTablesGuildId: "",
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
        ["member_status", "Estado"],
        ["updated_at_display", "Fecha"],
        ["__actions", "Acciones", "number"]
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
        ["reason", "Motivo"],
        ["player_status", "Estado"],
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
      ["\uD83D\uDDA5\uFE0F", "\uD83D\uDDA5\uFE0F"],
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
    const defaultTicketOwnerPermissions = [
      "view_channel",
      "send_messages",
      "read_message_history",
      "attach_files",
      "embed_links"
    ];
    const ownerPermissionGroups = [
      {
        title: "Acceso basico",
        description: "Lo minimo para que el usuario pueda entrar y seguir la conversacion.",
        keys: ["view_channel", "read_message_history", "send_messages"]
      },
      {
        title: "Contenido",
        description: "Permisos utiles para pruebas, imagenes, enlaces y reacciones.",
        keys: ["attach_files", "embed_links", "add_reactions", "use_external_emojis", "use_external_stickers"]
      },
      {
        title: "Avanzado",
        description: "Opciones sensibles que normalmente conviene dejar solo al staff.",
        keys: ["mention_everyone", "create_public_threads", "create_private_threads", "send_messages_in_threads", "use_application_commands"]
      },
      {
        title: "Gestion",
        description: "Permisos administrativos del canal y sus hilos.",
        keys: ["manage_messages", "manage_channels", "manage_threads"]
      }
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
            description: "Crear un ticket privado",
            ticket_open_content: "",
            ticket_open_title: "",
            ticket_open_description: "",
            ticket_open_color: "",
            ticket_open_footer: "",
            ticket_open_image_url: "",
            ticket_open_thumbnail_url: ""
          }
        ],
        permissions: {
          ticket_role_permissions: [],
          owner_permissions: [...defaultTicketOwnerPermissions],
          add_member_roles: "",
          add_member_user_ids: "",
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

    function formatDateTime(value) {
      const raw = String(value || "").trim();
      if (!raw) return "Sin fecha";
      const date = new Date(raw);
      if (Number.isNaN(date.getTime())) return raw;
      return date.toLocaleString("es-AR", {
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit"
      });
    }

    function formatDurationSeconds(value) {
      const seconds = Math.max(0, Number(value || 0));
      if (!Number.isFinite(seconds) || seconds <= 0) return "0 min";
      if (seconds < 60) return `${Math.ceil(seconds)} s`;
      const minutes = Math.floor(seconds / 60);
      const remainingSeconds = seconds % 60;
      return remainingSeconds ? `${minutes} min ${remainingSeconds} s` : `${minutes} min`;
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

    function lootVisibilityKey(playerName, item) {
      return lootItemKey(playerName, item.itemKey || item.itemId);
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

    function createLootItem(itemId, itemName, itemKey = "", quality = null) {
      return {
        itemKey: itemKey || itemId,
        itemId,
        itemName: itemName || itemId || "Objeto desconocido",
        tier: resolveLootTier(itemId),
        quality,
        totalQuantity: 0,
        price: null,
        priceAvailable: false,
        priceStatus: "pending",
        priceLocation: "",
        priceServer: "",
        priceQuality: quality || 1,
        priceUpdatedAt: "",
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
        lootMap[cleanPlayer][cleanItemId] = createLootItem(cleanItemId, itemName, cleanItemId);
      }
      const item = lootMap[cleanPlayer][cleanItemId];
      item.totalQuantity += numericQuantity;
      if (!item.priceAvailable && Number.isFinite(numericPrice) && numericPrice > 0) {
        item.price = numericPrice;
        item.priceAvailable = true;
      }
      if (Number.isFinite(numericPrice) && numericPrice > 0) item.totalPrice += numericPrice * numericQuantity;
    }

    function addPricedLootEntry(lootMap, playerName, itemRecord) {
      const cleanPlayer = String(playerName || "").trim();
      const cleanItemId = String(itemRecord.item_unique_name || itemRecord.item_id || "").trim();
      const quality = itemRecord.quality || itemRecord.price_quality || 1;
      const itemKey = `${cleanItemId}::q${quality}`;
      if (!cleanPlayer || !cleanItemId) return;
      if (!lootMap[cleanPlayer]) lootMap[cleanPlayer] = {};
      if (!lootMap[cleanPlayer][itemKey]) {
        lootMap[cleanPlayer][itemKey] = createLootItem(cleanItemId, itemRecord.item_name, itemKey, quality);
      }
      const item = lootMap[cleanPlayer][itemKey];
      item.totalQuantity += Number(itemRecord.quantity || 0);
      item.tier = itemRecord.tier ?? item.tier;
      item.quality = quality;
      item.price = itemRecord.price ?? null;
      item.priceAvailable = Boolean(itemRecord.price_available);
      item.priceStatus = itemRecord.price_status || (item.priceAvailable ? "priced" : "missing");
      item.priceLocation = itemRecord.price_location || "";
      item.priceServer = itemRecord.price_server || "";
      item.priceQuality = itemRecord.price_quality || quality;
      item.priceUpdatedAt = itemRecord.price_updated_at || "";
      item.totalPrice += Number(itemRecord.total_price || 0);
    }

    function lootPayloadToMap(loot) {
      const lootMap = {};
      (loot.players || []).forEach(player => {
        (player.items || []).forEach(item => addPricedLootEntry(lootMap, player.player_name, item));
      });
      return lootMap;
    }

    async function normalizeLootWithPrices({ content, format, fileName, refreshPrices = false, includePrices = true }) {
      const response = await fetch("/api/loot/normalize", {
        method: "POST",
        headers: csrfHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({
          guild_id: state.guildId,
          content,
          format,
          file_name: fileName,
          include_prices: includePrices,
          refresh_prices: refreshPrices
        })
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.error || "No pude procesar el loot.");
      return payload.loot || {};
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
      const key = lootVisibilityKey(playerName, item);
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
        state.loot.manualShows.has(lootVisibilityKey(playerName, item))
      ) ? "partial" : "none";
    }

    function clearLootTierOverrides(tier) {
      lootItemsForTier(tier).forEach(([playerName, item]) => {
        const key = lootVisibilityKey(playerName, item);
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
      const key = lootVisibilityKey(playerName, item);
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
      const noPrice = !item.priceAvailable;
      const priceLabel = item.priceStatus === "pending"
        ? "..."
        : (noPrice ? "N/A" : formatNumber(item.price));
      return `
        <div class="loot-item-wrap">
          <button class="loot-item${included ? "" : " excluded"}${noPrice ? " no-price" : ""}" type="button"
            data-loot-player="${escapeHtml(playerName)}" data-loot-item="${escapeHtml(item.itemKey)}"
            title="${escapeHtml(item.itemName)} - ${included ? "clic para excluir" : "clic para incluir"}">
            <img src="${escapeHtml(item.imageUrl)}" alt="${escapeHtml(item.itemName)}" loading="lazy">
            <span class="loot-quantity">${formatNumber(item.totalQuantity)}</span>
            <span class="loot-price">${escapeHtml(priceLabel)}</span>
          </button>
          <button class="loot-info" type="button" data-loot-detail-player="${escapeHtml(playerName)}"
            data-loot-detail-item="${escapeHtml(item.itemKey)}" aria-label="Ver detalles de ${escapeHtml(item.itemName)}">i</button>
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
            <span class="loot-player-total">${formatNumber(total)} silver</span>
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
      const pricing = state.loot.pricing || {};
      const pricingText = pricing.source === "deferred"
        ? "precios cargando"
        : `${pricing.priced_items || 0} con precio / ${pricing.unpriced_items || 0} sin precio`;
      document.getElementById("lootFileMeta").textContent =
        `${players.length} jugadores - ${itemKinds} objetos agrupados - ${state.loot.format.toUpperCase()} - ${pricingText}`;
      document.getElementById("lootGrandTotal").textContent = state.loot.format === "json"
        ? `${formatNumber(players.reduce((sum, [playerName, items]) => sum + Object.values(items).reduce((subtotal, item) => isLootItemIncluded(playerName, item) ? subtotal + item.totalPrice : subtotal, 0), 0))} silver total`
        : `${formatNumber(players.reduce((sum, [playerName, items]) => sum + Object.values(items).reduce((subtotal, item) => isLootItemIncluded(playerName, item) ? subtotal + item.totalPrice : subtotal, 0), 0))} silver total`;
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
      const noPrice = !item.priceAvailable;
      document.getElementById("lootModalPanel").innerHTML = `
        <button class="loot-modal-close" type="button" data-loot-modal-close aria-label="Cerrar">x</button>
        <div class="loot-modal-hero">
          <img src="${escapeHtml(item.imageUrl)}" alt="${escapeHtml(item.itemName)}">
          <div><h3 id="lootModalTitle">${escapeHtml(item.itemName)}</h3><p>${escapeHtml(playerName)}</p></div>
        </div>
        <div class="loot-detail-grid">
          <div class="loot-detail"><span>ID</span><strong>${escapeHtml(item.itemId)}</strong></div>
          <div class="loot-detail"><span>Tier</span><strong>${lootTierLabel(item.tier)}</strong></div>
          <div class="loot-detail"><span>Calidad</span><strong>${escapeHtml(item.priceQuality || item.quality || 1)}</strong></div>
          <div class="loot-detail"><span>Cantidad total</span><strong>${formatNumber(item.totalQuantity)}</strong></div>
          <div class="loot-detail"><span>Precio unitario</span><strong>${item.priceStatus === "pending" ? "Cargando" : (noPrice ? "N/A" : `${formatNumber(item.price)} silver`)}</strong></div>
          <div class="loot-detail"><span>Valor total</span><strong>${item.priceStatus === "pending" ? "Cargando" : (noPrice ? "N/A" : `${formatNumber(item.totalPrice)} silver`)}</strong></div>
          <div class="loot-detail"><span>Mercado</span><strong>${escapeHtml(item.priceLocation || "Sin precio")}</strong></div>
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
      const loadToken = Date.now();
      state.loot.loadToken = loadToken;
      const loot = await normalizeLootWithPrices({ content: text, format: extension, fileName: file.name, includePrices: false });
      const data = lootPayloadToMap(loot);
      if (!Object.keys(data).length) throw new Error("No se encontraron eventos de loot validos en el archivo.");
      state.loot.data = data;
      state.loot.fileName = file.name;
      state.loot.format = extension;
      state.loot.pricing = loot.pricing || null;
      resetLootVisibility();
      document.getElementById("lootError").hidden = true;
      renderLoot();
      normalizeLootWithPrices({ content: text, format: extension, fileName: file.name, includePrices: true })
        .then(pricedLoot => {
          if (state.loot.loadToken !== loadToken) return;
          state.loot.data = lootPayloadToMap(pricedLoot);
          state.loot.pricing = pricedLoot.pricing || null;
          renderLoot();
        })
        .catch(error => {
          if (state.loot.loadToken !== loadToken) return;
          const message = error.message || "No pude cargar precios de Albion Online Data.";
          state.loot.pricing = { ...(state.loot.pricing || {}), source: "error", errors: [message] };
          renderLoot();
        });
    }

    function clearLoot() {
      state.loot.data = null;
      state.loot.fileName = "";
      state.loot.format = "";
      state.loot.loadToken += 1;
      state.loot.pricing = null;
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
      if (field === "member_status" || field === "player_status") {
        if (lowered.includes("en servidor")) cls = "add";
        if (lowered.includes("fuera")) cls = "remove";
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
          if (field === "__actions") {
            return `<td class="${cls || ""}"><div class="row-actions"><button class="action-button economy-edit-balance" type="button" data-user-id="${escapeHtml(row.user_id || "")}" data-user-name="${escapeHtml(row.user_name || "")}" data-user-status="${escapeHtml(row.member_status || "")}">Editar</button></div></td>`;
          }
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
      } else if (section === "fines") {
        renderFines();
      } else if (section === "audit") {
        renderAudit();
      } else if (section === "permissions") {
        renderPermissions();
      } else if (section === "admin-panel") {
        renderAdminPanel();
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
      renderTicketTranscriptPreview();
      applyTicketFocusMode();
    }

    function renderFines() {
      renderFineConfig();
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
      const panel = currentTicketPanel();
      const hideTicketMessage = panel?.mode === "select";
      if (hideTicketMessage && state.ticketEditorSection === "ticketMessage") {
        state.ticketEditorSection = "options";
        localStorage.setItem("dashboardTicketEditorSection", state.ticketEditorSection);
      }
      document.querySelectorAll(".editor-tab").forEach(button => {
        if (button.dataset.editorSection === "ticketMessage") {
          button.hidden = hideTicketMessage;
        }
        button.classList.toggle("active", button.dataset.editorSection === state.ticketEditorSection);
      });
      document.querySelectorAll("[data-editor-panel]").forEach(panel => {
        panel.hidden = panel.dataset.editorPanel === "ticketMessage" && hideTicketMessage
          ? true
          : panel.dataset.editorPanel !== state.ticketEditorSection;
      });
    }

    function applyTicketFocusMode() {
      const dashboard = document.getElementById("ticketDashboardMain");
      if (!dashboard) return;
      dashboard.classList.toggle("ticket-focus-mode", Boolean(state.ticketFocusView));
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

    function systemPermissionValuesForRole(roleId) {
      const values = state.botSystemPermissions?.[String(roleId)] || [];
      return Array.isArray(values) ? values.map(String) : [];
    }

    function rolePermissionsAreReadOnly(roleId) {
      return (state.permissionReadOnlyRoleIds || []).map(String).includes(String(roleId));
    }

    function renderPermissions() {
      const grid = document.getElementById("permissionsGrid");
      const roles = state.ticketRoles || [];
      const options = state.botPermissionOptions || [];
      const search = String(state.permissionSearch || "").trim().toLowerCase();
      const categoryFilter = String(state.permissionCategoryFilter || "");
      const statusFilter = String(state.permissionStatusFilter || "");
      const categories = [];
      options.forEach(option => {
        const category = option.category || "Otros";
        if (!categories.includes(category)) categories.push(category);
      });
      let filteredOptions = categoryFilter
        ? options.filter(option => (option.category || "Otros") === categoryFilter)
        : options;
      const optionByKey = new Map(options.map(option => [String(option.key || ""), option]));
      const optionMatchesSearch = option => {
        if (!search) return false;
        return [
          option.key,
          option.label,
          option.description,
          option.category,
          option.scope
        ].some(value => String(value || "").toLowerCase().includes(search));
      };
      const searchMatchesPermission = Boolean(search) && options.some(optionMatchesSearch);
      if (searchMatchesPermission) {
        filteredOptions = filteredOptions.filter(optionMatchesSearch);
      }
      const roleMatchesStatus = role => {
        const values = permissionValuesForRole(role.id);
        const valueSet = new Set(values);
        if (statusFilter === "configured") return values.length > 0;
        if (statusFilter === "empty") return values.length === 0;
        if (statusFilter === "global") return valueSet.has("global");
        if (statusFilter === "editable") return state.canEditPermissions && !rolePermissionsAreReadOnly(role.id);
        if (statusFilter === "readonly") return rolePermissionsAreReadOnly(role.id);
        return true;
      };
      const roleMatchesSearch = role => {
        if (!search) return true;
        const roleFields = [role.name, role.id];
        if (roleFields.some(value => String(value || "").toLowerCase().includes(search))) return true;
        if (searchMatchesPermission) return true;
        return permissionValuesForRole(role.id).some(key => optionMatchesSearch(optionByKey.get(String(key)) || { key }));
      };
      const visibleRoles = roles.filter(role => roleMatchesStatus(role) && roleMatchesSearch(role));
      const configuredRoles = Object.values(state.botPermissions || {}).filter(values => Array.isArray(values) && values.length).length;
      const activeTotal = Object.values(state.botPermissions || {}).reduce((total, values) => total + (Array.isArray(values) ? values.length : 0), 0);

      document.getElementById("permissionRoleTotal").textContent = configuredRoles;
      document.getElementById("permissionActiveTotal").textContent = activeTotal;
      document.getElementById("permissionAvailableTotal").textContent = roles.length;
      document.getElementById("permissionRoleSearch").value = state.permissionSearch;
      document.getElementById("permissionCategoryFilter").innerHTML = `<option value="">Todas las categorias</option>${categories.map(category => (
        `<option value="${escapeHtml(category)}"${category === categoryFilter ? " selected" : ""}>${escapeHtml(category)}</option>`
      )).join("")}`;
      document.getElementById("permissionStatusFilter").value = statusFilter;

      if (!roles.length || !options.length) {
        grid.innerHTML = `<div class="ticket-empty-editor"><strong>Sin roles cargados</strong><p>Selecciona un servidor para cargar los roles disponibles.</p></div>`;
        return;
      }

      if (!visibleRoles.length) {
        grid.innerHTML = `<div class="ticket-empty-editor"><strong>No encontre resultados</strong><p>Prueba otro rol, ID, permiso, categoria o estado.</p></div>`;
        return;
      }

      if (!filteredOptions.length) {
        grid.innerHTML = `<div class="ticket-empty-editor"><strong>No encontre permisos</strong><p>Prueba otra categoria o termino de busqueda.</p></div>`;
        return;
      }

      grid.innerHTML = `
        <div class="permissions-results-summary">
          <span>${escapeHtml(visibleRoles.length)} de ${escapeHtml(roles.length)} roles visibles</span>
          <span>${escapeHtml(filteredOptions.length)} de ${escapeHtml(options.length)} permisos mostrados</span>
        </div>
        <div class="permissions-list permissions-list-stacked">
          ${visibleRoles.map(role => {
        const values = new Set(permissionValuesForRole(role.id));
        const systemValues = systemPermissionValuesForRole(role.id);
        const roleReadOnly = rolePermissionsAreReadOnly(role.id);
        const roleEditable = state.canEditPermissions && !roleReadOnly;
        return `
            <article class="permission-row permission-row-stacked" data-role-id="${escapeHtml(role.id)}">
              <div class="permission-role">
                <strong>@${escapeHtml(role.name)}</strong>
                <span class="muted">${escapeHtml(role.id)}</span>
                ${roleReadOnly ? `<span class="muted">No puedes editar un rol que ya posees.</span>` : ""}
                ${systemValues.length ? `<span class="muted">Este rol conserva permisos del sistema no editables.</span>` : ""}
              </div>
              <div class="permission-groups">
                ${categories.map(category => {
                  if (categoryFilter && category !== categoryFilter) return "";
                  const categoryOptions = filteredOptions.filter(option => (option.category || "Otros") === category);
                  if (!categoryOptions.length) return "";
                  return `
                    <section class="permission-group">
                      <div class="permission-group-head">
                        <strong>${escapeHtml(category)}</strong>
                        <span>${escapeHtml(categoryOptions.length)} permiso${categoryOptions.length === 1 ? "" : "s"}</span>
                      </div>
                      <div class="permission-group-options">
                        ${categoryOptions.map(option => {
                          const checked = values.has(option.key) ? " checked" : "";
                          const disabled = !roleEditable || !option.editable ? " disabled" : "";
                          const active = values.has(option.key) ? " active" : "";
                          return `
                            <label class="permission-pill${active}" title="${escapeHtml(option.description)}">
                              <input type="checkbox" data-permission-role="${escapeHtml(role.id)}" data-permission-key="${escapeHtml(option.key)}"${checked}${disabled}>
                              <span>${escapeHtml(option.label)}</span>
                            </label>
                          `;
                        }).join("")}
                      </div>
                    </section>
                  `;
                }).join("")}
              </div>
            </article>
        `;
          }).join("")}
        </div>
      `;
    }

    function renderAdminPanel() {
      const hasElevationStatus = Boolean(state.adminElevation);
      const elevation = state.adminElevation || {};
      const overview = state.adminOverview || {};
      const server = overview.server || {};
      const bot = overview.bot || {};
      const actions = overview.future_actions || [];
      const botStatus = bot.status === "connected" ? "Conectado" : "Fuera del servidor";
      const memberCount = server.member_count == null ? "No disponible" : formatNumber(server.member_count);
      const optionalCount = value => value == null ? "No disponible" : formatNumber(value);
      const elevationForm = document.getElementById("adminElevationForm");
      const elevationMessage = document.getElementById("adminElevationMessage");
      const elevationMeta = document.getElementById("adminElevationMeta");
      const elevationPassword = document.getElementById("adminElevationPassword");
      const elevationSubmit = document.getElementById("adminElevationSubmit");
      const elevationLogoutButton = document.getElementById("adminElevationLogoutButton");
      const workspaceShell = document.getElementById("adminPanelWorkspaceShell");
      const elevated = Boolean(elevation.elevated);
      const uiMessage = state.adminElevationUiMessage || elevation.message || (hasElevationStatus ? "" : "Validando acceso reforzado...");

      if (elevationForm) elevationForm.hidden = elevated;
      if (elevationMessage) elevationMessage.textContent = uiMessage;
      if (elevationPassword && elevated) elevationPassword.value = "";
      if (elevationSubmit) {
        elevationSubmit.disabled = state.adminElevationSubmitting || !state.guildId || elevated;
        elevationSubmit.textContent = state.adminElevationSubmitting ? "Validando..." : "Desbloquear panel";
      }
      if (elevationLogoutButton) elevationLogoutButton.hidden = !elevated;
      if (elevationMeta) {
        if (elevated && elevation.expiresAt) {
          elevationMeta.textContent = `Acceso elevado activo hasta ${formatDateTime(elevation.expiresAt)}.`;
        } else if (Number(elevation.retryAfterSeconds || 0) > 0) {
          elevationMeta.textContent = `Bloqueado temporalmente. Reintenta en ${formatDurationSeconds(elevation.retryAfterSeconds)}.`;
        } else if (elevation.expired) {
          elevationMeta.textContent = "La sesion elevada anterior vencio. Ingresa la clave secundaria otra vez.";
        } else if (hasElevationStatus && !elevation.configReady) {
          elevationMeta.textContent = "Hace falta completar la configuracion segura del panel administrativo en el entorno.";
        } else if (!hasElevationStatus) {
          elevationMeta.textContent = "Validando si ya existe una sesion elevada activa para este panel.";
        } else {
          elevationMeta.textContent = "La elevacion dura pocos minutos y protege todos los endpoints administrativos.";
        }
      }
      if (workspaceShell) workspaceShell.hidden = !elevated || !state.adminOverview;

      if (!elevated || !state.adminOverview) {
        document.getElementById("adminGuildList").innerHTML = `<div class="empty">Desbloquea el panel para cargar servidores administrables.</div>`;
        document.getElementById("adminServerName").textContent = "-";
        document.getElementById("adminServerId").textContent = "-";
        document.getElementById("adminBotStatus").textContent = "-";
        document.getElementById("adminMemberCount").textContent = "-";
        document.getElementById("adminChannelCount").textContent = "0";
        document.getElementById("adminRoleCount").textContent = "0";
        document.getElementById("adminServerDetails").innerHTML = `<div class="empty">El resumen administrativo se cargara despues de validar la clave secundaria.</div>`;
        document.getElementById("adminFutureActions").innerHTML = "";
        document.getElementById("adminPanelStatus").textContent = uiMessage;
        return;
      }

      document.getElementById("adminGuildList").innerHTML = state.adminGuilds.length
        ? state.adminGuilds.map(guild => {
          const active = String(guild.id || "") === String(state.guildId || "");
          const connected = guild.bot?.status === "connected";
          const icon = guild.icon_url
            ? `<img src="${escapeHtml(guild.icon_url)}" alt="">`
            : `<span>${initialForName(guild.name || "S")}</span>`;
          return `
            <button class="admin-guild-card${active ? " active" : ""}" type="button" data-admin-guild-id="${escapeHtml(guild.id || "")}">
              <span class="admin-guild-icon">${icon}</span>
              <span class="admin-guild-main">
                <strong>${escapeHtml(guild.name || `Servidor ${guild.id || ""}`)}</strong>
                <span>${escapeHtml(guild.id || "")}</span>
              </span>
              <span class="admin-guild-meta">
                <span class="pill">${connected ? "Conectado" : "Sin conexion"}</span>
                <span>${optionalCount(guild.channel_count)} canales</span>
                <span>${optionalCount(guild.role_count)} roles</span>
                <span>${guild.has_saved_config ? "Config guardada" : "Sin config"}</span>
              </span>
            </button>
          `;
        }).join("")
        : `<div class="empty">No hay servidores administrables disponibles.</div>`;

      document.getElementById("adminServerName").textContent = server.name || "-";
      document.getElementById("adminServerId").textContent = server.id || "-";
      document.getElementById("adminBotStatus").textContent = botStatus;
      document.getElementById("adminMemberCount").textContent = memberCount;
      document.getElementById("adminChannelCount").textContent = optionalCount(server.channel_count);
      document.getElementById("adminRoleCount").textContent = optionalCount(server.role_count);
      document.getElementById("adminServerDetails").innerHTML = [
        ["Nombre", server.name || "-"],
        ["ID", server.id || "-"],
        ["Miembros", memberCount],
        ["Canales", optionalCount(server.channel_count)],
        ["Roles", optionalCount(server.role_count)],
        ["Bot presente", server.bot_present ? "Si" : "No"],
        ["Metadata", bot.metadata_available ? "Disponible" : "Limitada"],
        ["Configuracion", server.has_saved_config ? "Guardada" : "Sin registros"]
      ].map(([label, value]) => `
        <div class="admin-detail">
          <span>${escapeHtml(label)}</span>
          <strong>${escapeHtml(value)}</strong>
        </div>
      `).join("");
      renderAdminServerBackups();
      renderAdminServerTemplate();
      document.getElementById("adminFutureActions").innerHTML = actions.map(action => `
        <article class="admin-action-card">
          <div>
            <strong>${escapeHtml(action.label || action.key || "Accion futura")}</strong>
            <span>${escapeHtml(action.description || "")}</span>
          </div>
          <span class="pill">${escapeHtml(action.status === "planned" ? "Preparado" : action.status || "Pendiente")}</span>
        </article>
      `).join("");
      document.getElementById("adminPanelStatus").textContent = state.adminElevationUiMessage || "";
      renderAdminBotMessageForm();
    }

    function renderAdminServerBackups() {
      const list = document.getElementById("adminServerBackupsList");
      const detail = document.getElementById("adminServerBackupDetail");
      const statusElement = document.getElementById("adminServerBackupsStatus");
      if (!list || !detail || !statusElement) return;

      const backups = state.adminServerBackups || [];
      const maxBackups = state.adminServerBackupsMax || 2;
      const status = state.adminServerBackupsStatus || "idle";
      const error = state.adminServerBackupsError || "";
      const createButton = document.getElementById("adminCreateBackupButton");
      createButton.disabled = !state.guildId || status === "loading";
      createButton.textContent = state.adminBackupReplaceMode ? "Cancelar reemplazo" : "Crear backup";
      statusElement.textContent = status === "loading"
        ? "Cargando backups..."
        : error || (state.adminBackupReplaceMode
          ? "Elige que backup quieres reemplazar."
          : `${backups.length} / ${maxBackups} backups guardados.`);

      if (!backups.length) {
        list.innerHTML = `<div class="empty">No hay backups guardados para este servidor.</div>`;
      } else {
        list.innerHTML = backups.map((backup, index) => {
          const active = String(backup.id || "") === String(state.selectedAdminBackupId || "");
          const label = `Backup ${index + 1}`;
          const createdAt = formatDateTime(backup.created_at);
          return `
            <article class="admin-action-card${active ? " active" : ""}">
              <div>
                <strong>${escapeHtml(label)}</strong>
                <span>Creado: ${escapeHtml(createdAt)}</span>
              </div>
              <div class="ticket-actions">
                <button class="action-button" type="button" data-admin-backup-id="${escapeHtml(backup.id || "")}" data-admin-backup-label="${escapeHtml(label)}">Ver detalle</button>
                ${state.adminBackupReplaceMode ? `<button class="action-button danger" type="button" data-admin-replace-backup-id="${escapeHtml(backup.id || "")}" data-admin-backup-label="${escapeHtml(label)}">Reemplazar este</button>` : ""}
              </div>
            </article>
          `;
        }).join("");
      }

      if (state.selectedAdminBackupDetail) {
        detail.hidden = false;
        detail.innerHTML = renderAdminBackupPreview(state.selectedAdminBackupDetail);
      } else {
        detail.hidden = true;
        detail.innerHTML = "";
      }
    }

    function renderAdminBackupPreview(detail) {
      const backup = detail.backup || {};
      const guild = backup.guild || {};
      const summary = detail.summary || {};
      const roles = backup.roles || [];
      const categories = backup.categories || [];
      const channels = backup.channels || [];
      const config = backup.bot_config || {};
      const categoryById = new Map(categories.map(category => [String(category.original_id || category.id || ""), category]));
      const channelsByCategory = channels.reduce((acc, channel) => {
        const parentId = String(channel.parent_id || "");
        if (!acc[parentId]) acc[parentId] = [];
        acc[parentId].push(channel);
        return acc;
      }, {});
      const rolePreview = roles
        .filter(role => role.name !== "@everyone")
        .slice(0, 10)
        .map(role => `
          <span class="admin-preview-chip">
            <span class="role-color-dot" style="background:${role.color ? `#${Number(role.color).toString(16).padStart(6, "0")}` : "#94a3b8"}"></span>
            ${escapeHtml(role.name || role.original_id || "")}
          </span>
        `).join("") || `<span class="muted">Sin roles personalizados.</span>`;

      const categoryPreview = categories.slice(0, 8).map(category => {
        const categoryId = String(category.original_id || category.id || "");
        const childChannels = channelsByCategory[categoryId] || [];
        return `
          <article class="admin-preview-group">
            <strong>${escapeHtml(category.name || "Categoria")}</strong>
            <div class="admin-preview-channel-list">
              ${childChannels.length ? childChannels.slice(0, 10).map(renderAdminBackupChannelRow).join("") : `<span class="muted">Sin canales en esta categoria.</span>`}
            </div>
          </article>
        `;
      }).join("");
      const uncategorized = (channelsByCategory[""] || []).slice(0, 10).map(renderAdminBackupChannelRow).join("");
      const configKeys = Object.keys(config.guild_config || {});
      const permissionRoles = Object.keys(config.role_permissions || {});

      return `
        <div class="admin-preview">
          <div class="admin-preview-heading">
            <div>
              <strong>${escapeHtml(guild.name || detail.guild_name || "Servidor")}</strong>
              <span>ID original: ${escapeHtml(guild.original_id || detail.guild_id || "")}</span>
              <span>Creado: ${escapeHtml(formatDateTime(detail.created_at))}</span>
            </div>
            <span class="pill">Version ${escapeHtml(backup.schema_version || detail.schema_version || 1)}</span>
          </div>
          <div class="admin-preview-stats">
            <div><span>Roles</span><strong>${escapeHtml(summary.roles || roles.length || 0)}</strong></div>
            <div><span>Categorias</span><strong>${escapeHtml(summary.categories || categories.length || 0)}</strong></div>
            <div><span>Canales</span><strong>${escapeHtml(summary.channels || channels.length || 0)}</strong></div>
            <div><span>Overwrites</span><strong>${escapeHtml(summary.permission_overwrites || 0)}</strong></div>
          </div>
          <section class="admin-preview-section">
            <strong>Roles</strong>
            <div class="admin-preview-chip-list">${rolePreview}</div>
          </section>
          <section class="admin-preview-section">
            <strong>Estructura de canales</strong>
            ${categoryPreview || `<div class="muted">Sin categorias guardadas.</div>`}
            ${uncategorized ? `<article class="admin-preview-group"><strong>Sin categoria</strong><div class="admin-preview-channel-list">${uncategorized}</div></article>` : ""}
          </section>
          <section class="admin-preview-section">
            <strong>Configuracion del bot</strong>
            <div class="admin-preview-config">
              <span>${escapeHtml(configKeys.length)} claves de configuracion</span>
              <span>${escapeHtml(permissionRoles.length)} roles con permisos del bot</span>
            </div>
          </section>
        </div>
      `;

      function renderAdminBackupChannelRow(channel) {
        const overwrites = (channel.permission_overwrites || []).length;
        const parent = categoryById.get(String(channel.parent_id || ""));
        const typeLabel = {
          text: "#",
          announcement: "#",
          voice: "Voz",
          stage_voice: "Stage",
          forum: "Foro",
          media: "Media",
        }[channel.type] || channel.type || "Canal";
        return `
          <div class="admin-preview-channel">
            <span>${escapeHtml(typeLabel)} ${escapeHtml(channel.name || channel.original_id || "")}</span>
            <small>${parent ? escapeHtml(parent.name || "") : "Sin categoria"} · ${escapeHtml(overwrites)} permisos</small>
          </div>
        `;
      }
    }

    function renderAdminServerTemplate() {
      const backupSelect = document.getElementById("adminTemplateBackup");
      const targetSelect = document.getElementById("adminTemplateTargetGuild");
      const previewPanel = document.getElementById("adminTemplatePreview");
      const applyButton = document.getElementById("adminTemplateApplyButton");
      const status = document.getElementById("adminTemplateStatus");
      if (!backupSelect || !targetSelect || !previewPanel || !applyButton || !status) return;

      const selectedBackup = backupSelect.value || state.selectedAdminBackupId || "";
      backupSelect.innerHTML = `<option value="">Seleccionar backup</option>${(state.adminServerBackups || []).map((backup, index) => {
        const selected = String(backup.id || "") === String(selectedBackup) ? " selected" : "";
        return `<option value="${escapeHtml(backup.id || "")}"${selected}>Backup ${index + 1} - ${escapeHtml(formatDateTime(backup.created_at))}</option>`;
      }).join("")}`;
      if (selectedBackup) backupSelect.value = selectedBackup;

      const selectedTarget = state.adminTemplateTargetGuildId || targetSelect.value || "";
      targetSelect.innerHTML = `<option value="">Seleccionar destino</option>${(state.adminGuilds || []).map(guild => {
        const isCurrentGuild = String(guild.id || "") === String(state.guildId || "");
        const selected = String(guild.id || "") === String(selectedTarget) ? " selected" : "";
        const label = `${guild.name || guild.id || ""}${isCurrentGuild ? " (mismo servidor)" : ""}`;
        return `<option value="${escapeHtml(guild.id || "")}"${selected}>${escapeHtml(label)}</option>`;
      }).join("")}`;
      if (selectedTarget) targetSelect.value = selectedTarget;

      document.getElementById("adminTemplateUpdateExisting").checked = Boolean(state.adminTemplateUpdateExisting);
      document.getElementById("adminTemplateIncludeBotConfig").checked = state.adminTemplateIncludeBotConfig !== false;
      document.getElementById("adminTemplateClearTarget").checked = Boolean(state.adminTemplateClearTarget);
      status.textContent = state.adminTemplateStatus || "";

      const confirmation = document.getElementById("adminTemplateConfirmation").value.trim().toUpperCase();
      const preview = state.adminTemplatePreview?.preview || state.adminTemplatePreview || null;
      applyButton.disabled = !preview || confirmation !== "APLICAR" || preview.bot_permissions_ok === false;
      if (!preview) {
        previewPanel.hidden = true;
        previewPanel.innerHTML = "";
        return;
      }
      previewPanel.hidden = false;
      previewPanel.innerHTML = renderAdminTemplatePreview(preview);
    }

    function renderAdminTemplatePreview(preview) {
      const count = key => (preview[key] || []).length;
      const overwrite = preview.permission_overwrites || {};
      const warnings = preview.warnings || [];
      const isSameGuild = String(preview.source?.guild_id || "") === String(preview.target?.guild_id || "");
      const conflictCount = [
        ...(preview.roles_to_create || []),
        ...(preview.categories_to_create || []),
        ...(preview.channels_to_create || []),
        ...(preview.roles_to_update || []),
        ...(preview.categories_to_update || []),
        ...(preview.channels_to_update || []),
        ...(preview.roles_to_map || []),
        ...(preview.categories_to_map || []),
        ...(preview.channels_to_map || [])
      ].filter(item => item.conflict).length;
      const mappedCount = (preview.roles_to_map || []).length + (preview.categories_to_map || []).length + (preview.channels_to_map || []).length;
      const sampleList = (items, empty) => {
        const list = (items || []).slice(0, 8);
        if (!list.length) return `<span class="muted">${escapeHtml(empty)}</span>`;
        return list.map(item => `<span class="admin-preview-chip">${escapeHtml(item.name || "")}${item.target_name && item.target_name !== item.name ? ` -> ${escapeHtml(item.target_name)}` : ""}${item.type ? ` - ${escapeHtml(item.type)}` : ""}</span>`).join("");
      };
      return `
        <div class="admin-preview-stats">
          <div><span>Roles nuevos</span><strong>${escapeHtml(count("roles_to_create"))}</strong></div>
          <div><span>Categorias nuevas</span><strong>${escapeHtml(count("categories_to_create"))}</strong></div>
          <div><span>Canales nuevos</span><strong>${escapeHtml(count("channels_to_create"))}</strong></div>
          <div><span>Overwrites</span><strong>${escapeHtml(overwrite.total || 0)}</strong></div>
          <div><span>Mapeados</span><strong>${escapeHtml(mappedCount)}</strong></div>
          <div><span>Conflictos</span><strong>${escapeHtml(conflictCount)}</strong></div>
        </div>
        ${preview.bot_permissions_ok === false ? `<div class="status error">El bot no tiene permisos suficientes en destino.</div>` : ""}
        ${isSameGuild ? `<div class="status">El destino es el mismo servidor del backup. Sin limpieza se reutilizaran elementos existentes; con limpieza se reconstruira la estructura desde la copia.</div>` : ""}
        ${warnings.length ? `<div class="status">${warnings.map(escapeHtml).join(" ")}</div>` : ""}
        <div class="admin-preview-chip-list">${sampleList(preview.roles_to_create, "Sin roles nuevos.")}</div>
        <div class="admin-preview-chip-list">${sampleList([...(preview.categories_to_create || []), ...(preview.channels_to_create || [])], "Sin canales nuevos.")}</div>
        ${mappedCount ? `<div class="admin-preview-chip-list">${sampleList([...(preview.roles_to_map || []), ...(preview.categories_to_map || []), ...(preview.channels_to_map || [])], "Sin elementos mapeados.")}</div>` : ""}
        <div class="admin-preview-config">
          <span>${escapeHtml(overwrite.role_overwrites || 0)} overwrites de roles</span>
          <span>${escapeHtml(overwrite.member_overwrites_skipped || 0)} overwrites de miembros omitidos</span>
          <span>${preview.bot_config?.enabled ? escapeHtml(preview.bot_config.guild_config_keys || 0) : 0} claves de config</span>
        </div>
      `;
    }

    function renderAdminBotMessageForm() {
      const channels = state.adminMessageChannels || [];
      const channelSelect = document.getElementById("adminBotMessageChannel");
      const submitButton = document.getElementById("adminBotMessageSubmit");
      const status = state.adminMessageChannelsStatus || "idle";
      const currentChannel = channelSelect.value || "";
      let placeholder = "Seleccionar canal";
      if (status === "loading") placeholder = "Cargando canales...";
      else if (status === "error") placeholder = "No pude cargar canales";
      else if (status === "loaded" && !channels.length) placeholder = "No hay canales permitidos";

      channelSelect.innerHTML = `<option value="">${escapeHtml(placeholder)}</option>` + channels.map(channel => {
        const selected = String(channel.id || "") === String(currentChannel) ? " selected" : "";
        const notes = [];
        if (!channel.can_read_history) notes.push("sin historial");
        if (!channel.can_manage_messages) notes.push("sin gestionar");
        const suffix = notes.length ? ` - ${notes.join(", ")}` : "";
        return `<option value="${escapeHtml(channel.id || "")}"${selected}>#${escapeHtml(channel.name || channel.id || "")}${suffix}</option>`;
      }).join("");
      if (currentChannel && channels.some(channel => String(channel.id || "") === String(currentChannel))) {
        channelSelect.value = currentChannel;
      }
      channelSelect.disabled = status === "loading" || status === "error" || !channels.length;
      submitButton.disabled = status !== "loaded" || !channels.length;

      if (status === "loading") {
        document.getElementById("adminBotMessageStatus").textContent = "Cargando canales permitidos...";
      } else if (status === "error") {
        document.getElementById("adminBotMessageStatus").textContent = state.adminMessageChannelsError || "No pude cargar los canales. Reintenta.";
      } else if (status === "loaded" && !channels.length) {
        document.getElementById("adminBotMessageStatus").textContent = "No hay canales donde el bot pueda ver y enviar mensajes.";
      } else if (status === "loaded") {
        document.getElementById("adminBotMessageStatus").textContent = "";
      }
      updateAdminBotMessageMode();
    }

    function updateAdminBotMessageMode() {
      const action = document.getElementById("adminBotMessageAction").value;
      const needsMessageId = action === "edit" || action === "delete";
      const needsContent = action === "send" || action === "edit";
      document.getElementById("adminBotMessageIdField").hidden = !needsMessageId;
      document.getElementById("adminBotMessageContentField").hidden = !needsContent;
      document.getElementById("adminBotMessageId").required = needsMessageId;
      document.getElementById("adminBotMessageContent").required = needsContent;
      if (action === "edit") scheduleLoadAdminBotMessageForEdit();
      updateAdminBotMessageCounter();
    }

    function updateAdminBotMessageCounter() {
      const content = document.getElementById("adminBotMessageContent").value || "";
      document.getElementById("adminBotMessageCounter").textContent = `${content.length} / 2000`;
    }

    function scheduleLoadAdminBotMessageForEdit() {
      window.clearTimeout(state.debounceTimers.adminBotMessageLoad);
      state.debounceTimers.adminBotMessageLoad = window.setTimeout(() => {
        loadAdminBotMessageForEdit().catch(error => {
          document.getElementById("adminBotMessageStatus").textContent = error.message;
        });
      }, 450);
    }

    async function loadAdminBotMessageForEdit() {
      if (document.getElementById("adminBotMessageAction").value !== "edit") return;
      const channelId = document.getElementById("adminBotMessageChannel").value;
      const messageId = document.getElementById("adminBotMessageId").value.trim();
      if (!state.guildId || !channelId || !messageId) return;
      if (!/^\d+$/.test(messageId)) return;

      const loadKey = `${state.guildId}:${channelId}:${messageId}`;
      state.adminBotMessageLoadKey = loadKey;
      document.getElementById("adminBotMessageStatus").textContent = "Cargando mensaje actual...";
      const params = new URLSearchParams({
        guild_id: state.guildId,
        channel_id: channelId,
        message_id: messageId
      });
      const response = await fetch(`/api/admin/bot-message?${params.toString()}`, { cache: "no-store" });
      const payload = await readJsonResponse(response);
      if (!response.ok) throw new Error(payload.error || "No pude cargar el mensaje.");
      if (state.adminBotMessageLoadKey !== loadKey) return;

      const message = payload.message || {};
      document.getElementById("adminBotMessageContent").value = message.content || "";
      updateAdminBotMessageCounter();
      document.getElementById("adminBotMessageStatus").textContent = "Mensaje actual cargado. Edita el contenido y envia la solicitud.";
    }

    function collectBotPermissions() {
      const permissions = Object.fromEntries(
        Object.entries(state.botPermissions || {}).map(([roleId, values]) => [
          String(roleId),
          Array.isArray(values) ? values.map(String) : []
        ])
      );
      const roleIds = (state.ticketRoles || []).map(role => String(role.id || "")).filter(Boolean);
      const renderedPermissionKeysByRole = {};
      document.querySelectorAll(".permission-row").forEach(row => {
        const roleId = String(row.dataset.roleId || "");
        if (!roleId) return;
        renderedPermissionKeysByRole[roleId] = new Set(
          Array.from(row.querySelectorAll("[data-permission-role]"))
            .map(input => String(input.dataset.permissionKey || ""))
            .filter(Boolean)
        );
        permissions[roleId] = (permissions[roleId] || [])
          .filter(key => !renderedPermissionKeysByRole[roleId].has(String(key)));
      });
      document.querySelectorAll("[data-permission-role]").forEach(input => {
        if (!input.checked) return;
        const roleId = String(input.dataset.permissionRole || "");
        const key = String(input.dataset.permissionKey || "");
        if (!roleId || !key) return;
        permissions[roleId] = permissions[roleId] || [];
        if (!permissions[roleId].includes(key)) permissions[roleId].push(key);
      });

      return { permissions, roleIds };
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
      renderTicketRecordTypeFilter(records);
      document.getElementById("ticketRecordPageSize").value = String(state.ticketRecordFilters.page_size || 10);
      renderTicketRecordSort();
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
        const recordId = record.record_id || record.channel_id || record.number || "";
        const panelName = record.panel_name || (record.ticket_type === "fine" ? "Multa" : "");
        const ticketName = `Ticket${panelName ? ` ${panelName}` : ""}`;
        const hasTranscript = Boolean(record.has_transcript || record.transcribed_at || (Array.isArray(record.transcript) && record.transcript.length));
        const fine = record.fine || {};
        const metadata = [
          ["ID", record.number || record.record_id || record.channel_id || "Sin ID"],
          ["Ticket", ticketName],
          ["Canal", record.channel_name || record.channel_id || "Sin canal"],
          ["Usuario", record.user_name || record.owner_name || record.user_id || record.owner_id || "Desconocido"],
          record.ticket_type === "fine" && (fine.amount || record.amount) ? ["Monto", String(fine.amount || record.amount)] : null,
          record.ticket_type === "fine" && (fine.reason || record.reason) ? ["Motivo", fine.reason || record.reason] : null,
          record.ticket_type === "fine" && (fine.status || record.fine_status) ? ["Estado multa", fine.status || record.fine_status] : null,
          record.ticket_type === "fine" && (fine.report_ava || record.report_ava) ? ["Reporte", fine.report_ava || record.report_ava] : null,
          record.option_label ? ["Opcion", record.option_label] : null,
          record.created_at ? ["Creado", record.created_at] : null,
          record.claimed_by_name ? ["Reclamado por", record.claimed_by_name] : null,
          record.closed_at ? ["Cerrado", record.closed_at] : null,
          record.deleted_at ? ["Eliminado", record.deleted_at] : null,
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
              <button class="action-button export-ticket-record-button" type="button" data-record-id="${escapeHtml(recordId)}" title="Exportar ticket" aria-label="Exportar ticket"${hasTranscript ? "" : " disabled"}>Exportar</button>
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
          previewTicketTranscript(button.dataset.recordId).catch(error => {
            document.getElementById("ticketStatus").textContent = error.message;
          });
        });
      });

      list.querySelectorAll(".export-ticket-record-button").forEach(button => {
        button.addEventListener("click", () => {
          exportTicketRecord(button.dataset.recordId).catch(error => {
            document.getElementById("ticketStatus").textContent = error.message;
          });
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

    function ticketRecordTypeOptions(records) {
      const options = new Map();
      for (const panel of state.ticketPanels || []) {
        if (!panel?.id || !panel?.name) continue;
        options.set(`panel:${panel.id}`, `Ticket de ${panel.name}`);
      }
      for (const record of records || []) {
        if (record.ticket_type === "fine") {
          options.set("fine", "Ticket de Multa");
          continue;
        }
        const panelId = String(record.panel_id || "").trim();
        const panelName = String(record.panel_name || "").trim();
        if (panelId && panelId !== "__fine__" && panelName) {
          options.set(`panel:${panelId}`, `Ticket de ${panelName}`);
        }
      }
      options.set("fine", options.get("fine") || "Ticket de Multa");
      return [...options.entries()].sort(([, left], [, right]) => left.localeCompare(right, "es"));
    }

    function renderTicketRecordTypeFilter(records) {
      const select = document.getElementById("ticketRecordTypeFilter");
      const current = state.ticketRecordFilters.record_type || "";
      const options = ticketRecordTypeOptions(records);
      select.innerHTML = `<option value="">Todos los tickets</option>${options.map(([value, label]) =>
        `<option value="${escapeHtml(value)}"${current === value ? " selected" : ""}>${escapeHtml(label)}</option>`
      ).join("")}`;
      if (current && !options.some(([value]) => value === current)) {
        select.insertAdjacentHTML("beforeend", `<option value="${escapeHtml(current)}" selected>Filtro actual</option>`);
      }
    }

    function renderTicketRecordSort() {
      const sort = state.ticketRecordFilters.sort === "oldest" ? "oldest" : "newest";
      const button = document.getElementById("ticketRecordSortButton");
      document.getElementById("ticketRecordSortIcon").textContent = sort === "oldest" ? "↑" : "↓";
      document.getElementById("ticketRecordSortLabel").textContent = sort === "oldest" ? "Mas viejos" : "Mas recientes";
      button.setAttribute("aria-pressed", String(sort === "oldest"));
      button.title = sort === "oldest" ? "Orden actual: mas viejos primero" : "Orden actual: mas recientes primero";
    }

    async function previewTicketTranscript(recordId) {
      const params = new URLSearchParams({
        guild_id: state.guildId,
        record_id: recordId
      });
      const response = await fetch(`/api/ticket-transcript?${params.toString()}`, { cache: "no-store" });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "No pude cargar la transcripcion.");
      state.selectedTicketRecordId = String(recordId || "");
      state.selectedTicketTranscriptRecord = payload.record || null;
      state.selectedTicketTranscriptMessages = payload.messages || [];
      state.selectedLiveTicketId = "";
      state.ticketLiveMessages = [];
      state.ticketLiveStatus = "";
      state.ticketFocusView = "transcript";
      document.getElementById("ticketStatus").textContent = `${payload.message_count || 0} mensajes cargados.`;
      renderTickets();
    }

    function renderTicketTranscriptPreview() {
      const preview = document.getElementById("ticketTranscriptPreview");
      if (!preview) return;
      const record = state.selectedTicketTranscriptRecord;
      const messages = state.selectedTicketTranscriptMessages || [];
      const open = state.ticketFocusView === "transcript" && Boolean(record);
      preview.hidden = !open;
      if (!open) return;
      document.getElementById("ticketTranscriptPreviewTitle").textContent = record.channel_name || `Ticket ${record.number || record.record_id || ""}`;
      const panelName = record.panel_name || (record.ticket_type === "fine" ? "Multa" : "");
      const ticketName = `Ticket${panelName ? ` ${panelName}` : ""}`;
      const fine = record.fine || {};
      const fineDetail = record.ticket_type === "fine" && (fine.amount || fine.reason)
        ? ` - ${fine.amount ? `Monto ${fine.amount}` : "Multa"}${fine.reason ? ` - ${fine.reason}` : ""}`
        : "";
      document.getElementById("ticketTranscriptPreviewSubtitle").textContent =
        `${ticketName} - ${record.user_name || record.user_id || "Usuario desconocido"}${fineDetail} - ${messages.length} mensajes`;
      document.getElementById("ticketTranscriptPreviewMessages").innerHTML = messages.length
        ? messages.map(renderTranscriptMessage).join("")
        : `<div class="transcript-message"><div></div><div class="muted">La transcripcion no tiene mensajes guardados.</div></div>`;
    }

    function openTicketTranscript(recordId) {
      const params = new URLSearchParams({
        guild_id: state.guildId,
        record_id: recordId
      });
      window.location.href = `/ticket-transcript?${params.toString()}`;
    }

    async function exportTicketRecord(recordId) {
      const params = new URLSearchParams({
        guild_id: state.guildId,
        record_id: recordId
      });
      const response = await fetch(`/api/export/ticket?${params.toString()}`, { cache: "no-store" });
      if (!response.ok) {
        let message = "No pude exportar este ticket.";
        try {
          const payload = await response.json();
          message = payload.error || message;
        } catch (error) {
          message = await response.text() || message;
        }
        throw new Error(message);
      }

      const blob = await response.blob();
      const disposition = response.headers.get("Content-Disposition") || "";
      const filenameMatch = disposition.match(/filename="([^"]+)"/i);
      const filename = filenameMatch ? filenameMatch[1] : `ticket_${recordId || "export"}.json`;
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      document.getElementById("ticketStatus").textContent = "Ticket exportado.";
    }

    async function deleteTicketRecord(recordId, channelId, recordName) {
      const confirmed = window.confirm(
        `Eliminar ${recordName || "este ticket"}? En tickets de multa se aplicara borrado logico y se conservara la transcripcion.`
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
      document.getElementById("ticketStatus").textContent = "Registro del ticket actualizado.";
      renderTickets();
    }

    function liveTicketRecord() {
      return (state.ticketRecords || []).find(record => String(record.channel_id || "") === String(state.selectedLiveTicketId || ""));
    }

    async function openLiveTicket(channelId) {
      state.selectedLiveTicketId = String(channelId || "");
      state.ticketLiveMessages = [];
      state.ticketLiveStatus = "Cargando mensajes...";
      state.selectedTicketRecordId = "";
      state.selectedTicketTranscriptRecord = null;
      state.selectedTicketTranscriptMessages = [];
      state.ticketFocusView = "live";
      renderTickets();
      await loadLiveTicketMessages();
    }

    function closeLiveTicket() {
      state.selectedLiveTicketId = "";
      state.ticketLiveMessages = [];
      state.ticketLiveStatus = "";
      state.ticketFocusView = "";
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
        headers: csrfHeaders({ "Content-Type": "application/json" }),
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
      const record = liveTicketRecord();
      const open = state.ticketFocusView === "live" && Boolean(state.selectedLiveTicketId && record && String(record.status || "open").toLowerCase() === "open");
      viewer.hidden = !open;
      if (!open) return;

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

    function userIdValues(value) {
      const source = Array.isArray(value) ? value.join(",") : String(value || "");
      return source.split(/[\s,]+/).map(item => item.trim()).filter(item => /^\d+$/.test(item));
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

    function normalizeTicketPermissionValues(values, fallback = []) {
      if (!Array.isArray(values)) return [...fallback];
      const allowed = new Set(ticketChannelPermissionOptions.map(([key]) => key));
      return values.map(String).filter(value => allowed.has(value));
    }

    function ticketPermissionOpenIndexes() {
      return new Set(
        Array.from(document.querySelectorAll("[data-ticket-permission-index]"))
          .filter(row => row.querySelector(".ticket-permission-details")?.open)
          .map(row => Number(row.dataset.ticketPermissionIndex))
      );
    }

    function renderTicketOwnerPermissions(panel) {
      const container = document.getElementById("ticketOwnerPermissions");
      if (!container) return;
      const selected = new Set(normalizeTicketPermissionValues(
        panel?.permissions?.owner_permissions,
        defaultTicketOwnerPermissions
      ));
      const optionByKey = new Map(ticketChannelPermissionOptions);
      const selectedCount = ticketChannelPermissionOptions.filter(([key]) => selected.has(key)).length;
      container.innerHTML = `
        <div class="owner-permission-toolbar">
          <span class="owner-permission-count">${selectedCount} activos</span>
          <span class="owner-permission-note">Se aplican al creador y a personas agregadas mientras el ticket esta abierto.</span>
          <button class="owner-permission-reset" type="button" data-owner-permission-defaults>Restaurar base</button>
        </div>
        <div class="owner-permission-groups">
          ${ownerPermissionGroups.map(group => `
            <section class="owner-permission-group">
              <div class="owner-permission-group-head">
                <strong>${escapeHtml(group.title)}</strong>
                <span>${escapeHtml(group.description)}</span>
              </div>
              <div class="owner-permission-options-row">
                ${group.keys.map(key => `
                  <label class="owner-permission-option${selected.has(key) ? " active" : ""}">
                    <input class="ticket-owner-permission-checkbox" type="checkbox" value="${escapeHtml(key)}"${selected.has(key) ? " checked" : ""}>
                    <span>${escapeHtml(optionByKey.get(key) || key)}</span>
                  </label>
                `).join("")}
              </div>
            </section>
          `).join("")}
        </div>
      `;
      container.querySelectorAll(".ticket-owner-permission-checkbox").forEach(input => {
        input.addEventListener("change", () => {
          const current = currentTicketPanel();
          if (!current) return;
          current.permissions = current.permissions || {};
          current.permissions.owner_permissions = collectTicketOwnerPermissions();
          input.closest(".owner-permission-option")?.classList.toggle("active", input.checked);
          persistCurrentTicketPanel();
          renderTicketOwnerPermissions(current);
        });
      });
      container.querySelector("[data-owner-permission-defaults]")?.addEventListener("click", () => {
        const current = currentTicketPanel();
        if (!current) return;
        current.permissions = current.permissions || {};
        current.permissions.owner_permissions = [...defaultTicketOwnerPermissions];
        persistCurrentTicketPanel();
        renderTicketOwnerPermissions(current);
      });
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
      const openIndexes = ticketPermissionOpenIndexes();
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
            <details class="ticket-permission-details"${openIndexes.has(index) ? " open" : ""}>
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

    function collectTicketOwnerPermissions() {
      return normalizeTicketPermissionValues(
        Array.from(document.querySelectorAll(".ticket-owner-permission-checkbox:checked")).map(input => input.value),
        []
      );
    }

    function renderAllRolePickers(panel) {
      renderRoleSelect("addMemberRoles", panel.permissions?.add_member_roles || []);
      renderRoleSelect("claimRoles", panel.permissions?.claim_roles || []);
      renderRoleSelect("closeRoles", panel.permissions?.close_roles || []);
      renderRoleSelect("reopenRoles", panel.permissions?.reopen_roles || []);
      renderRoleSelect("deleteRoles", panel.permissions?.delete_roles || []);
    }

    function renderRolePickerById(inputId) {
      const panel = currentTicketPanel();
      if (!panel) return;
      const map = {
        addMemberRoles: "add_member_roles",
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
      ["ticketName", "ticketMode", "ticketChannel", "ticketOpenCategory", "ticketColor", "ticketContent", "ticketTitle", "ticketFooter", "ticketDescription", "ticketImage", "ticketOpenContent", "ticketOpenTitle", "ticketOpenColor", "ticketOpenDescription", "ticketOpenFooter", "ticketOpenImage", "ticketOpenThumbnail", "addMemberRoles", "addMemberUserIds", "claimRoles", "closeRoles", "reopenRoles", "deleteRoles"].forEach(id => {
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
        document.getElementById("ticketOwnerPermissions").innerHTML = "";
        document.getElementById("addMemberUserIds").value = "";
        ["addMemberRoles", "claimRoles", "closeRoles", "reopenRoles", "deleteRoles"].forEach(id => {
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
      document.getElementById("addMemberUserIds").value = userIdValues(panel.permissions?.add_member_user_ids || []).join(", ");
      renderTicketRolePermissions(panel);
      renderTicketOwnerPermissions(panel);
      renderAllRolePickers(panel);
      renderTicketOptions(panel);
      renderTicketPreview(panel);
      renderTicketOpenPreview(panel);
    }

    function renderTicketOptions(panel) {
      const container = document.getElementById("ticketOptions");
      const emojiOptions = buildEmojiOptions();
      container.innerHTML = (panel.options || []).map((option, index) => `
        <article class="ticket-option-card" data-option-index="${index}">
          <div class="option-row">
            <select class="ticket-option-emoji">${emojiOptions(option.emoji || "")}</select>
            <input class="ticket-option-label" type="text" placeholder="Nombre de opcion" value="${escapeHtml(option.label || "")}">
            <input class="ticket-option-description" type="text" placeholder="Descripcion" value="${escapeHtml(option.description || "")}">
            <button class="icon-button remove-ticket-option" type="button" title="Quitar opcion" aria-label="Quitar opcion">x</button>
          </div>
          <details class="ticket-option-message-details">
            <summary>Mensaje propio de esta opcion</summary>
            <div class="ticket-option-message-grid">
              <div class="field full">
                <label>Mensaje arriba del embed</label>
                <textarea class="ticket-option-open-content" placeholder="Vacio: usa el mensaje general del panel.">${escapeHtml(option.ticket_open_content || "")}</textarea>
              </div>
              <div class="field">
                <label>Titulo del embed</label>
                <input class="ticket-option-open-title" type="text" placeholder="Vacio: usa el general" value="${escapeHtml(option.ticket_open_title || "")}">
              </div>
              <div class="field">
                <label>Color del embed</label>
                <input class="ticket-option-open-color" type="text" placeholder="#38bdf8" value="${escapeHtml(option.ticket_open_color || "")}">
              </div>
              <div class="field full">
                <label>Contenido del embed</label>
                <textarea class="ticket-option-open-description" placeholder="Vacio: usa el contenido general.">${escapeHtml(option.ticket_open_description || "")}</textarea>
              </div>
              <div class="field full">
                <label>Footer del embed</label>
                <input class="ticket-option-open-footer" type="text" placeholder="Vacio: usa el general" value="${escapeHtml(option.ticket_open_footer || "")}">
              </div>
              <div class="field">
                <label>Imagen grande URL</label>
                <input class="ticket-option-open-image" type="url" placeholder="https://..." value="${escapeHtml(option.ticket_open_image_url || "")}">
              </div>
              <div class="field">
                <label>Miniatura URL</label>
                <input class="ticket-option-open-thumbnail" type="url" placeholder="https://..." value="${escapeHtml(option.ticket_open_thumbnail_url || "")}">
              </div>
            </div>
          </details>
        </article>
      `).join("");

      container.querySelectorAll("input, select, textarea").forEach(input => {
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
          const card = event.target.closest("[data-option-index]");
          const index = Number(card?.dataset.optionIndex);
          const current = currentTicketPanel();
          if (!current || !Number.isFinite(index) || current.options.length <= 1) return;
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
      return Array.from(document.querySelectorAll("[data-option-index]")).map(row => ({
        id: currentTicketPanel()?.options?.[Number(row.dataset.optionIndex)]?.id || (crypto.randomUUID ? crypto.randomUUID() : String(Date.now())),
        emoji: row.querySelector(".ticket-option-emoji").value.trim(),
        label: row.querySelector(".ticket-option-label").value.trim() || "Abrir ticket",
        description: row.querySelector(".ticket-option-description").value.trim(),
        ticket_open_content: row.querySelector(".ticket-option-open-content")?.value || "",
        ticket_open_title: row.querySelector(".ticket-option-open-title")?.value.trim() || "",
        ticket_open_description: row.querySelector(".ticket-option-open-description")?.value || "",
        ticket_open_color: row.querySelector(".ticket-option-open-color")?.value.trim() || "",
        ticket_open_footer: row.querySelector(".ticket-option-open-footer")?.value.trim() || "",
        ticket_open_image_url: row.querySelector(".ticket-option-open-image")?.value.trim() || "",
        ticket_open_thumbnail_url: row.querySelector(".ticket-option-open-thumbnail")?.value.trim() || ""
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
        owner_permissions: collectTicketOwnerPermissions(),
        add_member_roles: rolePickerValues("addMemberRoles"),
        add_member_user_ids: userIdValues(document.getElementById("addMemberUserIds").value).slice(0, 10),
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
        showMapCost: mode !== "items",
        showRepairCost: true,
        showTabSale: mode === "items" || mode === "items_silver",
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
      setReportFieldVisible("reportMapCostField", config.showMapCost);
      setReportFieldVisible("reportRepairCostField", config.showRepairCost);
      setReportFieldVisible("reportCallerPercentField", config.showBothExtras);
      setReportFieldVisible("reportLooterPaymentField", config.showBothExtras);
      const looterPayment = config.showBothExtras ? parseReportAmount(document.getElementById("reportLooterPayment").value) : 0;
      setReportFieldVisible("reportLooterUserField", config.showBothExtras && looterPayment > 0);
      setReportFieldVisible("reportTabSaleField", config.showTabSale);
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

    function reportSplitExclusions() {
      return Array.isArray(state.reportCalculator?.split_exclusions)
        ? state.reportCalculator.split_exclusions
        : [];
    }

    function syncReportSplitExclusions(participants) {
      if (!state.reportCalculator) return [];
      const participantIds = new Set(participants.map(participant => String(participant.user_id)));
      const seen = new Set();
      const exclusions = reportSplitExclusions().filter(exclusion => {
        const userId = String(exclusion?.user_id || "");
        if (!userId || seen.has(userId) || !participantIds.has(userId)) return false;
        seen.add(userId);
        return true;
      }).map(exclusion => ({
        ...exclusion,
        user_id: String(exclusion.user_id),
        activity_percentage: String(exclusion.activity_percentage || ""),
      }));
      state.reportCalculator.split_exclusions = exclusions;
      return exclusions;
    }

    function findReportSplitExclusion(userId) {
      return reportSplitExclusions().find(exclusion => String(exclusion.user_id) === String(userId)) || null;
    }

    function reportExclusionDiscount(exclusion) {
      const rawPercentage = String(exclusion?.activity_percentage || "").trim();
      return rawPercentage ? parseReportPercentage(rawPercentage) : 100;
    }

    function reportParticipantSplitWeight(participant) {
      const exclusion = findReportSplitExclusion(participant?.user_id);
      if (!exclusion) return 1;
      return Math.max(0, (100 - reportExclusionDiscount(exclusion)) / 100);
    }

    function reportSplitModifierRows() {
      return [...document.querySelectorAll(".report-modifier-row")];
    }

    function reportModifierSignedAmount(modifier) {
      const amount = parseReportAmount(modifier.amount);
      return modifier.operation === "add" ? amount : -amount;
    }

    function collectReportSplitModifiers() {
      return reportSplitModifierRows().map(row => {
        const targetType = row.querySelector(".report-modifier-target").value;
        const userSelect = row.querySelector(".report-modifier-user");
        const selectedOption = userSelect.options[userSelect.selectedIndex];
        return {
          name: row.querySelector(".report-modifier-name").value.trim(),
          operation: row.querySelector(".report-modifier-operation").value,
          amount: row.querySelector(".report-modifier-amount").value.trim(),
          description: row.querySelector(".report-modifier-description").value.trim(),
          target_type: targetType,
          user_id: targetType === "player" ? userSelect.value : "",
          user_name: targetType === "player" ? (selectedOption?.textContent?.split(" - ")[0] || "") : "",
          slot: targetType === "player" ? (selectedOption?.textContent?.split(" - ").slice(1).join(" - ") || "") : "",
        };
      }).filter(modifier => {
        const amountText = String(modifier.amount || "").trim();
        return modifier.name && /\d/.test(amountText) && !amountText.startsWith("-") && parseReportAmount(amountText) >= 0;
      });
    }

    function syncReportModifierParticipantOptions(participants) {
      document.querySelectorAll(".report-modifier-user").forEach(select => {
        const previous = select.value;
        select.innerHTML = reportParticipantOptionsMarkup(participants, previous);
      });
    }

    function reportBuildLoanRows() {
      return [...document.querySelectorAll(".report-build-loan-row")];
    }

    const reportBuildLoanMethods = [
      ["split", "Descontar del split"],
      ["balance", "Descontar del balance"],
      ["paid_now", "Pago al momento"],
    ];

    function reportBuildLoanMethodOptions(selectedValue = "split") {
      const selected = selectedValue || "split";
      return reportBuildLoanMethods.map(([value, label]) => (
        `<option value="${escapeHtml(value)}"${value === selected ? " selected" : ""}>${escapeHtml(label)}</option>`
      )).join("");
    }

    function collectReportBuildLoanDiscounts({ includeProof = false } = {}) {
      return reportBuildLoanRows().map(row => {
        const userSelect = row.querySelector(".report-build-loan-user");
        const selectedOption = userSelect.options[userSelect.selectedIndex];
        const proofInput = row.querySelector(".report-build-loan-proof");
        const discount = {
          user_id: userSelect.value,
          user_name: selectedOption?.textContent?.split(" - ")[0] || "",
          slot: selectedOption?.textContent?.split(" - ").slice(1).join(" - ") || "",
          amount: row.querySelector(".report-build-loan-amount").value.trim(),
          collection_method: row.querySelector(".report-build-loan-method").value,
          reason: row.querySelector(".report-build-loan-reason").value.trim(),
          proof_name: proofInput?.dataset.proofName || "",
        };
        if (includeProof) discount.proof_data_url = proofInput?.dataset.proofDataUrl || "";
        return discount;
      }).filter(discount => {
        const amountText = String(discount.amount || "").trim();
        if (!discount.user_id || !discount.reason) return false;
        if (discount.collection_method === "paid_now") {
          return !amountText || (!amountText.startsWith("-") && parseReportAmount(amountText) >= 0);
        }
        return /\d/.test(amountText) && !amountText.startsWith("-") && parseReportAmount(amountText) > 0;
      });
    }

    function syncReportBuildLoanParticipantOptions(participants) {
      document.querySelectorAll(".report-build-loan-user").forEach(select => {
        const previous = select.value;
        select.innerHTML = reportParticipantOptionsMarkup(participants, previous);
      });
    }

    function bindReportBuildLoanRow(row) {
      row.querySelectorAll("select, input").forEach(element => {
        if (element.matches(".report-build-loan-proof")) return;
        const handleBuildLoanChange = () => {
          setReportCopyStatus();
          renderReportCalculator();
        };
        element.addEventListener("input", handleBuildLoanChange);
        element.addEventListener("change", handleBuildLoanChange);
      });
      row.querySelector(".report-build-loan-remove").addEventListener("click", () => {
        row.remove();
        setReportCopyStatus();
        renderReportCalculator();
      });
      row.querySelector(".report-build-loan-proof").addEventListener("change", async event => {
        const file = event.target.files?.[0];
        const label = row.querySelector(".report-build-loan-proof-name");
        if (!file) {
          event.target.dataset.proofDataUrl = "";
          event.target.dataset.proofName = "";
          label.textContent = "";
          return;
        }
        const proofRead = (async () => {
          event.target.dataset.proofDataUrl = await fileToDataUrl(file);
          event.target.dataset.proofName = file.name;
          label.textContent = file.name;
          setReportCopyStatus();
        })();
        state.reportBuildLoanProofReads.add(proofRead);
        try {
          await proofRead;
        } catch (error) {
          event.target.value = "";
          event.target.dataset.proofDataUrl = "";
          event.target.dataset.proofName = "";
          label.textContent = error.message;
        } finally {
          state.reportBuildLoanProofReads.delete(proofRead);
        }
      });
    }

    function appendReportBuildLoanRow(discount = {}) {
      const container = document.getElementById("reportBuildLoansList");
      const participants = state.reportCalculator?.participants || [];
      const row = document.createElement("div");
      const collectionMethod = discount.collection_method || "split";
      row.className = "report-build-loan-row";
      row.innerHTML = `
        <div class="field report-build-loan-user-field">
          <label>Jugador</label>
          <select class="report-build-loan-user">${reportParticipantOptionsMarkup(participants, discount.user_id || "")}</select>
        </div>
        <div class="field report-build-loan-amount-field">
          <label>Monto</label>
          <input class="report-build-loan-amount" type="text" inputmode="decimal" maxlength="50" placeholder="Ej: 500k" value="${escapeHtml(discount.amount || "")}">
        </div>
        <div class="field report-build-loan-method-field">
          <label>Cobro</label>
          <select class="report-build-loan-method">${reportBuildLoanMethodOptions(collectionMethod)}</select>
        </div>
        <div class="field report-build-loan-reason-field">
          <label>Motivo</label>
          <input class="report-build-loan-reason" type="text" maxlength="300" placeholder="Ej: préstamo build healer" value="${escapeHtml(discount.reason || "")}">
        </div>
        <div class="field report-build-loan-proof-field">
          <label>Imagen</label>
          <input class="report-build-loan-proof" type="file" accept="image/*">
          <div class="report-build-loan-proof-name report-fine-proof-name">${escapeHtml(discount.proof_name || "")}</div>
        </div>
        <button class="action-button danger report-build-loan-remove" type="button">Quitar</button>
      `;
      const proofInput = row.querySelector(".report-build-loan-proof");
      if (discount.proof_data_url) proofInput.dataset.proofDataUrl = discount.proof_data_url;
      if (discount.proof_name) proofInput.dataset.proofName = discount.proof_name;
      bindReportBuildLoanRow(row);
      container.appendChild(row);
    }

    function bindReportModifierRow(row) {
      const renderTargetVisibility = () => {
        const targetType = row.querySelector(".report-modifier-target").value;
        row.querySelector(".report-modifier-user-field").hidden = targetType !== "player";
      };
      row.querySelectorAll("select, input").forEach(element => {
        const handleModifierChange = () => {
          renderTargetVisibility();
          setReportCopyStatus();
          renderReportCalculator();
        };
        element.addEventListener("input", handleModifierChange);
        element.addEventListener("change", handleModifierChange);
      });
      row.querySelector(".report-modifier-remove").addEventListener("click", () => {
        row.remove();
        setReportCopyStatus();
        renderReportCalculator();
      });
      renderTargetVisibility();
    }

    function appendReportModifierRow(modifier = {}) {
      const container = document.getElementById("reportModifiersList");
      const participants = state.reportCalculator?.participants || [];
      const row = document.createElement("div");
      const operation = modifier.operation === "subtract" ? "subtract" : "add";
      const targetType = modifier.target_type === "player" ? "player" : "total";
      row.className = "report-modifier-row";
      row.innerHTML = `
        <div class="field">
          <label>Concepto</label>
          <input class="report-modifier-name" type="text" maxlength="120" placeholder="Ej: Compra de sets" value="${escapeHtml(modifier.name || "")}">
        </div>
        <div class="field">
          <label>Operacion</label>
          <select class="report-modifier-operation">
            <option value="add"${operation === "add" ? " selected" : ""}>Suma</option>
            <option value="subtract"${operation === "subtract" ? " selected" : ""}>Resta</option>
          </select>
        </div>
        <div class="field">
          <label>Monto</label>
          <input class="report-modifier-amount" type="text" inputmode="decimal" maxlength="50" placeholder="Ej: 100k" value="${escapeHtml(modifier.amount || "")}">
        </div>
        <div class="field">
          <label>Afecta a</label>
          <select class="report-modifier-target">
            <option value="total"${targetType === "total" ? " selected" : ""}>Total general</option>
            <option value="player"${targetType === "player" ? " selected" : ""}>Jugador</option>
          </select>
        </div>
        <div class="field report-modifier-user-field">
          <label>Jugador</label>
          <select class="report-modifier-user">${reportParticipantOptionsMarkup(participants, modifier.user_id || "")}</select>
        </div>
        <div class="field report-modifier-description-field">
          <label>Descripcion</label>
          <input class="report-modifier-description" type="text" maxlength="300" placeholder="Detalle opcional" value="${escapeHtml(modifier.description || "")}">
        </div>
        <button class="action-button danger report-modifier-remove" type="button">Quitar</button>
      `;
      bindReportModifierRow(row);
      container.appendChild(row);
    }

    function setReportSplitExclusion(participant, reason = "", activityPercentage = "") {
      if (!state.reportCalculator || !participant) return;
      const userId = String(participant.user_id || "");
      const exclusions = reportSplitExclusions().filter(exclusion => String(exclusion.user_id) !== userId);
      exclusions.push({
        user_id: userId,
        user_name: participant.display_name || participant.user_id || "",
        slot: participant.slot || "",
        reason: String(reason || "").trim(),
        activity_percentage: String(activityPercentage || "").trim(),
      });
      state.reportCalculator.split_exclusions = exclusions;
    }

    function removeReportSplitExclusion(userId) {
      if (!state.reportCalculator) return;
      state.reportCalculator.split_exclusions = reportSplitExclusions()
        .filter(exclusion => String(exclusion.user_id) !== String(userId));
    }

    function syncReportFineParticipantOptions(participants) {
      document.querySelectorAll(".report-fine-user").forEach(select => {
        const previous = select.value;
        select.innerHTML = reportParticipantOptionsMarkup(participants, previous);
      });
    }

    function manualReportParticipantCount() {
      const value = Number.parseInt(document.getElementById("reportManualParticipants").value, 10);
      if (!Number.isFinite(value)) return 0;
      return Math.max(0, Math.min(value, 200));
    }

    function manualReportTitle() {
      return document.getElementById("reportManualTitle").value.trim() || "Actividad manual";
    }

    function manualReportParticipants() {
      return Array.from({ length: manualReportParticipantCount() }, (_, index) => {
        const number = index + 1;
        return {
          index: number,
          slot: "Participante",
          user_id: String(-number),
          display_name: `Participante ${number}`,
        };
      });
    }

    function createManualReportCalculator() {
      const viewer = state.data?.viewer || {};
      return {
        guild_id: state.guildId || state.reportContext?.guildId || "",
        caller_id: viewer.id || "",
        numero_ava: "",
        title: manualReportTitle(),
        caller_name: viewer.global_name || viewer.username || "",
        finalized: true,
        cancelled: false,
        report_sent: false,
        report_generated: false,
        report_rejected: false,
        manual: true,
        participants: manualReportParticipants(),
      };
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
        const handleFineChange = () => {
          setReportCopyStatus();
          renderReportCalculator();
        };
        element.addEventListener("input", handleFineChange);
        element.addEventListener("change", handleFineChange);
      });
      row.querySelector(".report-fine-remove").addEventListener("click", () => {
        row.remove();
        setReportCopyStatus();
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

    function collectReportFines({ includeProof = true } = {}) {
      return [...document.querySelectorAll(".report-fine-row")].map(row => {
        const userSelect = row.querySelector(".report-fine-user");
        const selectedOption = userSelect.options[userSelect.selectedIndex];
        const proofInput = row.querySelector(".report-fine-proof");
        const fine = {
          user_id: userSelect.value,
          user_name: selectedOption?.textContent?.split(" - ")[0] || "",
          slot: selectedOption?.textContent?.split(" - ").slice(1).join(" - ") || "",
          amount: row.querySelector(".report-fine-amount").value,
          reason: row.querySelector(".report-fine-reason").value,
          proof_name: proofInput.dataset.proofName || "",
        };
        if (includeProof) fine.proof_data_url = proofInput.dataset.proofDataUrl || "";
        return fine;
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
      const currentCallerId = state.reportContext?.callerId || "";
      if (!state.reportCalculatorOptions.length) {
        state.reportContext = { guildId: state.guildId, callerId: state.data.viewer.id, ava: "__manual__" };
        state.reportCalculator = createManualReportCalculator();
        return;
      }
      const selected = state.reportCalculatorOptions.find(item => (
        item.numero_ava === currentAva
        && (!currentCallerId || String(item.caller_id || "") === String(currentCallerId))
      )) || state.reportCalculatorOptions.find(item => item.numero_ava === currentAva) || state.reportCalculatorOptions[0];
      state.reportContext = {
        guildId: state.guildId,
        callerId: selected.caller_id || state.data.viewer.id,
        ava: selected.numero_ava,
      };
    }

    function renderReportCalculatorOptions() {
      const select = document.getElementById("reportCalculatorSelect");
      const options = state.reportCalculatorOptions || [];
      const currentAva = state.reportContext?.ava || "";
      const currentCallerId = state.reportContext?.callerId || "";
      const currentKey = currentAva === "__manual__" || !currentAva ? "__manual__" : `${currentCallerId}:${currentAva}`;
      select.innerHTML = `<option value="__manual__"${currentKey === "__manual__" ? " selected" : ""}>Calculadora manual</option>` + options.map(option => {
        const optionKey = `${option.caller_id || ""}:${option.numero_ava}`;
        const selected = optionKey === currentKey ? " selected" : "";
        const suffix = option.report_rejected ? " - Rechazado" : option.report_sent ? " - Enviado" : "";
        return `<option value="${escapeHtml(optionKey)}"${selected}>${escapeHtml(option.title)}${escapeHtml(suffix)}</option>`;
      }).join("");
      select.disabled = false;
    }

    function reportCalculatorValues() {
      const participants = state.reportCalculator?.participants || [];
      const splitParticipantWeight = participants.reduce(
        (total, participant) => total + reportParticipantSplitWeight(participant),
        0
      );
      const mode = document.getElementById("reportSplitMode").value;
      const config = applyReportModeVisibility(mode);
      const items = config.showItems ? parseReportAmount(document.getElementById("reportItems").value) : 0;
      const silver = config.showSilver ? parseReportAmount(document.getElementById("reportSilver").value) : 0;
      const mapCost = config.showMapCost ? parseReportAmount(document.getElementById("reportMapCost").value) : 0;
      const repairCost = config.showRepairCost ? parseReportAmount(document.getElementById("reportRepairCost").value) : 0;
      const callerPercent = config.showBothExtras ? parseReportPercentage(document.getElementById("reportCallerPercent").value) : 0;
      const callerPayment = config.showBothExtras ? Math.floor(silver * callerPercent / 100) : 0;
      const looterPayment = config.showBothExtras ? parseReportAmount(document.getElementById("reportLooterPayment").value) : 0;
      const looterUserId = config.showBothExtras && looterPayment > 0 ? document.getElementById("reportLooterUser").value : "";
      const tabSalePercent = config.showTabSale ? parseReportPercentage(document.getElementById("reportTabSalePercent").value) : 0;
      const splitModifiers = collectReportSplitModifiers();
      const buildLoanDiscounts = collectReportBuildLoanDiscounts();
      const globalModifierTotal = splitModifiers
        .filter(modifier => modifier.target_type === "total")
        .reduce((total, modifier) => total + reportModifierSignedAmount(modifier), 0);
      const looterParticipant = participants.find(participant => String(participant.user_id) === String(looterUserId));
      const looterWeight = looterParticipant ? reportParticipantSplitWeight(looterParticipant) : 0;
      const looterExcluded = looterUserId && looterWeight < 1;
      const effectiveLooterPayment = looterExcluded ? 0 : looterPayment;
      const netSilver = Math.max(silver - callerPayment - effectiveLooterPayment - mapCost - repairCost, 0);
      const soldTabValue = config.showTabSale && tabSalePercent > 0
        ? Math.floor(items * ((100 - tabSalePercent) / 100))
        : 0;
      const splitParticipantCount = splitParticipantWeight - (effectiveLooterPayment > 0 && looterUserId ? 1 : 0);
      let itemPool = 0;
      let silverPool = 0;
      if (mode === "items") itemPool = Math.max((tabSalePercent > 0 ? soldTabValue : items) + silver - mapCost - repairCost, 0);
      else if (mode === "silver") silverPool = items + netSilver;
      else if (tabSalePercent > 0) silverPool = Math.max(netSilver - callerPayment, 0) + soldTabValue;
      else {
        itemPool = items;
        silverPool = netSilver;
      }
      if (globalModifierTotal) {
        if (mode === "items") itemPool = Math.max(itemPool + globalModifierTotal, 0);
        else silverPool = Math.max(silverPool + globalModifierTotal, 0);
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
        looterPayment: effectiveLooterPayment,
        requestedLooterPayment: looterPayment,
        looterUserId,
        looterExcluded,
        tabSalePercent,
        soldTabValue,
        splitModifiers,
        buildLoanDiscounts,
        globalModifierTotal,
        splitParticipantCount: Math.max(splitParticipantCount, 0),
        itemPool,
        silverPool,
        total: itemPool + silverPool,
        itemPerUser: splitParticipantCount > 0 ? Math.floor(itemPool / splitParticipantCount) : 0,
        silverPerUser: splitParticipantCount > 0 ? Math.floor(silverPool / splitParticipantCount) : 0
      };
    }

    function buildReportCalculatorPayload({ sendToChannel = false, includeProof = false } = {}) {
      if (!state.reportCalculator) return null;
      const mode = document.getElementById("reportSplitMode").value;
      const config = reportCalculatorModeConfig(mode);
      const isManual = Boolean(state.reportCalculator.manual);
      return {
        guild_id: state.reportCalculator.guild_id,
        caller_id: state.reportCalculator.caller_id,
        numero_ava: state.reportCalculator.numero_ava,
        manual: isManual,
        manual_title: isManual ? manualReportTitle() : "",
        participant_count: isManual ? String(manualReportParticipantCount()) : "",
        split_mode: mode,
        send_to_channel: isManual ? false : sendToChannel,
        estimated: document.getElementById("reportEstimated").value,
        items: config.showItems ? document.getElementById("reportItems").value : "",
        silver: config.showSilver ? document.getElementById("reportSilver").value : "",
        costs: (config.showMapCost || config.showRepairCost) ? `mapa=${config.showMapCost ? document.getElementById("reportMapCost").value : ""}; repa=${config.showRepairCost ? document.getElementById("reportRepairCost").value : ""}` : "",
        caller_percentage: config.showBothExtras ? document.getElementById("reportCallerPercent").value : "",
        looter_payment: config.showBothExtras && !findReportSplitExclusion(document.getElementById("reportLooterUser").value) ? document.getElementById("reportLooterPayment").value : "",
        looter_user_id: config.showBothExtras && !findReportSplitExclusion(document.getElementById("reportLooterUser").value) ? document.getElementById("reportLooterUser").value : "",
        tab_sale_percentage: config.showTabSale ? document.getElementById("reportTabSalePercent").value : "",
        adjustments: "",
        split_exclusions: reportSplitExclusions(),
        split_modifiers: collectReportSplitModifiers(),
        build_loan_discounts: collectReportBuildLoanDiscounts({ includeProof }),
        fines: collectReportFines({ includeProof }),
        chest_table_id: isPersistedChestId(state.chestTable?.id) && (state.chestTable?.rows || []).length ? String(state.chestTable.id) : "",
      };
    }

    function reportFinalTextFromPreview(preview) {
      return String(preview?.evaluation_content || preview?.content || "");
    }

    function setReportCopyStatus(message = "", tone = "") {
      const status = document.getElementById("reportCopyStatus");
      if (!status) return;
      status.textContent = message;
      status.dataset.tone = tone;
    }

    function syncReportCopyButton() {
      const button = document.getElementById("copyReportFinalButton");
      if (!button) return;
      button.disabled = state.reportSubmitting || !state.reportCalculator || !state.reportFinalPreviewText;
    }

    function renderReportFinalPreview(preview) {
      const previewBox = document.getElementById("reportFinalPreview");
      const warningsBox = document.getElementById("reportPreviewWarnings");
      const warnings = preview?.warnings || [];
      const previewText = reportFinalTextFromPreview(preview);
      const finalText = preview?.copyable === false ? "" : previewText;
      state.reportFinalPreviewText = finalText;
      previewBox.textContent = previewText || "Completa los datos para ver el informe final.";
      warningsBox.hidden = warnings.length === 0;
      warningsBox.innerHTML = warnings.map(warning => (
        `<div class="report-preview-warning">${escapeHtml(warning)}</div>`
      )).join("");
      syncReportCopyButton();
    }

    async function fetchReportFinalPreview() {
      const payload = buildReportCalculatorPayload({ sendToChannel: false, includeProof: false });
      if (!payload) throw new Error("No hay una Ava cargada.");
      const response = await fetch("/api/report-calculator/preview", {
        method: "POST",
        headers: csrfHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify(payload)
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body.error || "No pude generar la vista previa.");
      return body.preview;
    }

    async function copyTextToClipboard(text) {
      if (navigator.clipboard?.writeText && window.isSecureContext) {
        await navigator.clipboard.writeText(text);
        return;
      }

      const textarea = document.createElement("textarea");
      textarea.value = text;
      textarea.setAttribute("readonly", "");
      textarea.style.position = "fixed";
      textarea.style.top = "-9999px";
      textarea.style.opacity = "0";
      document.body.appendChild(textarea);
      textarea.focus();
      textarea.select();
      try {
        if (!document.execCommand("copy")) {
          throw new Error("El navegador rechazo la copia al portapapeles.");
        }
      } finally {
        textarea.remove();
      }
    }

    async function copyReportFinalPreview() {
      const button = document.getElementById("copyReportFinalButton");
      if (button) button.disabled = true;
      setReportCopyStatus("Generando...", "");
      try {
        const preview = await fetchReportFinalPreview();
        renderReportFinalPreview(preview);
        const finalText = reportFinalTextFromPreview(preview);
        if (!finalText) throw new Error("No hay informe final para copiar.");
        await copyTextToClipboard(finalText);
        setReportCopyStatus("Copiado.", "success");
      } catch (error) {
        setReportCopyStatus(error.message || "No pude copiar.", "error");
      } finally {
        syncReportCopyButton();
      }
    }

    function scheduleReportPreview() {
      window.clearTimeout(state.reportPreviewTimer);
      if (!state.reportCalculator) {
        renderReportFinalPreview(null);
        return;
      }
      state.reportPreviewTimer = window.setTimeout(async () => {
        const requestId = (state.reportPreviewRequestId || 0) + 1;
        state.reportPreviewRequestId = requestId;
        try {
          const preview = await fetchReportFinalPreview();
          if (requestId !== state.reportPreviewRequestId) return;
          renderReportFinalPreview(preview);
        } catch (error) {
          if (requestId !== state.reportPreviewRequestId) return;
          renderReportFinalPreview({
            content: "No pude generar la vista previa todavia.",
            copyable: false,
            warnings: [error.message]
          });
        }
      }, 250);
    }

    function parseChestAmount(value) {
      const text = String(value || "").trim();
      if (!text || text === "-") return 0;
      if (text.startsWith("-")) return 0;
      const digits = text.replace(/\D/g, "");
      return digits ? Number(digits) : 0;
    }

    function normalizeChestTableDraft() {
      const table = state.chestTable;
      if (!table) return null;
      return {
        ...table,
        name: table.name || "Cofres",
        columns: [...(table.columns || [])],
        rows: (table.rows || []).map((row, index) => ({
          ...row,
          name: `Cofre ${index + 1}`,
          position: index + 1,
        })),
        cells: { ...(table.cells || {}) },
      };
    }

    function chestTableTotals(table = state.chestTable) {
      const columns = table?.columns || [];
      const rows = table?.rows || [];
      const cells = table?.cells || {};
      const columnTotals = {};
      const rowTotals = {};
      let grandTotal = 0;
      columns.forEach(column => { columnTotals[String(column.id)] = 0; });
      rows.forEach(row => {
        const rowId = String(row.id);
        let rowTotal = 0;
        columns.forEach(column => {
          const columnId = String(column.id);
          const value = parseChestAmount(cells[rowId]?.[columnId]);
          columnTotals[columnId] += value;
          rowTotal += column.operation === "-" ? -value : value;
        });
        rowTotals[rowId] = rowTotal;
        grandTotal += rowTotal;
      });
      return { rows: rowTotals, columns: columnTotals, grand_total: grandTotal };
    }

    function chestColumnByRole(role) {
      const columns = state.chestTable?.columns || [];
      if (role === "loot") {
        return columns.find(column => String(column.name || "").trim().toUpperCase() === "LQS") || columns[0] || null;
      }
      if (role === "remaining") {
        return columns.find(column => String(column.name || "").trim().toUpperCase() === "LQQ") || columns[1] || null;
      }
      return null;
    }

    function chestEstimateValues() {
      const table = state.chestTable;
      if (!table || !(table.rows || []).length) {
        return { enabled: false, loot: 0, remaining: 0 };
      }
      const totals = chestTableTotals(table);
      const lootColumn = chestColumnByRole("loot");
      const remainingColumn = chestColumnByRole("remaining");
      return {
        enabled: true,
        loot: lootColumn ? totals.columns[String(lootColumn.id)] || 0 : 0,
        remaining: remainingColumn ? totals.columns[String(remainingColumn.id)] || 0 : 0,
      };
    }

    function applyChestEstimateToReport() {
      const input = document.getElementById("reportEstimated");
      if (!input) return chestEstimateValues();
      const chestValues = chestEstimateValues();
      input.readOnly = chestValues.enabled;
      input.classList.toggle("readonly-from-chests", chestValues.enabled);
      if (chestValues.enabled) {
        input.value = chestValues.loot ? formatNumber(chestValues.loot) : "";
        input.title = "Estimado calculado desde LQS de los cofres.";
      } else {
        input.title = "";
      }
      return chestValues;
    }

    function nextChestTempId(prefix) {
      state.chestTempId = (state.chestTempId || 0) + 1;
      return `${prefix}_${Date.now()}_${state.chestTempId}`;
    }

    function chestGuildId() {
      return String(state.guildId || state.reportCalculator?.guild_id || state.reportContext?.guildId || "");
    }

    function isPersistedChestId(value) {
      return /^\d+$/.test(String(value || ""));
    }

    function ensureLocalChestTable() {
      if (state.chestTable) return state.chestTable;
      state.chestTable = {
        id: "",
        guild_id: chestGuildId(),
        name: "Cofres",
        columns: [
          { id: "local_lqs", name: "LQS", operation: "+", position: 1 },
          { id: "local_lqq", name: "LQQ", operation: "+", position: 2 },
        ],
        rows: [],
        cells: {},
        images: [],
        totals: { rows: {}, columns: {}, grand_total: 0 },
      };
      state.chestTableDirty = true;
      return state.chestTable;
    }

    async function loadChestTables({ force = false } = {}) {
      const guildId = chestGuildId();
      if (!guildId) return;
      if (!force && state.chestTablesGuildId === guildId && state.chestTables.length) return;
      const params = new URLSearchParams({ guild_id: guildId });
      const response = await fetch(`/api/chest-tables?${params.toString()}`, { cache: "no-store" });
      const payload = await readJsonResponse(response);
      if (!response.ok) throw new Error(payload.error || "No pude cargar las tablas de cofres.");
      state.chestTables = payload.tables || [];
      state.chestTablesGuildId = guildId;
      const selectedId = localStorage.getItem(`dashboardChestTable:${guildId}`) || state.chestTables[0]?.id || "";
      if (selectedId) await loadChestTable(selectedId);
      else state.chestTable = null;
    }

    async function loadChestTable(tableId) {
      const guildId = chestGuildId();
      if (!guildId || !tableId) return;
      const params = new URLSearchParams({ guild_id: guildId, table_id: tableId });
      const response = await fetch(`/api/chest-tables?${params.toString()}`, { cache: "no-store" });
      const payload = await readJsonResponse(response);
      if (!response.ok) throw new Error(payload.error || "No pude cargar esa tabla de cofres.");
      state.chestTable = payload.table || null;
      state.chestTableDirty = false;
      if (state.chestTable?.id) localStorage.setItem(`dashboardChestTable:${guildId}`, state.chestTable.id);
      renderChestTables();
    }

    async function createChestTable() {
      const guildId = chestGuildId();
      if (!guildId) throw new Error("Selecciona un servidor antes de agregar cofres.");
      const response = await fetch("/api/chest-tables", {
        method: "POST",
        headers: csrfHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({ guild_id: guildId, name: "Cofres" })
      });
      const payload = await readJsonResponse(response);
      if (!response.ok) throw new Error(payload.error || "No pude crear la tabla de cofres.");
      state.chestTables = payload.tables || [];
      state.chestTable = payload.table || null;
      state.chestTableDirty = false;
      state.chestTableStatus = "";
      renderChestTables();
    }

    async function saveChestTable({ silent = false } = {}) {
      const table = normalizeChestTableDraft();
      const guildId = chestGuildId();
      if (!guildId || !table?.id || !isPersistedChestId(table.id)) return;
      const response = await fetch("/api/chest-tables", {
        method: "POST",
        headers: csrfHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({ guild_id: guildId, table_id: table.id, table })
      });
      const payload = await readJsonResponse(response);
      if (!response.ok) throw new Error(payload.error || "No pude guardar la tabla de cofres.");
      state.chestTables = payload.tables || state.chestTables;
      state.chestTable = payload.table || table;
      state.chestTableDirty = false;
      state.chestTableStatus = silent ? "" : "Cofres guardados.";
      renderChestTables();
    }

    function remapChestCells(cells, columnMap) {
      const remapped = {};
      Object.entries(cells || {}).forEach(([rowId, rowCells]) => {
        remapped[rowId] = {};
        Object.entries(rowCells || {}).forEach(([columnId, value]) => {
          remapped[rowId][String(columnMap[columnId] || columnId)] = value;
        });
      });
      return remapped;
    }

    async function syncChestTableNow({ silent = true } = {}) {
      const table = state.chestTable;
      const guildId = chestGuildId();
      if (!table || !guildId) return;
      if (isPersistedChestId(table.id)) {
        await saveChestTable({ silent });
        return;
      }

      const localTable = normalizeChestTableDraft();
      await createChestTable();
      const serverTable = state.chestTable;
      if (!serverTable?.id) return;
      const serverLootColumn = chestColumnByRole("loot");
      const serverRemainingColumn = chestColumnByRole("remaining");
      const localLootColumn = (localTable.columns || [])[0];
      const localRemainingColumn = (localTable.columns || [])[1];
      const columnMap = {
        [String(localLootColumn?.id || "")]: serverLootColumn?.id,
        [String(localRemainingColumn?.id || "")]: serverRemainingColumn?.id,
      };
      state.chestTable = {
        ...serverTable,
        rows: localTable.rows || [],
        cells: remapChestCells(localTable.cells || {}, columnMap),
        images: [],
      };
      state.chestTableDirty = true;
      await saveChestTable({ silent });
    }

    function scheduleChestAutosave() {
      window.clearTimeout(state.chestAutosaveTimer);
      state.chestAutosaveTimer = window.setTimeout(() => {
        syncChestTableNow({ silent: true }).then(() => {
          renderReportCalculator();
        }).catch(error => {
          state.chestTableStatus = error.message;
          renderChestTables();
        });
      }, 450);
    }

    async function deleteChestTable() {
      const table = state.chestTable;
      if (!state.guildId || !table?.id) return;
      if (!window.confirm(`Eliminar ${table.name || "esta tabla de cofres"}?`)) return;
      const response = await fetch("/api/chest-tables", {
        method: "DELETE",
        headers: csrfHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({ guild_id: state.guildId, table_id: table.id })
      });
      const payload = await readJsonResponse(response);
      if (!response.ok) throw new Error(payload.error || "No pude eliminar la tabla.");
      state.chestTables = payload.tables || [];
      state.chestTable = null;
      state.chestTableDirty = false;
      state.chestTableStatus = "Tabla eliminada.";
      if (state.chestTables[0]?.id) await loadChestTable(state.chestTables[0].id);
      else renderChestTables();
    }

    function setChestDirty(message = "Cambios sin guardar.") {
      state.chestTableDirty = true;
      state.chestTableStatus = message;
      renderChestTables();
      scheduleChestAutosave();
    }

    async function addChestRow() {
      ensureLocalChestTable();
      const rows = state.chestTable.rows || [];
      rows.push({ id: nextChestTempId("row"), name: `Cofre ${rows.length + 1}`, position: rows.length + 1 });
      state.chestTable.rows = rows;
      state.chestTableDirty = true;
      state.chestTableStatus = "";
      renderReportCalculator();
      scheduleChestAutosave();
    }

    function chestImageFor(rowId, imageType) {
      return (state.chestTable?.images || []).find(image => (
        String(image.row_id || "") === String(rowId || "")
        && String(image.image_type || "") === String(imageType || "")
      )) || null;
    }

    function renderChestTables() {
      const select = document.getElementById("chestTableSelect");
      const wrap = document.getElementById("chestTableWrap");
      if (!select || !wrap) return;
      const table = state.chestTable;
      select.innerHTML = state.chestTables.length
        ? state.chestTables.map(item => `<option value="${escapeHtml(item.id)}"${String(table?.id || "") === String(item.id) ? " selected" : ""}>${escapeHtml(item.name || `Tabla ${item.id}`)}</option>`).join("")
        : `<option value="">Sin tablas</option>`;
      const deleteButton = document.getElementById("deleteChestTableButton");
      if (deleteButton) deleteButton.disabled = !table;
      document.getElementById("addChestRowButton").disabled = false;
      document.getElementById("chestTableStatus").textContent = state.chestTableStatus || "";
      if (!table || !(table.rows || []).length) {
        wrap.innerHTML = "";
        if (state.chestTableStatus === "La tabla debe tener al menos un cofre.") {
          state.chestTableStatus = "";
          document.getElementById("chestTableStatus").textContent = "";
        }
        return;
      }

      const lootColumn = chestColumnByRole("loot");
      const remainingColumn = chestColumnByRole("remaining");
      const rows = table.rows || [];
      const cells = table.cells || {};
      const totals = chestTableTotals(table);
      wrap.innerHTML = `
        <table class="chest-table-grid">
          <thead>
            <tr>
              <th class="sticky-col">Cofre</th>
              <th class="chest-amount-col">LQS</th>
              <th>Subir evidencia</th>
              <th class="chest-amount-col">LQQ</th>
              <th>Subir evidencia</th>
              <th class="chest-action-col" aria-label="Acciones"></th>
            </tr>
          </thead>
          <tbody>
            ${rows.map((row, rowIndex) => {
              const rowId = String(row.id);
              const lootColumnId = String(lootColumn?.id || "");
              const remainingColumnId = String(remainingColumn?.id || "");
              const lootValue = parseChestAmount(cells[rowId]?.[lootColumnId]);
              const remainingValue = parseChestAmount(cells[rowId]?.[remainingColumnId]);
              const lootImage = chestImageFor(rowId, "lqs");
              const remainingImage = chestImageFor(rowId, "lqq");
              return `
                <tr data-row-id="${escapeHtml(rowId)}">
                  <th class="sticky-col">${escapeHtml(`Cofre ${rowIndex + 1}`)}</th>
                  <td><input class="chest-cell-input" inputmode="numeric" data-column-id="${escapeHtml(lootColumnId)}" value="${lootValue ? escapeHtml(formatNumber(lootValue)) : ""}" placeholder="0"></td>
                  <td>${chestEvidenceControl(rowId, "lqs", lootImage)}</td>
                  <td><input class="chest-cell-input" inputmode="numeric" data-column-id="${escapeHtml(remainingColumnId)}" value="${remainingValue ? escapeHtml(formatNumber(remainingValue)) : ""}" placeholder="0"></td>
                  <td>${chestEvidenceControl(rowId, "lqq", remainingImage)}</td>
                  <td class="chest-action-cell">
                    <button class="mini-action danger" type="button" data-chest-delete-row="${escapeHtml(rowId)}" title="Eliminar cofre" aria-label="Eliminar ${escapeHtml(`Cofre ${rowIndex + 1}`)}">x</button>
                  </td>
                </tr>
              `;
            }).join("")}
          </tbody>
          <tfoot>
            <tr>
              <th class="sticky-col">Total</th>
              <td class="chest-total-cell">${formatNumber(lootColumn ? totals.columns[String(lootColumn.id)] || 0 : 0)}</td>
              <td></td>
              <td class="chest-total-cell">${formatNumber(remainingColumn ? totals.columns[String(remainingColumn.id)] || 0 : 0)}</td>
              <td></td>
              <td></td>
            </tr>
          </tfoot>
        </table>
      `;
    }

    function chestEvidenceControl(rowId, imageType, image) {
      const label = image ? "Ver evidencia" : "Subir evidencia";
      const preview = image
        ? `<a class="chest-evidence-link" href="${escapeHtml(image.url)}" target="_blank" rel="noreferrer">${escapeHtml(label)}</a>`
        : "";
      return `
        <label class="mini-upload">
          <input class="chest-evidence-input" type="file" accept=".png,.jpg,.jpeg,.webp,image/png,image/jpeg,image/webp" data-row-id="${escapeHtml(rowId)}" data-image-type="${escapeHtml(imageType)}">
          <span>${image ? "Cambiar" : "Subir"}</span>
        </label>
        ${preview}
      `;
    }

    function renderReportCalculator() {
      let calculator = state.reportCalculator;
      if (calculator?.manual) {
        calculator = { ...calculator, title: manualReportTitle(), participants: manualReportParticipants() };
        state.reportCalculator = calculator;
      }
      const participants = calculator?.participants || [];
      const splitExclusions = syncReportSplitExclusions(participants);
      renderReportCalculatorOptions();
      document.getElementById("reportManualFields").hidden = !calculator?.manual;
      document.getElementById("addReportFineButton").disabled = !calculator;
      populateReportLooterOptions(participants);
      syncReportFineParticipantOptions(participants);
      syncReportModifierParticipantOptions(participants);
      syncReportBuildLoanParticipantOptions(participants);
      const selectedLooterId = document.getElementById("reportLooterUser").value;
      document.getElementById("reportCalculatorParticipantsTotal").textContent = participants.length;
      document.getElementById("reportCalculatorSubtitle").textContent = calculator
        ? calculator.manual
          ? `${calculator.title} - modo manual`
          : `${calculator.title} - Caller: ${calculator.caller_name || calculator.caller_id}`
        : "Usa la calculadora manual o selecciona una Ava finalizada.";
      document.getElementById("reportParticipantsList").innerHTML = participants.length
        ? participants.map(participant => {
            const exclusion = findReportSplitExclusion(participant.user_id);
            const isExcluded = Boolean(exclusion);
            return `
            <article class="report-participant-card${isExcluded ? " excluded" : ""}">
              <div class="report-participant-head">
                <strong>${escapeHtml(`${participant.index}. ${participant.slot}`)}</strong>
                <span class="report-participant-tags">
                  ${participant.user_id === selectedLooterId ? '<span class="report-participant-role">Looter</span>' : ''}
                  ${isExcluded ? '<span class="report-participant-role excluded">Excluido</span>' : ''}
                </span>
              </div>
              <span class="report-participant-name">${escapeHtml(participant.display_name || participant.user_id)}</span>
              ${isExcluded ? `
                <label class="report-exclusion-reason-field">
                  <span>Motivo opcional</span>
                  <input class="report-exclusion-reason" data-user-id="${escapeHtml(participant.user_id)}" type="text" maxlength="300" value="${escapeHtml(exclusion.reason || "")}" placeholder="Ej: no participa del loot">
                </label>
                <label class="report-exclusion-reason-field">
                  <span>Descuento actividad</span>
                  <input class="report-exclusion-percentage" data-user-id="${escapeHtml(participant.user_id)}" type="text" maxlength="20" value="${escapeHtml(exclusion.activity_percentage || "")}" placeholder="Ej: 50%">
                </label>
                <button class="action-button danger report-exclusion-toggle" data-action="remove" data-user-id="${escapeHtml(participant.user_id)}" type="button">Quitar exclusion</button>
              ` : `
                <button class="action-button report-exclusion-toggle" data-action="exclude" data-user-id="${escapeHtml(participant.user_id)}" type="button">Excluir del split</button>
              `}
            </article>
          `;
          }).join("")
        : `<article class="report-participant-card">
              <div class="report-participant-head">
                <strong>Sin integrantes cargados</strong>
              </div>
              <span class="muted">Indica la cantidad de participantes para usar la calculadora manual.</span>
            </article>
          `;

      const values = reportCalculatorValues();
      const chestValues = applyChestEstimateToReport();
      document.getElementById("reportSplitParticipantsTotal").textContent = formatNumber(values.splitParticipantCount);
      document.getElementById("reportItemsPerUserStat").hidden = values.itemPool <= 0;
      document.getElementById("reportSilverPerUserStat").hidden = values.silverPool <= 0;
      document.getElementById("reportItemsPerUser").textContent = formatNumber(values.itemPerUser);
      document.getElementById("reportSilverPerUser").textContent = formatNumber(values.silverPerUser);
      document.getElementById("reportNetTotal").textContent = formatNumber(values.total);
      if (calculator?.manual) document.getElementById("reportDeliveryMode").value = "preview";
      document.getElementById("reportDeliveryMode").disabled = Boolean(calculator?.manual);
      const deliveryMode = document.getElementById("reportDeliveryMode").value;
      const willSendReport = deliveryMode !== "preview";
      document.getElementById("reportDeliveryStatus").textContent = willSendReport
        ? "El informe se enviara al canal de evaluacion configurado."
        : calculator?.manual
          ? "Modo manual: la vista previa se actualiza automaticamente."
          : "El informe se guardara como vista previa y no se enviara a Discord.";
      document.getElementById("submitReportCalculatorButton").hidden = Boolean(calculator?.manual);
      document.getElementById("submitReportCalculatorButton").textContent = willSendReport
        ? "Enviar informe a evaluacion"
        : "Guardar vista previa";
      const breakdown = [];
      if (chestValues.enabled) {
        breakdown.push({
          label: "Estimado de lo que salio",
          value: formatNumber(chestValues.loot),
          tone: "accent"
        });
        breakdown.push({
          label: "Lo que quedo",
          value: formatNumber(chestValues.remaining),
          tone: "accent"
        });
      }
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
      if (values.tabSalePercent) {
        breakdown.push({
          label: `Venta de tab (${values.tabSalePercent}%)`,
          value: `-${formatNumber(Math.max(values.items - values.soldTabValue, 0))}`,
          tone: "negative"
        });
      }
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
      values.splitModifiers.forEach(modifier => {
        const signedAmount = reportModifierSignedAmount(modifier);
        if (!signedAmount) return;
        breakdown.push({
          label: modifier.target_type === "player"
            ? `${modifier.name} (${modifier.user_name || "Jugador"})`
            : modifier.name,
          value: `${signedAmount > 0 ? "+" : "-"}${formatNumber(Math.abs(signedAmount))}`,
          tone: signedAmount > 0 ? "accent" : "negative"
        });
      });
      values.buildLoanDiscounts.forEach(discount => {
        const methodLabels = {
          split: "split",
          balance: "balance",
          paid_now: "pago al momento",
        };
        const method = discount.collection_method || "split";
        const amount = parseReportAmount(discount.amount);
        breakdown.push({
          label: `Préstamo build (${discount.user_name || "Jugador"} - ${methodLabels[method] || "split"})`,
          value: method === "paid_now" && !amount ? "Pagado" : `${method === "paid_now" ? "" : "-"}${formatNumber(amount)}`,
          tone: method === "paid_now" ? "accent" : "negative"
        });
      });
      document.getElementById("reportCalculatorBreakdown").innerHTML = breakdown.length
        ? breakdown.map(item => `
            <div class="report-breakdown-item ${item.tone ? escapeHtml(item.tone) : ""}">
              <span class="report-breakdown-label">${escapeHtml(item.label)}</span>
              <strong class="report-breakdown-value">${escapeHtml(item.value)}</strong>
            </div>
          `).join("")
        : `<div class="report-breakdown-empty">Completa los datos para calcular el reparto.</div>`;
      if (values.looterPayment && participants.length > 0 && !values.looterUserId) {
        document.getElementById("reportCalculatorBreakdown").innerHTML += `
          <div class="report-breakdown-empty">Selecciona quien fue el looter para excluirlo del split.</div>
        `;
      }
      if (values.looterExcluded) {
        document.getElementById("reportCalculatorBreakdown").innerHTML += `
          <div class="report-breakdown-empty">El looter esta excluido y no recibira pago de looter.</div>
        `;
      }
      if (splitExclusions.length) {
        document.getElementById("reportCalculatorBreakdown").innerHTML += `
          <div class="report-breakdown-empty">${formatNumber(splitExclusions.length)} jugador(es) excluido(s) del split.</div>
        `;
      }
      const reportAlreadyGenerated = Boolean(calculator?.report_generated && !calculator?.report_rejected);
      document.getElementById("submitReportCalculatorButton").disabled = state.reportSubmitting || !calculator || calculator.report_sent || reportAlreadyGenerated || calculator.cancelled || !calculator.finalized || (values.looterPayment > 0 && participants.length > 0 && !values.looterUserId);
      renderChestTables();
      syncReportCopyButton();
      scheduleReportPreview();
    }

    function resetReportCalculator() {
      ["reportManualTitle", "reportEstimated", "reportItems", "reportSilver", "reportMapCost", "reportRepairCost", "reportCallerPercent", "reportLooterPayment", "reportLooterUser", "reportTabSalePercent"].forEach(id => {
        document.getElementById(id).value = "";
      });
      document.getElementById("reportManualParticipants").value = "0";
      document.getElementById("reportFinesList").innerHTML = "";
      document.getElementById("reportModifiersList").innerHTML = "";
      document.getElementById("reportBuildLoansList").innerHTML = "";
      if (state.reportCalculator) state.reportCalculator.split_exclusions = [];
      document.getElementById("reportCalculatorStatus").textContent = "";
      setReportCopyStatus();
      renderReportCalculator();
    }

    async function loadReportCalculator() {
      renderReportCalculatorOptions();
      if (!state.reportContext || state.reportContext.ava === "__manual__") {
        state.reportCalculator = createManualReportCalculator();
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
      document.getElementById("reportModifiersList").innerHTML = "";
      document.getElementById("reportBuildLoansList").innerHTML = "";
      state.guildId = payload.calculator.guild_id;
      renderReportCalculator();
    }

    async function submitReportCalculator() {
      if (!state.reportCalculator) throw new Error("No hay una Ava cargada.");
      const status = document.getElementById("reportCalculatorStatus");
      if (state.reportCalculator.manual) {
        state.reportSubmitting = true;
        renderReportCalculator();
        status.textContent = "Generando vista previa manual...";
        try {
          const preview = await fetchReportFinalPreview();
          renderReportFinalPreview(preview);
          status.textContent = "Vista previa manual generada.";
        } finally {
          state.reportSubmitting = false;
          renderReportCalculator();
        }
        return;
      }

      const sendToChannel = document.getElementById("reportDeliveryMode").value !== "preview";
      if (state.reportBuildLoanProofReads.size) {
        status.textContent = "Preparando imagenes de prestamos...";
        await Promise.allSettled([...state.reportBuildLoanProofReads]);
      }
      if (state.chestTable && (state.chestTable.rows || []).length) {
        status.textContent = "Guardando evidencias de cofres...";
        await syncChestTableNow({ silent: true });
      }
      const payload = buildReportCalculatorPayload({ sendToChannel, includeProof: true });
      state.reportSubmitting = true;
      renderReportCalculator();
      status.textContent = sendToChannel ? "Enviando informe al bot..." : "Generando vista previa...";
      try {
        const response = await fetch("/api/report-calculator", {
          method: "POST",
          headers: csrfHeaders({ "Content-Type": "application/json" }),
          body: JSON.stringify(payload)
        });
        const responsePayload = await response.json();
        if (!response.ok) {
          if (response.status === 404) {
            state.reportCalculator = null;
            renderReportCalculator();
            throw new Error("Esta Ava ya no esta activa o ya fue cerrada. Abrela de nuevo desde Discord.");
          }
          throw new Error(responsePayload.error || "No pude enviar el informe.");
        }
        state.reportRequestId = responsePayload.request.id;
        status.textContent = sendToChannel ? "El bot esta procesando el informe..." : "El bot esta guardando la vista previa...";
        await pollReportRequest();
      } catch (error) {
        state.reportSubmitting = false;
        renderReportCalculator();
        throw error;
      }
    }

    async function pollReportRequest() {
      if (!state.reportRequestId) return;
      const params = new URLSearchParams({ request_id: state.reportRequestId });
      const response = await fetch(`/api/report-calculator?${params.toString()}`, { cache: "no-store" });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "No pude consultar el envio.");
      const request = payload.request;
      if (request.status === "completed") {
        const sentToChannel = Boolean(request.result?.sent_to_channel ?? request.result?.published);
        document.getElementById("reportCalculatorStatus").textContent = sentToChannel
          ? "Informe enviado a evaluacion."
          : "Informe generado y guardado como vista previa.";
        state.reportSubmitting = false;
        state.reportCalculator.report_sent = sentToChannel;
        state.reportCalculator.report_generated = true;
        renderReportCalculator();
        return;
      }
      if (request.status === "error") {
        state.reportSubmitting = false;
        renderReportCalculator();
        throw new Error(request.error || "El bot no pudo enviar el informe.");
      }
      setTimeout(() => pollReportRequest().catch(error => {
        state.reportSubmitting = false;
        renderReportCalculator();
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
      document.getElementById("finesSection").hidden = state.section !== "fines";
      document.getElementById("reportCalculatorSection").hidden = state.section !== "report-calculator";
      document.getElementById("registrationSection").hidden = state.section !== "registration";
      document.getElementById("welcomeSection").hidden = state.section !== "welcome";
      document.getElementById("auditSection").hidden = state.section !== "audit";
      document.getElementById("permissionsSection").hidden = state.section !== "permissions";
      document.getElementById("adminPanelSection").hidden = state.section !== "admin-panel";
      document.querySelectorAll(".section-button").forEach(button => {
        button.hidden = !canUseSection(button.dataset.section);
        const active = button.dataset.section === state.section;
        button.classList.toggle("active", active);
        if (active) button.setAttribute("aria-current", "page");
        else button.removeAttribute("aria-current");
      });
      document.querySelectorAll(".sidebar-group").forEach(group => {
        const hasVisibleSection = [...group.querySelectorAll(".section-button")]
          .some(button => !button.hidden);
        group.hidden = !hasVisibleSection;
      });
    }

    function canUseSection(section) {
      const access = state.data?.access || {};
      if (access.admin) return true;
      const sectionAccess = {
        economy: "economy",
        templates: "templates",
        tickets: "tickets",
        fines: "fines",
        audit: "audit",
        permissions: "permissions",
        "admin-panel": "adminPanel",
        registration: "registration",
        loot: "loot",
        "report-calculator": "reportCalculator",
        welcome: "welcome"
      };
      if (sectionAccess[section]) return Boolean(access[sectionAccess[section]]);
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
      state.selectedTicketTranscriptMessages = [];
      state.selectedTicketTranscriptRecord = null;
      state.selectedLiveTicketId = "";
      state.ticketLiveMessages = [];
      state.auditCategories = [];
      state.auditConfig = { channels: {} };
      state.auditEvents = [];
      state.auditSearch = "";
      state.auditFilters = createPageState(12);
      state.botPermissions = {};
      state.botSystemPermissions = {};
      state.botPermissionOptions = [];
      state.manageablePermissions = [];
      state.permissionReadOnlyRoleIds = [];
      state.canEditPermissions = false;
      state.adminGuilds = [];
      state.adminOverview = null;
      state.adminElevation = null;
      state.adminElevationGuildId = "";
      state.adminElevationSubmitting = false;
      state.adminElevationUiMessage = "";
      state.adminMessageChannels = [];
      state.adminMessageChannelsStatus = "idle";
      state.adminMessageChannelsError = "";
      state.adminBotMessageRequestId = "";
      state.adminServerBackups = [];
      state.adminServerBackupsStatus = "idle";
      state.adminServerBackupsError = "";
      state.selectedAdminBackupId = "";
      state.selectedAdminBackupDetail = null;
      state.adminBackupReplaceMode = false;
      state.adminTemplateTargetGuildId = "";
      state.adminTemplateClearTarget = false;
      state.adminTemplatePreview = null;
      state.adminTemplateRequestId = "";
      state.adminTemplateStatus = "";
      state.albionRegistrationConfig = null;
      state.albionRegistrations = [];
      state.albionRegistrationSearch = "";
      state.albionRegistrationFilters = createPageState(15);
      state.reportCalculator = null;
      state.reportCalculatorOptions = [];
      state.reportRequestId = "";
      state.chestTables = [];
      state.chestTable = null;
      state.chestTableStatus = "";
      state.chestTableDirty = false;
      state.fineConfig = null;
      state.economyGuildId = "";
      state.search = "";
      state.permissionSearch = "";
      state.permissionCategoryFilter = "";
      state.permissionStatusFilter = "";
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
      state.adminPanelGuildId = "";
      state.albionRegistrationGuildId = "";
      state.reportCalculatorOptionsGuildId = "";
      state.chestTablesGuildId = "";
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
        fines: ["fineConfigStatus"],
        audit: ["auditStatus"],
        permissions: ["permissionsStatus"],
        "admin-panel": ["adminPanelStatus"],
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
        loadDashboardAccess,
        renderShell,
        renderSection,
        render,
        loadReportCalculatorOptions,
        loadReportCalculator,
        loadChestTables,
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

    function loadAdminPanelData(options = {}) {
      return window.NeoxDashboardRouter.load("admin-panel", createDashboardContext(), options);
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

    function openEconomyBalanceModal(button) {
      const userId = button.dataset.userId || "";
      const userName = button.dataset.userName || userId || "Usuario";
      const userStatus = button.dataset.userStatus || "Estado no verificado";
      document.getElementById("economyBalanceUser").value = userId;
      document.getElementById("economyBalanceAction").value = "remove";
      document.getElementById("economyBalanceCategory").value = "silver";
      document.getElementById("economyBalanceAmount").value = "";
      document.getElementById("economyBalanceReason").value = "";
      document.getElementById("economyBalanceTargetName").textContent = `${userName} (${userId})`;
      document.getElementById("economyBalanceTargetStatus").textContent = userStatus;
      document.getElementById("economyBalanceModal").hidden = false;
      document.getElementById("economyBalanceAmount").focus();
      setSectionMessage("economy", `Editando balance de ${userName}.`);
    }

    function closeEconomyBalanceModal() {
      document.getElementById("economyBalanceModal").hidden = true;
    }

    async function selectAdminPanelGuild(guildId) {
      guildId = String(guildId || "");
      if (!guildId || guildId === state.guildId) return;
      state.guildId = guildId;
      state.data = createEmptyDashboardData({
        ...state.data,
        selectedGuildId: state.guildId
      });
      localStorage.setItem("dashboardGuildId", state.guildId);
      resetGuildScopedData();
      state.adminMessageChannels = [];
      state.adminMessageChannelsStatus = "idle";
      state.adminMessageChannelsError = "";
      state.adminBotMessageRequestId = "";
      state.adminServerBackups = [];
      state.adminServerBackupsStatus = "idle";
      state.adminServerBackupsError = "";
      state.selectedAdminBackupId = "";
      state.selectedAdminBackupDetail = null;
      state.adminBackupReplaceMode = false;
      state.adminTemplateTargetGuildId = "";
      state.adminTemplateClearTarget = false;
      state.adminTemplatePreview = null;
      state.adminTemplateRequestId = "";
      state.adminTemplateStatus = "";
      state.section = "admin-panel";
      localStorage.setItem("dashboardSection", state.section);
      render();
      await loadDashboardAccess();
      render();
      await loadAdminPanelData({ force: true });
    }

    async function submitEconomyBalanceChange(event) {
      event.preventDefault();
      if (!state.guildId) return;
      const submitButton = document.getElementById("economyBalanceSubmit");
      submitButton.disabled = true;
      setSectionMessage("economy", "Aplicando cambio de balance...");
      try {
        const response = await fetch("/api/economy/balance", {
          method: "POST",
          headers: csrfHeaders({ "Content-Type": "application/json" }),
          body: JSON.stringify({
            guild_id: state.guildId,
            action: document.getElementById("economyBalanceAction").value,
            user: document.getElementById("economyBalanceUser").value,
            category: document.getElementById("economyBalanceCategory").value,
            amount: document.getElementById("economyBalanceAmount").value,
            reason: document.getElementById("economyBalanceReason").value
          })
        });
        const payload = await readJsonResponse(response);
        if (!response.ok) throw new Error(payload.error || "No pude modificar el balance.");
        const operation = payload.operation || {};
        document.getElementById("economyBalanceAmount").value = "";
        closeEconomyBalanceModal();
        await loadEconomyData({ force: true });
        setSectionMessage(
          "economy",
          `Balance actualizado: ${operation.player || operation.player_id || "usuario"} - ${operation.player_status || "estado no verificado"}.`
        );
      } finally {
        submitButton.disabled = false;
      }
    }

    async function submitAdminBotMessage(event) {
      event.preventDefault();
      if (!state.guildId) return;

      const action = document.getElementById("adminBotMessageAction").value;
      const channelId = document.getElementById("adminBotMessageChannel").value;
      const messageId = document.getElementById("adminBotMessageId").value.trim();
      const content = document.getElementById("adminBotMessageContent").value;
      if (action === "delete" && !window.confirm("Vas a eliminar un mensaje enviado por el bot. Esta accion no se puede deshacer.")) {
        return;
      }

      const submitButton = document.getElementById("adminBotMessageSubmit");
      submitButton.disabled = true;
      document.getElementById("adminBotMessageStatus").textContent = "Encolando solicitud...";
      try {
        const response = await fetch("/api/admin/bot-message", {
          method: "POST",
          headers: csrfHeaders({ "Content-Type": "application/json" }),
          body: JSON.stringify({
            guild_id: state.guildId,
            action,
            channel_id: channelId,
            message_id: messageId,
            content
          })
        });
        const payload = await readJsonResponse(response);
        if (!response.ok) throw new Error(payload.error || "No pude crear la solicitud.");

        const request = payload.request || {};
        state.adminBotMessageRequestId = request.id || "";
        document.getElementById("adminBotMessageStatus").textContent = "Solicitud enviada al bot. Esperando confirmacion...";
        await pollAdminBotMessageRequest(state.adminBotMessageRequestId);
      } finally {
        submitButton.disabled = state.adminMessageChannelsStatus !== "loaded" || !(state.adminMessageChannels || []).length;
      }
    }

    async function createAdminServerBackup({ replaceBackupId = "" } = {}) {
      if (!state.guildId) return;
      const button = document.getElementById("adminCreateBackupButton");
      button.disabled = true;
      document.getElementById("adminServerBackupsStatus").textContent = "Creando backup...";
      try {
        const response = await fetch("/api/admin/server-backups", {
          method: "POST",
          headers: csrfHeaders({ "Content-Type": "application/json" }),
          body: JSON.stringify({
            guild_id: state.guildId,
            replace_backup_id: replaceBackupId
          })
        });
        const payload = await readJsonResponse(response);
        if (response.status === 409 && payload.requires_replacement_choice) {
          state.adminServerBackups = payload.backups || state.adminServerBackups || [];
          state.adminBackupReplaceMode = true;
          state.selectedAdminBackupId = "";
          state.selectedAdminBackupDetail = null;
          renderAdminPanel();
          document.getElementById("adminServerBackupsStatus").textContent = "Elige que backup quieres reemplazar.";
          return;
        }
        if (!response.ok) throw new Error(payload.error || "No pude crear el backup.");

        state.adminBackupReplaceMode = false;
        state.selectedAdminBackupId = String(payload.backup?.id || "");
        state.selectedAdminBackupDetail = payload.backup || null;
        const page = window.NeoxDashboardPages?.["admin-panel"];
        if (page?.loadServerBackups) {
          await page.loadServerBackups(createDashboardContext());
        }
        renderAdminPanel();
        document.getElementById("adminServerBackupsStatus").textContent = "Backup creado correctamente.";
      } finally {
        button.disabled = false;
      }
    }

    async function loadAdminServerBackupDetail(backupId, label = "") {
      backupId = String(backupId || "");
      if (!state.guildId || !backupId) return;
      state.selectedAdminBackupId = backupId;
      state.adminTemplatePreview = null;
      state.adminTemplateRequestId = "";
      state.adminTemplateStatus = "";
      document.getElementById("adminServerBackupsStatus").textContent = "Cargando detalle...";
      const params = new URLSearchParams({
        guild_id: state.guildId,
        backup_id: backupId
      });
      const response = await fetch(`/api/admin/server-backups?${params.toString()}`, { cache: "no-store" });
      const payload = await readJsonResponse(response);
      if (!response.ok) throw new Error(payload.error || "No pude cargar el backup.");
      state.selectedAdminBackupDetail = payload.backup || null;
      renderAdminPanel();
      document.getElementById("adminServerBackupsStatus").textContent = `Detalle de ${label || "backup"}.`;
    }

    function adminTemplateOptions() {
      return {
        update_existing: Boolean(state.adminTemplateUpdateExisting),
        include_bot_config: Boolean(state.adminTemplateIncludeBotConfig),
        clear_target: Boolean(state.adminTemplateClearTarget)
      };
    }

    async function previewAdminServerTemplate() {
      if (!state.guildId || !state.selectedAdminBackupId || !state.adminTemplateTargetGuildId) return;
      state.adminTemplateStatus = "Calculando vista previa...";
      renderAdminPanel();
      const response = await fetch("/api/admin/server-template/preview", {
        method: "POST",
        headers: csrfHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({
          source_guild_id: state.guildId,
          backup_id: state.selectedAdminBackupId,
          target_guild_id: state.adminTemplateTargetGuildId,
          options: adminTemplateOptions()
        })
      });
      const payload = await readJsonResponse(response);
      if (!response.ok) throw new Error(payload.error || "No pude generar la vista previa.");
      state.adminTemplatePreview = payload;
      state.adminTemplateStatus = "Vista previa lista.";
      renderAdminPanel();
    }

    async function applyAdminServerTemplate() {
      const confirmation = String(document.getElementById("adminTemplateConfirmation")?.value || "").trim();
      if (confirmation.toUpperCase() !== "APLICAR") {
        state.adminTemplateStatus = "Escribe APLICAR para confirmar.";
        renderAdminPanel();
        return;
      }
      const applyingToSameGuild = String(state.adminTemplateTargetGuildId || "") === String(state.guildId || "");
      const confirmMessage = state.adminTemplateClearTarget
        ? applyingToSameGuild
          ? "Esta operacion eliminara primero roles, canales y configuracion existente de este mismo servidor, y luego lo reconstruira desde el backup. Puedes cancelar ahora."
          : "Esta operacion eliminara primero roles, canales y configuracion existente del servidor destino, y luego aplicara la plantilla. Puedes cancelar ahora."
        : applyingToSameGuild
          ? "Esta operacion aplicara el backup sobre este mismo servidor y reutilizara elementos existentes cuando coincidan. Puedes cancelar ahora."
          : "Esta operacion creara roles, categorias, canales y permisos en el servidor destino. Puedes cancelar ahora.";
      if (!window.confirm(confirmMessage)) {
        state.adminTemplateStatus = "Operacion cancelada.";
        renderAdminPanel();
        return;
      }

      state.adminTemplateStatus = "Encolando aplicacion de plantilla...";
      renderAdminPanel();
      const response = await fetch("/api/admin/server-template/apply", {
        method: "POST",
        headers: csrfHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({
          source_guild_id: state.guildId,
          backup_id: state.selectedAdminBackupId,
          target_guild_id: state.adminTemplateTargetGuildId,
          options: adminTemplateOptions(),
          confirmation,
          confirmed: true
        })
      });
      const payload = await readJsonResponse(response);
      if (!response.ok) throw new Error(payload.error || "No pude encolar la plantilla.");
      state.adminTemplateRequestId = payload.request?.id || "";
      state.adminTemplateStatus = "Solicitud enviada al bot. Esperando resultado...";
      renderAdminPanel();
      await pollAdminTemplateRequest(state.adminTemplateRequestId);
    }

    async function pollAdminTemplateRequest(requestId) {
      requestId = String(requestId || "");
      if (!requestId) return;
      for (let attempt = 0; attempt < 60; attempt += 1) {
        await new Promise(resolve => window.setTimeout(resolve, attempt < 2 ? 1000 : 2500));
        const params = new URLSearchParams({ request_id: requestId });
        const response = await fetch(`/api/dashboard-action-request?${params.toString()}`, { cache: "no-store" });
        const payload = await readJsonResponse(response);
        if (!response.ok) throw new Error(payload.error || "No pude consultar el estado de la plantilla.");
        const request = payload.request || {};
        if (request.status === "completed") {
          const result = request.result || {};
          const created = result.created || {};
          const deleted = result.deleted || {};
          state.adminTemplateStatus = `Plantilla aplicada: ${(created.roles || []).length} roles, ${(created.categories || []).length} categorias, ${(created.channels || []).length} canales. Eliminados: ${(deleted.roles || []).length} roles y ${(deleted.channels || []).length} canales.`;
          renderAdminPanel();
          return;
        }
        if (request.status === "failed") {
          throw new Error(request.error || "El bot no pudo aplicar la plantilla.");
        }
        state.adminTemplateStatus = `Solicitud ${request.status || "pendiente"}...`;
        renderAdminPanel();
      }
      state.adminTemplateStatus = "Solicitud enviada. El bot sigue procesandola.";
      renderAdminPanel();
    }

    async function pollAdminBotMessageRequest(requestId) {
      requestId = String(requestId || "");
      if (!requestId) return;

      for (let attempt = 0; attempt < 20; attempt += 1) {
        await new Promise(resolve => window.setTimeout(resolve, attempt < 2 ? 800 : 1500));
        const params = new URLSearchParams({ request_id: requestId });
        const response = await fetch(`/api/dashboard-action-request?${params.toString()}`, { cache: "no-store" });
        const payload = await readJsonResponse(response);
        if (!response.ok) throw new Error(payload.error || "No pude consultar el estado de la solicitud.");

        const request = payload.request || {};
        const status = String(request.status || "");
        if (status === "completed") {
          const result = request.result || {};
          document.getElementById("adminBotMessageStatus").textContent =
            `Accion completada. Mensaje: ${result.message_id || "sin ID"}.`;
          if (document.getElementById("adminBotMessageAction").value === "send") {
            document.getElementById("adminBotMessageContent").value = "";
            updateAdminBotMessageCounter();
          }
          return;
        }
        if (status === "failed") {
          throw new Error(request.error || "El bot no pudo completar la accion.");
        }
        document.getElementById("adminBotMessageStatus").textContent = `Solicitud ${status || "pendiente"}...`;
      }

      document.getElementById("adminBotMessageStatus").textContent = "Solicitud enviada. El bot sigue procesandola.";
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
      if (filters.record_type) params.set("type", filters.record_type);
      if (filters.sort) params.set("sort", filters.sort);
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
      const body = collectBotPermissions();
      const response = await fetch("/api/bot-permissions", {
        method: "POST",
        headers: csrfHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({
          guild_id: state.guildId,
          permissions: body.permissions,
          role_ids: body.roleIds
        })
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "No pude guardar los permisos.");
      state.botPermissions = payload.permissions || {};
      state.botSystemPermissions = payload.system_permissions || {};
      state.botPermissionOptions = payload.options || state.botPermissionOptions;
      state.manageablePermissions = payload.manageable_permissions || state.manageablePermissions;
      state.permissionReadOnlyRoleIds = payload.read_only_role_ids || state.permissionReadOnlyRoleIds;
      state.canEditPermissions = Boolean(payload.can_edit);
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

    document.getElementById("economyBalanceForm").addEventListener("submit", event => {
      submitEconomyBalanceChange(event).catch(showError);
    });

    document.getElementById("tableBody").addEventListener("click", event => {
      const button = event.target.closest(".economy-edit-balance");
      if (!button) return;
      openEconomyBalanceModal(button);
    });

    document.getElementById("economyBalanceModal").addEventListener("click", event => {
      if (event.target.id === "economyBalanceModal" || event.target.closest("[data-economy-balance-close]")) {
        closeEconomyBalanceModal();
      }
    });

    document.getElementById("adminGuildList").addEventListener("click", event => {
      const button = event.target.closest("[data-admin-guild-id]");
      if (!button) return;
      selectAdminPanelGuild(button.dataset.adminGuildId).catch(showError);
    });

    document.getElementById("adminElevationForm").addEventListener("submit", event => {
      event.preventDefault();
      const passwordInput = document.getElementById("adminElevationPassword");
      const password = passwordInput.value;
      const page = window.NeoxDashboardPages?.["admin-panel"];
      if (!page?.submitElevation) return;

      state.adminElevationSubmitting = true;
      state.adminElevationUiMessage = "Validando clave secundaria...";
      renderAdminPanel();
      page.submitElevation(createDashboardContext(), password)
        .then(status => {
          state.adminElevationSubmitting = false;
          state.adminElevationUiMessage = status?.message || "Acceso elevado habilitado.";
          passwordInput.value = "";
          renderAdminPanel();
          if (status?.elevated) {
            return loadAdminPanelData({ force: true });
          }
          return null;
        })
        .then(() => {
          renderAdminPanel();
        })
        .catch(error => {
          state.adminElevationSubmitting = false;
          state.adminElevationUiMessage = error.message || "No pude validar la clave secundaria.";
          renderAdminPanel();
        });
    });

    document.getElementById("adminElevationLogoutButton").addEventListener("click", () => {
      const page = window.NeoxDashboardPages?.["admin-panel"];
      if (!page?.logoutElevation) return;
      state.adminElevationUiMessage = "Cerrando acceso elevado...";
      renderAdminPanel();
      page.logoutElevation(createDashboardContext())
        .then(() => {
          state.adminElevationSubmitting = false;
          state.adminElevationUiMessage = "Acceso elevado cerrado.";
          renderAdminPanel();
        })
        .catch(error => {
          state.adminElevationUiMessage = error.message || "No pude cerrar el acceso elevado.";
          renderAdminPanel();
        });
    });

    document.getElementById("adminBotMessageForm").addEventListener("submit", event => {
      submitAdminBotMessage(event).catch(error => {
        document.getElementById("adminBotMessageStatus").textContent = error.message;
        document.getElementById("adminBotMessageSubmit").disabled =
          state.adminMessageChannelsStatus !== "loaded" || !(state.adminMessageChannels || []).length;
      });
    });

    document.getElementById("adminCreateBackupButton").addEventListener("click", () => {
      if (state.adminBackupReplaceMode) {
        state.adminBackupReplaceMode = false;
        renderAdminPanel();
        document.getElementById("adminServerBackupsStatus").textContent = "Reemplazo cancelado.";
        return;
      }
      createAdminServerBackup().catch(error => {
        document.getElementById("adminServerBackupsStatus").textContent = error.message;
        document.getElementById("adminCreateBackupButton").disabled = false;
      });
    });

    document.getElementById("adminServerBackupsList").addEventListener("click", event => {
      const replaceButton = event.target.closest("[data-admin-replace-backup-id]");
      if (replaceButton) {
        const label = replaceButton.dataset.adminBackupLabel || "este backup";
        if (!window.confirm(`Se eliminara ${label} y se creara uno nuevo. Quieres continuar?`)) return;
        createAdminServerBackup({ replaceBackupId: replaceButton.dataset.adminReplaceBackupId }).catch(error => {
          document.getElementById("adminServerBackupsStatus").textContent = error.message;
          document.getElementById("adminCreateBackupButton").disabled = false;
        });
        return;
      }

      const button = event.target.closest("[data-admin-backup-id]");
      if (!button) return;
      loadAdminServerBackupDetail(button.dataset.adminBackupId, button.dataset.adminBackupLabel).catch(error => {
        document.getElementById("adminServerBackupsStatus").textContent = error.message;
      });
    });

    document.getElementById("adminServerTemplateForm").addEventListener("change", event => {
      if (event.target.id === "adminTemplateBackup") {
        state.selectedAdminBackupId = event.target.value;
        state.selectedAdminBackupDetail = null;
        state.adminTemplatePreview = null;
        state.adminTemplateStatus = "";
        renderAdminPanel();
      }
      if (event.target.id === "adminTemplateTargetGuild") {
        state.adminTemplateTargetGuildId = event.target.value;
        state.adminTemplatePreview = null;
        state.adminTemplateStatus = "";
        renderAdminPanel();
      }
      if (event.target.id === "adminTemplateUpdateExisting") {
        state.adminTemplateUpdateExisting = event.target.checked;
        state.adminTemplatePreview = null;
        renderAdminPanel();
      }
      if (event.target.id === "adminTemplateIncludeBotConfig") {
        state.adminTemplateIncludeBotConfig = event.target.checked;
        state.adminTemplatePreview = null;
        renderAdminPanel();
      }
      if (event.target.id === "adminTemplateClearTarget") {
        state.adminTemplateClearTarget = event.target.checked;
        state.adminTemplatePreview = null;
        renderAdminPanel();
      }
    });

    document.getElementById("adminTemplateConfirmation").addEventListener("input", () => {
      renderAdminServerTemplate();
    });

    document.getElementById("adminTemplatePreviewButton").addEventListener("click", () => {
      previewAdminServerTemplate().catch(error => {
        state.adminTemplateStatus = error.message;
        renderAdminPanel();
      });
    });

    document.getElementById("adminServerTemplateForm").addEventListener("submit", event => {
      event.preventDefault();
      applyAdminServerTemplate().catch(error => {
        state.adminTemplateStatus = error.message;
        renderAdminPanel();
      });
    });

    document.getElementById("adminServerBackupDetail").addEventListener("click", event => {
      if (event.target.closest("#adminTemplatePreviewButton")) {
        previewAdminServerTemplate().catch(error => {
          state.adminTemplateStatus = error.message;
          renderAdminPanel();
        });
      }
      if (event.target.closest("#adminTemplateApplyButton")) {
        applyAdminServerTemplate().catch(error => {
          state.adminTemplateStatus = error.message;
          renderAdminPanel();
        });
      }
    });

    document.getElementById("adminBotMessageAction").addEventListener("change", updateAdminBotMessageMode);
    document.getElementById("adminBotMessageChannel").addEventListener("change", scheduleLoadAdminBotMessageForEdit);
    document.getElementById("adminBotMessageId").addEventListener("input", scheduleLoadAdminBotMessageForEdit);
    document.getElementById("adminBotMessageContent").addEventListener("input", updateAdminBotMessageCounter);
    document.getElementById("refreshAdminMessageChannelsButton").addEventListener("click", () => {
      const page = window.NeoxDashboardPages?.["admin-panel"];
      if (!page?.loadMessageChannels) return;
      page.loadMessageChannels(createDashboardContext(), { force: true }).catch(error => {
        state.adminMessageChannels = [];
        state.adminMessageChannelsStatus = "error";
        state.adminMessageChannelsError = error.message || "No pude recargar canales.";
        renderAdminPanel();
      });
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
        if (window.matchMedia?.("(max-width: 760px)")?.matches) {
          state.sidebarCollapsed = true;
        }
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

    ["ticketName", "ticketMode", "ticketChannel", "ticketOpenCategory", "ticketColor", "ticketContent", "ticketTitle", "ticketFooter", "ticketDescription", "ticketImage", "ticketOpenContent", "ticketOpenTitle", "ticketOpenColor", "ticketOpenDescription", "ticketOpenFooter", "ticketOpenImage", "ticketOpenThumbnail", "addMemberRoles", "addMemberUserIds", "claimRoles", "closeRoles", "reopenRoles", "deleteRoles"].forEach(id => {
      document.getElementById(id).addEventListener("input", () => {
        if (id.endsWith("Roles")) enforceRoleLimit(document.getElementById(id));
        persistCurrentTicketPanel();
        renderCurrentTicketPreviews();
        if (id === "ticketMode") renderTicketEditorSections();
      });
      document.getElementById(id).addEventListener("change", () => {
        if (id.endsWith("Roles")) enforceRoleLimit(document.getElementById(id));
        persistCurrentTicketPanel();
        renderCurrentTicketPreviews();
        if (id === "ticketMode") renderTicketEditorSections();
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

    document.getElementById("ticketRecordTypeFilter").addEventListener("change", event => {
      state.ticketRecordFilters.record_type = event.target.value;
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

    document.getElementById("ticketRecordSortButton").addEventListener("click", () => {
      state.ticketRecordFilters.sort = state.ticketRecordFilters.sort === "oldest" ? "newest" : "oldest";
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

    document.getElementById("closeTicketTranscriptPreviewButton").addEventListener("click", () => {
      state.selectedTicketRecordId = "";
      state.selectedTicketTranscriptRecord = null;
      state.selectedTicketTranscriptMessages = [];
      state.ticketFocusView = "";
      renderTickets();
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
        description: "",
        ticket_open_content: "",
        ticket_open_title: "",
        ticket_open_description: "",
        ticket_open_color: "",
        ticket_open_footer: "",
        ticket_open_image_url: "",
        ticket_open_thumbnail_url: ""
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
      state.botPermissions = collectBotPermissions().permissions;
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

    document.getElementById("chestTableSelect").addEventListener("change", event => {
      loadChestTable(event.target.value).catch(error => {
        state.chestTableStatus = error.message;
        renderChestTables();
      });
    });

    const deleteChestTableButton = document.getElementById("deleteChestTableButton");
    if (deleteChestTableButton) {
      deleteChestTableButton.addEventListener("click", () => {
        deleteChestTable().catch(error => {
          state.chestTableStatus = error.message;
          renderChestTables();
        });
      });
    }

    document.getElementById("addChestRowButton").addEventListener("click", () => {
      addChestRow().then(() => {
        renderReportCalculator();
      }).catch(error => {
        state.chestTableStatus = error.message;
        renderChestTables();
      });
    });

    document.getElementById("chestTableWrap").addEventListener("click", event => {
      const deleteRow = event.target.closest("[data-chest-delete-row]");
      if (deleteRow && state.chestTable) {
        const rowId = String(deleteRow.dataset.chestDeleteRow || "");
        state.chestTable.rows = (state.chestTable.rows || []).filter(row => String(row.id) !== rowId);
        delete (state.chestTable.cells || {})[rowId];
        setChestDirty();
        renderReportCalculator();
      }
    });

    document.getElementById("chestTableWrap").addEventListener("input", event => {
      if (!state.chestTable) return;
      const target = event.target;
      if (target.matches(".chest-cell-input")) {
        const rowId = String(target.closest("tr")?.dataset.rowId || "");
        const columnId = String(target.dataset.columnId || "");
        state.chestTable.cells = state.chestTable.cells || {};
        state.chestTable.cells[rowId] = state.chestTable.cells[rowId] || {};
        state.chestTable.cells[rowId][columnId] = parseChestAmount(target.value);
        state.chestTableDirty = true;
        state.chestTableStatus = "Cambios sin guardar.";
        document.getElementById("chestTableStatus").textContent = state.chestTableStatus;
        applyChestEstimateToReport();
        scheduleChestAutosave();
      }
    });

    document.getElementById("chestTableWrap").addEventListener("change", async event => {
      if (!state.chestTable) return;
      if (event.target.matches(".chest-cell-input")) {
        renderReportCalculator();
        return;
      }
      if (!event.target.matches(".chest-evidence-input")) return;
      const input = event.target;
      const file = input.files?.[0];
      if (!file || !state.chestTable?.id) return;
      try {
        state.chestTableStatus = "Subiendo evidencia...";
        renderChestTables();
        const dataUrl = await fileToDataUrl(file);
        const response = await fetch("/api/chest-table-image", {
          method: "POST",
          headers: csrfHeaders({ "Content-Type": "application/json" }),
          body: JSON.stringify({
            guild_id: state.guildId,
            table_id: state.chestTable.id,
            row_id: input.dataset.rowId || "",
            image_type: input.dataset.imageType || "",
            filename: file.name,
            data_url: dataUrl
          })
        });
        const payload = await readJsonResponse(response);
        if (!response.ok) throw new Error(payload.error || "No pude subir la evidencia.");
        state.chestTable = payload.table || state.chestTable;
        state.chestTableStatus = "Evidencia subida.";
        renderChestTables();
      } catch (error) {
        state.chestTableStatus = error.message;
        renderChestTables();
      } finally {
        input.value = "";
      }
    });

    ["reportSplitMode", "reportManualTitle", "reportManualParticipants", "reportEstimated", "reportItems", "reportSilver", "reportMapCost", "reportRepairCost", "reportCallerPercent", "reportLooterPayment", "reportLooterUser", "reportTabSalePercent", "reportDeliveryMode"].forEach(id => {
      const handleReportInput = () => {
        setReportCopyStatus();
        renderReportCalculator();
      };
      document.getElementById(id).addEventListener("input", handleReportInput);
      document.getElementById(id).addEventListener("change", handleReportInput);
    });

    document.getElementById("addReportFineButton").addEventListener("click", () => {
      appendReportFineRow();
      renderReportCalculator();
    });

    document.getElementById("addReportModifierButton").addEventListener("click", () => {
      appendReportModifierRow();
      renderReportCalculator();
    });

    document.getElementById("addReportBuildLoanButton").addEventListener("click", () => {
      appendReportBuildLoanRow();
      renderReportCalculator();
    });

    document.getElementById("reportParticipantsList").addEventListener("click", event => {
      const button = event.target.closest(".report-exclusion-toggle");
      if (!button || !state.reportCalculator) return;
      const userId = button.dataset.userId || "";
      const participant = (state.reportCalculator.participants || [])
        .find(item => String(item.user_id) === String(userId));
      if (!participant) return;
      if (button.dataset.action === "remove") {
        removeReportSplitExclusion(userId);
      } else {
        setReportSplitExclusion(participant, "");
      }
      setReportCopyStatus();
      renderReportCalculator();
    });

    document.getElementById("reportParticipantsList").addEventListener("input", event => {
      if (!event.target.matches(".report-exclusion-reason, .report-exclusion-percentage") || !state.reportCalculator) return;
      const userId = event.target.dataset.userId || "";
      const participant = (state.reportCalculator.participants || [])
        .find(item => String(item.user_id) === String(userId));
      if (!participant) return;
      const current = findReportSplitExclusion(userId) || {};
      const reason = event.target.matches(".report-exclusion-reason")
        ? event.target.value
        : current.reason || "";
      const activityPercentage = event.target.matches(".report-exclusion-percentage")
        ? event.target.value
        : current.activity_percentage || "";
      setReportSplitExclusion(participant, reason, activityPercentage);
      setReportCopyStatus();
      scheduleReportPreview();
    });

    document.getElementById("reportCalculatorSelect").addEventListener("change", event => {
      const selectedKey = event.target.value;
      if (!selectedKey) {
        state.reportContext = null;
        state.reportCalculator = null;
        renderReportCalculator();
        return;
      }
      if (selectedKey === "__manual__") {
        state.reportContext = {
          guildId: state.guildId,
          callerId: state.data?.viewer?.id || "",
          ava: "__manual__",
        };
        document.getElementById("reportCalculatorStatus").textContent = "";
        loadReportCalculator().catch(error => {
          document.getElementById("reportCalculatorStatus").textContent = error.message;
        });
        return;
      }
      const selected = state.reportCalculatorOptions.find(item => `${item.caller_id || ""}:${item.numero_ava}` === selectedKey);
      const ava = selected?.numero_ava || selectedKey.split(":").slice(1).join(":");
      state.reportContext = {
        guildId: state.guildId,
        callerId: selected?.caller_id || state.data?.viewer?.id || "",
        ava,
      };
      document.getElementById("reportCalculatorStatus").textContent = "";
      loadReportCalculator().catch(error => {
        document.getElementById("reportCalculatorStatus").textContent = error.message;
      });
    });

    document.getElementById("submitReportCalculatorButton").addEventListener("click", () => {
      submitReportCalculator().catch(error => {
        document.getElementById("reportCalculatorStatus").textContent = error.message;
      });
    });

    document.getElementById("copyReportFinalButton").addEventListener("click", copyReportFinalPreview);

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

    document.getElementById("refreshAdminPanelButton").addEventListener("click", () => {
      state.adminPanelGuildId = "";
      state.adminElevationGuildId = "";
      loadAdminPanelData({ force: true }).then(() => {
        document.getElementById("adminPanelStatus").textContent = "Panel administrativo recargado.";
        renderAdminPanel();
      }).catch(error => {
        document.getElementById("adminPanelStatus").textContent = error.message;
      });
    });

    document.getElementById("permissionsGrid").addEventListener("change", event => {
      if (!event.target.matches("[data-permission-role]")) return;
      state.botPermissions = collectBotPermissions().permissions;
      document.getElementById("permissionsStatus").textContent = "Cambios sin guardar.";
      renderPermissions();
    });

    document.getElementById("permissionRoleSearch").addEventListener("input", event => {
      state.botPermissions = collectBotPermissions().permissions;
      state.permissionSearch = event.target.value;
      renderPermissions();
    });

    document.getElementById("permissionCategoryFilter").addEventListener("change", event => {
      state.botPermissions = collectBotPermissions().permissions;
      state.permissionCategoryFilter = event.target.value;
      renderPermissions();
    });

    document.getElementById("permissionStatusFilter").addEventListener("change", event => {
      state.botPermissions = collectBotPermissions().permissions;
      state.permissionStatusFilter = event.target.value;
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
