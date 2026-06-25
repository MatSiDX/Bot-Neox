(function () {
  const pages = window.NeoxDashboardPages = window.NeoxDashboardPages || {};

  pages.audit = {
    async load(ctx, { force = false } = {}) {
      const { state } = ctx;
      if (!state.guildId) return;
      if (!force && state.auditGuildId === state.guildId) return;

      ctx.setSectionMessage("audit", "Cargando auditoria...");
      await ctx.ensureDiscordMetadata({ force, kinds: ["channels"] });

      const params = new URLSearchParams({ guild_id: state.guildId });
      const eventParams = new URLSearchParams({
        guild_id: state.guildId,
        page: String(state.auditFilters.page || 1),
        page_size: String(state.auditFilters.page_size || 12),
        q: state.auditSearch || ""
      });
      if (state.auditFilters.record_type) eventParams.set("type", state.auditFilters.record_type);
      if (state.auditFilters.status) eventParams.set("status", state.auditFilters.status);
      if (state.auditFilters.date_from) eventParams.set("date_from", state.auditFilters.date_from);
      if (state.auditFilters.date_to) eventParams.set("date_to", state.auditFilters.date_to);
      const [auditResponse, auditEventsResponse] = await Promise.all([
        fetch(`/api/audit-config?${params.toString()}`, { cache: "no-store" }),
        fetch(`/api/audit-events?${eventParams.toString()}`, { cache: "no-store" }),
      ]);

      if (auditResponse.ok) {
        const payload = await auditResponse.json();
        state.auditCategories = payload.categories || [];
        state.auditConfig = payload.config || { channels: {} };
      }
      if (auditEventsResponse.ok) {
        const payload = await ctx.readJsonResponse(auditEventsResponse);
        ctx.applyPagePayload(state.auditFilters, payload);
        state.auditEvents = payload.events || [];
      }
      state.auditGuildId = state.guildId;
      ctx.clearSectionMessage("audit");
      ctx.renderSection("audit");
    },
  };
})();
