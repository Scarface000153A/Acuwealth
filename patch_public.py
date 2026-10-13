import sys

def main():
    path = r"C:\Users\User\Desktop\Acuwealth\app.py"
    src = open(path, "r", encoding="utf-8").read()
    
    # Find the unsubscribe endpoint and add a public data request endpoint after it
    anchor = '        db.execute("UPDATE users SET email_opt_out = 1 WHERE email = ?", (email,))\n        db.commit()\n        return jsonify(ok=True, message="You have been unsubscribed from non-essential emails.")\n'
    
    if anchor not in src:
        print("Anchor not found")
        return 1
    
    new_route = anchor + '\n    \n    @app.post("/api/data-request-public")\n    def public_data_request() -> Any:\n        """Public data deletion request by email address (no auth required)."""\n        email = str(json_body().get("email", "") or request.form.get("email", "") or "").strip().lower()\n        if not email or len(email) > 254 or not re.fullmatch(r"[^@\\s]+@[^@\\s]+\\.[^@\\s]+", email):\n            return jsonify(error="Enter a valid email address."), 422\n        db = get_db()\n        db.execute("DELETE FROM transactions WHERE user_id = (SELECT id FROM users WHERE email = ?)", (email,))\n        db.execute("DELETE FROM users WHERE email = ?", (email,))\n        db.commit()\n        return jsonify(ok=True, message="If an account exists with that email, it has been scheduled for deletion.")\n'
    
    src = src.replace(anchor, new_route, 1)
    open(path, "w", encoding="utf-8").write(src)
    print("Public data request endpoint added")
    return 0

if __name__ == "__main__":
    sys.exit(main())