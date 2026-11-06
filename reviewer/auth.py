"""Email authentication for the shared review workspace."""

import json
import os
import re
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, build_opener
from urllib.request import Request as UpstreamRequest

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

PUBLIC_ROUTES = {
    "/api/health",
    "/api/auth/session",
    "/api/auth/login",
    "/api/auth/signup",
    "/api/auth/forgot",
    "/api/auth/confirm",
    "/api/auth/reset",
    "/api/auth/logout",
}
EMAIL = re.compile(r"[^\s@,]+@[^\s@,]+\.[^\s@,]+")


@dataclass(frozen=True)
class AuthConfig:
    provider: str
    key: str
    origin: str
    emails: frozenset[str]

    @property
    def secure(self):
        return self.origin.startswith("https://")

    @property
    def session_cookie(self):
        return "__Host-warren-session" if self.secure else "warren-session"

    @classmethod
    def from_env(cls):
        names = (
            "WARREN_SUPABASE_URL",
            "WARREN_SUPABASE_PUBLISHABLE_KEY",
            "WARREN_PUBLIC_URL",
            "WARREN_ALLOWED_EMAILS",
        )
        provider, key, origin, allowed = values = [
            os.getenv(n, "").strip() for n in names
        ]
        hosted = bool(
            os.getenv("RAILWAY_ENVIRONMENT_ID") or os.getenv("RAILWAY_PUBLIC_DOMAIN")
        )
        if not any(values) and not hosted:
            return None
        if not all(values):
            raise RuntimeError(
                "Set all Warren authentication variables before starting."
            )
        provider = provider.rstrip("/")
        origin = origin.rstrip("/")
        app_url = urlsplit(origin)
        if not re.fullmatch(r"https://[a-z0-9-]+\.supabase\.co", provider):
            raise RuntimeError("Use the HTTPS URL of your Supabase project.")
        if not key.startswith("sb_publishable_"):
            raise RuntimeError("Use a Supabase publishable key.")
        if (
            not app_url.hostname
            or app_url.username
            or app_url.password
            or app_url.path
            or app_url.query
            or app_url.fragment
        ):
            raise RuntimeError(
                "WARREN_PUBLIC_URL must be the app origin, without a path."
            )
        if app_url.scheme != "https" and not (
            app_url.scheme == "http"
            and not hosted
            and app_url.hostname in {"localhost", "127.0.0.1"}
        ):
            raise RuntimeError("Use HTTPS for the hosted app.")
        emails = frozenset(
            e.strip().casefold() for e in allowed.split(",") if e.strip()
        )
        if not emails or not all(EMAIL.fullmatch(e) for e in emails):
            raise RuntimeError(
                "Set WARREN_ALLOWED_EMAILS to comma-separated email addresses."
            )
        return cls(provider, key, origin, emails)

    def email_for(self, user):
        email = (user.get("email") or "").casefold()
        return (
            email if user.get("email_confirmed_at") and email in self.emails else None
        )


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def provider_request(config, path, *, method="GET", body=None, token=None):
    headers = {"apikey": config.key, "Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = UpstreamRequest(
        f"{config.provider}/auth/v1{path}",
        data=json.dumps(body).encode() if body is not None else None,
        headers=headers,
        method=method,
    )
    try:
        with build_opener(NoRedirect()).open(req, timeout=8) as reply:
            contents = reply.read()
            return json.loads(contents) if contents else {}
    except HTTPError as exc:
        if exc.code == 429:
            raise HTTPException(
                429, "Too many attempts. Wait before trying again."
            ) from None
        if exc.code in {400, 401, 403, 404, 422}:
            return None
        raise HTTPException(
            503, "Sign-in service unavailable. Try again shortly."
        ) from None
    except (URLError, OSError, ValueError):
        raise HTTPException(
            503, "Sign-in service unavailable. Try again shortly."
        ) from None


def signed_in_email(config, request):
    token = request.cookies.get(config.session_cookie)
    if not token or not re.fullmatch(r"[\w.-]{1,4096}", token, flags=re.ASCII):
        return None
    user = provider_request(config, "/user", token=token)
    return config.email_for(user or {})


class EmailBody(BaseModel):
    email: str = Field(max_length=254)


class Credentials(EmailBody):
    password: str = Field(min_length=1, max_length=128)


class NewPassword(BaseModel):
    password: str = Field(min_length=12, max_length=72)


class Confirmation(BaseModel):
    kind: str = Field(pattern="^(email|recovery)$")
    token_hash: str = Field(min_length=16, max_length=256, pattern=r"^[a-zA-Z0-9_-]+$")


def register_auth(app: FastAPI, config: AuthConfig | None):
    reset_cookie = "warren-recovery"
    reset_path = "/api/auth/reset"

    def configured():
        if config is None:
            raise HTTPException(404, "Account sign-in is unavailable.")
        return config

    def validate_password(password):
        if not 12 <= len(password) or len(password.encode()) > 72:
            raise HTTPException(
                400, "Choose a password of at least 12 characters and at most 72 bytes."
            )

    def set_token(response, cfg, name, path, result, limit):
        response.set_cookie(
            name,
            result["access_token"],
            max_age=min(int(result["expires_in"]), limit),
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
        return {
            "enabled": config is not None,
            "email": signed_in_email(config, request) if config else None,
        }

    @app.post("/api/auth/login")
    def login(body: Credentials, response: Response):
        cfg = configured()
        email = body.email.strip().casefold()
        result = None
        if email in cfg.emails:
            result = provider_request(
                cfg,
                "/token?grant_type=password",
                method="POST",
                body={"email": email, "password": body.password},
            )
        if (
            not result
            or not result.get("access_token")
            or not cfg.email_for(result.get("user") or {})
        ):
            raise HTTPException(
                401, "Unable to sign in. Check your details and verify your email."
            )
        set_token(response, cfg, cfg.session_cookie, "/", result, 3600)
        return {"email": email}

    @app.post("/api/auth/signup")
    def signup(body: Credentials):
        cfg = configured()
        email = body.email.strip().casefold()
        validate_password(body.password)
        if email in cfg.emails:
            provider_request(
                cfg,
                "/signup",
                method="POST",
                body={"email": email, "password": body.password},
            )
        return {
            "message": "If this address is eligible, check your inbox for a verification email."
        }

    @app.post("/api/auth/forgot")
    def forgot(body: EmailBody):
        cfg = configured()
        email = body.email.strip().casefold()
        if email in cfg.emails:
            provider_request(cfg, "/recover", method="POST", body={"email": email})
        return {
            "message": "If an eligible account exists, you'll receive a password reset email."
        }

    @app.post("/api/auth/confirm")
    def confirm(body: Confirmation, response: Response):
        cfg = configured()
        result = provider_request(
            cfg,
            "/verify",
            method="POST",
            body={"token_hash": body.token_hash, "type": body.kind},
        )
        if not result or not cfg.email_for(result.get("user") or {}):
            raise HTTPException(
                400, "This link is invalid or expired. Request a new email."
            )
        if body.kind == "recovery":
            if not result.get("access_token"):
                raise HTTPException(400, "Request a new password reset email.")
            set_token(response, cfg, reset_cookie, reset_path, result, 600)
        return {"kind": body.kind}

    @app.post(reset_path)
    def reset(body: NewPassword, request: Request, response: Response):
        cfg = configured()
        validate_password(body.password)
        token = request.cookies.get(reset_cookie)
        user = provider_request(cfg, "/user", token=token) if token else None
        if not user or not cfg.email_for(user):
            raise HTTPException(
                400, "Your reset link has expired. Request a new email."
            )
        if not provider_request(
            cfg, "/user", method="PUT", body={"password": body.password}, token=token
        ):
            raise HTTPException(
                400,
                "Could not set this password. Try a different password or request a new link.",
            )
        clear(response, cfg, reset_cookie, reset_path)
        clear(response, cfg, cfg.session_cookie)
        return {"message": "Password updated. Sign in with your new password."}

    @app.post("/api/auth/logout")
    def logout(response: Response):
        cfg = configured()
        clear(response, cfg, cfg.session_cookie)
        clear(response, cfg, reset_cookie, reset_path)
        return {"ok": True}
