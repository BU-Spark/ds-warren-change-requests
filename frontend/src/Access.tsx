import { useEffect, useState, type FormEvent } from "react";
import { Building2, ShieldCheck } from "lucide-react";
import App from "./App";
import AccountDialog from "./AccountDialog";
import { api, json } from "./api";
import "./access.css";

type Session = {
  enabled: boolean;
  email: string | null;
  role?: string | null;
  mode?: "code" | "accounts";
};
type Mode = "login" | "confirm" | "reset";
type AccessLink = { kind: "invite" | "recovery"; token: string };

function readLink(): AccessLink | null {
  const params = new URLSearchParams(window.location.hash.slice(1));
  const kind = params.get("type");
  const token = params.get("token");
  if (
    params.get("auth") === "confirm" &&
    (kind === "invite" || kind === "recovery") &&
    token
  ) {
    window.history.replaceState(null, "", window.location.pathname);
    return { kind, token };
  }
  return null;
}
const accessLink = readLink();

export default function Access() {
  const [session, setSession] = useState<Session>();
  const [mode, setMode] = useState<Mode>(accessLink ? "confirm" : "login");
  const [email, setEmail] = useState("");
  const codeMode = session?.mode === "code";
  const [password, setPassword] = useState("");
  const [repeat, setRepeat] = useState("");
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [manageAccounts, setManageAccounts] = useState(false);

  function reloadSession() {
    setError("");
    api<Session>("/auth/session")
      .then((next) => {
        setSession(next);
        if (next.mode === "code") setMode("login");
      })
      .catch(() =>
        setError(
          "Could not connect to the workspace. Check that the app is running.",
        ),
      );
  }
  useEffect(() => {
    reloadSession();
    const expired = () => {
      setSession((previous) => ({ ...previous, enabled: true, email: null }));
      setMode("login");
      setManageAccounts(false);
      setError("Your session ended. Sign in again to continue.");
    };
    window.addEventListener("warren-session-ended", expired);
    return () => window.removeEventListener("warren-session-ended", expired);
  }, []);

  function changeMode(value: Mode) {
    setMode(value);
    setPassword("");
    setRepeat("");
    setError("");
    setNotice("");
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setNotice("");
    setError("");
    try {
      if (mode === "reset" && password !== repeat)
        throw new Error("The passwords do not match.");
      if (mode === "confirm") {
        await api("/auth/confirm", json("POST", accessLink));
        changeMode("reset");
      } else if (mode === "login") {
        const result = await api<{ email: string; role: string }>(
          "/auth/login",
          json("POST", codeMode ? { code: password } : { email, password }),
        );
        setSession({ enabled: true, mode: session?.mode, ...result });
        changeMode("login");
      } else {
        const result = await api<{ message: string }>(
          "/auth/reset",
          json("POST", { password }),
        );
        setSession((previous) => ({ ...previous, enabled: true, email: null }));
        changeMode("login");
        setNotice(result.message);
      }
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Something went wrong. Try again.",
      );
    } finally {
      setPassword("");
      setRepeat("");
      setBusy(false);
    }
  }

  async function logout() {
    setBusy(true);
    setError("");
    try {
      await api("/auth/logout", json("POST", {}));
      changeMode("login");
      setManageAccounts(false);
      setSession((previous) => ({ ...previous, enabled: true, email: null }));
    } catch {
      setError("Could not sign out. Try again.");
    } finally {
      setBusy(false);
    }
  }

  if (session && !session.enabled) return <App />;
  if (session?.email && mode === "login")
    return (
      <>
        <App
          account={{
            email: session.email,
            onLogout: logout,
            busy,
            error,
            onManageAccounts:
              session.role === "admin"
                ? () => setManageAccounts(true)
                : undefined,
          }}
        />
        {manageAccounts && (
          <AccountDialog onClose={() => setManageAccounts(false)} />
        )}
      </>
    );

  const title =
    mode === "login"
      ? "Sign in"
      : mode === "confirm"
        ? "Open your access link"
        : "Set your password";
  const summary =
    mode === "login"
      ? codeMode
        ? "Enter your project access code to open the review workspace."
        : "Use your invited account to access the review workspace."
      : mode === "confirm"
        ? "Continue to accept your invitation or reset your password."
        : "Choose a password of at least 12 characters.";
  return (
    <main className="access-page">
      <div className="access-identity">
        <span className="brand-symbol">
          <Building2 size={25} aria-hidden="true" />
        </span>
        <span>
          WARREN<span className="brand-sub">PROJECT REVIEW</span>
        </span>
      </div>
      <section className="access-card" aria-labelledby="access-title">
        <span className="access-label">
          <ShieldCheck size={17} aria-hidden="true" /> WARREN TOWERS WORKSPACE
        </span>
        <h1 id="access-title">{session ? title : "Opening workspace"}</h1>
        {!session ? (
          error ? (
            <>
              <p role="alert" className="access-error">
                {error}
              </p>
              <button className="primary" onClick={reloadSession}>
                Try again
              </button>
            </>
          ) : (
            <p role="status">Checking access…</p>
          )
        ) : (
          <>
            <p className="access-summary">{summary}</p>
            <form onSubmit={submit} className="access-form">
              {mode === "login" && !codeMode && (
                <label>
                  Email
                  <input
                    name="email"
                    type="email"
                    autoComplete="username"
                    maxLength={254}
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    required
                  />
                </label>
              )}
              {mode !== "confirm" && (
                <label>
                  {codeMode
                    ? "Access code"
                    : mode === "reset"
                      ? "New password"
                      : "Password"}
                  <input
                    name={codeMode ? "code" : "password"}
                    type="password"
                    autoComplete={
                      mode === "login" ? "current-password" : "new-password"
                    }
                    autoCapitalize="none"
                    spellCheck={false}
                    minLength={mode === "login" ? 1 : 12}
                    maxLength={128}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    required
                  />
                </label>
              )}
              {mode === "reset" && (
                <label>
                  Confirm new password
                  <input
                    type="password"
                    autoComplete="new-password"
                    maxLength={128}
                    value={repeat}
                    onChange={(e) => setRepeat(e.target.value)}
                    required
                  />
                </label>
              )}
              {error && (
                <p className="access-error" role="alert">
                  {error}
                </p>
              )}
              {notice && (
                <p className="access-notice" role="status">
                  {notice}
                </p>
              )}
              <button className="primary" disabled={busy} type="submit">
                {busy
                  ? "Please wait…"
                  : mode === "login"
                    ? "Sign in"
                    : mode === "confirm"
                      ? "Continue"
                      : "Save password"}
              </button>
            </form>
            <p className="access-summary">
              {codeMode
                ? "Contact your project team if you need the access code."
                : "Need an invitation or password reset? Contact your project team for a private access link."}
            </p>
            {mode !== "login" && (
              <div className="access-links">
                <button disabled={busy} onClick={() => changeMode("login")}>
                  Back to sign in
                </button>
              </div>
            )}
          </>
        )}
      </section>
    </main>
  );
}
