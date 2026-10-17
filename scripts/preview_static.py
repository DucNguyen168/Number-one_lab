from __future__ import annotations

import argparse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


APP_ROUTES = {
    "/",
    "/ket-qua",
    "/du-doan-2-so",
    "/du-doan-n-1",
    "/du-doan-than-tai",
    "/du-doan-catboost-2-so",
    "/backtest",
}
PROJECT_ROOT = Path(__file__).resolve().parents[1]


class PreviewHandler(SimpleHTTPRequestHandler):
    def translate_path(self, path: str) -> str:
        clean_path = path.split("?", 1)[0]
        if clean_path in APP_ROUTES:
            return str(PROJECT_ROOT / "app" / "static" / "index.html")
        if clean_path.startswith("/static/"):
            relative = clean_path.removeprefix("/static/")
            return str(PROJECT_ROOT / "app" / "static" / relative)
        if clean_path.startswith("/img/"):
            relative = clean_path.removeprefix("/img/")
            return str(PROJECT_ROOT / "img" / relative)
        return super().translate_path(path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Preview the dashboard without MongoDB")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), PreviewHandler)
    print(f"Static preview: http://127.0.0.1:{args.port}/du-doan-than-tai")
    server.serve_forever()


if __name__ == "__main__":
    main()
