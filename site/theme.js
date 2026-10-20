(() => {
  const root = document.documentElement;
  const key = "brawl-theme";
  const system = window.matchMedia("(prefers-color-scheme: dark)");
  const valid = (value) => value === "dark" || value === "light";
  let preference = null;
  try {
    const saved = localStorage.getItem(key);
    if (valid(saved)) preference = saved;
  } catch (e) {}

  function applyTheme() {
    root.dataset.theme = preference || (system.matches ? "dark" : "light");
    for (const button of document.querySelectorAll("[data-set-theme]")) {
      button.setAttribute("aria-pressed", String(button.dataset.setTheme === root.dataset.theme));
    }
  }
  // Restore the selected colors before the page is painted.
  applyTheme();

  const labels = {
    ja: { theme: "カラーテーマ", dark: "ブラック", light: "ホワイト" },
    en: { theme: "Color theme", dark: "Black", light: "White" },
    zh: { theme: "颜色主题", dark: "黑色", light: "白色" },
    ko: { theme: "색상 테마", dark: "블랙", light: "화이트" },
  };
  function updateLabels() {
    const words = labels[root.lang.slice(0, 2)] || labels.en;
    for (const control of document.querySelectorAll("[data-theme-switch]")) {
      control.setAttribute("aria-label", words.theme);
      for (const button of control.querySelectorAll("[data-set-theme]")) {
        button.querySelector("[data-theme-label]").textContent = words[button.dataset.setTheme];
      }
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    for (const control of document.querySelectorAll("[data-theme-switch]")) {
      for (const button of control.querySelectorAll("[data-set-theme]")) {
        button.addEventListener("click", () => {
          preference = button.dataset.setTheme;
          try { localStorage.setItem(key, preference); } catch (e) {}
          applyTheme();
        });
      }
      control.hidden = false;
    }
    applyTheme();
    updateLabels();
    new MutationObserver(updateLabels).observe(root, { attributes: true, attributeFilter: ["lang"] });
  });

  system.addEventListener("change", () => { if (!preference) applyTheme(); });
  window.addEventListener("storage", (event) => {
    if (event.key !== key && event.key !== null) return;
    preference = valid(event.newValue) ? event.newValue : null;
    applyTheme();
  });
  window.addEventListener("pageshow", (event) => {
    if (!event.persisted) return;
    try {
      const saved = localStorage.getItem(key);
      preference = valid(saved) ? saved : null;
    } catch (e) {}
    applyTheme();
  });
})();
