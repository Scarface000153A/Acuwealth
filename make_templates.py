from pathlib import Path

TEMPLATES = Path(r"C:\Users\User\Desktop\Acuwealth\templates")

NAV_AND_HEAD = """<!doctype html>
<html lang="en" data-theme="dark">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta name="csrf-token" content="{{ csrf_token }}">
    <meta name="theme-color" content="#030405">
    <meta name="description" content="{desc}">
    <title>{title} | Acuwealth</title>
    <link rel="icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 24 24%22 fill=%22none%22 stroke=%22%23c6c9ce%22 stroke-width=%221.5%22><circle cx=%2212%22 cy=%2212%22 r=%229%22/><path d=%22M3.5 12h17M12 3c2.4 2.5 3.6 5.5 3.6 9S14.4 18.5 12 21c-2.4-2.5-3.6-5.5-3.6-9S9.6 5.5 12 3Z%22/></svg>">
    <link rel="stylesheet" href="{{ url_for('static', filename='styles.css') }}">
    <script src="{{ url_for('static', filename='app.js') }}" defer></script>
  </head>
  <body class="legal-page">
    <a href="#content" class="skip-link">Skip to content</a>
    <div class="scroll-progress" id="scrollProgress" aria-hidden="true"></div>
    <header class="legal-nav liquid-glass">
      <a class="landing-brand" href="/" aria-label="Acuwealth home">
        <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <circle cx="12" cy="12" r="9"></circle>
          <path d="M3.5 12h17M12 3c2.4 2.5 3.6 5.5 3.6 9S14.4 18.5 12 21c-2.4-2.5-3.6-5.5-3.6-9S9.6 5.5 12 3Z"></path>
        </svg>
        <span>Acuwealth</span>
      </a>
      <nav class="landing-links" aria-label="Main navigation">
        <a href="/#features">Features</a>
        <a href="/#currencies">Currencies</a>
        <a href="/faq">FAQ</a>
        <a href="/privacy">Privacy</a>
      </nav>
      <div class="landing-nav-actions">
        <a class="landing-login-button liquid-glass" href="/">Open App</a>
      </div>
    </header>
    <main id="content" class="legal-main">
"""

FOOTER = """
    </main>
    <footer class="landing-footer legal-footer">
      <a class="landing-brand" href="/" aria-label="Acuwealth home">
        <svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><circle cx="12" cy="12" r="9"></circle><path d="M3.5 12h17M12 3c2.4 2.5 3.6 5.5 3.6 9S14.4 18.5 12 21c-2.4-2.5-3.6-5.5-3.6-9S9.6 5.5 12 3Z"></path></svg>
        <span>Acuwealth</span>
      </a>
      <div class="legal-footer-links">
        <a href="/privacy">Privacy Policy</a>
        <a href="/terms">Terms of Service</a>
        <a href="/refund">Refund Policy</a>
        <a href="/cookies">Cookie Policy</a>
        <a href="/faq">FAQ</a>
      </div>
      <p>&copy; {{ year }} Acuwealth. Personal finance tracker. Free, open, private.</p>
    </footer>
    <button class="back-to-top" id="backToTop" type="button" aria-label="Back to top">
      <svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="m18 15-6-6-6 6"></path></svg>
    </button>
  </body>
</html>
"""

PAGES = {
    "privacy.html": (
        "Privacy Policy",
        "Acuwealth Privacy Policy — how we protect your personal financial data.",
        """
      <article class="legal-article">
        <p class="landing-label">LEGAL &amp; PRIVACY</p>
        <h1>Privacy Policy</h1>
        <p class="legal-meta">Last updated: October 13, 2026 &bull; Effective date: October 13, 2026</p>

        <section>
          <h2>1. Overview</h2>
          <p>Acuwealth ("we", "our", or "us") is committed to protecting your personal information. This Privacy Policy describes how we collect, use, and safeguard your data when you use the Acuwealth personal finance application.</p>
        </section>

        <section>
          <h2>2. Data We Collect (And What We Don't)</h2>
          <p>We believe in minimal data collection. We only collect data that is strictly necessary to provide the service:</p>
          <ul>
            <li><strong>Account data:</strong> Your name, email address, and a salted and hashed password (PBKDF2-HMAC-SHA256 with 310,000 iterations). We never store plaintext passwords.</li>
            <li><strong>Financial activity:</strong> Income and expense transactions you explicitly record (description, amount, currency, category, and date).</li>
            <li><strong>Preferences:</strong> Your preferred display currency.</li>
            <li><strong>Marketing attribution:</strong> Optional UTM parameters (source, medium, campaign) if you arrived via a link.</li>
          </ul>
          <p><strong>We do NOT collect:</strong> Bank credentials, credit card numbers, location tracking, device telemetry, or children's personal data.</p>
        </section>

        <section>
          <h2>3. Children's Privacy</h2>
          <p>Acuwealth is not directed to individuals under the age of 16. We do not knowingly collect personal data from children. If you believe a child has provided us with personal information, please submit a deletion request and we will promptly remove it.</p>
        </section>

        <section>
          <h2>4. Third-Party Services and SDKs</h2>
          <p>We do not use advertising networks, social tracking pixels, or commercial analytics SDKs. The only third-party services we interact with are:</p>
          <ul>
            <li><strong>Exchange rates (open.er-api.com):</strong> Public exchange rate data is fetched by our server and cached locally. No user or account data is ever shared with the exchange rate provider.</li>
            <li><strong>Google Fonts:</strong> Typography stylesheets (Instrument Serif). Only your browser's standard font request is made.</li>
            <li><strong>Media CDN (CloudFront):</strong> Video demonstrations are hosted on a content delivery network. No cookies or personal identifiers are passed.</li>
          </ul>
        </section>

        <section>
          <h2>5. Your Rights &amp; Data Deletion</h2>
          <p>You have full ownership of your data. You may:</p>
          <ul>
            <li>View all of your stored transactions and account details at any time in the app.</li>
            <li>Delete individual transactions instantly.</li>
            <li>Request permanent deletion of your entire account and all associated transactions via our in-app Data Deletion tool or by submitting a request below.</li>
            <li>Opt out of non-essential email notifications at any time.</li>
          </ul>
          <div class="data-deletion-box">
            <h3>Need your data deleted?</h3>
            <p>Signed-in users can delete their entire account and all associated financial records immediately from their Preferences page, or use the form below.</p>
            <form id="publicDataRequestForm" class="legal-action-form">
              <label class="field">
                <span>Account email address</span>
                <input type="email" name="email" id="dataRequestEmail" required placeholder="you@example.com">
              </label>
              <button class="button button-danger" type="submit">Request Data Deletion</button>
            </form>
            <p id="dataRequestStatus" class="form-feedback" role="status" hidden></p>
          </div>
        </section>

        <section>
          <h2>6. Contact Us</h2>
          <p>For any questions regarding this Privacy Policy or your data, contact our Data Protection Officer:</p>
          <p>Email: <a href="mailto:privacy@acuwealth.example.com">privacy@acuwealth.example.com</a><br>
          Phone: <a href="tel:+18005550199">+1 (800) 555-0199</a></p>
        </section>
      </article>
"""
    ),
    "terms.html": (
        "Terms of Service",
        "Acuwealth Terms of Service — conditions of using our personal finance platform.",
        """
      <article class="legal-article">
        <p class="landing-label">LEGAL &amp; POLICIES</p>
        <h1>Terms of Service</h1>
        <p class="legal-meta">Last updated: October 13, 2026 &bull; Effective date: October 13, 2026</p>

        <section>
          <h2>1. Agreement to Terms</h2>
          <p>By accessing or using Acuwealth, you agree to be bound by these Terms of Service. If you do not agree to these terms, do not access or use our services.</p>
        </section>

        <section>
          <h2>2. Description of Service</h2>
          <p>Acuwealth is a personal finance tracker designed to help you record income and expenses, organize cash flow by category, and review your finances in your chosen currency. Acuwealth is currently provided completely free of charge.</p>
        </section>

        <section>
          <h2>3. No Financial, Legal, or Tax Advice</h2>
          <p>Acuwealth is a self-directed organizational tool. Nothing provided by Acuwealth constitutes financial, investment, tax, or legal advice. Exchange rates are provided for informational convenience and should not be relied upon for mission-critical currency trading.</p>
        </section>

        <section>
          <h2>4. User Responsibilities</h2>
          <p>You agree to:</p>
          <ul>
            <li>Provide accurate account information and keep your credentials secure.</li>
            <li>Maintain a strong password with at least 10 characters.</li>
            <li>Use the service solely for lawful personal finance tracking purposes.</li>
            <li>Not attempt to exploit, reverse engineer, or disrupt the platform or its APIs.</li>
          </ul>
        </section>

        <section>
          <h2>5. Transparent Practices (No Dark Patterns)</h2>
          <p>We are committed to honest software engineering. Acuwealth promises:</p>
          <ul>
            <li>No hidden fees or surprise subscriptions.</li>
            <li>No fake reviews, fabricated testimonials, or unverified claims.</li>
            <li>No pre-checked consents or manipulative interface patterns.</li>
            <li>Easy, one-click export or permanent deletion of your account.</li>
          </ul>
        </section>

        <section>
          <h2>6. Termination</h2>
          <p>You may stop using Acuwealth and delete your account at any time. We reserve the right to suspend or terminate accounts that violate these terms or abuse system resources.</p>
        </section>

        <section>
          <h2>7. Contact</h2>
          <p>Questions about the Terms of Service should be sent to <a href="mailto:support@acuwealth.example.com">support@acuwealth.example.com</a>.</p>
        </section>
      </article>
"""
    ),
    "refund.html": (
        "Refund Policy",
        "Acuwealth Refund Policy — our free service and billing principles.",
        """
      <article class="legal-article">
        <p class="landing-label">BILLING &amp; REFUNDS</p>
        <h1>Refund Policy</h1>
        <p class="legal-meta">Last updated: October 13, 2026 &bull; Effective date: October 13, 2026</p>

        <section>
          <h2>1. Completely Free Service</h2>
          <p><strong>Acuwealth is currently 100% free to use.</strong> You do not need to provide a credit card, payment details, or subscription commitment to use any feature of the platform.</p>
        </section>

        <section>
          <h2>2. No Hidden Fees</h2>
          <p>There are no setup fees, transaction fees, monthly maintenance fees, or hidden surcharges. All features — including multi-currency conversions, category tracking, and cash flow charts — are available at zero cost.</p>
        </section>

        <section>
          <h2>3. Future Paid Tiers (Should Any Be Introduced)</h2>
          <p>If Acuwealth ever introduces optional paid tiers or premium features in the future, we will offer a clear 30-day money-back guarantee, full refund terms, and transparent upfront pricing before charging any payment method.</p>
        </section>

        <section>
          <h2>4. Contact Billing Support</h2>
          <p>If you have any billing or account questions, contact us at <a href="mailto:billing@acuwealth.example.com">billing@acuwealth.example.com</a>.</p>
        </section>
      </article>
"""
    ),
    "cookies.html": (
        "Cookie Policy",
        "Acuwealth Cookie Policy — transparent explanation of our local storage and cookies.",
        """
      <article class="legal-article">
        <p class="landing-label">COOKIES &amp; PRIVACY</p>
        <h1>Cookie Policy</h1>
        <p class="legal-meta">Last updated: October 13, 2026 &bull; Effective date: October 13, 2026</p>

        <section>
          <h2>1. What Are Cookies?</h2>
          <p>Cookies and browser storage are small text files or key-value entries stored on your device by websites you visit. They help sites remember your session and preferences.</p>
        </section>

        <section>
          <h2>2. Cookies We Use</h2>
          <p>We use only <strong>strictly necessary</strong> cookies and local storage items essential for the application to function:</p>
          <table class="cookie-table">
            <thead>
              <tr>
                <th>Identifier</th>
                <th>Type</th>
                <th>Purpose</th>
                <th>Duration</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td><code>session</code></td>
                <td>HTTP cookie (HttpOnly, SameSite=Lax)</td>
                <td>Stores your signed-in session state and CSRF token.</td>
                <td>Session only</td>
              </tr>
              <tr>
                <td><code>acuwealth-theme</code></td>
                <td>localStorage</td>
                <td>Remembers your light/dark mode preference.</td>
                <td>Persistent</td>
              </tr>
              <tr>
                <td><code>acuwealth-cookie-consent</code></td>
                <td>localStorage</td>
                <td>Remembers your cookie banner acknowledgement.</td>
                <td>1 year</td>
              </tr>
            </tbody>
          </table>
        </section>

        <section>
          <h2>3. No Third-Party Tracking Cookies</h2>
          <p>We do not use advertising cookies, remarketing beacons, or third-party tracking cookies. Your financial data is never shared with advertiser networks.</p>
        </section>

        <section>
          <h2>4. Managing Your Preferences</h2>
          <p>You can clear cookies and local storage at any time via your browser settings. You can also reset your cookie consent choice below:</p>
          <button class="button button-quiet" id="resetCookieConsent" type="button">Reset Cookie Preferences</button>
        </section>
      </article>
"""
    ),
    "faq.html": (
        "Frequently Asked Questions",
        "Find answers about tracking finances, currency conversions, privacy, and account security in Acuwealth.",
        """
      <article class="legal-article faq-article">
        <p class="landing-label">SUPPORT &amp; HELP</p>
        <h1>Frequently Asked Questions</h1>
        <p class="legal-meta">Last updated: October 13, 2026 &bull; Find quick answers to common questions</p>

        <div class="faq-list">
          <details class="faq-item" open>
            <summary class="faq-question">Is Acuwealth really free to use?</summary>
            <div class="faq-answer">
              <p>Yes. Acuwealth is completely free for all users. There are no trial periods, no hidden fees, and no credit card required to sign up or use any tracking features.</p>
            </div>
          </details>

          <details class="faq-item">
            <summary class="faq-question">How does multi-currency conversion work?</summary>
            <div class="faq-answer">
              <p>When you record a transaction in a foreign currency, it stays in its original currency and amount. Dashboard totals and converted amounts are calculated using public exchange rates fetched from open.er-api.com, updated hourly and cached locally.</p>
            </div>
          </details>

          <details class="faq-item">
            <summary class="faq-question">Is my financial data shared with third parties?</summary>
            <div class="faq-answer">
              <p>Never. We do not sell your data, use advertising trackers, or share your financial records with any third party. The exchange rate service only receives currency pairs, never user or account information.</p>
            </div>
          </details>

          <details class="faq-item">
            <summary class="faq-question">How do I delete my data permanently?</summary>
            <div class="faq-answer">
              <p>You can delete individual transactions at any time. To permanently delete your entire account and all associated transactions, use the "Delete account" option in Preferences or submit a request on our <a href="/privacy">Privacy Policy</a> page.</p>
            </div>
          </details>

          <details class="faq-item">
            <summary class="faq-question">Can I access Acuwealth on my mobile phone?</summary>
            <div class="faq-answer">
              <p>Yes. Acuwealth is fully responsive and mobile-optimized. You get the complete tracking interface, slide-out navigation, and live updates on any modern mobile browser.</p>
            </div>
          </details>

          <details class="faq-item">
            <summary class="faq-question">Does Acuwealth work offline?</summary>
            <div class="faq-answer">
              <p>Acuwealth requires a network connection to sync your transactions securely with the server, but it includes an offline indicator to let you know if your internet connection is lost so you never lose track of unsaved actions.</p>
            </div>
          </details>
        </div>

        <section class="faq-contact">
          <h2>Still have questions?</h2>
          <p>Reach out to our support team at <a href="mailto:support@acuwealth.example.com">support@acuwealth.example.com</a> or call <a href="tel:+18005550199">+1 (800) 555-0199</a>.</p>
        </section>
      </article>
"""
    ),
    "404.html": (
        "Page Not Found",
        "The page you were looking for does not exist on Acuwealth.",
        """
      <article class="legal-article error-page-article">
        <p class="landing-label">ERROR 404</p>
        <h1>Page Not Found</h1>
        <p class="error-description">We couldn't find the page you were looking for. It might have been moved or doesn't exist.</p>
        <div class="error-actions">
          <a class="button button-primary" href="/">Return to Dashboard</a>
          <a class="button button-quiet" href="/faq">Visit FAQ</a>
        </div>
      </article>
"""
    )
}

for filename, (title, desc, body) in PAGES.items():
    html = NAV_AND_HEAD.format(title=title, desc=desc) + body + FOOTER
    (TEMPLATES / filename).write_text(html, encoding="utf-8")
    print(f"Created {filename}")