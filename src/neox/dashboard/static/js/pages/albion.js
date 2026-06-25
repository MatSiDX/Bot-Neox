(function () {
  const pages = window.NeoxDashboardPages = window.NeoxDashboardPages || {};

  pages.registration = {
    async load(ctx, { force = false } = {}) {
      const { state } = ctx;
      if (!state.guildId) return;
      if (!force && state.albionRegistrationGuildId === state.guildId) return;

      ctx.setSectionMessage("registration", "Cargando registro de Albion...");
      await ctx.ensureDiscordMetadata({ force, kinds: ["channels", "roles"] });

      const params = new URLSearchParams({
        guild_id: state.guildId,
        page: String(state.albionRegistrationFilters.page || 1),
        page_size: String(state.albionRegistrationFilters.page_size || 15),
        q: state.albionRegistrationSearch || ""
      });
      if (state.albionRegistrationFilters.status) params.set("status", state.albionRegistrationFilters.status);
      if (state.albionRegistrationFilters.date_from) params.set("date_from", state.albionRegistrationFilters.date_from);
      if (state.albionRegistrationFilters.date_to) params.set("date_to", state.albionRegistrationFilters.date_to);
      const response = await fetch(`/api/albion-registration?${params.toString()}`, { cache: "no-store" });
      const payload = await ctx.readJsonResponse(response);
      if (!response.ok) throw new Error(payload.error || "No pude cargar el registro de Albion.");

      state.albionRegistrationConfig = payload.config || null;
      ctx.applyPagePayload(state.albionRegistrationFilters, payload);
      state.albionRegistrations = payload.registrations || [];
      state.albionRegistrationGuildId = state.guildId;
      ctx.clearSectionMessage("registration");
      ctx.renderSection("registration");
    },
  };
})();
