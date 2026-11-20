# Railway deployment

The app service and PostgreSQL are separate services in the **same project and
environment**. The repo supplies a Dockerfile and Railway configuration. The
image builds React and installs Python runtime dependencies plus Tesseract;
notebooks, local credentials, and client documents are excluded from its build
context. The initial shared access code is 1234; override it with
`WARREN_ACCESS_CODE` before sharing client access. No private documents are embedded in the image.

## Dashboard setup

1. Connect the GitHub app service to the intended reviewed branch (`UI_dev`
   after the authentication changes are merged and pushed). Use the repository
   root as the service root. Remove stale build/start overrides that conflict
   with the Dockerfile. Connecting the repo alone does not create a database.
2. Add **PostgreSQL** through **+ New → Database → PostgreSQL** if it doesn't
   already exist. Keep its private networking and its own `postgres-volume`.
3. On the **app service**, open **Variables → Add Reference Variable** and
   reference PostgreSQL's `DATABASE_URL`. Do not put the connection URL in source
   code, frontend `VITE_*` settings, screenshots, or chat.
4. Create a **second volume**, attach it to the **app service**, and set its
   mount path to `/app/data`. The PostgreSQL volume is not the app volume.
   Creating an environment variable alone does not create or attach a volume.
5. Add `WARREN_DATA_DIR=/app/data` on the app service. Railway manages
   `RAILWAY_VOLUME_MOUNT_PATH` automatically; do not set it manually.
6. Generate a public domain for the app under **Settings → Networking**, and
   set `WARREN_PUBLIC_URL=https://YOUR-APP-DOMAIN` with no path. Set the public
   domain's target port to the service's `PORT` (default 8000 if none is set).
7. Remove all `WARREN_SUPABASE_*`, `WARREN_ALLOWED_EMAILS`, and
   `WARREN_ALLOW_UNAUTHENTICATED` settings. No email-provider settings are needed.
8. Deploy. Keep **one replica and one Python worker**. The launcher listens on
   `0.0.0.0` and Railway's `PORT`; the healthcheck uses `/api/health` and allows
   Railway's healthcheck hostname.

The three app variables you configure are:

| Variable | Value |
| --- | --- |
| `DATABASE_URL` | Reference to PostgreSQL's private `DATABASE_URL` |
| `WARREN_DATA_DIR` | `/app/data` |
| `WARREN_PUBLIC_URL` | The app's full HTTPS origin |

If permissions prevent adding a volume, changing variables, connecting the
repo/branch, or opening a deployment shell, ask the project manager to perform
those operations. An app admin cannot grant Railway project access.

Railway documents [PostgreSQL](https://docs.railway.com/databases/postgresql),
[volumes](https://docs.railway.com/volumes), and
[healthchecks](https://docs.railway.com/deployments/healthchecks).

## Access code and smoke check

The default login needs only the shared access code **1234**; no first-admin
command is required. To change it, set `WARREN_ACCESS_CODE` on the **app service**
to 4–128 letters/numbers and redeploy. Codes are case-sensitive. Use a longer
code for client access. Changing it revokes existing code sessions; sign-out
also revokes the current session. Access lasts one hour. Everyone with this
code shares reviewer access, including document deletion.

`WARREN_AUTH_MODE=code` is the default; remove an existing `accounts` override
or set it to `code` for the simplified screen. The database, volume and public
URL settings above remain required. Verify wrong codes are rejected and test
sign-in, a synthetic upload/save/check, sign-out and restart.

## Optional first admin for account mode

The instructions below apply only with `WARREN_AUTH_MODE=accounts`.

After the service starts successfully, an authorized project operator runs this
**inside the deployed app container**, using its existing variables:

```bash
python -m reviewer.manage_accounts invite YOUR-ADMIN-EMAIL --admin
```

The command creates a pending app admin and prints a one-time private link.
An authorized operator can access the container using `railway ssh` with the
correct project/environment/service selected. Running the command in an
unconfigured local VS Code terminal would create a different local account.
Do not use `railway run` with a private database hostname from outside Railway;
use the remote container instead. No real admin has been created by this code.

Accept the invitation, set a password, sign in, and use **Manage accounts** to
invite reviewers. Confirm that signed-out requests to `/api/records` return 401,
reviewers cannot manage accounts, and a disabled reviewer loses access. Test a
synthetic PDF upload, save, check, sign-out, and restart before using real data.

## Storage and existing data

PostgreSQL stores shared-code session hashes, accounts, account session-token
hashes, access-link hashes, review sessions, comparison details, immutable reference versions and check runs.
The app volume stores accepted CSVs, uploaded PDFs/images, copied source
documents, and extraction evidence. Both need appropriate backup arrangements.
The uploaded reference schedule can be imported through **Manage schedule**;
the container does not include private reference CSVs.

This creates a fresh hosted workspace. It does **not** automatically upload or
migrate your laptop's private data, existing SQLite review history, or accepted
CSV. Those remain untouched. Importing an existing workspace needs a separate
controlled transfer so its database entries and file evidence stay consistent.
Restarting or deploying reuses the database and mounted volume. Schema setup
creates missing tables and does not clear existing data. Use one instance until
the CSV storage and extraction queue support coordination across instances.
