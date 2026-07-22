"""Loopback-only Covermail application."""

from covermail.web.app import AppConfig, create_app, run_local_app

__all__ = ["AppConfig", "create_app", "run_local_app"]
