import { useEffect, useState, type FormEvent } from "react";
import { Modal } from "./components";
import { api, json } from "./api";

type Account = {
  email: string;
  activated: number;
  disabled: number;
  role: string;
};

export default function AccountDialog({ onClose }: { onClose: () => void }) {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [email, setEmail] = useState("");
  const [error, setError] = useState("");
  const [link, setLink] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    api<Account[]>("/admin/accounts")
      .then(setAccounts)
      .catch((e) => setError(e.message));
  }, []);

  async function change(
    action: "invite" | "reset" | "disable",
    address: string,
  ) {
    setBusy(true);
    setError("");
    setLink("");
    setNotice("");
    try {
      const result = await api<{ link?: string; message: string }>(
        "/admin/accounts",
        json("POST", { action, email: address }),
      );
      setLink(result.link || "");
      setNotice(result.message);
      setAccounts(await api<Account[]>("/admin/accounts"));
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "Could not update this account.",
      );
    } finally {
      setBusy(false);
    }
  }
  function invite(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void change("invite", email);
  }

  return (
    <Modal title="Manage accounts" onClose={onClose} wide>
      <p>
        Invite reviewers and share access links privately after confirming their
        identity. No emails are sent.
      </p>
      <form className="access-form" onSubmit={invite}>
        <label>
          Reviewer email
          <input
            type="email"
            autoComplete="off"
            maxLength={254}
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
        </label>
        <button className="primary" disabled={busy}>
          Create invitation link
        </button>
      </form>
      {error && (
        <p role="alert" className="access-error">
          {error}
        </p>
      )}
      {notice && (
        <p role="status" className="access-notice">
          {notice}
        </p>
      )}
      {link && (
        <label className="account-link">
          Private single-use access link
          <textarea
            readOnly
            rows={4}
            value={link}
            onFocus={(e) => e.target.select()}
          />
          <span>
            Copy this link now. It is hidden when you close this dialog.
          </span>
        </label>
      )}
      <div className="account-list">
        {accounts.map((account) => (
          <article key={account.email} className="account-row">
            <div>
              <strong>{account.email}</strong>
              <p>
                {account.role} ·{" "}
                {account.disabled
                  ? "Disabled"
                  : account.activated
                    ? "Active"
                    : "Invited"}
              </p>
            </div>
            <div className="account-actions">
              {!account.disabled && !account.activated && (
                <button
                  className="secondary"
                  disabled={busy}
                  onClick={() => change("invite", account.email)}
                >
                  Replace invitation
                </button>
              )}
              {!account.disabled && !!account.activated && (
                <button
                  className="secondary"
                  disabled={busy}
                  onClick={() => change("reset", account.email)}
                >
                  Create reset link
                </button>
              )}
              {!account.disabled && account.role !== "admin" && (
                <button
                  className="secondary"
                  disabled={busy}
                  onClick={() => change("disable", account.email)}
                >
                  Disable access
                </button>
              )}
            </div>
          </article>
        ))}
      </div>
    </Modal>
  );
}
