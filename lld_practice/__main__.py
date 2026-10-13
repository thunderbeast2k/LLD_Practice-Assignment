import argparse

from .config import build_service
from .server import serve


def main():
    ap = argparse.ArgumentParser(description="LLD Practice Platform")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--db", default="lld_practice.db")
    args = ap.parse_args()
    service = build_service(args.db)
    httpd = serve(service, args.host, args.port)
    print(f"LLD Practice Platform on http://{args.host}:{args.port}  (Ctrl+C to stop)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
