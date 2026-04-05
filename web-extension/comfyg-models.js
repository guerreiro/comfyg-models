import { app } from "../../scripts/app.js";

app.registerExtension({
  name: "Comfyg.Models.Access",
  async setup() {
    // Mantém o botão no menu flutuante (Legacy UI)
    const menu = document.querySelector(".comfy-menu");
    if (menu && !document.getElementById("comfyg-models-legacy-btn")) {
      const btn = document.createElement("button");
      btn.id = "comfyg-models-legacy-btn";
      btn.textContent = "🖼️ Comfyg Models";
      Object.assign(btn.style, {
        backgroundColor: "rgba(16, 185, 129, 0.25)",
        border: "1px solid rgba(16, 185, 129, 0.4)",
        color: "#fff",
        margin: "2px 0",
        fontWeight: "600",
        borderRadius: "4px",
        cursor: "pointer",
        padding: "5px 10px"
      });
      btn.onclick = () => window.open("/comfyg-models", "_blank");
      const settingsBtn = Array.from(menu.querySelectorAll("button")).find(b => b.innerText.toLowerCase().includes("settings"));
      if (settingsBtn) menu.insertBefore(btn, settingsBtn);
      else menu.append(btn);
    }
  },

  async init() {
    // Volta para o Menu Lateral Esquerdo (New UI)
    if (app.extensionManager && app.extensionManager.registerSidebarTab) {
      app.extensionManager.registerSidebarTab({
        id: "comfyg-models-tab",
        icon: "pi pi-images",
        title: "Comfyg Models",
        tooltip: "Abrir Biblioteca",
        type: "custom",
        render: (el) => {
          el.style.display = "flex";
          el.style.flexDirection = "column";
          el.style.alignItems = "center";
          el.style.justifyContent = "center";
          el.style.height = "100%";
          el.style.padding = "20px";

          const btn = document.createElement("button");
          btn.textContent = "🚀 Abrir Comfyg Models";
          btn.style.padding = "12px 24px";
          btn.style.backgroundColor = "var(--p-primary-color)";
          btn.style.color = "var(--p-primary-contrast-color)";
          btn.style.border = "none";
          btn.style.borderRadius = "8px";
          btn.style.cursor = "pointer";
          btn.style.fontWeight = "bold";
          btn.style.width = "100%";

          btn.onclick = () => window.open("/comfyg-models", "_blank");
          el.appendChild(btn);
        }
      });
    }
  }
});
