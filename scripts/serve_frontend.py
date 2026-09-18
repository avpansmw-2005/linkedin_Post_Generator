import sys
import os
import http.server
import socketserver
import webbrowser

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

PORT = 8080
DIRECTORY = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)


def find_free_port(start_port: int = 8080) -> int:
    import socket
    port = start_port
    while port < start_port + 50:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("localhost", port)) != 0:
                return port
            port += 1
    return start_port


def main():
    port = find_free_port(PORT)
    url = f"http://localhost:{port}"
    print("=" * 65)
    print(f"🚀 Autonomous LinkedIn AI Agent — Explainer Dashboard")
    print(f"📂 Serving directory: {DIRECTORY}")
    print(f"🔗 URL: {url}")
    print("=" * 65)
    print("Press Ctrl+C to stop the server.\n")

    # Automatically open in browser if not headless
    if "--no-browser" not in sys.argv:
        try:
            webbrowser.open(url)
        except Exception:
            pass

    with socketserver.TCPServer(("", port), Handler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down server.")


if __name__ == "__main__":
    main()
