import json
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError

import app as finance_app


class FinanceAppTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.app = finance_app.create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "test-secret-key",
                "DATABASE": str(Path(self.temp_dir.name) / "test.sqlite3"),
                "DATABASE_URL": None,
            }
        )
        self.client = self.app.test_client()
        response = self.client.get("/")
        html = response.get_data(as_text=True)
        marker = '<meta name="csrf-token" content="'
        self.csrf_token = html.split(marker, 1)[1].split('"', 1)[0]

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_landing_page_includes_finance_content_and_auth_actions(self):
        response = self.client.get("/")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn('id="landingSignupForm"', html)
        self.assertIn("Track your money.", html)
        self.assertIn('data-open-auth="signup"', html)
        self.assertIn('data-open-auth="login"', html)
        self.assertIn('id="authForm"', html)
        self.assertIn('class="auth-aside"', html)
        self.assertEqual(html.count('class="button theme-toggle"'), 2)
        self.assertIn('id="appShell"', html)
        self.assertIn('id="profileMenuButton"', html)
        self.assertIn('id="profileMenu"', html)
        self.assertIn("Switch account", html)
        self.assertIn("Log out", html)
        self.assertNotIn('class="button logout-button"', html)

    def headers(self):
        return {"X-CSRF-Token": self.csrf_token}

    def sign_up(self, email="maya@example.com", password="good-password-123"):
        response = self.client.post(
            "/api/auth/signup",
            json={"name": "Maya Rao", "email": email, "password": password},
            headers=self.headers(),
        )
        if response.status_code == 201:
            self.csrf_token = response.json["csrf_token"]
        return response

    def add_transaction(
        self,
        *,
        kind="income",
        category="Salary",
        amount="52000.00",
        currency="INR",
        description="Monthly pay",
        occurred_on="2026-10-02",
    ):
        return self.client.post(
            "/api/transactions",
            json={
                "kind": kind,
                "category": category,
                "amount": amount,
                "currency": currency,
                "description": description,
                "occurred_on": occurred_on,
            },
            headers=self.headers(),
        )

    def test_new_account_defaults_to_inr_and_login_works(self):
        response = self.sign_up()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json["user"]["currency"], "INR")
        self.assertNotIn("password", response.json["user"])
        self.csrf_token = response.json["csrf_token"]

        logout_response = self.client.post("/api/auth/logout", json={}, headers=self.headers())
        self.assertEqual(logout_response.status_code, 200)
        self.csrf_token = logout_response.json["csrf_token"]
        login_response = self.client.post(
            "/api/auth/login",
            json={"email": "MAYA@example.com", "password": "good-password-123"},
            headers=self.headers(),
        )
        self.assertEqual(login_response.status_code, 200)
        self.assertEqual(login_response.json["user"]["email"], "maya@example.com")

    def test_signup_validates_password_and_email_uniqueness(self):
        short_password = self.client.post(
            "/api/auth/signup",
            json={"name": "Maya Rao", "email": "maya@example.com", "password": "short"},
            headers=self.headers(),
        )
        self.assertEqual(short_password.status_code, 422)

        self.assertEqual(self.sign_up().status_code, 201)
        duplicate = self.sign_up(email="MAYA@example.com")
        self.assertEqual(duplicate.status_code, 409)

    def test_api_requires_csrf_token_and_login(self):
        without_token = self.client.post(
            "/api/auth/signup",
            json={"name": "Maya Rao", "email": "maya@example.com", "password": "good-password-123"},
        )
        self.assertEqual(without_token.status_code, 400)
        unauthenticated = self.client.get("/api/dashboard")
        self.assertEqual(unauthenticated.status_code, 401)
        bootstrap = self.client.get("/api/session")
        self.assertEqual(bootstrap.status_code, 200)
        self.assertIsNone(bootstrap.json["user"])
        self.assertTrue(bootstrap.json["csrf_token"])

    def test_api_server_errors_return_json(self):
        broken_database = Path(self.temp_dir.name) / "database-directory"
        broken_database.mkdir()
        self.app.config["DATABASE"] = str(broken_database)
        self.app.config["PROPAGATE_EXCEPTIONS"] = False

        response = self.client.post(
            "/api/auth/login",
            json={"email": "maya@example.com", "password": "good-password-123"},
            headers=self.headers(),
        )

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.mimetype, "application/json")
        self.assertIn("server error", response.json["error"].lower())

    def test_postgres_backend_initializes_schema_and_uses_postgres_placeholders(self):
        class FakeCursor:
            def fetchone(self):
                return None

        class FakePostgresConnection:
            def __init__(self):
                self.queries = []
                self.committed = False
                self.closed = False

            def execute(self, query, parameters=()):
                self.queries.append((query, parameters))
                return FakeCursor()

            def cursor(self):
                return self

            def executemany(self, query, parameters):
                self.queries.append((query, list(parameters)))

            def commit(self):
                self.committed = True

            def close(self):
                self.closed = True

        connection = FakePostgresConnection()
        self.app.config["DATABASE_URL"] = "postgresql://user:pass@localhost/acuwealth"

        with patch("app.psycopg.connect", return_value=connection) as connect:
            response = self.client.post(
                "/api/auth/login",
                json={"email": "maya@example.com", "password": "good-password-123"},
                headers=self.headers(),
            )

        self.assertEqual(response.status_code, 401)
        connect.assert_called_once()
        self.assertTrue(connection.committed)
        self.assertTrue(connection.closed)
        self.assertTrue(
            any("GENERATED BY DEFAULT AS IDENTITY" in query for query, _ in connection.queries)
        )
        self.assertTrue(
            any("WHERE email = %s" in query for query, _ in connection.queries)
        )

    def test_transaction_is_saved_in_its_original_currency_and_is_user_scoped(self):
        self.sign_up()
        self.csrf_token = self.client.get("/api/me").json["csrf_token"]
        response = self.add_transaction(
            kind="expense",
            category="Groceries",
            amount="1499.25",
            currency="USD",
            description="Market",
        )
        self.assertEqual(response.status_code, 201)
        result = self.client.get("/api/transactions")
        self.assertEqual(len(result.json["transactions"]), 1)
        self.assertEqual(result.json["transactions"][0]["amount"], "1499.25")
        self.assertEqual(result.json["transactions"][0]["currency"], "USD")

        outsider = self.app.test_client()
        outsider.get("/")
        outsider_html = outsider.get("/").get_data(as_text=True)
        marker = '<meta name="csrf-token" content="'
        outsider_csrf = outsider_html.split(marker, 1)[1].split('"', 1)[0]
        outsider.post(
            "/api/auth/signup",
            json={"name": "Nikhil Shah", "email": "nikhil@example.com", "password": "another-password"},
            headers={"X-CSRF-Token": outsider_csrf},
        )
        self.assertEqual(
            outsider.delete(
                f"/api/transactions/{response.json['id']}",
                headers={"X-CSRF-Token": outsider.get("/api/me").json["csrf_token"]},
            ).status_code,
            404,
        )

    def test_transactions_validate_amount_and_category(self):
        self.sign_up()
        wrong_category = self.add_transaction(kind="expense", category="Salary")
        self.assertEqual(wrong_category.status_code, 422)

        invalid_amount = self.add_transaction(amount="NaN")
        self.assertEqual(invalid_amount.status_code, 422)

        zero_amount = self.add_transaction(amount="0")
        self.assertEqual(zero_amount.status_code, 422)

    def test_dashboard_converts_foreign_currency_and_stores_original_amount(self):
        self.sign_up()
        self.add_transaction(amount="100.00", currency="USD")
        provider_data = json.dumps(
            {"result": "success", "rates": {"INR": 1, "USD": 0.012, "EUR": 0.011}}
        ).encode()
        with patch(
            "app.urllib.request.urlopen",
            return_value=BytesIO(provider_data),
        ):
            response = self.client.get("/api/dashboard")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["summary"]["balance"], "8333.33")
        self.assertEqual(response.json["transactions"][0]["amount"], "100.00")
        self.assertEqual(response.json["transactions"][0]["base_amount"], "8333.33")

    def test_dashboard_says_when_conversion_is_unavailable(self):
        self.sign_up()
        self.add_transaction(amount="100.00", currency="USD")
        with patch("app.urllib.request.urlopen", side_effect=URLError("offline")):
            response = self.client.get("/api/dashboard")
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json["summary"]["balance"])
        self.assertEqual(response.json["rates"]["status"], "unavailable")
        self.assertIn("provider", response.json["rates"]["error"])

    def test_conversion_uses_cached_rates_when_provider_is_offline(self):
        self.sign_up()
        with self.app.app_context():
            db = finance_app.sqlite3.connect(self.app.config["DATABASE"])
            db.execute(
                "INSERT INTO exchange_rates (base_currency, quote_currency, rate, fetched_at) "
                "VALUES ('INR', 'USD', '0.01', '2026-10-10T12:00:00+00:00')"
            )
            db.commit()
            db.close()
        with patch("app.urllib.request.urlopen", side_effect=URLError("offline")):
            response = self.client.get("/api/convert?amount=10&from=USD&to=INR")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["converted_amount"], "1000.00")
        self.assertEqual(response.json["status"], "cached")

    def test_user_can_change_display_currency(self):
        self.sign_up()
        response = self.client.patch(
            "/api/preferences",
            json={"currency": "EUR"},
            headers=self.headers(),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get("/api/me").json["user"]["currency"], "EUR")

        unsupported = self.client.patch(
            "/api/preferences",
            json={"currency": "ZZZ"},
            headers=self.headers(),
        )
        self.assertEqual(unsupported.status_code, 422)


if __name__ == "__main__":
    unittest.main()
