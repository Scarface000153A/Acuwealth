import sys

def main():
    js_path = r"C:\Users\User\Desktop\Acuwealth\static\app.js"
    try:
        src = open(js_path, "r", encoding="utf-8").read()
    except Exception as e:
        print(f"Error reading file: {e}")
        return 1

    # Helper functions to insert after state declaration
    helpers = '''

/* ========== NEW FEATURE HELPERS ========== */

function setupMobileMenu() {
  const toggle = document.getElementById("mobileMenuToggle");
  const drawer = document.getElementById("mobileDrawer");
  if (!toggle || !drawer) return;
  
  toggle.addEventListener("click", () => {
    const expanded = toggle.getAttribute("aria-expanded") === "true" || false;
    toggle.setAttribute("aria-expanded", String(!expanded));
    drawer.hidden = expanded;
  });
  
  // Close drawer when clicking a link
  drawer.querySelectorAll("a").forEach(link => {
    link.addEventListener("click", () => {
      toggle.setAttribute("aria-expanded", "false");
      drawer.hidden = true;
    });
  });
}

function setupCookieConsent() {
  const banner = document.getElementById("cookieBanner");
  const acceptBtn = document.getElementById("cookieAccept");
  const rejectBtn = document.getElementById("cookieReject");
  const manageBtn = document.getElementById("cookieManage");
  const resetBtn = document.getElementById("resetCookieConsent");
  
  if (!banner) return;
  
  const hasConsent = localStorage.getItem("acuwealth-cookie-consent") === "true";
  const hasRejected = localStorage.getItem("acuwealth-cookie-consent") === "false";
  
  if (!hasConsent && !hasRejected) {
    banner.hidden = false;
  }
  
  if (acceptBtn) {
    acceptBtn.addEventListener("click", () => {
      localStorage.setItem("acuwealth-cookie-consent", "true");
      banner.hidden = true;
    });
  }
  
  if (rejectBtn) {
    rejectBtn.addEventListener("click", () => {
      localStorage.setItem("acuwealth-cookie-consent", "false");
      banner.hidden = true;
    });
  }
  
  if (manageBtn || resetBtn) {
    const btn = manageBtn || resetBtn;
    btn.addEventListener("click", () => {
      localStorage.removeItem("acuwealth-cookie-consent");
      banner.hidden = false;
    });
  }
}

function setupScrollProgress() {
  const progressBar = document.getElementById("scrollProgress");
  if (!progressBar) return;
  
  const updateProgress = () => {
    const windowHeight = document.documentElement.scrollHeight - window.innerHeight;
    if (windowHeight <= 0) {
      progressBar.style.width = "0%";
      return;
    }
    const scrolled = (window.scrollY / windowHeight) * 100;
    progressBar.style.width = ${scrolled}%;
  };
  
  window.addEventListener("scroll", updateProgress);
  window.addEventListener("resize", updateProgress);
  updateProgress(); // Initial call
}

function setupOfflineDetection() {
  const banner = document.getElementById("offlineBanner");
  if (!banner) return;
  
  const updateOnlineStatus = () => {
    if (navigator.onLine) {
      banner.hidden = true;
    } else {
      banner.hidden = false;
    }
  };
  
  window.addEventListener("online", updateOnlineStatus);
  window.addEventListener("offline", updateOnlineStatus);
  updateOnlineStatus();
}

function setupBackToTop() {
  const button = document.getElementById("backToTop");
  if (!button) return;
  
  const toggleBackToTop = () => {
    if (window.scrollY > 300) {
      button.classList.add("visible");
    } else {
      button.classList.remove("visible");
    }
  };
  
  button.addEventListener("click", () => {
    window.scrollTo({ top: 0, behavior: "smooth" });
  });
  
  window.addEventListener("scroll", toggleBackToTop);
  toggleBackToTop(); // Initial check
}

function setupPasswordToggle() {
  const toggleBtn = document.getElementById("passwordToggleBtn");
  const passwordInput = document.getElementById("authPasswordInput");
  if (!toggleBtn || !passwordInput) return;
  
  toggleBtn.addEventListener("click", () => {
    const isPassword = passwordInput.type === "password";
    passwordInput.type = isPassword ? "text" : "password";
    toggleBtn.setAttribute("aria-pressed", String(!isPassword));
    toggleBtn.setAttribute("aria-label", isPassword ? "Hide password" : "Show password");
  });
}

function setupCopyToClipboard() {
  // This will be initialized later when dashboard elements are available
  window.initCopyToClipboard = function() {
    const amounts = [
      { id: "balanceAmount", label: "Balance" },
      { id: "incomeAmount", label: "Income this month" },
      { id: "expenseAmount", label: "Expenses this month" },
      { id: "monthlyNet", label: "Monthly net" }
    ];
    
    amounts.forEach(({id, label}) => {
      const element = document.getElementById(id);
      if (!element) return;
      
      // Create copy button
      const copyBtn = document.createElement("button");
      copyBtn.className = "copy-btn";
      copyBtn.setAttribute("aria-label", Copy );
      copyBtn.innerHTML = <svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h3a2 2 0 0 1 2 2v1"/></svg>;
      
      // Position it
      const wrapper = document.createElement("span");
      wrapper.style.position = "relative";
      wrapper.style.display = "inline-block";
      
      // Replace the element with wrapper containing both
      const parent = element.parentNode;
      if (!parent) return;
      
      wrapper.appendChild(element);
      wrapper.appendChild(copyBtn);
      parent.replaceChild(wrapper, element);
      
      copyBtn.addEventListener("click", async () => {
        try {
          await navigator.clipboard.writeText(element.textContent.trim());
          copyBtn.innerHTML = <svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M9 12l2 2 4-4"/></svg>;
          setTimeout(() => {
            copyBtn.innerHTML = <svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h3a2 2 0 0 1 2 2v1"/></svg>;
          }, 1500);
        } catch (err) {
          console.warn("Copy failed", err);
          copyBtn.setAttribute("aria-label", "Copy failed");
          setTimeout(() => {
            copyBtn.setAttribute("aria-label", Copy );
          }, 1500);
        }
      });
    });
  };
}

function setupConfirmationDialogs() {
  const dialog = document.getElementById("confirmDialog");
  const form = document.getElementById("confirmForm");
  const cancelBtn = document.getElementById("confirmCancel");
  const confirmBtn = document.getElementById("confirmConfirm");
  const title = document.getElementById("confirmTitle");
  const message = document.getElementById("confirmMessage");
  
  if (!dialog || !form) return;
  
  window.showConfirm = (titleText, messageText, onConfirm) => {
    if (title) title.textContent = titleText;
    if (message) message.textContent = messageText;
    dialog.showModal();
    
    const handleConfirm = (e) => {
      e.preventDefault();
      dialog.close();
      if (typeof onConfirm === "function") onConfirm();
    };
    
    const handleCancel = () => {
      dialog.close();
    };
    
    form.removeEventListener("submit", handleConfirm);
    cancelBtn.removeEventListener("click", handleCancel);
    
    form.addEventListener("submit", handleConfirm);
    cancelBtn.addEventListener("click", handleCancel);
  };
  
  if (cancelBtn) {
    cancelBtn.addEventListener("click", () => dialog.close());
  }
}

function setupDataDeletion() {
  const deleteBtn = document.getElementById("deleteAccountButton");
  if (!deleteBtn) return;
  
  deleteBtn.addEventListener("click", async () => {
    window.showConfirm(
      "Delete Account",
      "Are you sure you want to permanently delete your account and all financial data? This action cannot be undone.",
      async () => {
        try {
          const response = await fetch("/api/data-request", {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              "X-CSRF-Token": state.csrfToken
            }
          });
          
          if (response.ok) {
            showToast("Your account and all data have been permanently deleted.");
            // Redirect to landing page after delay
            setTimeout(() => {
              window.location.href = "/";
            }, 1500);
          } else {
            const error = await response.json();
            showToast(error.error || "Failed to delete account");
          }
        } catch (err) {
          showToast("Network error. Please try again.");
        }
      }
    );
  });
}

function setupUnsubscribe() {
  const unsubscribeForm = document.getElementById("unsubscribeForm");
  if (!unsubscribeForm) return;
  
  unsubscribeForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const emailInput = document.getElementById("unsubscribeEmail");
    if (!emailInput) return;
    
    const email = emailInput.value.trim();
    if (!email) return;
    
    try {
      const response = await fetch("/api/unsubscribe", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email })
      });
      
      if (response.ok) {
        showToast("You have been unsubscribed from non-essential emails.");
        emailInput.value = "";
      } else {
        const error = await response.json();
        showToast(error.error || "Unsubscribe failed");
      }
    } catch (err) {
      showToast("Network error. Please try again.");
    }
  });
}

function setupPublicDataRequest() {
  const form = document.getElementById("publicDataRequestForm");
  if (!form) return;
  
  const statusEl = document.getElementById("dataRequestStatus");
  
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const emailInput = document.getElementById("dataRequestEmail");
    if (!emailInput) return;
    
    const email = emailInput.value.trim();
    if (!email) {
      if (statusEl) {
        statusEl.textContent = "Please enter your email address.";
        statusEl.hidden = false;
      }
      return;
    }
    
    try {
      const response = await fetch("/api/data-request", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email })
      });
      
      if (response.ok) {
        if (statusEl) {
          statusEl.textContent = "If an account exists with that email, it has been scheduled for deletion.";
          statusEl.hidden = false;
          statusEl.className = "form-feedback success";
        }
        emailInput.value = "";
      } else {
        const error = await response.json();
        if (statusEl) {
          statusEl.textContent = error.error || "Request failed";
          statusEl.hidden = false;
          statusEl.className = "form-feedback error";
        }
      }
    } catch (err) {
      if (statusEl) {
        statusEl.textContent = "Network error. Please try again.";
        statusEl.hidden = false;
        statusEl.className = "form-feedback error";
      }
    }
  });
}

function captureUTMParams() {
  // Capture UTM params from URL and store in localStorage for signup
  const urlParams = new URLSearchParams(window.location.search);
  const utmParams = ["utm_source", "utm_medium", "utm_campaign"];
  let hasUTM = false;
  
  utmParams.forEach(param => {
    const value = urlParams.get(param);
    if (value) {
      localStorage.setItem(param, value);
      hasUTM = true;
    }
  });
  
  return hasUTM;
}

function applyUTMToSignupForm() {
  // Apply stored UTM params to the signup form when shown via landing page
  const utmParams = ["utm_source", "utm_medium", "utm_campaign"];
  utmParams.forEach(param => {
    const value = localStorage.getItem(param);
    if (value) {
      // Find the auth form inputs and set their values
      const authForm = document.getElementById("authForm");
      if (!authForm) return;
      
      const input = authForm.elements.namedItem(param.replace("utm_", ""));
      if (input) {
        input.value = value;
      }
    }
  });
}

/* ========== END NEW FEATURE HELPERS ========== */
'''

    # Insert helpers after the state declaration
    state_end = "    searchTimer: null,"
    if state_end in src:
        src = src.replace(state_end, state_end + helpers, 1)
    else:
        print("State end marker not found")
        return 1

    # Update the start() function to call the new initializers
    old_start = '''    async function start() {
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
  }'''

    new_start = '''    async function start() {
    try {
      const savedTheme = localStorage.getItem("acuwealth-theme");
      if (savedTheme === "dark" || savedTheme === "light") setTheme(savedTheme);
    } catch {
      setTheme("dark");
    }
    setupRevealAnimations();
    setupMobileMenu();
    setupCookieConsent();
    setupScrollProgress();
    setupOfflineDetection();
    setupBackToTop();
    setupPasswordToggle();
    setupConfirmationDialogs();
    setupDataDeletion();
    setupUnsubscribe();
    setupPublicDataRequest();
    
    // Handle UTM parameters
    if (window.location.pathname === "/" || window.location.pathname === "" || window.location.pathname === "/index.html") {
      captureUTMParams();
      applyUTMToSignupForm();
    }
    
    showLanding();
    try {
      await loadCurrencies();
      const response = await api("/api/session");
      if (response.user) displayApplication(response.user);
    } catch (error) {
      showToast(error.message);
    }
  }'''

    if old_start in src:
        src = src.replace(old_start, new_start, 1)
    else:
        print("Old start marker not found")
        return 1

    # Also need to init copy-to-clipboard when dashboard loads
    # Find the loadDashboard function and add the call
    load_dashboard_end = "    return { today, month_label };"
    if load_dashboard_end in src:
        src = src.replace(load_dashboard_end, load_dashboard_end + "\n\n    // Initialize copy-to-clipboard for dashboard amounts\n    initCopyToClipboard();", 1)
    else:
        print("Load dashboard end marker not found")
        return 1

    try:
        open(js_path, "w", encoding="utf-8").write(src)
        print("JavaScript updated successfully")
        return 0
    except Exception as e:
        print(f"Error writing file: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())