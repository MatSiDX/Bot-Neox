(function () {
  const pages = window.NeoxDashboardPages = window.NeoxDashboardPages || {};

  pages.permissions = {
    async load(ctx, { force = false } = {}) {
      const { state } = ctx;
      if (!state.guildId) return;
      if (!force && state.permissionsGuildId === state.guildId) return;

      ctx.setSectionMessage("permissions", "Cargando permisos...");
      await ctx.ensureDiscordMetadata({ force, kinds: ["roles"] });

      const params = new URLSearchParams({ guild_id: state.guildId });
      const response = await fetch(`/api/bot-permissions?${params.toString()}`, { cache: "no-store" });
      const payload = await ctx.readJsonResponse(response);
      if (!response.ok) throw new Error(payload.error || "No pude cargar los permisos.");

      state.botPermissions = payload.permissions || {};
      state.botPermissionOptions = payload.options || [];
      state.permissionsGuildId = state.guildId;
      ctx.clearSectionMessage("permissions");
      ctx.renderSection("permissions");
    },
  };
})();
