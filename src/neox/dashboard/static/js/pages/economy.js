(function () {
  const pages = window.NeoxDashboardPages = window.NeoxDashboardPages || {};

  pages.economy = {
    async load(ctx) {
      const { state } = ctx;
      if (!state.guildId) {
        state.data = ctx.createEmptyDashboardData({
          guilds: state.data?.guilds || [],
          viewer: state.data?.viewer || {},
          access: state.data?.access || {},
        });
        ctx.renderShell();
        ctx.renderSection("economy");
        return;
      }

      ctx.setSectionMessage("economy", "Cargando economia...");
      const filters = ctx.currentEconomyPageState();
      const summaryParams = new URLSearchParams({ guild_id: state.guildId });
      const listParams = new URLSearchParams({
        guild_id: state.guildId,
        tab: state.tab,
        page: String(filters.page || 1),
        page_size: String(filters.page_size || 25),
        q: state.search || ""
      });
      if (filters.status) listParams.set("status", filters.status);
      if (filters.record_type) listParams.set("type", filters.record_type);
      if (filters.date_from) listParams.set("date_from", filters.date_from);
      if (filters.date_to) listParams.set("date_to", filters.date_to);

      const [summaryResponse, listResponse] = await Promise.all([
        fetch(`/api/economy/summary?${summaryParams.toString()}`, { cache: "no-store" }),
        fetch(`/api/economy/list?${listParams.toString()}`, { cache: "no-store" })
      ]);
      if (
        summaryResponse.status === 401 || summaryResponse.status === 503 ||
        listResponse.status === 401 || listResponse.status === 503
      ) {
        window.location.href = "/";
        return;
      }
      const summaryPayload = await ctx.readJsonResponse(summaryResponse);
      const listPayload = await ctx.readJsonResponse(listResponse);
      if (!summaryResponse.ok) throw new Error(summaryPayload.error || "No se pudo cargar el resumen de economia.");
      if (!listResponse.ok) throw new Error(listPayload.error || "No se pudo cargar la lista de economia.");

      state.data = ctx.createEmptyDashboardData({
        ...state.data,
        selectedGuildId: state.guildId,
        [state.tab]: listPayload.items || [],
        totals: summaryPayload.totals || state.data?.totals || { players: 0, items: 0, silver: 0, total: 0 },
        updatedAt: summaryPayload.updatedAt || state.data?.updatedAt || "",
        viewer: state.data?.viewer || {},
        access: state.data?.access || {},
      });
      ctx.applyPagePayload(filters, listPayload);
      state.economyGuildId = state.guildId;
      ctx.clearSectionMessage("economy");
      ctx.renderShell();
      ctx.renderSection("economy");
    },
  };
})();
