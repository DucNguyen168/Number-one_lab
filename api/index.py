from app.main import app as _app


class VercelPathMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            path = scope.get("path", "")
            headers = dict(scope.get("headers", []))
            x_matched = headers.get(b"x-matched-path", b"").decode("latin-1")
            x_forwarded_uri = headers.get(b"x-forwarded-uri", b"").decode("latin-1")

            if x_forwarded_uri and not x_forwarded_uri.startswith("/api/index"):
                scope["path"] = x_forwarded_uri.split("?")[0]
            elif x_matched and not x_matched.startswith("/api/index"):
                scope["path"] = x_matched.split("?")[0]
            elif path in ("/api/index.py", "/api/index", "/api"):
                scope["path"] = "/"
            elif path.startswith("/api/index.py/"):
                scope["path"] = path[len("/api/index.py"):]
            elif path.startswith("/api/index/"):
                scope["path"] = path[len("/api/index"):]

        await self.app(scope, receive, send)


app = VercelPathMiddleware(_app)
