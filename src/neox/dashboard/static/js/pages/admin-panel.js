(function () {
  const pages = window.NeoxDashboardPages = window.NeoxDashboardPages || {};
  const CHANNEL_CACHE_TTL_MS = 5 * 60 * 1000;
  const CHANNEL_LOAD_TIMEOUT_MS = 15000;

  function adminAccessHeaders(state, extra = {}) {
    const headers = { ...extra };
    if (state.csrfToken) headers["X-CSRF-Token"] = state.csrfToken;
    return headers;
  }

  async function fetchWithTimeout(url, options = {}, timeoutMs = CHANNEL_LOAD_TIMEOUT_MS) {
    const controller = new AbortController();
    const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);
    try {
      return await fetch(url, { ...options, signal: controller.signal });
    } finally {
      window.clearTimeout(timeoutId);
    }
  }

  async function loadAdminAccessStatus(ctx, { force = false } = {}) {
    const { state } = ctx;
    const guildId = String(state.guildId || "");
    if (!guildId) {
      state.adminElevation = {
        active: false,
        message: "Selecciona un servidor antes de abrir el panel administrativo.",
      };
      ctx.renderSection("admin-panel");
      return state.adminElevation;
    }

    const params = new URLSearchParams({ guild_id: guildId });
    const response = await fetch(`/api/admin-access/status?${params.toString()}`, { cache: "no-store" });
    const payload = await ctx.readJsonResponse(response);
    if (!response.ok) throw new Error(payload.error || "No pude validar el acceso reforzado.");

    state.adminElevation = payload.status || { elevated: false };
    state.adminElevationGuildId = guildId;
    ctx.renderSection("admin-panel");
    return state.adminElevation;
  }

  async function loadMessageChannels(ctx, { force = false } = {}) {
    const { state } = ctx;
    const guildId = String(state.guildId || "");
    if (!guildId) return;

    state.adminMessageChannelsCache = state.adminMessageChannelsCache || {};
    const cached = state.adminMessageChannelsCache[guildId];
    if (!force && cached && Date.now() - Number(cached.loadedAt || 0) < CHANNEL_CACHE_TTL_MS) {
      state.adminMessageChannels = cached.channels || [];
      state.adminMessageChannelsStatus = "loaded";
      state.adminMessageChannelsError = "";
      ctx.renderSection("admin-panel");
      return;
    }

    state.adminMessageChannels = [];
    state.adminMessageChannelsStatus = "loading";
    state.adminMessageChannelsError = "";
    ctx.renderSection("admin-panel");

    const params = new URLSearchParams({ guild_id: guildId });
    if (force) params.set("refresh", "1");
    try {
      const response = await fetchWithTimeout(`/api/admin/message-channels?${params.toString()}`, { cache: "no-store" });
      const payload = await ctx.readJsonResponse(response);
      if (!response.ok) throw new Error(payload.error || "No pude cargar los canales permitidos.");
      if (String(state.guildId || "") !== guildId) return;

      state.adminMessageChannels = payload.channels || [];
      state.adminMessageChannelsStatus = "loaded";
      state.adminMessageChannelsError = "";
      state.adminMessageChannelsCache[guildId] = {
        channels: state.adminMessageChannels,
        loadedAt: Date.now(),
      };
    } catch (error) {
      if (String(state.guildId || "") !== guildId) return;
      state.adminMessageChannels = [];
      state.adminMessageChannelsStatus = "error";
      state.adminMessageChannelsError = error.name === "AbortError"
        ? "La carga de canales tardo demasiado. Reintenta en unos segundos."
        : (error.message || "No pude cargar los canales permitidos.");
    }
    ctx.renderSection("admin-panel");
  }

  async function loadServerBackups(ctx) {
    const { state } = ctx;
    const guildId = String(state.guildId || "");
    if (!guildId) return;

    state.adminServerBackupsStatus = "loading";
    state.adminServerBackupsError = "";
    ctx.renderSection("admin-panel");

    try {
      const params = new URLSearchParams({ guild_id: guildId });
      const response = await fetch(`/api/admin/server-backups?${params.toString()}`, { cache: "no-store" });
      const payload = await ctx.readJsonResponse(response);
      if (!response.ok) throw new Error(payload.error || "No pude cargar los backups.");
      if (String(state.guildId || "") !== guildId) return;

      state.adminServerBackups = payload.backups || [];
      state.adminServerBackupsMax = payload.max_backups || 2;
      state.adminServerBackupsStatus = "loaded";
      state.adminServerBackupsError = "";
    } catch (error) {
      if (String(state.guildId || "") !== guildId) return;
      state.adminServerBackups = [];
      state.adminServerBackupsStatus = "error";
      state.adminServerBackupsError = error.message || "No pude cargar los backups.";
    }
    ctx.renderSection("admin-panel");
  }

  async function loadProtectedData(ctx, { force = false } = {}) {
    const { state } = ctx;
    if (!force && state.adminPanelGuildId === state.guildId && state.adminGuilds.length && state.adminOverview) {
      return;
    }

    const guildsResponse = await fetch("/api/admin/guilds", { cache: "no-store" });
    const guildsPayload = await ctx.readJsonResponse(guildsResponse);
    if (!guildsResponse.ok) throw new Error(guildsPayload.error || "No pude cargar los servidores administrables.");

    state.adminGuilds = guildsPayload.guilds || [];
    const availableIds = new Set(state.adminGuilds.map(guild => String(guild.id || "")));
    if (!availableIds.size) {
      state.adminOverview = null;
      state.adminPanelGuildId = "";
      ctx.setSectionMessage("admin-panel", "No hay servidores administrables disponibles.");
      ctx.renderSection("admin-panel");
      return;
    }

    if (!state.guildId || !availableIds.has(String(state.guildId))) {
      state.guildId = availableIds.has(String(guildsPayload.selectedGuildId || ""))
        ? String(guildsPayload.selectedGuildId)
        : String(state.adminGuilds[0].id || "");
      if (state.guildId) localStorage.setItem("dashboardGuildId", state.guildId);
      else localStorage.removeItem("dashboardGuildId");
      if (ctx.loadDashboardAccess) await ctx.loadDashboardAccess();
      ctx.renderShell();
    }

    const params = new URLSearchParams({ guild_id: state.guildId });
    const response = await fetch(`/api/admin/overview?${params.toString()}`, { cache: "no-store" });
    const payload = await ctx.readJsonResponse(response);
    if (!response.ok) throw new Error(payload.error || "No pude cargar el panel administrativo.");

    state.adminOverview = payload;
    state.adminPanelGuildId = state.guildId;
    ctx.clearSectionMessage("admin-panel");
    ctx.renderSection("admin-panel");
    loadServerBackups(ctx);
    loadMessageChannels(ctx, { force: false });
  }

  async function submitElevation(ctx, password) {
    const { state } = ctx;
    const guildId = String(state.guildId || "");
    const response = await fetch("/api/admin-access/verify", {
      method: "POST",
      headers: adminAccessHeaders(state, { "Content-Type": "application/json" }),
      body: JSON.stringify({
        guild_id: guildId,
        password,
      }),
    });
    const payload = await ctx.readJsonResponse(response);
    if (!response.ok) throw new Error(payload.error || "No pude validar la clave secundaria.");

    state.adminElevation = payload.status || { elevated: false };
    state.adminElevationGuildId = guildId;
    return state.adminElevation;
  }

  async function logoutElevation(ctx) {
    const { state } = ctx;
    const response = await fetch("/api/admin-access/logout", {
      method: "POST",
      headers: adminAccessHeaders(state, { "Content-Type": "application/json" }),
      body: JSON.stringify({}),
    });
    const payload = await ctx.readJsonResponse(response);
    if (!response.ok) throw new Error(payload.error || "No pude cerrar el acceso elevado.");

    state.adminElevation = {
      ...(state.adminElevation || {}),
      elevated: false,
      expiresAt: "",
      expiresInSeconds: 0,
      message: "Acceso elevado cerrado.",
    };
    state.adminOverview = null;
    state.adminPanelGuildId = "";
    state.adminGuilds = [];
    state.adminMessageChannels = [];
    state.adminMessageChannelsStatus = "idle";
    state.adminMessageChannelsError = "";
    state.adminServerBackups = [];
    state.adminServerBackupsStatus = "idle";
    state.adminServerBackupsError = "";
    return payload;
  }

  pages["admin-panel"] = {
    loadMessageChannels,
    loadServerBackups,
    loadAdminAccessStatus,
    submitElevation,
    logoutElevation,

    async load(ctx, { force = false } = {}) {
      const { state } = ctx;
      ctx.setSectionMessage("admin-panel", "Validando acceso reforzado...");
      const status = await loadAdminAccessStatus(ctx, { force });
      if (!status?.elevated) {
        state.adminOverview = null;
        state.adminPanelGuildId = "";
        ctx.clearSectionMessage("admin-panel");
        ctx.renderSection("admin-panel");
        return;
      }

      ctx.setSectionMessage("admin-panel", "Cargando panel administrativo...");
      await loadProtectedData(ctx, { force });
    },
  };
})();
