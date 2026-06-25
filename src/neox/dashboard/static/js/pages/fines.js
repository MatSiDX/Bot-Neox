(function () {
  const pages = window.NeoxDashboardPages = window.NeoxDashboardPages || {};

  pages.fines = {
    async load(ctx, { force = false } = {}) {
      const { state } = ctx;
      if (!state.guildId) return;
      if (!force && state.fineConfigGuildId === state.guildId) return;

      const params = new URLSearchParams({ guild_id: state.guildId });
      const response = await fetch(`/api/fine-config?${params.toString()}`, { cache: "no-store" });
      if (!response.ok) {
        const payload = await ctx.readJsonResponse(response);
        throw new Error(payload.error || "No pude cargar la configuracion de multas.");
      }

      state.fineConfig = await response.json();
      state.fineConfigGuildId = state.guildId;
    },
  };
})();
