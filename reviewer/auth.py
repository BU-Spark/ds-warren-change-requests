"""Invite-only accounts with operator-issued links; no external identity provider."""

import os
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlencode, urlsplit

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .accounts import Accounts

PUBLIC_ROUTES = {
    "/api/health",
    "/api/auth/session",
    "/api/auth/login",
    "/api/auth/confirm",
    "/api/auth/reset",
    "/api/auth/logout",
}
EMAIL = re.compile(r"[^\s@,]+@[^\s@,]+\.[^\s@,]+")


def normalize_email(email):
    email = email.strip().casefold()
    if len(email) > 254 or not EMAIL.fullmatch(email):
        raise ValueError("Enter a valid email address.")
    return email


@dataclass(frozen=True)
class AuthConfig:
    origin: str

    @property
    def secure(self):
        return self.origin.startswith("https://")

    @property
    def session_cookie(self):
        return "__Host-warren-session" if self.secure else "warren-session"

    @classmethod
    def from_env(cls):
        if os.getenv("WARREN_SUPABASE_URL") or os.getenv(
            "WARREN_SUPABASE_PUBLISHABLE_KEY"
        ):
            raise RuntimeError(
                "Remove obsolete WARREN_SUPABASE settings; authentication is now managed by this app."
            )
        origin = os.getenv("WARREN_PUBLIC_URL", "").strip().rstrip("/")
        hosted = bool(
            os.getenv("RAILWAY_ENVIRONMENT_ID") or os.getenv("RAILWAY_PUBLIC_DOMAIN")
        )
        if (
            not origin
            and not hosted
            and os.getenv("WARREN_ALLOW_UNAUTHENTICATED") == "1"
        ):
            return None
        app_url = urlsplit(origin)
        try:
            port = app_url.port
        except ValueError:
            raise RuntimeError("WARREN_PUBLIC_URL has an invalid port.") from None
        if (
            not app_url.hostname
            or app_url.username
            or app_url.password
            or app_url.path
            or app_url.query
            or app_url.fragment
            or port == 0
        ):
            raise RuntimeError(
                "Set WARREN_PUBLIC_URL to the app origin without a path; authentication is required."
            )
        if app_url.scheme != "https" and not (
            app_url.scheme == "http"
            and not hosted
            and app_url.hostname in {"localhost", "127.0.0.1"}
        ):
            raise RuntimeError("Use HTTPS for the hosted app.")
        if hosted and (
            not os.getenv("DATABASE_URL") or not os.getenv("WARREN_DATA_DIR")
        ):
            raise RuntimeError(
                "Railway requires DATABASE_URL and WARREN_DATA_DIR on a persistent volume."
            )
        if hosted:
            mount = os.getenv("RAILWAY_VOLUME_MOUNT_PATH", "")
            if (
                not mount
                or not Path(mount).is_dir()
                or Path(mount).resolve()
                != Path(os.environ["WARREN_DATA_DIR"]).resolve()
            ):
                raise RuntimeError(
                    "Attach an app volume and set WARREN_DATA_DIR to its mount path."
                )
        return cls(origin)


def signed_in_email(config, request):
    return request.app.state.accounts.session_email(
        request.cookies.get(config.session_cookie)
    )


class Credentials(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(min_length=1, max_length=128)


class NewPassword(BaseModel):
    password: str = Field(min_length=12, max_length=128)


class Confirmation(BaseModel):
    kind: str = Field(pattern="^(invite|recovery)$")
    token: str = Field(min_length=32, max_length=128, pattern=r"^[a-zA-Z0-9_-]+$")


class AccountAction(BaseModel):
    email: str = Field(max_length=254)
    action: str = Field(pattern="^(invite|reset|disable)$")


def invitation_link(config, token, kind):
    # Fragment tokens never reach server access logs or Referer headers.
    return (
        config.origin
        + "/#"
        + urlencode({"auth": "confirm", "type": kind, "token": token})
    )


def register_auth(app: FastAPI, config: AuthConfig | None):
    accounts = Accounts(app.state.store.database) if config else None
    app.state.accounts = accounts
    reset_cookie = (
        "__Secure-warren-recovery" if config and config.secure else "warren-recovery"
    )
    reset_path = "/api/auth/reset"

    def configured():
        if config is None:
            raise HTTPException(404, "Account sign-in is unavailable.")
        return config

    def set_token(response, cfg, name, path, token, seconds):
        response.set_cookie(
            name,
            token,
            max_age=seconds,
            path=path,
            httponly=True,
            secure=cfg.secure,
            samesite="lax",
        )

    def clear(response, cfg, name, path="/"):
        response.delete_cookie(
            name, path=path, secure=cfg.secure, httponly=True, samesite="lax"
        )

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request, exc):
        if request.url.path.startswith("/api/auth/"):
            return JSONResponse(
                {"detail": "Check your entries and try again."}, status_code=422
            )
        from fastapi.exception_handlers import request_validation_exception_handler

        return await request_validation_exception_handler(request, exc)

    @app.get("/api/auth/session")
    def session(request: Request):
        email = signed_in_email(config, request) if config else None
        return {
            "enabled": config is not None,
            "email": email,
            "role": accounts.role(email) if email else None,
        }

    @app.post("/api/auth/login")
    def login(body: Credentials, response: Response):
        cfg = configured()
        email = body.email.strip().casefold()
        token = accounts.login(email, body.password)
        if not token:
            raise HTTPException(
                401,
                "Unable to sign in. Check your details or contact your project team.",
            )
        set_token(response, cfg, cfg.session_cookie, "/", token, 3600)
        return {"email": email, "role": accounts.role(email)}

    @app.post("/api/auth/confirm")
    def confirm(body: Confirmation, response: Response):
        cfg = configured()
        token = accounts.confirm(body.token, body.kind)
        if not token:
            raise HTTPException(
                400,
                "This link is invalid or expired. Contact your project team for a new link.",
            )
        set_token(response, cfg, reset_cookie, reset_path, token, 600)
        return {"kind": body.kind}

    @app.post(reset_path)
    def reset(body: NewPassword, request: Request, response: Response):
        cfg = configured()
        token = request.cookies.get(reset_cookie)
        if (
            not token
            or len(token) > 128
            or not accounts.set_password(token, body.password)
        ):
            raise HTTPException(
                400, "Your link has expired. Contact your project team for a new link."
            )
        clear(response, cfg, reset_cookie, reset_path)
        clear(response, cfg, cfg.session_cookie)
        return {"message": "Password saved. Sign in to continue."}

    @app.post("/api/auth/logout")
    def logout(request: Request, response: Response):
        cfg = configured()
        accounts.logout(request.cookies.get(cfg.session_cookie))
        clear(response, cfg, cfg.session_cookie)
        clear(response, cfg, reset_cookie, reset_path)
        return {"ok": True}

    def require_admin(request):
        configured()
        email = signed_in_email(config, request)
        if not email or accounts.role(email) != "admin":
            raise HTTPException(403, "App-admin access is required.")
        return email

    @app.get("/api/admin/accounts")
    def list_accounts(request: Request):
        require_admin(request)
        return accounts.list_accounts()

    @app.post("/api/admin/accounts")
    def manage_account(body: AccountAction, request: Request):
        require_admin(request)
        email = normalize_email(body.email)
        if body.action == "disable":
            if accounts.role(email) == "admin":
                raise HTTPException(
                    400, "Use the operator command to disable an app admin."
                )
            accounts.disable(email)
            return {"message": "Account disabled and sessions revoked."}
        token = (
            accounts.invite(email)
            if body.action == "invite"
            else accounts.recovery(email)
        )
        if not token:
            raise HTTPException(400, "No active account is eligible for recovery.")
        return {
            "link": invitation_link(
                config, token, "invite" if body.action == "invite" else "recovery"
            ),
            "message": "Share this single-use link privately after confirming the recipient's identity.",
        }
