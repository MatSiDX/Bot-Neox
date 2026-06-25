(function () {
  const pages = window.NeoxDashboardPages = window.NeoxDashboardPages || {};

  pages["report-calculator"] = {
    async load(ctx, { force = false } = {}) {
      ctx.setSectionMessage("report-calculator", "Cargando calculadora...");
      await ctx.loadReportCalculatorOptions({ force });
      await ctx.loadReportCalculator();
      ctx.clearSectionMessage("report-calculator");
      ctx.renderSection("report-calculator");
    },
  };
})();
