(function () {
  const pages = window.NeoxDashboardPages = window.NeoxDashboardPages || {};

  pages.templates = {
    async load(ctx, { force = false } = {}) {
      const { state } = ctx;
      if (!state.guildId) return;
      if (!force && state.templateGuildId === state.guildId) return;

      ctx.setSectionMessage("templates", "Cargando plantillas...");
      const params = new URLSearchParams({ guild_id: state.guildId });
      const response = await fetch(`/api/ping-templates?${params.toString()}`, { cache: "no-store" });
      const payload = await ctx.readJsonResponse(response);
      if (!response.ok) throw new Error(payload.error || "No pude cargar las plantillas.");

      ctx.applyPingTemplatesPayload(payload);
      state.templateGuildId = state.guildId;
      ctx.clearSectionMessage("templates");
      ctx.renderSection("templates");
    },
  };
})();
