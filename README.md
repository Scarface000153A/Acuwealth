# Acuwealth

A personal finance tracker built with Flask, SQLite, HTML, CSS, and JavaScript. Its public landing page introduces the product and leads into account sign-up or sign-in. Create an account to record income and expenses, review monthly cash flow, and convert dashboard totals into your preferred display currency.

## Run locally

1. Install Python 3.10 or newer.
2. Install the dependency:

   ```powershell
   python -m pip install -r requirements.txt
   ```

3. Start the development server:

   ```powershell
   python app.py
   ```

4. Open <http://127.0.0.1:5000>.

New accounts default to INR. Change the display currency in the dashboard or in **Preferences**. Transactions retain the currency and amount in which they were entered.

## Exchange rates

The app retrieves public exchange rates from [open.er-api.com](https://open.er-api.com/) when a conversion is needed and caches them in SQLite for one hour. No account data is sent to the rate provider. If a refresh fails, the app identifies when it is displaying cached rates. If no rate is available, converted totals remain unavailable instead of being estimated.

## Smooth text inputs

Text, email, password, and search fields use a smoothly tracking caret inspired by [Skiper UI's skiper106](https://skiper-ui.com/registry/skiper106.json). The effect is implemented in the app's plain JavaScript and CSS, not copied from the React component or its `framer-motion` and `dialkit` dependencies. It respects reduced-motion preferences and retains native inputs, labels, and keyboard behavior.

The account and dashboard theme control is an accessible sun-and-moon switch with no external component dependency.

## Transaction and form animations

The sign-in/sign-up panel and the dashboard content animate into view, and animated text overlays add a brief pop to the newest typed character while inputs retain native validation and keyboard behavior. Sign-up includes a live password-strength meter. After a transaction is saved, dashboard totals count from their current values and the new transaction row slides into view. These effects respect reduced-motion preferences; if Chrome reports `prefers-reduced-motion: reduce`, motion is intentionally suppressed.

## Configuration

- `SECRET_KEY`: set a persistent, private random value before deploying.
- `APP_DATABASE`: optional SQLite database path. Defaults to `instance/acuwealth.sqlite3`.
- `APP_ENV=production`: enables secure session cookies. Serve the site over HTTPS in production.
- `PORT`: optional development-server port. Defaults to `5000`.

The Flask development server is intended for local development. Deploy behind a production WSGI server and HTTPS before exposing the app publicly.

## Tests

```powershell
python -m unittest -v
```
