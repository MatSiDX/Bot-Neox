(function () {
  const pages = window.NeoxDashboardPages = window.NeoxDashboardPages || {};

  window.NeoxDashboardRouter = {
    load(section, context, options = {}) {
      const page = pages[section];
      if (!page || typeof page.load !== "function") {
        return Promise.resolve();
      }
      return page.load(context, options);
    }
  };
})();
