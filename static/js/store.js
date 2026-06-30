"use strict";

const brl = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });

const copyButton = document.getElementById("copy-pix");
if (copyButton) {
  copyButton.addEventListener("click", async () => {
    await navigator.clipboard.writeText(document.getElementById("pix-code").value);
    copyButton.textContent = "Copiado";
  });
}

const checkoutForm = document.getElementById("checkout-form");
const packageBenefits = document.getElementById("package-benefits");
if (packageBenefits) {
  const quantity = Number(packageBenefits.dataset.packageQuantity);
  const benefits = ["Suporte no WhatsApp"];

  if (quantity >= 10000) {
    benefits.push(
      "Acompanhamento do pedido",
      "Entrega optimizada",
      "Prioridade na fila de processamento"
    );
  } else if (quantity >= 2000) {
    benefits.push("Acompanhamento do pedido", "Entrega optimizada");
  } else {
    benefits.push("Acompanhamento básico do pedido");
  }

  const list = document.getElementById("package-benefits-list");
  list.replaceChildren(
    ...benefits.map((benefit) => {
      const item = document.createElement("li");
      item.textContent = benefit;
      return item;
    })
  );
}

const targetInput = document.getElementById("id_target");
const profileWarning = document.getElementById("profile-warning");
if (checkoutForm && targetInput && profileWarning) {
  const statusText = profileWarning.querySelector(".target-status-text");
  const statusIndicator = checkoutForm.querySelector(".target-input-status");
  const targetKind = checkoutForm.dataset.targetKind;
  const platform = checkoutForm.dataset.profilePlatform;
  const usernamePattern = /^[A-Za-z0-9._]{1,30}$/;

  const parseUrl = (target) => {
    try {
      const url = new URL(target);
      if (!["http:", "https:"].includes(url.protocol)) return null;
      return url;
    } catch {
      return null;
    }
  };

  const validProfileTarget = (target) => {
    if (!/^https?:\/\//i.test(target)) {
      return usernamePattern.test(target.startsWith("@") ? target.slice(1) : target);
    }
    const url = parseUrl(target);
    if (!url) return false;
    const parts = url.pathname.split("/").filter(Boolean);
    if (platform === "instagram") {
      return ["instagram.com", "www.instagram.com"].includes(url.hostname) &&
        parts.length === 1 && usernamePattern.test(parts[0]);
    }
    return ["tiktok.com", "www.tiktok.com"].includes(url.hostname) &&
      parts.length === 1 && parts[0].startsWith("@") && usernamePattern.test(parts[0].slice(1));
  };

  const validContentTarget = (target) => {
    const url = parseUrl(target);
    if (!url) return false;
    const parts = url.pathname.split("/").filter(Boolean);
    if (platform === "instagram") {
      const types = targetKind === "views" ? ["reel", "reels"] : ["p", "reel", "reels", "tv"];
      return ["instagram.com", "www.instagram.com"].includes(url.hostname) &&
        parts.length >= 2 && types.includes(parts[0].toLowerCase()) && Boolean(parts[1]);
    }
    if (["vm.tiktok.com", "vt.tiktok.com"].includes(url.hostname)) return parts.length > 0;
    return ["tiktok.com", "www.tiktok.com"].includes(url.hostname) &&
      parts.length >= 3 && parts[0].startsWith("@") &&
      usernamePattern.test(parts[0].slice(1)) && parts[1].toLowerCase() === "video" &&
      Boolean(parts[2]);
  };

  const setTargetStatus = (state, message) => {
    profileWarning.classList.remove("is-valid-format", "is-invalid-format");
    statusIndicator.classList.remove("is-valid-format", "is-invalid-format");
    if (state) {
      profileWarning.classList.add(state);
      statusIndicator.classList.add(state);
    }
    statusText.textContent = message;
  };

  const validateTarget = () => {
    const target = targetInput.value;
    if (!target) {
      setTargetStatus(
        "",
        "Informe o @ ou link do perfil. O perfil precisa estar público para receber o pedido."
      );
      return;
    }
    const valid = !/\s/.test(target) &&
      (targetKind === "profile" ? validProfileTarget(target) : validContentTarget(target));
    setTargetStatus(
      valid ? "is-valid-format" : "is-invalid-format",
      valid
        ? "Formato válido. Confira se este é o perfil correto e mantenha o perfil público até a conclusão do pedido."
        : "Formato inválido. Não use espaços. Informe apenas @usuario ou um link válido."
    );
  };

  targetInput.addEventListener("input", validateTarget);
  validateTarget();
}

if (checkoutForm) {
  const inputs = [...document.querySelectorAll(".upsell-input")];
  const totalOutput = document.getElementById("checkout-total");
  const summaryItems = document.getElementById("summary-items");
  const upsellFeedback = document.getElementById("upsell-feedback");
  const basePrice = Number(checkoutForm.dataset.basePrice.replace(",", "."));
  const staticItems = [...summaryItems.querySelectorAll(".summary-static-item")].map((item) =>
    item.cloneNode(true)
  );


  const parseUpsellUrl = (value) => {
    try {
      const url = new URL(value);
      if (!["http:", "https:"].includes(url.protocol)) return null;
      return url;
    } catch {
      return null;
    }
  };

  const getUpsellMeta = (checkbox) => {
    const text = [
      checkbox.dataset.serviceName || "",
      checkbox.dataset.label || "",
      checkbox.dataset.platform || "",
    ].join(" ").toLowerCase();

    const platform = checkbox.dataset.platform || (text.includes("tiktok") ? "tiktok" : "instagram");
    const isLikes = text.includes("curtida");
    const isViews = text.includes("visualiza");
    const isComments = text.includes("coment");

    return { text, platform, isLikes, isViews, isComments };
  };

  const setUpsellTargetState = (box, field, state, message) => {
    let dot = box.querySelector(".upsell-link-status");
    if (!dot) {
      dot = document.createElement("span");
      dot.className = "upsell-link-status";
      dot.setAttribute("aria-hidden", "true");
      box.append(dot);
    }

    let feedback = box.querySelector(".upsell-target-feedback");
    if (!feedback) {
      feedback = document.createElement("small");
      feedback.className = "upsell-target-feedback";
      box.append(feedback);
    }

    box.classList.remove("is-valid-format", "is-invalid-format");
    field.classList.remove("is-valid-format", "is-invalid-format");
    dot.classList.remove("is-valid-format", "is-invalid-format");

    if (state) {
      box.classList.add(state);
      field.classList.add(state);
      dot.classList.add(state);
    }

    feedback.textContent = message || "";
  };

  const validInstagramUpsellTarget = (value, meta) => {
    const url = parseUpsellUrl(value);
    if (!url) return false;

    const host = url.hostname.toLowerCase();
    const parts = url.pathname.split("/").filter(Boolean);
    if (!["instagram.com", "www.instagram.com"].includes(host)) return false;
    if (parts.length < 2) return false;

    const type = parts[0].toLowerCase();
    const code = parts[1];

    if (!code) return false;

    if (meta.isViews) {
      return ["reel", "reels"].includes(type);
    }

    return ["p", "reel", "reels", "tv"].includes(type);
  };

  const validTikTokUpsellTarget = (value) => {
    const url = parseUpsellUrl(value);
    if (!url) return false;

    const host = url.hostname.toLowerCase();
    const parts = url.pathname.split("/").filter(Boolean);

    if (["vm.tiktok.com", "vt.tiktok.com"].includes(host)) {
      return parts.length >= 1;
    }

    return ["tiktok.com", "www.tiktok.com"].includes(host) &&
      parts.length >= 3 &&
      parts[0].startsWith("@") &&
      parts[1].toLowerCase() === "video" &&
      Boolean(parts[2]);
  };

  const validateUpsellTarget = (checkbox) => {
    const wrapper = checkbox.closest(".upsell-card-wrapper") || checkbox.closest(".upsell-card")?.parentElement;
    const box = wrapper?.querySelector(".upsell-target-input");
    const field = box?.querySelector("input");

    if (!box || !field) return true;

    if (!checkbox.checked) {
      setUpsellTargetState(box, field, "", "");
      return true;
    }

    const value = field.value.trim();
    const meta = getUpsellMeta(checkbox);

    if (!value) {
      setUpsellTargetState(
        box,
        field,
        "is-invalid-format",
        meta.isViews ? "Cole o link do vídeo/Reels." : "Cole o link da publicação."
      );
      return false;
    }

    if (/\s/.test(value)) {
      setUpsellTargetState(box, field, "is-invalid-format", "Link inválido. Não use espaços.");
      return false;
    }

    const valid = meta.platform === "tiktok"
      ? validTikTokUpsellTarget(value)
      : validInstagramUpsellTarget(value, meta);

    if (!valid) {
      let message = "Link inválido para este complemento.";

      if (meta.platform === "tiktok") {
        message = "Use o link do vídeo TikTok. Ex.: https://www.tiktok.com/@usuario/video/...";
      } else if (meta.isViews) {
        message = "Use o link do Reels/vídeo. Ex.: https://www.instagram.com/reel/...";
      } else {
        message = "Use o link da publicação. Ex.: https://www.instagram.com/p/...";
      }

      setUpsellTargetState(box, field, "is-invalid-format", message);
      return false;
    }

    setUpsellTargetState(box, field, "is-valid-format", "Link válido para este complemento.");
    return true;
  };


  const showUpsellFeedback = (message = "") => {
    if (upsellFeedback) upsellFeedback.textContent = message;
  };

  const updateCheckout = () => {
    let total = basePrice;
    summaryItems.replaceChildren(...staticItems.map((item) => item.cloneNode(true)));
    inputs.forEach((input) => {
      const label = input.closest(".upsell-card");
      const toggle = label.querySelector(".upsell-toggle");
      const icon = label.querySelector(".upsell-icon");
      toggle.textContent = input.checked ? "Remover" : "Adicionar";
      icon.textContent = input.checked ? "✓" : input.dataset.icon;
      label.classList.toggle("is-selected", input.checked);
      
      // Handle upsell target input visibility and state
      let targetInput = null;

      const wrapper = input.closest(".upsell-card-wrapper");
      if (wrapper) {
        targetInput = wrapper.querySelector(".upsell-target-input");
      }

      if (!targetInput && label.nextElementSibling && label.nextElementSibling.classList.contains("upsell-target-input")) {
        targetInput = label.nextElementSibling;
      }

      if (!targetInput && label.parentElement) {
        const ownInput = label.parentElement.querySelector(`input[name="upsell_target_${input.value}"]`);
        if (ownInput) {
          targetInput = ownInput.closest(".upsell-target-input");
        }
      }

      if (targetInput) {
        const inputField = targetInput.querySelector("input");
        targetInput.style.display = input.checked ? "block" : "none";

        if (inputField) {
          inputField.disabled = !input.checked;
          inputField.required = input.checked;

          if (!input.checked) {
            inputField.value = "";
          }
        }
      }

      validateUpsellTarget(input);
      if (!input.checked) return;
      const price = Number(input.dataset.price.replace(",", "."));
      total += price;
      const item = document.createElement("div");
      const name = document.createElement("span");
      const amount = document.createElement("b");
      name.textContent = input.dataset.label;
      amount.textContent = brl.format(price);
      item.append(name, amount);
      summaryItems.append(item);
    });
    totalOutput.textContent = brl.format(total);
  };

  const validateUpsellSelection = (input) => {
    showUpsellFeedback();
    if (!input.checked) return true;

    const selected = inputs.filter((candidate) => candidate.checked);
    const sameService = selected.filter(
      (candidate) => candidate.dataset.serviceKey === input.dataset.serviceKey
    );
    if (sameService.length > 1) {
      input.checked = false;
      showUpsellFeedback("Escolha somente um pacote por serviço complementar.");
      return false;
    }
    if (selected.length > 3) {
      input.checked = false;
      showUpsellFeedback("Você pode adicionar no máximo três complementos.");
      return false;
    }
    return true;
  };

  inputs.forEach((input) => {
    input.addEventListener("change", () => {
      validateUpsellSelection(input);
      updateCheckout();
      validateUpsellTarget(input);
    });

    const wrapper = input.closest(".upsell-card-wrapper") || input.closest(".upsell-card")?.parentElement;
    const targetBox = wrapper?.querySelector(".upsell-target-input");
    const field = targetBox?.querySelector("input");

    if (field) {
      field.addEventListener("input", () => validateUpsellTarget(input));
      field.addEventListener("blur", () => validateUpsellTarget(input));
    }
  });

  checkoutForm.addEventListener("submit", (event) => {
    let firstInvalid = null;

    inputs.forEach((input) => {
      if (input.checked && !validateUpsellTarget(input)) {
        if (!firstInvalid) firstInvalid = input;
      }
    });

    if (firstInvalid) {
      event.preventDefault();
      showUpsellFeedback("Corrija os links dos complementos antes de finalizar.");

      const wrapper = firstInvalid.closest(".upsell-card-wrapper") || firstInvalid.closest(".upsell-card")?.parentElement;
      const field = wrapper?.querySelector(".upsell-target-input input");

      if (field) {
        field.focus();
        field.scrollIntoView({ behavior: "smooth", block: "center" });
      }
    }
  });

  updateCheckout();
}

// ── Brindes opcionais ──────────────────────────────────────────────────────────
const bonusSection = document.getElementById("bonus-opt-list");
if (bonusSection && checkoutForm) {
  const bonusCheckboxes = [...bonusSection.querySelectorAll(".bonus-checkbox")];
  const bonusFeedback = document.getElementById("bonus-opt-feedback");
  const summaryItems = document.getElementById("summary-items");
  const totalOutput = document.getElementById("checkout-total");
  const bonusBasePrice = Number(checkoutForm.dataset.basePrice.replace(",", "."));
  const platform = checkoutForm.dataset.profilePlatform;

  const parseUrl = (v) => {
    try {
      const u = new URL(v);
      return ["http:", "https:"].includes(u.protocol) ? u : null;
    } catch { return null; }
  };

  const usernamePattern = /^[A-Za-z0-9._]{1,30}$/;

  const validBonusProfileTarget = (value) => {
    if (!/^https?:\/\//i.test(value)) {
      const user = value.startsWith("@") ? value.slice(1) : value;
      return usernamePattern.test(user);
    }
    const url = parseUrl(value);
    if (!url) return false;
    const parts = url.pathname.split("/").filter(Boolean);
    if (platform === "instagram") {
      return ["instagram.com", "www.instagram.com"].includes(url.hostname) &&
        parts.length === 1 && usernamePattern.test(parts[0]);
    }
    return ["tiktok.com", "www.tiktok.com"].includes(url.hostname) &&
      parts.length === 1 && parts[0].startsWith("@") && usernamePattern.test(parts[0].slice(1));
  };

  const validBonusContentTarget = (value, kind) => {
    const url = parseUrl(value);
    if (!url) return false;
    const host = url.hostname.toLowerCase();
    const parts = url.pathname.split("/").filter(Boolean);
    if (platform === "instagram") {
      if (!["instagram.com", "www.instagram.com"].includes(host) || parts.length < 2) return false;
      const type = parts[0].toLowerCase();
      return kind === "views"
        ? ["reel", "reels"].includes(type)
        : ["p", "reel", "reels", "tv"].includes(type);
    }
    if (["vm.tiktok.com", "vt.tiktok.com"].includes(host)) return parts.length > 0;
    return ["tiktok.com", "www.tiktok.com"].includes(host) &&
      parts.length >= 3 && parts[0].startsWith("@") &&
      usernamePattern.test(parts[0].slice(1)) && parts[1].toLowerCase() === "video" &&
      Boolean(parts[2]);
  };

  const validateBonusTarget = (checkbox) => {
    const wrapper = checkbox.closest(".bonus-opt-card-wrapper");
    const wrap = wrapper?.querySelector(".bonus-opt-target-wrap");
    const field = wrap?.querySelector(".bonus-target-input");
    if (!wrap || !field) return true;
    if (!checkbox.checked) return true;

    const value = field.value.trim();
    const kind = checkbox.dataset.kind;

    let dot = wrap.querySelector(".bonus-link-status");
    if (!dot) {
      dot = document.createElement("span");
      dot.className = "bonus-link-status";
      dot.setAttribute("aria-hidden", "true");
      wrap.prepend(dot);
    }
    let msg = wrap.querySelector(".bonus-target-feedback");
    if (!msg) {
      msg = document.createElement("small");
      msg.className = "bonus-target-feedback";
      wrap.append(msg);
    }

    const setState = (state, text) => {
      wrap.classList.remove("bonus-is-valid", "bonus-is-invalid");
      field.classList.remove("bonus-is-valid", "bonus-is-invalid");
      dot.classList.remove("bonus-is-valid", "bonus-is-invalid");
      if (state) { wrap.classList.add(state); field.classList.add(state); dot.classList.add(state); }
      msg.textContent = text;
    };

    if (!value) {
      setState("bonus-is-invalid", kind === "profile"
        ? "Informe o @ ou link do perfil."
        : kind === "views"
          ? "Cole o link do Reels ou vídeo."
          : "Cole o link da publicação.");
      return false;
    }
    if (/\s/.test(value)) { setState("bonus-is-invalid", "Sem espaços no link."); return false; }

    const ok = kind === "profile"
      ? validBonusProfileTarget(value)
      : validBonusContentTarget(value, kind);

    if (!ok) {
      let hint = "Link inválido.";
      if (kind === "profile") hint = "Use @usuario ou o link do perfil.";
      else if (kind === "views") hint = "Use o link do Reels. Ex.: instagram.com/reel/...";
      else hint = "Use o link da publicação. Ex.: instagram.com/p/...";
      setState("bonus-is-invalid", hint);
      return false;
    }
    setState("bonus-is-valid", "Destino válido.");
    return true;
  };

  const updateBonusSummary = () => {
    summaryItems.querySelectorAll(".summary-bonus-opt-item").forEach((el) => el.remove());
    let bonusTotal = 0;
    bonusCheckboxes.forEach((cb) => {
      if (!cb.checked) return;
      const price = Number(cb.dataset.price || 0);
      bonusTotal += price;
      const item = document.createElement("div");
      item.className = "summary-bonus-opt-item";
      const name = document.createElement("span");
      const priceEl = document.createElement("b");
      name.textContent = cb.dataset.label;
      priceEl.textContent = brl.format(price);
      item.append(name, priceEl);
      summaryItems.append(item);
    });
    // Recalculate full total: base + upsells + bonuses
    const upsellTotal = [...document.querySelectorAll(".upsell-input")]
      .filter((inp) => inp.checked)
      .reduce((acc, inp) => acc + Number(inp.dataset.price.replace(",", ".")), 0);
    if (totalOutput) totalOutput.textContent = brl.format(bonusBasePrice + upsellTotal + bonusTotal);
  };

  // After any upsell change, updateCheckout() clears the summary — re-add bonus items afterward
  document.querySelectorAll(".upsell-input").forEach((inp) => {
    inp.addEventListener("change", () => setTimeout(updateBonusSummary, 0));
  });

  bonusCheckboxes.forEach((cb) => {
    cb.addEventListener("change", () => {
      const wrapper = cb.closest(".bonus-opt-card-wrapper");
      const card = wrapper?.querySelector(".bonus-opt-card");
      const wrap = wrapper?.querySelector(".bonus-opt-target-wrap");
      const field = wrap?.querySelector(".bonus-target-input");
      const toggle = card?.querySelector(".bonus-opt-toggle");

      const checked = cb.checked;
      card?.classList.toggle("bonus-is-selected", checked);
      if (toggle) toggle.textContent = checked ? "Remover" : "Adicionar";
      if (wrap) wrap.style.display = checked ? "block" : "none";
      if (field) {
        field.disabled = !checked;
        field.required = checked;
        if (!checked) field.value = "";
      }
      updateBonusSummary();
    });

    const wrapper = cb.closest(".bonus-opt-card-wrapper");
    const field = wrapper?.querySelector(".bonus-target-input");
    if (field) {
      field.addEventListener("input", () => validateBonusTarget(cb));
      field.addEventListener("blur", () => validateBonusTarget(cb));
    }
  });

  // Hook into form submit to block if bonus checked but target invalid
  checkoutForm.addEventListener("submit", (event) => {
    let firstInvalid = null;
    bonusCheckboxes.forEach((cb) => {
      if (cb.checked && !validateBonusTarget(cb)) {
        if (!firstInvalid) firstInvalid = cb;
      }
    });
    if (firstInvalid) {
      event.preventDefault();
      if (bonusFeedback) bonusFeedback.textContent = "Informe o destino do brinde antes de finalizar.";
      const wrapper = firstInvalid.closest(".bonus-opt-card-wrapper");
      const field = wrapper?.querySelector(".bonus-target-input");
      if (field) { field.focus(); field.scrollIntoView({ behavior: "smooth", block: "center" }); }
    } else {
      if (bonusFeedback) bonusFeedback.textContent = "";
    }
  });

  updateBonusSummary();
}

const activityToast = document.getElementById("activity-toast");
if (activityToast && !checkoutForm) {
  const activityName = document.getElementById("activity-name");
  const activityMessage = document.getElementById("activity-message");

  const variavel_cliente = [
    "Mariana",
    "Lucas",
    "Ana Clara",
    "Pedro Henrique",
    "Rafael Mendes",
    "Camila",
    "João Victor",
    "Larissa",
    "Felipe Santos",
    "Amanda",
    "Bruno Oliveira",
    "Isabela Rocha",
    "Mateus",
    "Juliana Alves",
    "Renan Costa",
    "Carolina",
    "Vitor Hugo",
    "Fernanda Lopes",
    "Thiago",
    "Bianca Moreira",
    "Eduardo",
    "Letícia Ramos",
    "Gabriel",
    "Natália",
    "Vinícius",
    "Sofia Martins",
    "Gustavo",
    "Helena",
    "Daniel Souza",
    "Beatriz",
    "Arthur",
    "Luana",
    "Caio",
    "Melissa",
    "Rodrigo Lima",
    "Yasmin",
    "André",
    "Manuela",
    "Diego",
    "Priscila"
  ];

  const variavel_pacotes = {
    pequenos: [
      { quantidade: "250", servico: "curtidas para Instagram" },
      { quantidade: "500", servico: "seguidores para Instagram" },
      { quantidade: "500", servico: "curtidas para Instagram" },
      { quantidade: "1.000", servico: "seguidores para Instagram" },
      { quantidade: "3.000", servico: "visualizações para Reels" }
    ],
    medios: [
      { quantidade: "1.500", servico: "seguidores para Instagram" },
      { quantidade: "2.000", servico: "seguidores para Instagram" },
      { quantidade: "1.000", servico: "curtidas para Instagram" },
      { quantidade: "5.000", servico: "visualizações para Reels" }
    ],
    grandes: [
      { quantidade: "3.000", servico: "seguidores para Instagram" },
      { quantidade: "5.000", servico: "seguidores para Instagram" },
      { quantidade: "10.000", servico: "visualizações para Reels" },
      { quantidade: "10.000", servico: "seguidores para Instagram" }
    ]
  };

  const pesos_categorias = [
    { categoria: "pequenos", peso: 8 },
    { categoria: "medios", peso: 4 },
    { categoria: "grandes", peso: 1 }
  ];

  const variavel_modelos = [
    "Comprou {quantidade} {servico}",
    "Acabou de comprar {quantidade} {servico}",
    "Finalizou um pedido de {quantidade} {servico}",
    "Pagou via Pix um pacote de {quantidade} {servico}"
  ];

  let ultimoNome = "";
  let ultimaMensagem = "";
  let hideTimer = null;
  let nextTimer = null;
  let resetTimer = null;

  const randomBetween = (min, max) => Math.floor(Math.random() * (max - min + 1)) + min;

  const clearToastTimers = () => {
    window.clearTimeout(hideTimer);
    window.clearTimeout(nextTimer);
    window.clearTimeout(resetTimer);
    hideTimer = null;
    nextTimer = null;
    resetTimer = null;
  };

  const escolherItem = (lista, ultimoValor = "") => {
    if (!Array.isArray(lista) || !lista.length) return "";

    let item = lista[randomBetween(0, lista.length - 1)];

    if (lista.length > 1) {
      let tentativas = 0;
      while (item === ultimoValor && tentativas < 8) {
        item = lista[randomBetween(0, lista.length - 1)];
        tentativas += 1;
      }
    }

    return item;
  };

  const escolherCategoria = () => {
    const pesoTotal = pesos_categorias.reduce((soma, item) => soma + item.peso, 0);
    let sorteio = Math.random() * pesoTotal;

    for (const item of pesos_categorias) {
      sorteio -= item.peso;
      if (sorteio <= 0) return item.categoria;
    }

    return "pequenos";
  };

  const escolherPacote = () => {
    const categoria = escolherCategoria();
    const pacotesDaCategoria = variavel_pacotes[categoria] || variavel_pacotes.pequenos;
    const pacote = pacotesDaCategoria[randomBetween(0, pacotesDaCategoria.length - 1)];

    if (!pacote || !pacote.quantidade || !pacote.servico) {
      return { quantidade: "500", servico: "seguidores para Instagram" };
    }

    return pacote;
  };

  const montarMensagem = () => {
    const pacote = escolherPacote();
    const modelo = escolherItem(variavel_modelos);

    return modelo
      .replace("{quantidade}", pacote.quantidade)
      .replace("{servico}", pacote.servico);
  };

  const resetToast = () => {
    clearToastTimers();
    activityToast.classList.remove("is-visible");
    activityToast.classList.remove("is-leaving");
    activityToast.hidden = true;
  };

  const hideToast = () => {
    activityToast.classList.remove("is-visible");
    activityToast.classList.add("is-leaving");

    resetTimer = window.setTimeout(() => {
      activityToast.hidden = true;
      activityToast.classList.remove("is-leaving");
    }, 760);
  };

  const showToast = () => {
    if (document.hidden) return;

    const nome = escolherItem(variavel_cliente, ultimoNome);
    let mensagem = montarMensagem();

    let tentativas = 0;
    while (mensagem === ultimaMensagem && tentativas < 8) {
      mensagem = montarMensagem();
      tentativas += 1;
    }

    ultimoNome = nome;
    ultimaMensagem = mensagem;

    if (activityName) {
      activityName.hidden = false;
      activityName.textContent = nome;
    }

    if (activityMessage) activityMessage.textContent = mensagem;

    activityToast.hidden = false;
    activityToast.classList.remove("is-leaving");

    clearToastTimers();

    requestAnimationFrame(() => {
      activityToast.classList.add("is-visible");
    });

    const tempoVisivel = randomBetween(4800, 6500);
    const proximoDelay = randomBetween(8000, 25000);

    hideTimer = window.setTimeout(() => {
      hideToast();
      nextTimer = window.setTimeout(showToast, proximoDelay);
    }, tempoVisivel);
  };

  resetToast();
  nextTimer = window.setTimeout(showToast, randomBetween(3500, 7000));

  window.addEventListener("pagehide", resetToast);

  window.addEventListener("pageshow", () => {
    resetToast();
    nextTimer = window.setTimeout(showToast, randomBetween(3500, 7000));
  });

  document.addEventListener("visibilitychange", () => {
    if (document.hidden) {
      resetToast();
    } else {
      nextTimer = window.setTimeout(showToast, randomBetween(3500, 7000));
    }
  });

  window.addEventListener("beforeunload", resetToast);
}
/* ===== FAQ acordeão ===== */
document.querySelectorAll(".faq-trigger").forEach((trigger) => {
  trigger.addEventListener("click", () => {
    const expanded = trigger.getAttribute("aria-expanded") === "true";
    const body = trigger.nextElementSibling;

    trigger.setAttribute("aria-expanded", String(!expanded));
    if (expanded) {
      body.style.maxHeight = null;
    } else {
      body.style.maxHeight = body.scrollHeight + "px";
    }
  });
});




