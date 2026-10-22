(() => {
  const root = document.documentElement;
  root.classList.add("js");
  const landingPage = document.getElementById("landingPage");
  const authShell = document.getElementById("authShell");
  const appShell = document.getElementById("appShell");
  const csrfMeta = document.querySelector('meta[name="csrf-token"]');
  const authForm = document.getElementById("authForm");
  const authError = document.getElementById("authError");
  const toast = document.getElementById("toast");
  const heroVideo = document.getElementById("landingHeroVideo");
  const landingVideos = [...document.querySelectorAll("[data-landing-video]")];
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  const transactionDialog = document.getElementById("transactionDialog");
  const transactionForm = document.getElementById("transactionForm");

  const incomeCategories = ["Salary", "Freelance", "Investments", "Gifts", "Other income"];
  const expenseCategories = [
    "Housing",
    "Groceries",
    "Transport",
    "Utilities",
    "Dining",
    "Healthcare",
    "Shopping",
    "Entertainment",
    "Travel",
    "Education",
    "Other expense",
  ];
  const state = {
    csrfToken: csrfMeta?.content ?? "",
    user: null,
    currencies: [],
    filter: "all",
    view: "overview",
    theme: "dark",
    previewRequest: 0,
    previewTimer: null,
    searchTimer: null,
    toastTimer: null,
    dashboardAnimationFrame: 0,
    dashboardSummary: null,
    dashboardCurrency: null,
  };
  const animatedInputSync = new WeakMap();
  let landingMediaObserver = null;
  let revealObserver = null;
  let revealCheckFrame = 0;
  let heroFadeFrame = 0;
  let heroFadingOut = false;

  function fadeHeroVideo(targetOpacity, duration) {
    window.cancelAnimationFrame(heroFadeFrame);
    const startOpacity = Number.parseFloat(getComputedStyle(heroVideo).opacity) || 0;
    const startTime = performance.now();

    function frame(now) {
      const progress = Math.min((now - startTime) / duration, 1);
      heroVideo.style.opacity = String(startOpacity + (targetOpacity - startOpacity) * progress);
      if (progress < 1) heroFadeFrame = window.requestAnimationFrame(frame);
    }

    heroFadeFrame = window.requestAnimationFrame(frame);
  }

  function playLandingVideo(video) {
    const source = video.querySelector("source[data-lazy-src]");
    if (source && !source.src) {
      source.src = source.dataset.lazySrc;
      video.load();
    }
    video.play().catch((error) => {
      console.error("Acuwealth landing video could not play.", error);
    });
  }

  function pauseLandingMedia() {
    window.cancelAnimationFrame(heroFadeFrame);
    heroVideo.pause();
    for (const video of landingVideos) video.pause();
    landingMediaObserver?.disconnect();
    landingMediaObserver = null;
  }

  function startLandingMedia() {
    if (reducedMotion.matches) {
      if (heroVideo.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA) heroVideo.style.opacity = "0.58";
      return;
    }
    if (heroVideo.readyState >= HTMLMediaElement.HAVE_FUTURE_DATA) {
      playHeroVideo();
    }
    if ("IntersectionObserver" in window) {
      landingMediaObserver = new IntersectionObserver((entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) playLandingVideo(entry.target);
          else entry.target.pause();
        }
      }, { rootMargin: "160px 0px" });
      for (const video of landingVideos) landingMediaObserver.observe(video);
    } else {
      for (const video of landingVideos) playLandingVideo(video);
    }
  }

  function playHeroVideo() {
    if (landingPage.hidden || reducedMotion.matches) return;
    heroVideo.play().then(() => {
      fadeHeroVideo(1, 500);
    }).catch((error) => {
      console.error("Acuwealth hero video could not play.", error);
    });
  }

  heroVideo.addEventListener("canplay", () => {
    if (reducedMotion.matches) heroVideo.style.opacity = "0.58";
    else playHeroVideo();
  });
  heroVideo.addEventListener("timeupdate", () => {
    if (heroVideo.duration - heroVideo.currentTime <= 0.55 && !heroFadingOut) {
      heroFadingOut = true;
      fadeHeroVideo(0, 500);
    }
  });
  heroVideo.addEventListener("ended", () => {
    heroVideo.style.opacity = "0";
    window.setTimeout(() => {
      if (landingPage.hidden || reducedMotion.matches) return;
      heroVideo.currentTime = 0;
      heroFadingOut = false;
      playHeroVideo();
    }, 100);
  });
  heroVideo.addEventListener("error", () => {
    console.error("Acuwealth hero video could not be loaded.");
  });
  reducedMotion.addEventListener("change", () => {
    if (reducedMotion.matches) {
      pauseLandingMedia();
      revealAllItems();
    } else if (!landingPage.hidden) startLandingMedia();
  });
  for (const video of landingVideos) {
    video.addEventListener("error", () => {
      console.error("An Acuwealth landing video could not be loaded.", video.currentSrc);
    });
  }

  function setupRevealAnimations() {
    const revealItems = document.querySelectorAll(".reveal");
    if (reducedMotion.matches || !("IntersectionObserver" in window)) {
      revealAllItems();
      return;
    }

    function show(item) {
      item.classList.add("is-visible");
      revealObserver?.unobserve(item);
    }

    revealObserver = new IntersectionObserver((entries) => {
      for (const entry of entries) {
        if (entry.isIntersecting) show(entry.target);
      }
    }, { rootMargin: "0px 0px -80px 0px" });
    for (const item of revealItems) revealObserver.observe(item);

    function revealPassedItems() {
      if (revealCheckFrame) return;
      revealCheckFrame = window.requestAnimationFrame(() => {
        revealCheckFrame = 0;
        const viewportBottom = window.innerHeight + 120;
        for (const item of revealItems) {
          if (!item.classList.contains("is-visible") && item.getBoundingClientRect().top <= viewportBottom) {
            show(item);
          }
        }
      });
    }

    window.addEventListener("scroll", revealPassedItems, { passive: true });
    window.addEventListener("resize", revealPassedItems, { passive: true });
    revealPassedItems();
  }

  function revealAllItems() {
    if (revealCheckFrame) {
      window.cancelAnimationFrame(revealCheckFrame);
      revealCheckFrame = 0;
    }
    for (const item of document.querySelectorAll(".reveal")) item.classList.add("is-visible");
    revealObserver?.disconnect();
    revealObserver = null;
  }

  class ApiError extends Error {
    constructor(message, status) {
      super(message);
      this.status = status;
    }
  }

  async function api(path, options = {}) {
    const method = (options.method ?? "GET").toUpperCase();
    const headers = { Accept: "application/json", ...options.headers };
    if (options.body !== undefined) headers["Content-Type"] = "application/json";
    if (["POST", "PATCH", "PUT", "DELETE"].includes(method)) {
      headers["X-CSRF-Token"] = state.csrfToken;
    }
    const response = await fetch(path, {
      ...options,
      method,
      headers,
      credentials: "same-origin",
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
    });
    const contentType = response.headers.get("content-type") ?? "";
    if (!contentType.toLowerCase().includes("application/json")) {
      throw new ApiError(
        `The server returned a web page instead of API data (HTTP ${response.status}). Check that Render is deploying Acuwealth as a Python Web Service, not a Static Site.`,
        response.status,
      );
    }
    let data;
    try {
      data = await response.json();
    } catch {
      throw new ApiError("The server returned an invalid response. Please try again.", response.status);
    }
    if (!data || typeof data !== "object" || Array.isArray(data)) {
      throw new ApiError("The server returned an invalid response. Please try again.", response.status);
    }
    if (!response.ok) throw new ApiError(data.error || "Something went wrong. Please try again.", response.status);
    if (typeof data.csrf_token === "string") {
      state.csrfToken = data.csrf_token;
      if (csrfMeta) csrfMeta.content = data.csrf_token;
    }
    return data;
  }

  function escapeHTML(value) {
    return String(value).replace(/[&<>"']/g, (character) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    })[character]);
  }

  function formatMoney(value, currency = state.user?.currency ?? "INR") {
    if (value === null || value === undefined || value === "") return "Not available";
    const number = Number(value);
    if (!Number.isFinite(number)) return "Not available";
    try {
      return new Intl.NumberFormat(navigator.language || "en", {
        style: "currency",
        currency,
        minimumFractionDigits: currency === "JPY" || currency === "KRW" ? 0 : 2,
        maximumFractionDigits: currency === "JPY" || currency === "KRW" ? 0 : 2,
      }).format(number);
    } catch {
      return `${currency} ${number.toFixed(2)}`;
    }
  }

  function setDashboardSummary(summary, currency) {
    const values = {
      balance: summary.balance,
      income: summary.income,
      expenses: summary.expenses,
      net: summary.net,
    };
    cancelAnimationFrame(state.dashboardAnimationFrame);
    state.dashboardAnimationFrame = 0;
    for (const [key, elementId] of Object.entries({
      balance: "balanceAmount",
      income: "incomeAmount",
      expenses: "expenseAmount",
      net: "monthlyNet",
    })) {
      document.getElementById(elementId).textContent = formatMoney(values[key], currency);
    }
    state.dashboardSummary = values;
    state.dashboardCurrency = currency;
  }

  function animateDashboardSummary(summary, currency) {
    const keys = ["balance", "income", "expenses", "net"];
    const target = Object.fromEntries(keys.map((key) => {
      const value = summary[key];
      return [key, value === null || value === undefined || value === "" || !Number.isFinite(Number(value))
        ? null
        : Number(value)];
    }));
    const hasPreviousSummary = state.dashboardSummary
      && state.dashboardCurrency === currency
      && keys.every((key) => Number.isFinite(state.dashboardSummary[key]));
    const previous = hasPreviousSummary
      ? state.dashboardSummary
      : Object.fromEntries(keys.map((key) => [key, 0]));
    const canAnimate = !reducedMotion.matches
      && keys.every((key) => Number.isFinite(previous[key]) && Number.isFinite(target[key]))
      && keys.some((key) => previous[key] !== target[key]);

    if (!canAnimate) {
      setDashboardSummary(target, currency);
      return;
    }

    cancelAnimationFrame(state.dashboardAnimationFrame);
    const startedAt = performance.now();
    const duration = 1100;
    const step = (now) => {
      const progress = Math.min((now - startedAt) / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3);
      const values = Object.fromEntries(keys.map((key) => [
        key,
        previous[key] + (target[key] - previous[key]) * eased,
      ]));
      state.dashboardSummary = values;
      for (const [key, elementId] of Object.entries({
        balance: "balanceAmount",
        income: "incomeAmount",
        expenses: "expenseAmount",
        net: "monthlyNet",
      })) {
        document.getElementById(elementId).textContent = formatMoney(values[key], currency);
      }
      if (progress < 1) {
        state.dashboardAnimationFrame = requestAnimationFrame(step);
      } else {
        state.dashboardSummary = target;
        state.dashboardAnimationFrame = 0;
      }
    };
    state.dashboardCurrency = currency;
    state.dashboardAnimationFrame = requestAnimationFrame(step);
  }

  function updatePasswordStrength(password) {
    const meter = document.getElementById("passwordStrengthMeter");
    const fill = document.getElementById("passwordStrengthFill");
    const label = document.getElementById("passwordStrengthLabel");
    const score = password.length
      ? Math.min(100, password.length * 8
        + (/[A-Z]/.test(password) ? 15 : 0)
        + (/\d/.test(password) ? 15 : 0)
        + (/[^A-Za-z0-9]/.test(password) ? 15 : 0))
      : 0;
    const level = score === 0 ? "empty" : score < 35 ? "weak" : score < 70 ? "fair" : "strong";
    const strengthLabel = score === 0 ? "Start typing" : level[0].toUpperCase() + level.slice(1);
    fill.style.width = `${score}%`;
    fill.className = `password-strength-fill is-${level}`;
    label.textContent = strengthLabel;
    meter.setAttribute("aria-valuenow", String(score));
    meter.setAttribute("aria-valuetext", `${strengthLabel}, ${score}%`);
  }

  function syncAnimatedInputs(animate = false) {
    for (const input of document.querySelectorAll("[data-animated-input]")) {
      animatedInputSync.get(input)?.(animate);
    }
  }

  function addAnimatedInput(input) {
    let wrapper = input.parentElement;
    if (!wrapper?.classList.contains("smooth-input-wrap")) {
      wrapper = document.createElement("span");
      wrapper.className = "animated-input-wrap";
      input.parentNode.insertBefore(wrapper, input);
      wrapper.append(input);
    } else {
      wrapper.classList.add("animated-input-wrap");
    }

    const overlay = document.createElement("span");
    overlay.className = "animated-input-overlay";
    overlay.setAttribute("aria-hidden", "true");
    const line = document.createElement("span");
    line.className = "animated-input-line";
    const prefix = document.createElement("span");
    prefix.className = "animated-input-prefix";
    const last = document.createElement("span");
    last.className = "animated-input-last";
    line.append(prefix, last);
    overlay.append(line);
    wrapper.append(overlay);
    input.classList.add("animated-input-control");

    let previousValue = null;
    let animationIndex = 0;
    const syncScrollPosition = () => {
      line.style.transform = `translate3d(${-input.scrollLeft}px, 0, 0)`;
    };
    const update = (animate = true) => {
      const styles = getComputedStyle(input);
      overlay.style.left = `${(Number.parseFloat(styles.paddingLeft) || 0)
        + (Number.parseFloat(styles.borderLeftWidth) || 0)}px`;
      overlay.style.right = `${(Number.parseFloat(styles.paddingRight) || 0)
        + (Number.parseFloat(styles.borderRightWidth) || 0)}px`;
      overlay.style.font = styles.font;
      overlay.style.letterSpacing = styles.letterSpacing;
      overlay.style.textTransform = styles.textTransform;
      syncScrollPosition();
      const value = input.value;
      if (value === previousValue) return;
      previousValue = value;
      const characters = Array.from(value);
      const displayCharacters = input.type === "password"
        ? characters.map(() => "\u2022")
        : characters;
      prefix.textContent = displayCharacters.slice(0, -1).join("");
      last.textContent = displayCharacters.at(-1) ?? "";
      last.className = `animated-input-last${animate && last.textContent
        ? animationIndex++ % 2 === 0 ? " pop-a" : " pop-b"
        : ""}`;
      input.classList.toggle("has-animated-value", characters.length > 0);
      if (input.name === "password") updatePasswordStrength(value);
    };
    input.addEventListener("input", () => update(true));
    input.addEventListener("change", () => update(false));
    input.addEventListener("compositionend", () => update(true));
    input.addEventListener("scroll", syncScrollPosition, { passive: true });
    animatedInputSync.set(input, update);
    update(false);
  }

  function formatDate(value, options = {}) {
    const date = new Date(`${value}T12:00:00`);
    if (!Number.isFinite(date.getTime())) return value;
    return new Intl.DateTimeFormat(navigator.language || "en", options).format(date);
  }

  function showToast(message) {
    toast.textContent = message;
    toast.hidden = false;
    window.clearTimeout(state.toastTimer);
    state.toastTimer = window.setTimeout(() => {
      toast.hidden = true;
    }, 3400);
  }

  function setError(element, message) {
    element.textContent = message;
    element.hidden = false;
  }

  function clearError(element) {
    element.textContent = "";
    element.hidden = true;
  }

  function replayEntrance(element) {
    if (reducedMotion.matches) return;

    element.classList.remove("is-entering");
    void element.offsetWidth;
    element.classList.add("is-entering");
    element.addEventListener("animationend", (event) => {
      if (event.target === element && event.animationName === "surface-enter") {
        element.classList.remove("is-entering");
      }
    }, { once: true });
  }

  function showAuth(mode = "login") {
    landingPage.hidden = true;
    pauseLandingMedia();
    appShell.hidden = true;
    authShell.hidden = false;
    replayEntrance(authShell);
    state.user = null;
    authForm.dataset.mode = mode;
    const isSignup = mode === "signup";
    document.getElementById("nameField").hidden = !isSignup;
    authForm.elements.name.required = isSignup;
    authForm.elements.password.autocomplete = isSignup ? "new-password" : "current-password";
    document.getElementById("passwordHelp").hidden = !isSignup;
    document.getElementById("passwordStrength").hidden = !isSignup;
    document.getElementById("authHeroLead").textContent = isSignup ? "Grow what" : "Know your wealth,";
    document.getElementById("authHeroEmphasis").textContent = isSignup ? "matters." : "in focus.";
    document.getElementById("authHeroDescription").textContent = isSignup
      ? "Build a clear picture of your income, expenses, and monthly cash flow."
      : "Track every transaction, understand your monthly cash flow, and see your money in one clear view.";
    document.getElementById("authKicker").textContent = isSignup ? "YOUR MONEY, IN FOCUS" : "WELCOME BACK";
    document.getElementById("authHeading").textContent = isSignup ? "Start with a clear view." : "Good to have you back.";
    document.getElementById("authDescription").textContent = isSignup
      ? "Create your account and start tracking your finances."
      : "Sign in to pick up where you left off.";
    document.getElementById("authSubmit").textContent = isSignup ? "Create account" : "Sign in";
    document.getElementById("authSwitchLabel").textContent = isSignup ? "Already have an account?" : "New to Acuwealth?";
    document.getElementById("authSwitch").textContent = isSignup ? "Sign in" : "Create an account";
    for (const tab of document.querySelectorAll(".auth-mode-tab")) {
      const selected = tab.dataset.authMode === mode;
      tab.classList.toggle("is-active", selected);
      tab.setAttribute("aria-selected", String(selected));
    }
    clearError(authError);
    authForm.reset();
    syncAnimatedInputs();
    updatePasswordStrength("");
  }

  function showLanding() {
    appShell.hidden = true;
    authShell.hidden = true;
    landingPage.hidden = false;
    state.user = null;
    startLandingMedia();
  }

  function currencyOptions(selected) {
    return state.currencies.map(({ code, name }) =>
      `<option value="${escapeHTML(code)}"${code === selected ? " selected" : ""}>${escapeHTML(code)} - ${escapeHTML(name)}</option>`,
    ).join("");
  }

  function populateCurrencySelects() {
    const selected = state.user?.currency ?? "INR";
    document.getElementById("overviewCurrency").innerHTML = currencyOptions(selected);
    document.getElementById("settingsCurrency").innerHTML = currencyOptions(selected);
    document.getElementById("transactionCurrency").innerHTML = currencyOptions(selected);
  }

  async function loadCurrencies() {
    if (state.currencies.length) return;
    const response = await api("/api/currencies");
    state.currencies = response.currencies;
  }

  function displayApplication(user) {
    state.user = user;
    state.dashboardSummary = null;
    state.dashboardCurrency = null;
    landingPage.hidden = true;
    authShell.hidden = true;
    pauseLandingMedia();
    appShell.hidden = false;
    document.getElementById("profileMenuName").textContent = user.name;
    document.getElementById("profileInitials").textContent = user.name.trim().charAt(0).toUpperCase() || "A";
    document.getElementById("profileMenuButton").setAttribute("aria-label", `Profile options for ${user.name}`);
    populateCurrencySelects();
    loadDashboard({ animateSummary: true, animateEntry: true });
  }

  function renderTrend(trend) {
    const chart = document.getElementById("cashflowChart");
    if (trend.some((month) => month.income === null || month.expense === null)) {
      chart.setAttribute("aria-label", "Six-month income and expense chart. Exchange rates are unavailable.");
      chart.innerHTML = '<p class="chart-chart-unavailable">Chart totals are unavailable until exchange rates are available.</p>';
      return;
    }
    chart.setAttribute(
      "aria-label",
      `Six-month income and expense chart. ${trend.map(
        (month) => `${month.month}: income ${formatMoney(month.income)}, expenses ${formatMoney(month.expense)}`,
      ).join(". ")}.`,
    );
    const maxValue = Math.max(
      ...trend.flatMap((month) => [Number(month.income), Number(month.expense)]),
    );
    if (maxValue <= 0) {
      chart.innerHTML = '<p class="chart-empty">Your six-month cash flow will appear here.</p>';
      return;
    }
    chart.innerHTML = trend.map((month) => {
      const incomeHeight = Math.max(0, Number(month.income) / maxValue * 100);
      const expenseHeight = Math.max(0, Number(month.expense) / maxValue * 100);
      return `<div class="chart-month">
        <div class="chart-bars">
          <span class="chart-bar chart-bar-income" style="height:${incomeHeight.toFixed(2)}%" title="Income: ${escapeHTML(formatMoney(month.income))}"></span>
          <span class="chart-bar chart-bar-expense" style="height:${expenseHeight.toFixed(2)}%" title="Expenses: ${escapeHTML(formatMoney(month.expense))}"></span>
        </div>
        <span class="chart-month-label">${escapeHTML(month.month)}</span>
      </div>`;
    }).join("");
  }

  function renderCategories(categories) {
    const list = document.getElementById("categoryList");
    if (!categories.length) {
      list.innerHTML = '<p class="category-empty">Your spending categories will appear here after you add an expense.</p>';
      return;
    }
    const values = categories.map((category) => Number(category.amount)).filter(Number.isFinite);
    const largest = Math.max(...values, 0);
    list.innerHTML = categories.map((category) => {
      const ratio = category.amount === null || largest === 0
        ? 0
        : Math.max(4, Math.round(Number(category.amount) / largest * 100));
      return `<div class="category-row">
        <span class="category-row-name">${escapeHTML(category.category)}</span>
        <strong class="category-row-amount">${escapeHTML(formatMoney(category.amount))}</strong>
        <span class="category-track" aria-label="${category.share === null ? "Exchange rate unavailable" : `${category.share}% of monthly expenses`}">
          <span class="category-fill" style="width:${ratio}%"></span>
        </span>
      </div>`;
    }).join("");
  }

  function transactionRow(transaction, showAction = false, newTransactionId = null) {
    const income = transaction.kind === "income";
    const direction = income ? "+" : "-";
    const isNew = newTransactionId !== null && Number(transaction.id) === Number(newTransactionId);
    const animationClass = isNew ? (Number(transaction.id) % 2 ? "new-a" : "new-b") : "";
    const converted = transaction.base_amount && transaction.currency !== state.user.currency
      ? `<span class="converted-amount">≈ ${escapeHTML(formatMoney(transaction.base_amount))} in ${escapeHTML(state.user.currency)}</span>`
      : "";
    const action = showAction
      ? `<td><button class="delete-button" type="button" data-delete-id="${transaction.id}" aria-label="Delete ${escapeHTML(transaction.description || transaction.category)}">Delete</button></td>`
      : "";
    return `<tr${animationClass ? ` class="transaction-row-${animationClass}"` : ""}>
      <td>
        <div class="transaction-name">
          <span class="transaction-mark ${income ? "income-mark" : "expense-mark"}">${income ? "IN" : "OUT"}</span>
          <span class="transaction-description">
            <span>${escapeHTML(transaction.description || transaction.category)}</span>
            <span>${income ? "Income" : "Expense"}</span>
          </span>
        </div>
      </td>
      <td>${escapeHTML(transaction.category)}</td>
      <td>${escapeHTML(formatDate(transaction.occurred_on, { day: "numeric", month: "short", year: "numeric" }))}</td>
      <td class="amount-column ${income ? "amount-positive" : "amount-negative"}">${direction}${escapeHTML(formatMoney(transaction.amount, transaction.currency))}${converted}</td>
      ${action}
    </tr>`;
  }

  function renderTransactions(element, transactions, showAction = false, newTransactionId = null) {
    if (!transactions.length) {
      const colspan = showAction ? 5 : 4;
      element.innerHTML = `<tr><td colspan="${colspan}" class="table-empty">No transactions to show yet. Add your first income or expense.</td></tr>`;
      return;
    }
    element.innerHTML = transactions.map((transaction) => transactionRow(transaction, showAction, newTransactionId)).join("");
  }

  function renderRateStatus(rates) {
    const notice = document.getElementById("rateNotice");
    const settingsStatus = document.getElementById("settingsRateStatus");
    if (rates.status === "cached" && rates.fetched_at) {
      const updated = new Date(rates.fetched_at);
      const label = Number.isFinite(updated.getTime())
        ? updated.toLocaleString(navigator.language || "en")
        : rates.fetched_at;
      const message = `Exchange rates could not be refreshed. Showing rates last saved on ${label}.`;
      notice.textContent = message;
      notice.hidden = false;
      settingsStatus.textContent = message;
    } else if (rates.status === "unavailable") {
      const message = rates.error || "Exchange rates are unavailable. Converted amounts will appear when current rates are available.";
      notice.textContent = message;
      notice.hidden = false;
      settingsStatus.textContent = message;
    } else if (rates.status === "not_needed") {
      notice.hidden = true;
      settingsStatus.textContent = `Your transactions are already in ${state.user.currency}. No conversion is needed.`;
    } else {
      notice.hidden = true;
      settingsStatus.textContent = rates.fetched_at
        ? `Exchange rates last refreshed ${new Date(rates.fetched_at).toLocaleString(navigator.language || "en")}.`
        : "Exchange rates are refreshed when you record a transaction in another currency.";
    }
  }

  async function loadDashboard({ animateSummary = false, animateEntry = false, newTransactionId = null } = {}) {
    try {
      const data = await api("/api/dashboard");
      state.user = data.user;
      state.currencies = data.currencies;
      populateCurrencySelects();
      document.getElementById("monthLabel").textContent = data.month_label;
      document.getElementById("currentDate").textContent = formatDate(data.today, {
        weekday: "short",
        day: "numeric",
        month: "short",
      });
      const currency = data.currency;
      if (animateSummary) animateDashboardSummary(data.summary, currency);
      else setDashboardSummary(data.summary, currency);
      document.getElementById("monthlyNet").classList.toggle(
        "amount-negative",
        data.summary.net !== null && Number(data.summary.net) < 0,
      );
      document.getElementById("monthlyNet").classList.toggle(
        "income-text",
        data.summary.net !== null && Number(data.summary.net) >= 0,
      );
      renderRateStatus(data.rates);
      renderTrend(data.trend);
      renderCategories(data.categories);
      renderTransactions(document.getElementById("recentTransactions"), data.transactions, false, newTransactionId);
      if (animateEntry) replayEntrance(document.getElementById("pageContent"));
      if (state.view === "transactions") loadTransactions(newTransactionId);
    } catch (error) {
      if (error.status === 401) {
        showAuth();
      } else {
        showToast(error.message);
        document.getElementById("balanceAmount").textContent = "Unable to load";
      }
    }
  }

  async function loadTransactions(newTransactionId = null) {
    const query = new URLSearchParams();
    if (state.filter !== "all") query.set("kind", state.filter);
    const search = document.getElementById("transactionSearch").value.trim();
    if (search) query.set("q", search);
    const list = document.getElementById("allTransactions");
    list.innerHTML = '<tr><td colspan="5" class="table-empty" role="status">Loading transactions…</td></tr>';
    try {
      const data = await api(`/api/transactions?${query.toString()}`);
      renderTransactions(list, data.transactions, true, newTransactionId);
    } catch (error) {
      list.innerHTML = `<tr><td colspan="5" class="table-empty">${escapeHTML(error.message)}</td></tr>`;
      if (error.status === 401) showAuth();
    }
  }

  async function loadPredictions() {
    const summaryEl = document.getElementById("predictionsSummary");
    const chartEl = document.getElementById("predictionsChart");
    const tableBody = document.getElementById("predictionsTable");
    const seasonalGrid = document.getElementById("seasonalGrid");
    const recommendationsList = document.getElementById("recommendationsList");
    
    // Show loading states
    summaryEl.innerHTML = `
      <article class="prediction-stat-card loading">
        <div class="prediction-stat-header"><span>Avg. Monthly Expense</span><span>AVG</span></div>
        <p class="prediction-stat-value">Loading…</p>
      </article>
      <article class="prediction-stat-card loading">
        <div class="prediction-stat-header"><span>Next Month</span><span>NEXT</span></div>
        <p class="prediction-stat-value">Loading…</p>
      </article>
      <article class="prediction-stat-card loading">
        <div class="prediction-stat-header"><span>3-Month Total</span><span>3M</span></div>
        <p class="prediction-stat-value">Loading…</p>
      </article>
      <article class="prediction-stat-card loading">
        <div class="prediction-stat-header"><span>Yearly Projection</span><span>12M</span></div>
        <p class="prediction-stat-value">Loading…</p>
      </article>
    `;
    chartEl.innerHTML = '<p class="chart-empty">Loading predictions…</p>';
    tableBody.innerHTML = '<tr><td colspan="4" class="table-empty">Loading…</td></tr>';
    seasonalGrid.innerHTML = '<p class="table-empty">Loading…</p>';
    recommendationsList.innerHTML = '<p class="table-empty">Loading…</p>';

    try {
      const data = await api("/api/predictions");
      const predictions = data.predictions;
      
      // Populate currency select
      const currencySelect = document.getElementById("predictionsCurrency");
      if (currencySelect) {
        currencySelect.innerHTML = state.currencies.map(({ code, name }) =>
          `<option value="${escapeHTML(code)}"${code === predictions.currency ? " selected" : ""}>${escapeHTML(code)} - ${escapeHTML(name)}</option>`
        ).join("");
        currencySelect.value = predictions.currency;
      }

      // Render all sections
      renderPredictionsSummary(predictions);
      renderPredictionsChart(predictions);
      renderPredictionsTable(predictions);
      renderSeasonalPatterns(predictions);
      renderRecommendations(predictions);
    } catch (error) {
      summaryEl.innerHTML = `
        <article class="prediction-stat-card">
          <div class="prediction-stat-header"><span>Error</span><span>ERR</span></div>
          <p class="prediction-stat-value expense-text">Failed to load</p>
        </article>
      `;
      chartEl.innerHTML = `<p class="chart-chart-unavailable">${escapeHTML(error.message)}</p>`;
      tableBody.innerHTML = `<tr><td colspan="4" class="table-empty">${escapeHTML(error.message)}</td></tr>`;
      if (error.status === 401) showAuth();
    }
  }

  function renderPredictionsSummary(predictions) {
    const summaryEl = document.getElementById("predictionsSummary");
    const monthly = predictions.monthly_breakdown || [];
    
    if (!monthly.length) {
      summaryEl.innerHTML = `
        <article class="prediction-stat-card">
          <div class="prediction-stat-header"><span>Avg. Monthly Expense</span><span>AVG</span></div>
          <p class="prediction-stat-value">Not available</p>
        </article>
        <article class="prediction-stat-card">
          <div class="prediction-stat-header"><span>Next Month</span><span>NEXT</span></div>
          <p class="prediction-stat-value">Not available</p>
        </article>
        <article class="prediction-stat-card">
          <div class="prediction-stat-header"><span>3-Month Total</span><span>3M</span></div>
          <p class="prediction-stat-value">Not available</p>
        </article>
        <article class="prediction-stat-card">
          <div class="prediction-stat-header"><span>Yearly Projection</span><span>12M</span></div>
          <p class="prediction-stat-value">Not available</p>
        </article>
      `;
      return;
    }

    const currency = predictions.currency || state.user?.currency || "INR";
    const nextMonth = monthly[0]?.predicted_amount || 0;
    const threeMonthTotal = monthly.slice(0, 3).reduce((sum, m) => sum + m.predicted_amount, 0);
    const yearlyTotal = monthly.reduce((sum, m) => sum + m.predicted_amount, 0);
    const avgMonthly = yearlyTotal / monthly.length;

    summaryEl.innerHTML = `
      <article class="prediction-stat-card">
        <div class="prediction-stat-header">
          <span class="prediction-stat-label">Avg. Monthly Expense</span>
          <span class="prediction-stat-mark">AVG</span>
        </div>
        <p class="prediction-stat-value expense-text">${formatMoney(avgMonthly, currency)}</p>
      </article>
      <article class="prediction-stat-card">
        <div class="prediction-stat-header">
          <span class="prediction-stat-label">Next Month</span>
          <span class="prediction-stat-mark">NEXT</span>
        </div>
        <p class="prediction-stat-value expense-text">${formatMoney(nextMonth, currency)}</p>
      </article>
      <article class="prediction-stat-card">
        <div class="prediction-stat-header">
          <span class="prediction-stat-label">3-Month Total</span>
          <span class="prediction-stat-mark">3M</span>
        </div>
        <p class="prediction-stat-value expense-text">${formatMoney(threeMonthTotal, currency)}</p>
      </article>
      <article class="prediction-stat-card">
        <div class="prediction-stat-header">
          <span class="prediction-stat-label">Yearly Projection</span>
          <span class="prediction-stat-mark">12M</span>
        </div>
        <p class="prediction-stat-value expense-text">${formatMoney(yearlyTotal, currency)}</p>
      </article>
    `;
  }

  function renderPredictionsChart(predictions) {
    const chart = document.getElementById("predictionsChart");
    const monthly = predictions.monthly_breakdown || [];
    const currency = predictions.currency || state.user?.currency || "INR";
    
    if (!monthly.length) {
      chart.innerHTML = '<p class="chart-empty">Add expense transactions to see predictions.</p>';
      return;
    }

    // Prepare data for chart
    const actualMonths = 6; // We'll show last 6 months of actual data if available
    const maxValue = Math.max(...monthly.map(m => m.predicted_amount));
    const minValue = Math.min(...monthly.map(m => m.lower_bound || m.predicted_amount));
    const range = maxValue - minValue || 1;
    
    chart.setAttribute(
      "aria-label",
      `12-month expense prediction chart. ${monthly.map(
        (m) => `${m.month}: predicted ${formatMoney(m.predicted_amount)}, range ${formatMoney(m.lower_bound)}–${formatMoney(m.upper_bound)}`
      ).join(". ")}.`
    );

    chart.innerHTML = monthly.map((month, index) => {
      // Normalize for chart height
      const predHeight = Math.max(5, ((month.predicted_amount - minValue) / range) * 100);
      const lowerHeight = Math.max(0, ((month.lower_bound - minValue) / range) * 100);
      const upperHeight = Math.min(100, ((month.upper_bound - minValue) / range) * 100);
      
      const isCurrentOrPast = index < 0; // All are future in our case
      
      return `
        <div class="chart-month prediction-month" data-month="${month.month}">
          <div class="chart-bars prediction-bars">
            <div class="prediction-confidence-band" style="bottom: ${lowerHeight}%; height: ${upperHeight - lowerHeight}%;">
              <span class="confidence-label" aria-hidden="true">${formatMoney(month.lower_bound)}–${formatMoney(month.upper_bound)}</span>
            </div>
            <span class="chart-bar chart-bar-prediction" style="height:${predHeight}%" 
              title="Predicted: ${escapeHTML(formatMoney(month.predicted_amount, currency))} (${month.confidence}% confidence)"></span>
          </div>
          <span class="chart-month-label">${escapeHTML(month.date)}</span>
          <span class="prediction-value-label">${escapeHTML(formatMoney(month.predicted_amount, currency))}</span>
        </div>
      `;
    }).join("");
  }

  function renderPredictionsTable(predictions) {
    const tableBody = document.getElementById("predictionsTable");
    const monthly = predictions.monthly_breakdown || [];
    const currency = predictions.currency || state.user?.currency || "INR";
    
    if (!monthly.length) {
      tableBody.innerHTML = '<tr><td colspan="4" class="table-empty">No predictions available. Add expense transactions to generate forecasts.</td></tr>';
      return;
    }

    tableBody.innerHTML = monthly.map((month, index) => `
      <tr${index === 0 ? ' class="current-month"' : ''}>
        <td>${escapeHTML(month.date)}</td>
        <td class="amount-column expense-text">${escapeHTML(formatMoney(month.predicted_amount, currency))}</td>
        <td>${escapeHTML(formatMoney(month.lower_bound, currency))} – ${escapeHTML(formatMoney(month.upper_bound, currency))}</td>
        <td><span class="confidence-badge confidence-${month.confidence >= 80 ? 'high' : month.confidence >= 60 ? 'medium' : 'low'}">${month.confidence}%</span></td>
      </tr>
    `).join("");
  }

  function renderSeasonalPatterns(predictions) {
    const seasonalGrid = document.getElementById("seasonalGrid");
    const seasonal = predictions.seasonal_factors || {};
    
    if (!seasonal || Object.keys(seasonal).length === 0) {
      seasonalGrid.innerHTML = `
        <div class="seasonal-empty">
          <p>Seasonal analysis requires at least 12 months of expense data.</p>
          <p class="seasonal-hint">Keep tracking your expenses to unlock seasonal insights.</p>
        </div>
      `;
      return;
    }

    const peakMonth = seasonal.peak_month_label || "Unknown";
    const lowestMonth = seasonal.lowest_month_label || "Unknown";
    const averageMonth = seasonal.average_month || 0;
    const trend = seasonal.trend || "stable";

    seasonalGrid.innerHTML = `
      <div class="seasonal-card">
        <div class="seasonal-card-header">
          <span class="seasonal-icon">📈</span>
          <h3>Peak Spending</h3>
        </div>
        <p class="seasonal-value">${escapeHTML(peakMonth)}</p>
        <p class="seasonal-description">Typically your highest expense month</p>
      </div>
      <div class="seasonal-card">
        <div class="seasonal-card-header">
          <span class="seasonal-icon">📉</span>
          <h3>Lowest Spending</h3>
        </div>
        <p class="seasonal-value">${escapeHTML(lowestMonth)}</p>
        <p class="seasonal-description">Typically your lowest expense month</p>
      </div>
      <div class="seasonal-card">
        <div class="seasonal-card-header">
          <span class="seasonal-icon">📊</span>
          <h3>Monthly Average</h3>
        </div>
        <p class="seasonal-value expense-text">${escapeHTML(formatMoney(averageMonth))}</p>
        <p class="seasonal-description">Average across all months</p>
      </div>
      <div class="seasonal-card">
        <div class="seasonal-card-header">
          <span class="seasonal-icon">${trend === 'increasing' ? '📈' : '📉'}</span>
          <h3>Overall Trend</h3>
        </div>
        <p class="seasonal-value trend-${trend}">${escapeHTML(trend)}</p>
        <p class="seasonal-description">Expense trajectory over time</p>
      </div>
    `;
  }

  function renderRecommendations(predictions) {
    const recommendationsList = document.getElementById("recommendationsList");
    const recommendations = predictions.recommendations || [];
    
    if (!recommendations.length) {
      recommendationsList.innerHTML = `
        <div class="recommendations-empty">
          <p>No specific recommendations available yet.</p>
          <p class="recommendation-hint">Add more transactions to get personalized savings advice.</p>
        </div>
      `;
      return;
    }

    recommendationsList.innerHTML = recommendations.map((rec, index) => `
      <article class="recommendation-card">
        <div class="recommendation-number">${index + 1}</div>
        <div class="recommendation-content">
          <p>${escapeHTML(rec)}</p>
        </div>
      </article>
    `).join("");
  }

  function setView(view) {
    const headings = {
      overview: "Overview",
      transactions: "Transactions",
      predictions: "Predictions",
      settings: "Preferences",
    };
    if (!headings[view]) return;
    state.view = view;
    for (const button of document.querySelectorAll("[data-view]")) {
      const selected = button.dataset.view === view;
      if (button.classList.contains("nav-link")) {
        button.classList.toggle("is-active", selected);
        if (selected) button.setAttribute("aria-current", "page");
        else button.removeAttribute("aria-current");
      }
    }
    for (const [name, id] of Object.entries({
      overview: "overviewView",
      transactions: "transactionsView",
      predictions: "predictionsView",
      settings: "settingsView",
    })) {
      document.getElementById(id).hidden = name !== view;
    }
    document.getElementById("breadcrumb").textContent = headings[view];
    if (view === "transactions") loadTransactions();
    if (view === "predictions") loadPredictions();
  }

  function updateCategoryOptions() {
    const kind = transactionForm.elements.kind.value;
    const options = kind === "income" ? incomeCategories : expenseCategories;
    document.getElementById("transactionCategory").innerHTML = options.map(
      (category) => `<option value="${escapeHTML(category)}">${escapeHTML(category)}</option>`,
    ).join("");
  }

  function updateConversionPreview() {
    window.clearTimeout(state.previewTimer);
    const amount = transactionForm.elements.amount.value;
    const from = transactionForm.elements.currency.value;
    const to = state.user?.currency;
    const preview = document.getElementById("conversionPreview");
    clearError(preview);
    preview.classList.remove("is-error");
    if (!amount || !from || !to || Number(amount) <= 0) {
      preview.textContent = "";
      return;
    }
    if (from === to) {
      preview.textContent = `Saved in ${from}, the same as your display currency.`;
      return;
    }
    const requestId = ++state.previewRequest;
    preview.textContent = "Checking current exchange rate…";
    state.previewTimer = window.setTimeout(async () => {
      const query = new URLSearchParams({ amount, from, to });
      try {
        const result = await api(`/api/convert?${query.toString()}`);
        if (requestId !== state.previewRequest) return;
        preview.textContent = `${formatMoney(amount, from)} converts to ${formatMoney(result.converted_amount, to)} at the current rate.`;
      } catch (error) {
        if (requestId !== state.previewRequest) return;
        preview.textContent = error.message;
        preview.classList.add("is-error");
      }
    }, 350);
  }

  function openTransactionDialog() {
    transactionForm.reset();
    syncAnimatedInputs();
    const now = new Date();
    const localToday = new Date(now.getTime() - now.getTimezoneOffset() * 60_000)
      .toISOString()
      .slice(0, 10);
    document.getElementById("transactionDate").value = localToday;
    document.getElementById("transactionCurrency").value = state.user.currency;
    updateCategoryOptions();
    document.getElementById("conversionPreview").textContent = "";
    clearError(document.getElementById("transactionError"));
    if (typeof transactionDialog.showModal === "function") transactionDialog.showModal();
    else showToast("Your browser does not support the transaction form.");
  }

  function setTheme(theme) {
    state.theme = theme === "dark" ? "dark" : "light";
    root.dataset.theme = state.theme;
    for (const button of document.querySelectorAll(".theme-toggle")) {
      button.setAttribute("aria-label", state.theme === "dark" ? "Use light appearance" : "Use dark appearance");
      button.setAttribute("aria-pressed", String(state.theme === "dark"));
      button.title = "Change appearance";
      button.dataset.theme = state.theme;
    }
    try {
      localStorage.setItem("acuwealth-theme", state.theme);
    } catch {
      // The theme still applies for this page when browser storage is disabled.
    }
  }

  function addSmoothInputCaret(input) {
    const wrapper = document.createElement("span");
    wrapper.className = "smooth-input-wrap";
    input.parentNode.insertBefore(wrapper, input);
    wrapper.append(input);
    input.classList.add("smooth-input-control");

    const caret = document.createElement("span");
    caret.className = "smooth-caret";
    caret.setAttribute("aria-hidden", "true");
    const measure = document.createElement("span");
    measure.className = "smooth-input-measure";
    measure.setAttribute("aria-hidden", "true");
    wrapper.append(caret, measure);

    const canvas = document.createElement("canvas");
    const context = canvas.getContext("2d");
    let frame = 0;

    function updateCaret() {
      window.cancelAnimationFrame(frame);
      frame = window.requestAnimationFrame(() => {
        if (document.activeElement !== input || !input.offsetWidth) {
          caret.classList.remove("is-visible");
          return;
        }

        const styles = window.getComputedStyle(input);
        const caretIndex = input.selectionStart ?? input.value.length;
        const prefix = input.type === "password"
          ? "\u2022".repeat(caretIndex)
          : input.value.slice(0, caretIndex);
        let textWidth = 0;
        if (context) {
          context.font = styles.font;
          if ("letterSpacing" in context) context.letterSpacing = styles.letterSpacing;
          textWidth = context.measureText(prefix).width;
          if (!("letterSpacing" in context)) {
            const letterSpacing = Number.parseFloat(styles.letterSpacing);
            if (Number.isFinite(letterSpacing) && prefix.length > 1) {
              textWidth += letterSpacing * (Array.from(prefix).length - 1);
            }
          }
        } else {
          measure.style.font = styles.font;
          measure.style.letterSpacing = styles.letterSpacing;
          measure.textContent = prefix;
          textWidth = measure.getBoundingClientRect().width;
        }

        const contentStart = input.offsetLeft
          + (Number.parseFloat(styles.borderLeftWidth) || 0)
          + (Number.parseFloat(styles.paddingLeft) || 0);
        const contentWidth = input.clientWidth
          - (Number.parseFloat(styles.paddingLeft) || 0)
          - (Number.parseFloat(styles.paddingRight) || 0);
        const absoluteX = contentStart + textWidth;
        if (absoluteX - input.scrollLeft > input.offsetLeft + input.clientWidth - (Number.parseFloat(styles.paddingRight) || 0)) {
          input.scrollLeft = Math.max(0, absoluteX - input.clientWidth + (Number.parseFloat(styles.paddingRight) || 0));
        } else if (absoluteX - input.scrollLeft < contentStart) {
          input.scrollLeft = Math.max(0, absoluteX - contentStart);
        }

        const visibleX = Math.max(
          contentStart - input.offsetLeft,
          Math.min(contentWidth + contentStart - input.offsetLeft, absoluteX - input.scrollLeft - input.offsetLeft),
        );
        caret.style.transform = `translate3d(${visibleX}px, -50%, 0)`;
        caret.style.top = `${input.offsetTop + input.clientHeight / 2}px`;
        caret.classList.add("is-visible");
      });
    }

    for (const eventName of ["focus", "input", "click", "keyup", "select", "scroll"]) {
      input.addEventListener(eventName, updateCaret);
    }
    input.addEventListener("blur", () => {
      window.cancelAnimationFrame(frame);
      caret.classList.remove("is-visible");
    });
    document.addEventListener("selectionchange", () => {
      if (document.activeElement === input) updateCaret();
    });
    window.addEventListener("resize", updateCaret);
  }

  document.getElementById("authSwitch").addEventListener("click", () => {
    showAuth(authForm.dataset.mode === "signup" ? "login" : "signup");
  });

  document.getElementById("authBack").addEventListener("click", showLanding);

  for (const button of document.querySelectorAll("[data-open-auth]")) {
    button.addEventListener("click", () => showAuth(button.dataset.openAuth));
  }
  for (const button of document.querySelectorAll("[data-auth-mode]")) {
    button.addEventListener("click", () => showAuth(button.dataset.authMode));
  }

  document.getElementById("landingSignupForm").addEventListener("submit", (event) => {
    event.preventDefault();
    const email = document.getElementById("landingEmail").value.trim();
    showAuth("signup");
    authForm.elements.email.value = email;
    syncAnimatedInputs();
  });

  authForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    clearError(authError);
    const submit = document.getElementById("authSubmit");
    const mode = authForm.dataset.mode;
    const body = Object.fromEntries(new FormData(authForm));
    submit.disabled = true;
    submit.textContent = mode === "signup" ? "Creating account…" : "Signing in…";
    try {
      const response = await api(`/api/auth/${mode}`, { method: "POST", body });
      authForm.reset();
      displayApplication(response.user);
    } catch (error) {
      setError(authError, error.message);
    } finally {
      submit.disabled = false;
      submit.textContent = mode === "signup" ? "Create account" : "Sign in";
    }
  });

  for (const button of document.querySelectorAll("[data-view]")) {
    button.addEventListener("click", () => setView(button.dataset.view));
  }

  document.getElementById("addTransactionButton").addEventListener("click", openTransactionDialog);
  document.getElementById("closeTransactionDialog").addEventListener("click", () => transactionDialog.close());
  document.getElementById("cancelTransaction").addEventListener("click", () => transactionDialog.close());
  for (const button of document.querySelectorAll(".theme-toggle")) {
    button.addEventListener("click", () => {
      setTheme(state.theme === "dark" ? "light" : "dark");
    });
  }

  const profileMenuButton = document.getElementById("profileMenuButton");
  const profileMenu = document.getElementById("profileMenu");

  function closeProfileMenu({ restoreFocus = false } = {}) {
    profileMenu.hidden = true;
    profileMenuButton.setAttribute("aria-expanded", "false");
    if (restoreFocus) profileMenuButton.focus();
  }

  profileMenuButton.addEventListener("click", () => {
    const isOpening = profileMenu.hidden;
    profileMenu.hidden = !isOpening;
    profileMenuButton.setAttribute("aria-expanded", String(isOpening));
  });

  document.addEventListener("click", (event) => {
    if (
      !profileMenu.hidden
      && !(event.target instanceof Element && event.target.closest(".profile-menu-wrap"))
    ) {
      closeProfileMenu();
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !profileMenu.hidden) closeProfileMenu({ restoreFocus: true });
  });

  async function leaveAccount() {
    const buttons = [...document.querySelectorAll("[data-account-action]")];
    closeProfileMenu();
    buttons.forEach((button) => {
      button.disabled = true;
    });
    try {
      await api("/api/auth/logout", { method: "POST", body: {} });
      showAuth();
    } catch (error) {
      showToast(error.message);
    } finally {
      buttons.forEach((button) => {
        button.disabled = false;
      });
    }
  }

  for (const button of document.querySelectorAll("[data-account-action]")) {
    button.addEventListener("click", leaveAccount);
  }

  document.getElementById("overviewCurrency").addEventListener("change", async (event) => {
    const select = event.currentTarget;
    const previous = state.user.currency;
    select.disabled = true;
    try {
      await api("/api/preferences", {
        method: "PATCH",
        body: { currency: select.value },
      });
      state.user.currency = select.value;
      document.getElementById("settingsCurrency").value = select.value;
      await loadDashboard();
    } catch (error) {
      select.value = previous;
      showToast(error.message);
    } finally {
      select.disabled = false;
    }
  });

  document.getElementById("preferencesForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const submit = event.currentTarget.querySelector('button[type="submit"]');
    const errorElement = document.getElementById("preferencesError");
    clearError(errorElement);
    submit.disabled = true;
    try {
      const response = await api("/api/preferences", {
        method: "PATCH",
        body: { currency: document.getElementById("settingsCurrency").value },
      });
      state.user.currency = response.currency;
      await loadDashboard();
      showToast(response.message);
    } catch (error) {
      setError(errorElement, error.message);
    } finally {
      submit.disabled = false;
    }
  });

  document.querySelectorAll('input[name="kind"]').forEach((radio) => {
    radio.addEventListener("change", updateCategoryOptions);
  });
  transactionForm.elements.amount.addEventListener("input", updateConversionPreview);
  transactionForm.elements.currency.addEventListener("change", updateConversionPreview);

  transactionForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const submit = document.getElementById("saveTransaction");
    const errorElement = document.getElementById("transactionError");
    clearError(errorElement);
    submit.disabled = true;
    submit.textContent = "Saving…";
    const body = Object.fromEntries(new FormData(transactionForm));
    try {
      const transaction = await api("/api/transactions", { method: "POST", body });
      transactionDialog.close();
      showToast("Transaction saved.");
      await loadDashboard({ animateSummary: true, newTransactionId: transaction.id });
    } catch (error) {
      setError(errorElement, error.message);
    } finally {
      submit.disabled = false;
      submit.textContent = "Save transaction";
    }
  });

  document.querySelectorAll("[data-filter]").forEach((button) => {
    button.addEventListener("click", () => {
      state.filter = button.dataset.filter;
      document.querySelectorAll("[data-filter]").forEach((option) => {
        const selected = option === button;
        option.classList.toggle("is-selected", selected);
        option.setAttribute("aria-pressed", String(selected));
      });
      loadTransactions();
    });
  });

  document.getElementById("transactionSearch").addEventListener("input", () => {
    window.clearTimeout(state.searchTimer);
    state.searchTimer = window.setTimeout(loadTransactions, 250);
  });

  document.getElementById("allTransactions").addEventListener("click", async (event) => {
    const button = event.target.closest("[data-delete-id]");
    if (!button) return;
    if (!window.confirm("Delete this transaction? This action cannot be undone.")) return;
    button.disabled = true;
    try {
      await api(`/api/transactions/${button.dataset.deleteId}`, { method: "DELETE" });
      await loadDashboard();
      showToast("Transaction deleted.");
    } catch (error) {
      button.disabled = false;
      showToast(error.message);
    }
  });

  for (const input of document.querySelectorAll("[data-smooth-input], [data-animated-input]")) {
    if (input.hasAttribute("data-smooth-input")) addSmoothInputCaret(input);
    if (input.hasAttribute("data-animated-input")) addAnimatedInput(input);
  }

  async function start() {
    try {
      const savedTheme = localStorage.getItem("acuwealth-theme");
      if (savedTheme === "dark" || savedTheme === "light") setTheme(savedTheme);
    } catch {
      setTheme("dark");
    }
    setupRevealAnimations();
    showLanding();
    try {
      await loadCurrencies();
      const response = await api("/api/session");
      if (response.user) displayApplication(response.user);
    } catch (error) {
      showToast(error.message);
    }
  }

  start();
})();
