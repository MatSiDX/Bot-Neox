(function () {
  const pages = window.NeoxDashboardPages = window.NeoxDashboardPages || {};

  pages.tickets = {
    async load(ctx, { force = false } = {}) {
      const { state } = ctx;
      if (!state.guildId) return;
      if (!force && state.ticketConfigGuildId === state.guildId && !state.ticketPanelsDirty) return;

      ctx.setSectionMessage("tickets", "Cargando tickets...");
      await ctx.ensureDiscordMetadata({ force, kinds: ["channels", "categories", "emojis", "roles"] });

      const params = new URLSearchParams({ guild_id: state.guildId });
      const recordParams = new URLSearchParams({
        guild_id: state.guildId,
        page: String(state.ticketRecordFilters.page || 1),
        page_size: String(state.ticketRecordFilters.page_size || 10),
        q: state.ticketRecordSearch || ""
      });
      if (state.ticketRecordFilters.status) recordParams.set("status", state.ticketRecordFilters.status);
      if (state.ticketRecordFilters.record_type) recordParams.set("type", state.ticketRecordFilters.record_type);
      if (state.ticketRecordFilters.date_from) recordParams.set("date_from", state.ticketRecordFilters.date_from);
      if (state.ticketRecordFilters.date_to) recordParams.set("date_to", state.ticketRecordFilters.date_to);
      const [panelsResponse, recordsResponse] = await Promise.all([
        fetch(`/api/ticket-panels?${params.toString()}`, { cache: "no-store" }),
        fetch(`/api/ticket-records?${recordParams.toString()}`, { cache: "no-store" }),
      ]);

      if (panelsResponse.ok) {
        const payload = await panelsResponse.json();
        state.ticketPanels = payload.panels || [];
      }
      if (recordsResponse.ok) {
        const payload = await ctx.readJsonResponse(recordsResponse);
        ctx.applyPagePayload(state.ticketRecordFilters, payload);
        state.ticketRecords = payload.records || [];
        state.ticketRecordsSummary = payload.summary || {};
      }

      state.ticketConfigGuildId = state.guildId;
      state.ticketPanelsDirty = false;
      if (!state.ticketPanels.some(panel => panel.id === state.currentTicketPanelId)) {
        state.currentTicketPanelId = "";
        localStorage.removeItem("dashboardTicketPanelId");
      }
      ctx.clearSectionMessage("tickets");
      ctx.renderSection("tickets");
    },
  };
})();
