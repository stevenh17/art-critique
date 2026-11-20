"""Command line: `artcrit serve` runs the local app on 127.0.0.1."""

import argparse


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="artcrit")
    sub = p.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve", help="run the local web app")
    serve.add_argument("--host", default="127.0.0.1", help="bind address (keep it local)")
    serve.add_argument("--port", type=int, default=8000)
    sub.add_parser("publish", help="build the portfolio site into site/ and publish it to gh-pages")
    sub.add_parser("fetch-models", help="download the face landmark model into data/models/")
    return p


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    if args.command == "publish":
        from artcrit.config import Settings
        from artcrit.site.service import Publisher
        from artcrit.store.images import ImageStore
        from artcrit.store.sessions import SessionStore

        settings = Settings()
        p = Publisher(SessionStore(settings.db_path), ImageStore(settings.images_dir), settings, lambda fn: fn())
        p.request()
        print(p.last())
    elif args.command == "fetch-models":
        from artcrit.config import Settings
        from artcrit.geometry.landmarks import fetch_model

        print(fetch_model(Settings()))
    elif args.command == "serve":
        import uvicorn

        from artcrit.config import Settings
        from artcrit.engine.claude_sdk import ClaudeSDKEngine
        from artcrit.web.app import create_app

        from artcrit.geometry.landmarks import model_path
        from artcrit.geometry.service import Geometry

        settings = Settings()
        app = create_app(settings, ClaudeSDKEngine(), geometry=Geometry(model_path(settings)))
        uvicorn.run(app, host=args.host, port=args.port)
