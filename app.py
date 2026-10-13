from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from functools import wraps
from pathlib import Path
from typing import Any, Callable

from flask import Flask, g, jsonify, render_template, request, session


ROOT = Path(__file__).resolve().parent
PASSWORD_ITERATIONS = 310_000
RATE_CACHE_SECONDS = 60 * 60
SUPPORTED_CURRENCIES = {
    "AED": ("UAE dirham", "د.إ"),
    "AUD": ("Australian dollar", "A$"),
    "BRL": ("Brazilian real", "R$"),
    "CAD": ("Canadian dollar", "CA$"),
    "CHF": ("Swiss franc", "CHF"),
    "CNY": ("Chinese yuan", "CN¥"),
    "EUR": ("Euro", "€"),
    "GBP": ("British pound", "£"),
    "HKD": ("Hong Kong dollar", "HK$"),
    "INR": ("Indian rupee", "₹"),
    "JPY": ("Japanese yen", "¥"),
    "KRW": ("South Korean won", "₩"),
    "MXN": ("Mexican peso", "MX$"),
    "NOK": ("Norwegian krone", "NOK"),
    "NZD": ("New Zealand dollar", "NZ$"),
    "SEK": ("Swedish krona", "SEK"),
    "SGD": ("Singapore dollar", "S$"),
    "USD": ("US dollar", "$"),
    "ZAR": ("South African rand", "R"),
}
INCOME_CATEGORIES = (
    "Salary",
    "Freelance",
    "Investments",
    "Gifts",
    "Other income",
)
EXPENSE_CATEGORIES = (
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
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_salt TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    currency TEXT NOT NULL DEFAULT 'INR',
    utm_source TEXT DEFAULT '',
    utm_medium TEXT DEFAULT '',
    utm_campaign TEXT DEFAULT '',
    email_opt_out INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (kind IN ('income', 'expense')),
    category TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
    currency TEXT NOT NULL,
    occurred_on TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS transactions_by_user_date
    ON transactions (user_id, occurred_on DESC, id DESC);

CREATE TABLE IF NOT EXISTS exchange_rates (
    base_currency TEXT NOT NULL,
    quote_currency TEXT NOT NULL,
    rate TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (base_currency, quote_currency)
);
"""


class ExchangeRateUnavailable(Exception):
    pass


class RateLimiter:
    """Simple per-IP + per-endpoint token bucket.

    Disabled entirely when ``APP_ENV`` is not ``production`` so that
    local development and the test suite are unaffected.
    """

    def __init__(self, requests_per_minute: int = 60) -> None:
        self.enabled = os.environ.get("APP_ENV") == "production"
        self.requests_per_minute = max(1, requests_per_minute)
        self.buckets: dict[tuple[str, str], tuple[float, int]] = {}

    def allow(self, key: str, *, limit: int | None = None) -> bool:
        if not self.enabled:
            return True
        effective_limit = limit if limit is not None else self.requests_per_minute
        now = time.monotonic()
        window_start, tokens = self.buckets.get(key, (now, effective_limit))
        elapsed = now - window_start
        if elapsed >= 60:
            tokens = effective_limit
            window_start = now
        else:
            tokens = min(effective_limit, tokens + elapsed * effective_limit / 60.0)
        if tokens < 1:
            self.buckets[key] = (window_start, tokens)
            return False
        self.buckets[key] = (window_start, tokens - 1)
        return True

    def client_key(self) -> str:
        forwarded = request.headers.get("X-Forwarded-For", "")
        if forwarded:
            return forwarded.split(",", 1)[0].strip() or request.remote_addr or "unknown"
        return request.remote_addr or "unknown"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def amount_to_cents(value: Any) -> int:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError("Enter a valid amount.") from None
    if not amount.is_finite() or amount <= 0 or amount > Decimal("999999999999.99"):
        raise ValueError("Enter an amount greater than zero and below 1 trillion.")
    return int((amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def cents_to_amount(cents: int) -> str:
    return format((Decimal(cents) / 100).quantize(Decimal("0.01")), "f")


def convert_cents(cents: int, source: str, target: str, rates: dict[str, Decimal]) -> int:
    if source == target:
        return cents
    target_per_source = Decimal(1) / rates[source]
    return int(
        (Decimal(cents) * target_per_source).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    )


def create_app(test_config: dict[str, Any] | None = None) -> Flask:
    app = Flask(__name__)
    default_database = Path(os.environ.get("APP_DATABASE", ROOT / "instance" / "acuwealth.sqlite3"))
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY") or secrets.token_hex(32),
        DATABASE=str(default_database),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("APP_ENV") == "production",
        MAX_CONTENT_LENGTH=1 * 1024 * 1024,
    )
    if test_config:
        app.config.update(test_config)

    def run_migrations(connection: sqlite3.Connection) -> None:
        for column, default in (
            ("utm_source", "''"),
            ("utm_medium", "''"),
            ("utm_campaign", "''"),
            ("email_opt_out", "0"),
        ):
            try:
                connection.execute(f"ALTER TABLE users ADD COLUMN {column} TEXT DEFAULT {default}")
                connection.commit()
            except sqlite3.OperationalError as exc:
                if "duplicate column name" not in str(exc).lower():
                    raise

    limiter = RateLimiter()

    @app.before_request
    def protect_state_changes() -> Any:
        # Exempt public endpoints from CSRF protection
        if request.path in ["/api/unsubscribe", "/api/data-request-public"]:
            return None
        if request.method in {"POST", "PATCH", "PUT", "DELETE"}:
            supplied = request.headers.get("X-CSRF-Token", "")
            expected = session.get("csrf_token", "")
            if not expected or not hmac.compare_digest(supplied, expected):
                return jsonify(error="Your session token has expired. Reload the page and try again."), 400
        return None

    def get_db() -> sqlite3.Connection:
        if "db" not in g:
            database_path = Path(app.config["DATABASE"])
            database_path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(database_path)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(SCHEMA)
            run_migrations(connection)
            g.db = connection
        return g.db

    @app.teardown_appcontext
    def close_db(_error: BaseException | None = None) -> None:
        connection = g.pop("db", None)
        if connection is not None:
            connection.close()

    def csrf_token() -> str:
        token = session.get("csrf_token")
        if not token:
            token = secrets.token_urlsafe(32)
            session["csrf_token"] = token
        return token

    def authenticated(view: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(view)
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            user_id = session.get("user_id")
            if not user_id:
                return jsonify(error="Please sign in to continue."), 401
            user = get_db().execute(
                "SELECT id, name, email, currency FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
            if user is None:
                session.clear()
                return jsonify(error="Your account session has expired. Please sign in again."), 401
            g.user = user
            return view(*args, **kwargs)

        return wrapped

    def json_body() -> dict[str, Any]:
        body = request.get_json(silent=True)
        return body if isinstance(body, dict) else {}

    def user_payload(user: sqlite3.Row) -> dict[str, str]:
        return {
            "id": str(user["id"]),
            "name": user["name"],
            "email": user["email"],
            "currency": user["currency"],
        }

    def stored_rates(base: str) -> tuple[dict[str, Decimal], str | None]:
        rows = get_db().execute(
            "SELECT quote_currency, rate, fetched_at FROM exchange_rates "
            "WHERE base_currency = ?",
            (base,),
        ).fetchall()
        if not rows:
            return {}, None
        try:
            rates = {row["quote_currency"]: Decimal(row["rate"]) for row in rows}
            fetched_at = min(row["fetched_at"] for row in rows)
        except (InvalidOperation, ValueError):
            return {}, None
        rates[base] = Decimal(1)
        return rates, fetched_at

    def exchange_rates(base: str) -> tuple[dict[str, Decimal], str, str]:
        db = get_db()
        cached, cached_at = stored_rates(base)
        if cached_at:
            try:
                cache_time = datetime.fromisoformat(cached_at)
            except ValueError:
                cache_time = datetime.min.replace(tzinfo=timezone.utc)
            if (utc_now() - cache_time).total_seconds() < RATE_CACHE_SECONDS:
                return cached, "live", cached_at

        url = f"https://open.er-api.com/v6/latest/{base}"
        req = urllib.request.Request(url, headers={"User-Agent": "Acuwealth/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
            response_rates = payload.get("rates")
            if payload.get("result") != "success" or not isinstance(response_rates, dict):
                raise ExchangeRateUnavailable("The exchange rate provider returned an invalid response.")
            fetched_at = utc_now().isoformat(timespec="seconds")
            fresh_rates = {base: Decimal(1)}
            for code in SUPPORTED_CURRENCIES:
                rate_value = response_rates.get(code)
                if rate_value is not None:
                    rate = Decimal(str(rate_value))
                    if rate.is_finite() and rate > 0:
                        fresh_rates[code] = rate
            if len(fresh_rates) < 2:
                raise ExchangeRateUnavailable("The exchange rate provider returned incomplete currency data.")
            db.executemany(
                "INSERT INTO exchange_rates (base_currency, quote_currency, rate, fetched_at) "
                "VALUES (?, ?, ?, ?) ON CONFLICT (base_currency, quote_currency) "
                "DO UPDATE SET rate = excluded.rate, fetched_at = excluded.fetched_at",
                [
                    (base, code, format(rate, "f"), fetched_at)
                    for code, rate in fresh_rates.items()
                ],
            )
            db.commit()
            return fresh_rates, "live", fetched_at
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError, InvalidOperation) as exc:
            if cached:
                return cached, "cached", cached_at or ""
            if isinstance(exc, urllib.error.URLError):
                reason = "The rate provider could not be reached."
            elif isinstance(exc, (TimeoutError, OSError)):
                reason = "The rate provider is temporarily unavailable."
            else:
                reason = "The rate provider returned data that could not be read."
            raise ExchangeRateUnavailable(reason) from exc
        except ExchangeRateUnavailable:
            if cached:
                return cached, "cached", cached_at or ""
            raise

    def convert_groups(
        groups: list[sqlite3.Row],
        base: str,
        rates: dict[str, Decimal],
        amount_field: str = "amount_cents",
    ) -> int | None:
        total = 0
        for row in groups:
            currency = row["currency"]
            if currency not in rates:
                return None
            total += convert_cents(row[amount_field], currency, base, rates)
        return total

    def format_converted_amount(
        cents: int,
        source: str,
        base: str,
        rates: dict[str, Decimal],
    ) -> str | None:
        if source not in rates:
            return None
        return cents_to_amount(convert_cents(cents, source, base, rates))

    def resolve_rates(base: str, foreign_currencies: set[str]) -> tuple[dict[str, Decimal], str, str, str | None]:
        required = foreign_currencies - {base}
        if not required:
            return {base: Decimal(1)}, "not_needed", "", None
        try:
            rates, status, fetched_at = exchange_rates(base)
            return rates, status, fetched_at, None
        except ExchangeRateUnavailable as exc:
            return {base: Decimal(1)}, "unavailable", "", str(exc)

    @app.get("/")
    def index() -> str:
        return render_template("index.html", csrf_token=csrf_token(), year=date.today().year)

    @app.get("/privacy")
    def privacy_policy() -> str:
        return render_template("privacy.html", csrf_token=csrf_token(), year=date.today().year)

    @app.get("/terms")
    def terms_of_service() -> str:
        return render_template("terms.html", csrf_token=csrf_token(), year=date.today().year)

    @app.get("/refund")
    def refund_policy() -> str:
        return render_template("refund.html", csrf_token=csrf_token(), year=date.today().year)

    @app.get("/cookies")
    def cookie_policy() -> str:
        return render_template("cookies.html", csrf_token=csrf_token(), year=date.today().year)

    @app.get("/faq")
    def faq_page() -> str:
        return render_template("faq.html", csrf_token=csrf_token(), year=date.today().year)

    @app.errorhandler(404)
    def not_found(error: Any) -> Any:
        if request.path.startswith("/api/"):
            return jsonify(error="Resource not found."), 404
        return render_template("404.html", csrf_token=csrf_token(), year=date.today().year), 404

    @app.errorhandler(500)
    def internal_server_error(_error: Any) -> Any:
        if request.path.startswith("/api/"):
            return jsonify(error="A server error occurred while processing your request. Please try again."), 500
        return "An internal server error occurred.", 500

    @app.get("/api/session")
    def session_state() -> Any:
        user_id = session.get("user_id")
        user = None
        if user_id:
            user = get_db().execute(
                "SELECT id, name, email, currency FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
            if user is None:
                session.clear()
        return jsonify(
            user=user_payload(user) if user is not None else None,
            csrf_token=csrf_token(),
        )

    @app.get("/api/me")
    @authenticated
    def current_user() -> Any:
        return jsonify(user=user_payload(g.user), csrf_token=csrf_token())

    @app.post("/api/auth/signup")
    def signup() -> Any:
        body = json_body()
        name = str(body.get("name", "")).strip()
        email = str(body.get("email", "")).strip().lower()
        password = body.get("password", "")
        utm = {
            "source": str(body.get("utm_source", "") or request.args.get("utm_source", "")).strip().lower()[:64],
            "medium": str(body.get("utm_medium", "") or request.args.get("utm_medium", "")).strip().lower()[:64],
            "campaign": str(body.get("utm_campaign", "") or request.args.get("utm_campaign", "")).strip().lower()[:64],
        }
        if not 2 <= len(name) <= 80:
            return jsonify(error="Enter your name using 2 to 80 characters."), 422
        if len(email) > 254 or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            return jsonify(error="Enter a valid email address."), 422
        if not isinstance(password, str) or len(password) < 10 or len(password) > 128:
            return jsonify(error="Choose a password between 10 and 128 characters."), 422

        salt = secrets.token_bytes(16)
        password_hash = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS
        ).hex()
        try:
            cursor = get_db().execute(
                "INSERT INTO users (name, email, password_salt, password_hash, currency, "
                "utm_source, utm_medium, utm_campaign, email_opt_out, created_at) "
                "VALUES (?, ?, ?, ?, 'INR', ?, ?, ?, 0, ?)",
                (
                    name,
                    email,
                    salt.hex(),
                    password_hash,
                    utm["source"],
                    utm["medium"],
                    utm["campaign"],
                    utc_now().isoformat(timespec="seconds"),
                ),
            )
            get_db().commit()
        except sqlite3.IntegrityError:
            return jsonify(error="An account with that email address already exists."), 409

        session.clear()
        session["user_id"] = cursor.lastrowid
        return jsonify(
            user=user_payload(
                get_db().execute(
                    "SELECT id, name, email, currency FROM users WHERE id = ?",
                    (cursor.lastrowid,),
                ).fetchone()
            ),
            csrf_token=csrf_token(),
        ), 201

    @app.post("/api/data-request")
    @authenticated
    def data_request() -> Any:
        user_id = g.user["id"]
        db = get_db()
        db.execute("DELETE FROM transactions WHERE user_id = ?", (user_id,))
        db.execute("DELETE FROM users WHERE id = ?", (user_id,))
        db.commit()
        session.clear()
        return jsonify(ok=True, message="Your account and all stored data have been permanently deleted.")

    @app.post("/api/unsubscribe")
    def unsubscribe() -> Any:
        email = str(json_body().get("email", "") or request.form.get("email", "") or "").strip().lower()
        if not email or len(email) > 254 or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            return jsonify(error="Enter a valid email address."), 422
        db = get_db()
        db.execute("UPDATE users SET email_opt_out = 1 WHERE email = ?", (email,))
        db.commit()
        return jsonify(ok=True, message="You have been unsubscribed from non-essential emails.")

    
    @app.post("/api/data-request-public")
    def public_data_request() -> Any:
        """Public data deletion request by email address (no auth required)."""
        email = str(json_body().get("email", "") or request.form.get("email", "") or "").strip().lower()
        if not email or len(email) > 254 or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            return jsonify(error="Enter a valid email address."), 422
        db = get_db()
        db.execute("DELETE FROM transactions WHERE user_id = (SELECT id FROM users WHERE email = ?)", (email,))
        db.execute("DELETE FROM users WHERE email = ?", (email,))
        db.commit()
        return jsonify(ok=True, message="If an account exists with that email, it has been scheduled for deletion.")

    @app.post("/api/auth/login")
    def login() -> Any:
        body = json_body()
        email = str(body.get("email", "")).strip().lower()
        password = body.get("password", "")
        if not isinstance(password, str) or len(password) > 128:
            return jsonify(error="The email address or password is incorrect."), 401
        user = get_db().execute(
            "SELECT id, name, email, password_salt, password_hash, currency "
            "FROM users WHERE email = ?",
            (email,),
        ).fetchone()
        valid = False
        if user is not None:
            candidate = hashlib.pbkdf2_hmac(
                "sha256",
                password.encode("utf-8"),
                bytes.fromhex(user["password_salt"]),
                PASSWORD_ITERATIONS,
            ).hex()
            valid = hmac.compare_digest(candidate, user["password_hash"])
        if not valid:
            return jsonify(error="The email address or password is incorrect."), 401
        session.clear()
        session["user_id"] = user["id"]
        return jsonify(user=user_payload(user), csrf_token=csrf_token())

    @app.post("/api/auth/logout")
    @authenticated
    def logout() -> Any:
        session.clear()
        return jsonify(ok=True, csrf_token=csrf_token())

    @app.get("/api/currencies")
    def currencies() -> Any:
        return jsonify(
            currencies=[
                {"code": code, "name": name, "symbol": symbol}
                for code, (name, symbol) in SUPPORTED_CURRENCIES.items()
            ]
        )

    @app.get("/api/convert")
    @authenticated
    def convert() -> Any:
        source = request.args.get("from", "").upper()
        target = request.args.get("to", "").upper()
        if source not in SUPPORTED_CURRENCIES or target not in SUPPORTED_CURRENCIES:
            return jsonify(error="Choose currencies from the supported currency list."), 422
        try:
            cents = amount_to_cents(request.args.get("amount", ""))
        except ValueError as exc:
            return jsonify(error=str(exc)), 422
        if source == target:
            return jsonify(
                amount=cents_to_amount(cents),
                converted_amount=cents_to_amount(cents),
                rate="1",
                from_currency=source,
                to_currency=target,
                status="live",
            )
        try:
            rates, status, fetched_at = exchange_rates(target)
        except ExchangeRateUnavailable as exc:
            return jsonify(error=str(exc)), 503
        if source not in rates:
            return jsonify(error=f"A current {source} to {target} rate is not available."), 503
        converted = convert_cents(cents, source, target, rates)
        rate = Decimal(1) / rates[source]
        return jsonify(
            amount=cents_to_amount(cents),
            converted_amount=cents_to_amount(converted),
            rate=format(rate.quantize(Decimal("0.00000001")), "f"),
            from_currency=source,
            to_currency=target,
            status=status,
            fetched_at=fetched_at,
        )

    @app.post("/api/transactions")
    @authenticated
    def create_transaction() -> Any:
        body = json_body()
        kind = str(body.get("kind", ""))
        if kind not in {"income", "expense"}:
            return jsonify(error="Choose income or expense."), 422
        category = str(body.get("category", "")).strip()
        allowed_categories = INCOME_CATEGORIES if kind == "income" else EXPENSE_CATEGORIES
        if category not in allowed_categories:
            return jsonify(error="Choose a category that matches this transaction type."), 422
        currency = str(body.get("currency", "")).upper()
        if currency not in SUPPORTED_CURRENCIES:
            return jsonify(error="Choose a supported currency."), 422
        description = str(body.get("description", "")).strip()
        if len(description) > 120:
            return jsonify(error="Keep the description to 120 characters or fewer."), 422
        try:
            cents = amount_to_cents(body.get("amount", ""))
        except ValueError as exc:
            return jsonify(error=str(exc)), 422
        try:
            occurred_on = date.fromisoformat(str(body.get("occurred_on", "")))
        except ValueError:
            return jsonify(error="Choose a valid transaction date."), 422

        cursor = get_db().execute(
            "INSERT INTO transactions "
            "(user_id, kind, category, description, amount_cents, currency, occurred_on, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                g.user["id"],
                kind,
                category,
                description,
                cents,
                currency,
                occurred_on.isoformat(),
                utc_now().isoformat(timespec="seconds"),
            ),
        )
        get_db().commit()
        return jsonify(id=cursor.lastrowid, message="Transaction saved."), 201

    @app.delete("/api/transactions/<int:transaction_id>")
    @authenticated
    def delete_transaction(transaction_id: int) -> Any:
        result = get_db().execute(
            "DELETE FROM transactions WHERE id = ? AND user_id = ?",
            (transaction_id, g.user["id"]),
        )
        get_db().commit()
        if result.rowcount == 0:
            return jsonify(error="This transaction was not found."), 404
        return jsonify(ok=True)

    @app.get("/api/transactions")
    @authenticated
    def list_transactions() -> Any:
        kind = request.args.get("kind", "")
        if kind and kind not in {"income", "expense"}:
            return jsonify(error="Choose income or expense."), 422
        query = request.args.get("q", "").strip()[:80]
        sql = (
            "SELECT id, kind, category, description, amount_cents, currency, occurred_on "
            "FROM transactions WHERE user_id = ?"
        )
        parameters: list[Any] = [g.user["id"]]
        if kind:
            sql += " AND kind = ?"
            parameters.append(kind)
        if query:
            sql += " AND (category LIKE ? OR description LIKE ?)"
            parameters.extend((f"%{query}%", f"%{query}%"))
        sql += " ORDER BY occurred_on DESC, id DESC LIMIT 100"
        rows = get_db().execute(sql, parameters).fetchall()
        return jsonify(
            transactions=[
                {
                    "id": row["id"],
                    "kind": row["kind"],
                    "category": row["category"],
                    "description": row["description"],
                    "amount": cents_to_amount(row["amount_cents"]),
                    "currency": row["currency"],
                    "occurred_on": row["occurred_on"],
                }
                for row in rows
            ]
        )

    @app.patch("/api/preferences")
    @authenticated
    def update_preferences() -> Any:
        currency = str(json_body().get("currency", "")).upper()
        if currency not in SUPPORTED_CURRENCIES:
            return jsonify(error="Choose a supported display currency."), 422
        get_db().execute(
            "UPDATE users SET currency = ? WHERE id = ?",
            (currency, g.user["id"]),
        )
        get_db().commit()
        return jsonify(currency=currency, message="Display currency updated.")

    @app.get("/api/dashboard")
    @authenticated
    def dashboard() -> Any:
        db = get_db()
        user_id = g.user["id"]
        base = g.user["currency"]
        today = date.today()
        month_start = today.replace(day=1).isoformat()
        if today.month == 12:
            next_month = today.replace(year=today.year + 1, month=1, day=1)
        else:
            next_month = today.replace(month=today.month + 1, day=1)

        all_totals = db.execute(
            "SELECT currency, kind, SUM(amount_cents) AS amount_cents "
            "FROM transactions WHERE user_id = ? GROUP BY currency, kind",
            (user_id,),
        ).fetchall()
        monthly_totals = db.execute(
            "SELECT currency, kind, SUM(amount_cents) AS amount_cents FROM transactions "
            "WHERE user_id = ? AND occurred_on >= ? AND occurred_on < ? "
            "GROUP BY currency, kind",
            (user_id, month_start, next_month.isoformat()),
        ).fetchall()
        all_transactions = db.execute(
            "SELECT currency FROM transactions WHERE user_id = ? GROUP BY currency",
            (user_id,),
        ).fetchall()
        foreign_currencies = {row["currency"] for row in all_transactions}
        rates, rate_status, rates_fetched_at, rate_error = resolve_rates(base, foreign_currencies)

        def net_total(groups: list[sqlite3.Row]) -> int | None:
            by_kind: dict[str, list[sqlite3.Row]] = {"income": [], "expense": []}
            for group in groups:
                by_kind[group["kind"]].append(group)
            income = convert_groups(by_kind["income"], base, rates)
            expense = convert_groups(by_kind["expense"], base, rates)
            if income is None or expense is None:
                return None
            return income - expense

        balance_cents = net_total(all_totals)
        month_income = convert_groups(
            [row for row in monthly_totals if row["kind"] == "income"], base, rates
        )
        month_expense = convert_groups(
            [row for row in monthly_totals if row["kind"] == "expense"], base, rates
        )

        trend_start = (today.replace(day=1) - timedelta(days=155)).replace(day=1)
        trend_rows = db.execute(
            "SELECT substr(occurred_on, 1, 7) AS month, currency, kind, "
            "SUM(amount_cents) AS amount_cents FROM transactions "
            "WHERE user_id = ? AND occurred_on >= ? AND occurred_on < ? "
            "GROUP BY month, currency, kind ORDER BY month",
            (user_id, trend_start.isoformat(), next_month.isoformat()),
        ).fetchall()
        trend_months: dict[str, dict[str, list[sqlite3.Row]]] = {}
        for row in trend_rows:
            trend_months.setdefault(row["month"], {"income": [], "expense": []})[
                row["kind"]
            ].append(row)
        month_keys: list[str] = []
        for offset in range(5, -1, -1):
            year = today.year
            month_number = today.month - offset
            while month_number <= 0:
                month_number += 12
                year -= 1
            month_keys.append(f"{year:04d}-{month_number:02d}")
        trend = []
        for month in month_keys:
            groups = trend_months.get(month, {"income": [], "expense": []})
            trend.append(
                {
                    "month": datetime.strptime(month, "%Y-%m").strftime("%b"),
                    "income": (
                        cents_to_amount(convert_groups(groups["income"], base, rates))
                        if convert_groups(groups["income"], base, rates) is not None
                        else None
                    ),
                    "expense": (
                        cents_to_amount(convert_groups(groups["expense"], base, rates))
                        if convert_groups(groups["expense"], base, rates) is not None
                        else None
                    ),
                }
            )

        categories_rows = db.execute(
            "SELECT category, currency, SUM(amount_cents) AS amount_cents "
            "FROM transactions WHERE user_id = ? AND kind = 'expense' "
            "AND occurred_on >= ? AND occurred_on < ? "
            "GROUP BY category, currency ORDER BY amount_cents DESC",
            (user_id, month_start, next_month.isoformat()),
        ).fetchall()
        category_totals: dict[str, int | None] = {}
        for row in categories_rows:
            category_value = format_converted_amount(
                row["amount_cents"], row["currency"], base, rates
            )
            category_cents = (
                int(Decimal(category_value) * 100) if category_value is not None else None
            )
            if row["category"] not in category_totals:
                category_totals[row["category"]] = category_cents
            elif category_totals[row["category"]] is None or category_cents is None:
                category_totals[row["category"]] = None
            else:
                category_totals[row["category"]] += category_cents
        categories = sorted(
            [
                {"category": category, "amount": cents_to_amount(value) if value is not None else None}
                for category, value in category_totals.items()
            ],
            key=lambda item: Decimal(item["amount"]) if item["amount"] is not None else Decimal(-1),
            reverse=True,
        )[:5]
        if month_expense is not None:
            for category in categories:
                category["share"] = (
                    round(Decimal(category["amount"]) * 100 / Decimal(cents_to_amount(month_expense)))
                    if category["amount"] is not None and month_expense > 0
                    else 0
                )
        else:
            for category in categories:
                category["share"] = None

        recent = db.execute(
            "SELECT id, kind, category, description, amount_cents, currency, occurred_on "
            "FROM transactions WHERE user_id = ? "
            "ORDER BY occurred_on DESC, id DESC LIMIT 8",
            (user_id,),
        ).fetchall()
        recent_transactions = []
        for row in recent:
            recent_transactions.append(
                {
                    "id": row["id"],
                    "kind": row["kind"],
                    "category": row["category"],
                    "description": row["description"],
                    "amount": cents_to_amount(row["amount_cents"]),
                    "currency": row["currency"],
                    "base_amount": format_converted_amount(
                        row["amount_cents"], row["currency"], base, rates
                    ),
                    "occurred_on": row["occurred_on"],
                }
            )
        return jsonify(
            user=user_payload(g.user),
            currency=base,
            summary={
                "balance": cents_to_amount(balance_cents) if balance_cents is not None else None,
                "income": cents_to_amount(month_income) if month_income is not None else None,
                "expenses": cents_to_amount(month_expense) if month_expense is not None else None,
                "net": (
                    cents_to_amount(month_income - month_expense)
                    if month_income is not None and month_expense is not None
                    else None
                ),
            },
            trend=trend,
            categories=categories,
            transactions=recent_transactions,
            rates={"status": rate_status, "fetched_at": rates_fetched_at, "error": rate_error},
            today=today.isoformat(),
            month_label=today.strftime("%B %Y"),
            currencies=[
                {"code": code, "name": name, "symbol": symbol}
                for code, (name, symbol) in SUPPORTED_CURRENCIES.items()
            ],
        )

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "5000")))
