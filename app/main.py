"""
Flow Manual Search - offline question search for the Dirac Flow user manual.

Normal start:  a native window (Microsoft Edge WebView2, built into Windows 11).
Fallback:      if the native window cannot start, the same interface opens in
               Microsoft Edge "app mode", served from 127.0.0.1 only.
No part of the program contacts the internet.

Command-line options (for troubleshooting):
    --server      force the fallback mode
    --selftest    run a test search, print the result and exit
"""
import base64
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

APP_NAME = "Flow Manual Search"


def resource_dir() -> Path:
    # PyInstaller unpacks bundled files to sys._MEIPASS
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))


def exe_dir() -> Path:
    return Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent


RES = resource_dir()
DATA = RES / "data"
UI_FILE = RES / "ui" / "index.html"

sys.path.insert(0, str(RES))
from search_engine import ManualIndex  # noqa: E402


def synonyms_file() -> Path:
    """A synonyms.json placed next to the .exe overrides the built-in list."""
    local = exe_dir() / "synonyms.json"
    return local if local.exists() else RES / "synonyms.json"


def log(msg: str):
    try:
        folder = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "FlowManualSearch"
        folder.mkdir(parents=True, exist_ok=True)
        with open(folder / "log.txt", "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + msg + "\n")
    except OSError:
        pass


class Api:
    """Functions the interface calls. Return values are plain JSON-able data."""

    def __init__(self):
        self.index = ManualIndex(DATA, synonyms_file())
        self._page_cache = {}

    def search(self, query):
        return self.index.search(str(query)[:500])

    def info(self):
        return self.index.info()

    def page_image(self, n):
        n = int(n)
        if n not in self._page_cache:
            p = DATA / "pages" / f"{n:02d}.jpg"
            if not p.exists():
                return None
            self._page_cache[n] = "data:image/jpeg;base64," + base64.b64encode(p.read_bytes()).decode()
        return self._page_cache[n]

    def open_pdf(self, page=1):
        """Open the manual in the PDF viewer at the given page."""
        page = max(1, int(page))
        try:
            pdf = self._stable_pdf_copy()
        except OSError as e:
            log(f"PDF copy failed: {e}")
            return {"ok": False, "message": "The manual file could not be prepared."}
        edge = self._find_edge()
        if edge:  # Edge honours #page=N for local PDFs
            subprocess.Popen([edge, pdf.as_uri() + f"#page={page}"])
            return {"ok": True, "message": f"Opened the manual at page {page} in Microsoft Edge."}
        if hasattr(os, "startfile"):
            os.startfile(str(pdf))  # default viewer; page jump depends on the viewer
            return {"ok": True, "message": f"Opened the manual. Go to page {page}."}
        webbrowser.open(pdf.as_uri() + f"#page={page}")
        return {"ok": True, "message": f"Opened the manual at page {page}."}

    @staticmethod
    def _stable_pdf_copy() -> Path:
        # The one-file .exe unpacks to a temp folder that disappears on exit,
        # so the viewer gets its own copy in %LOCALAPPDATA%.
        src = DATA / "manual.pdf"
        folder = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "FlowManualSearch"
        folder.mkdir(parents=True, exist_ok=True)
        dst = folder / "Dirac_Flow_User_Manual.pdf"
        if not dst.exists() or dst.stat().st_size != src.stat().st_size:
            shutil.copyfile(src, dst)
        return dst

    @staticmethod
    def _find_edge():
        for base in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles"),
                     os.environ.get("LOCALAPPDATA")):
            if base:
                p = Path(base) / "Microsoft" / "Edge" / "Application" / "msedge.exe"
                if p.exists():
                    return str(p)
        return shutil.which("msedge")


# ---------------- native window ----------------
def run_native(api: Api) -> bool:
    try:
        import webview
    except Exception as e:  # pywebview or its Windows bridge missing
        log(f"pywebview unavailable: {e!r}")
        return False
    try:
        webview.create_window(APP_NAME, url=str(UI_FILE), js_api=api,
                              width=1200, height=800, min_size=(820, 560),
                              background_color="#EDF0F3", text_select=True)
        webview.start(gui="edgechromium" if sys.platform == "win32" else None,
                      private_mode=True)
        return True
    except Exception as e:
        log(f"native window failed: {e!r}")
        return False


# ---------------- fallback: local-only server + Edge app window ----------------
def run_server(api: Api):
    last_ping = [time.time()]
    html = UI_FILE.read_bytes()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, body: bytes, ctype="application/json"):
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            u = urlparse(self.path)
            q = {k: v[0] for k, v in parse_qs(u.query).items()}
            last_ping[0] = time.time()
            if u.path in ("/", "/index.html"):
                return self._send(html, "text/html; charset=utf-8")
            routes = {
                "/api/search": lambda: api.search(q.get("q", "")),
                "/api/info": api.info,
                "/api/page": lambda: api.page_image(q.get("n", 1)),
                "/api/open": lambda: api.open_pdf(q.get("page", 1)),
                "/api/ping": lambda: {"ok": True},
            }
            if u.path == "/favicon.ico":
                self.send_response(204)
                self.end_headers()
                return
            if u.path in routes:
                return self._send(json.dumps(routes[u.path]()).encode())
            self.send_error(404)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)  # loopback only
    url = f"http://127.0.0.1:{server.server_port}/?mode=server"
    threading.Thread(target=server.serve_forever, daemon=True).start()

    edge = Api._find_edge()
    if edge:
        subprocess.Popen([edge, f"--app={url}", "--window-size=1200,800"])
    else:
        webbrowser.open(url)
    print(f"{APP_NAME} running at {url}", flush=True)
    # The page pings every 5 s; quit once the window has been closed for a while.
    try:
        while time.time() - last_ping[0] < 30:
            time.sleep(2)
    except KeyboardInterrupt:
        pass
    server.shutdown()


def main():
    args = sys.argv[1:]
    try:
        api = Api()
    except Exception as e:
        log(f"index load failed: {e!r}")
        raise
    if "--selftest" in args:
        r = api.search("How do I connect Flow to the device?")
        print(json.dumps(r["results"][:2], indent=2, ensure_ascii=False))
        return
    if "--server" in args or not run_native(api):
        run_server(api)


if __name__ == "__main__":
    main()
