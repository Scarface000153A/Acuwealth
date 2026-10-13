import sys

def main():
    path = r"C:\Users\User\Desktop\Acuwealth\app.py"
    src = open(path, "r", encoding="utf-8").read()
    
    # Find the protect_state_changes function and add exemption for public endpoints
    old_code = '''    @app.before_request
    def protect_state_changes() -> Any:
        if request.method in {"POST", "PATCH", "PUT", "DELETE"}:
            supplied = request.headers.get("X-CSRF-Token", "")
            expected = session.get("csrf_token", "")
            if not expected or not hmac.compare_digest(supplied, expected):
                return jsonify(error="Your session token has expired. Reload the page and try again."), 400
        return None'''
    
    new_code = '''    @app.before_request
    def protect_state_changes() -> Any:
        # Exempt public endpoints from CSRF protection
        if request.path in ["/api/unsubscribe", "/api/data-request-public"]:
            return None
        if request.method in {"POST", "PATCH", "PUT", "DELETE"}:
            supplied = request.headers.get("X-CSRF-Token", "")
            expected = session.get("csrf_token", "")
            if not expected or not hmac.compare_digest(supplied, expected):
                return jsonify(error="Your session token has expired. Reload the page and try again."), 400
        return None'''
    
    if old_code not in src:
        print("Old code not found")
        return 1
        
    src = src.replace(old_code, new_code, 1)
    open(path, "w", encoding="utf-8").write(src)
    print("CSRF protection updated to exempt public endpoints")
    return 0

if __name__ == "__main__":
    sys.exit(main())