(function () {
  const root = document.documentElement;
  const header = document.querySelector("[data-header]");
  const nav = document.querySelector("[data-nav]");
  const navToggle = document.querySelector("[data-nav-toggle]");
  const navLinks = Array.from(document.querySelectorAll("[data-nav-link]"));
  const revealNodes = Array.from(document.querySelectorAll("[data-reveal]"));
  const demoTabs = Array.from(document.querySelectorAll("[data-demo-tab]"));
  const demoPanels = Array.from(document.querySelectorAll("[data-demo-panel]"));
  const yearNode = document.getElementById("footerYear");
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");

  function setYear() {
    if (yearNode) {
      yearNode.textContent = String(new Date().getFullYear());
    }
  }

  function syncHeaderState() {
    if (!header) {
      return;
    }
    header.classList.toggle("is-scrolled", window.scrollY > 18);
  }

  function closeNav() {
    if (!nav || !navToggle) {
      return;
    }
    nav.classList.remove("is-open");
    navToggle.setAttribute("aria-expanded", "false");
  }

  function toggleNav() {
    if (!nav || !navToggle) {
      return;
    }
    const isOpen = nav.classList.toggle("is-open");
    navToggle.setAttribute("aria-expanded", isOpen ? "true" : "false");
  }

  function activateSection(id) {
    navLinks.forEach((link) => {
      const linkId = link.getAttribute("href");
      link.classList.toggle("is-active", linkId === "#" + id);
    });
  }

  function setupSectionObserver() {
    const sections = navLinks
      .map((link) => document.querySelector(link.getAttribute("href")))
      .filter(Boolean);

    if (!sections.length) {
      return;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((left, right) => right.intersectionRatio - left.intersectionRatio)[0];
        if (visible && visible.target.id) {
          activateSection(visible.target.id);
        }
      },
      {
        rootMargin: "-22% 0px -55% 0px",
        threshold: [0.2, 0.45, 0.7],
      }
    );

    sections.forEach((section) => observer.observe(section));
  }

  function setupRevealObserver() {
    if (!revealNodes.length) {
      return;
    }

    if (reducedMotion.matches) {
      revealNodes.forEach((node) => node.classList.add("is-visible"));
      return;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting) {
            return;
          }
          entry.target.classList.add("is-visible");
          observer.unobserve(entry.target);
        });
      },
      {
        threshold: 0.18,
        rootMargin: "0px 0px -10% 0px",
      }
    );

    revealNodes.forEach((node) => observer.observe(node));
  }

  function setDemoState(tabKey) {
    demoTabs.forEach((tab) => {
      const isActive = tab.dataset.demoTab === tabKey;
      tab.classList.toggle("is-active", isActive);
      tab.setAttribute("aria-selected", isActive ? "true" : "false");
      tab.tabIndex = isActive ? 0 : -1;
    });

    demoPanels.forEach((panel) => {
      const isActive = panel.dataset.demoPanel === tabKey;
      panel.classList.toggle("is-active", isActive);
      panel.hidden = !isActive;
    });
  }

  function setupDemoTabs() {
    if (!demoTabs.length) {
      return;
    }

    demoTabs.forEach((tab) => {
      tab.addEventListener("click", () => setDemoState(tab.dataset.demoTab));
      tab.addEventListener("keydown", (event) => {
        const currentIndex = demoTabs.indexOf(tab);
        if (event.key !== "ArrowRight" && event.key !== "ArrowLeft") {
          return;
        }
        event.preventDefault();
        const direction = event.key === "ArrowRight" ? 1 : -1;
        const nextIndex = (currentIndex + direction + demoTabs.length) % demoTabs.length;
        const nextTab = demoTabs[nextIndex];
        setDemoState(nextTab.dataset.demoTab);
        nextTab.focus();
      });
    });
  }

  if (navToggle) {
    navToggle.addEventListener("click", toggleNav);
  }

  navLinks.forEach((link) => {
    link.addEventListener("click", () => {
      if (window.innerWidth <= 860) {
        closeNav();
      }
    });
  });

  window.addEventListener("scroll", syncHeaderState, { passive: true });
  window.addEventListener("resize", () => {
    if (window.innerWidth > 860) {
      closeNav();
    }
  });

  setYear();
  syncHeaderState();
  setupRevealObserver();
  setupSectionObserver();
  setupDemoTabs();
  setDemoState("economia");

  if (reducedMotion.addEventListener) {
    reducedMotion.addEventListener("change", () => {
      if (reducedMotion.matches) {
        revealNodes.forEach((node) => node.classList.add("is-visible"));
      }
    });
  }

  root.classList.add("landing-ready");
})();
