"""Command line: `artcrit serve` runs the local app on 127.0.0.1."""

import argparse


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="artcrit")
    sub = p.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve", help="run the local web app")
    serve.add_argument("--host", default="127.0.0.1", help="bind address (keep it local)")
    serve.add_argument("--port", type=int, default=8000)
    sub.add_parser("fetch-models", help="download the face landmark model into data/models/")
    return p


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    if args.command == "fetch-models":
        from artcrit.config import Settings
        from artcrit.geometry.landmarks import fetch_model

        print(fetch_model(Settings()))
    elif args.command == "serve":
        import uvicorn

        from artcrit.config import Settings
        from artcrit.engine.claude_sdk import ClaudeSDKEngine
        from artcrit.web.app import create_app

        uvicorn.run(create_app(Settings(), ClaudeSDKEngine()), host=args.host, port=args.port)
