import { useEffect, useState, type FormEvent } from "react";
import { Building2, ShieldCheck } from "lucide-react";
import App from "./App";
import { api, json } from "./api";
import "./access.css";

type Session = { enabled: boolean; email: string | null };
type Mode = "login" | "signup" | "forgot" | "confirm" | "reset";
type EmailLink = { kind: "email" | "recovery"; token_hash: string };

function readEmailLink(): EmailLink | null {
  const params = new URLSearchParams(window.location.hash.slice(1));
  const kind = params.get("type");
  const token_hash = params.get("token_hash");
  if (
    params.get("auth") === "confirm" &&
    (kind === "email" || kind === "recovery") &&
    token_hash
  ) {
    window.history.replaceState(null, "", window.location.pathname);
    return { kind, token_hash };
  }
  return null;
}
const emailLink = readEmailLink();

const copy = {
  login: ["Sign in", "Use your verified email to access the review workspace."],
  signup: [
    "Create an account",
    "Use the email your project team approved. We’ll send a verification link.",
  ],
  forgot: [
    "Forgot your password?",
    "Enter your email to request a password reset link.",
  ],
  confirm: [
    "Open your email link",
    "Continue to verify your email or start resetting your password.",
  ],
  reset: ["Choose a new password", "Use at least 12 characters."],
};

export default function Access() {
  const [session, setSession] = useState<Session>();
  const [mode, setMode] = useState<Mode>(emailLink ? "confirm" : "login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [repeat, setRepeat] = useState("");
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  function reloadSession() {
    setError("");
    api<Session>("/auth/session")
      .then(setSession)
      .catch(() => {
        setError(
          "Could not connect to the workspace. Check that the app is running.",
        );
      });
  }
  useEffect(() => {
    reloadSession();
    const expired = () => {
      setSession({ enabled: true, email: null });
      setMode("login");
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
      if (mode === "reset" && password !== repeat) {
        throw new Error("The passwords do not match.");
      }
      if (mode === "confirm") {
        const result = await api<{ kind: EmailLink["kind"] }>(
          "/auth/confirm",
          json("POST", emailLink),
        );
        changeMode(result.kind === "recovery" ? "reset" : "login");
        if (result.kind === "email")
          setNotice("Email verified. You can sign in.");
      } else if (mode === "login") {
        const result = await api<{ email: string }>(
          "/auth/login",
          json("POST", { email, password }),
        );
        setSession({ enabled: true, email: result.email });
        changeMode("login");
      } else {
        const body =
          mode === "forgot"
            ? { email }
            : mode === "reset"
              ? { password }
              : { email, password };
        const result = await api<{ message: string }>(
          `/auth/${mode}`,
          json("POST", body),
        );
        if (mode === "reset") {
          setSession({ enabled: true, email: null });
          changeMode("login");
        }
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
      setSession({ enabled: true, email: null });
    } catch {
      setError("Could not sign out. Try again.");
    } finally {
      setBusy(false);
    }
  }

  if (session && !session.enabled) return <App />;
  if (session?.email && mode !== "confirm" && mode !== "reset")
    return (
      <App account={{ email: session.email, onLogout: logout, busy, error }} />
    );

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
        <h1 id="access-title">
          {session ? copy[mode][0] : "Opening workspace"}
        </h1>
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
            <p className="access-summary">{copy[mode][1]}</p>
            <form onSubmit={submit} className="access-form">
              {mode !== "confirm" && mode !== "reset" && (
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
              {(mode === "login" || mode === "signup" || mode === "reset") && (
                <label>
                  {mode === "reset" ? "New password" : "Password"}
                  <input
                    name="password"
                    type="password"
                    autoComplete={
                      mode === "login" ? "current-password" : "new-password"
                    }
                    minLength={mode === "login" ? 1 : 12}
                    maxLength={mode === "login" ? 128 : 72}
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
                  : {
                      login: "Sign in",
                      signup: "Send verification email",
                      forgot: "Send reset email",
                      confirm: "Continue",
                      reset: "Save new password",
                    }[mode]}
              </button>
            </form>
            <div className="access-links">
              {mode === "login" ? (
                <>
                  <button disabled={busy} onClick={() => changeMode("signup")}>
                    Sign up
                  </button>
                  <button disabled={busy} onClick={() => changeMode("forgot")}>
                    Forgot password?
                  </button>
                </>
              ) : (
                <button disabled={busy} onClick={() => changeMode("login")}>
                  Back to sign in
                </button>
              )}
            </div>
          </>
        )}
      </section>
    </main>
  );
}
