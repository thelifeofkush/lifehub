# Bank of America automatic sync

LifeHub uses Plaid Transactions to import account activity. It never asks for
your bank password itself and does not request payment initiation. Your bank
authorization happens in Plaid Link and, for Bank of America, its OAuth flow.

## 1. Create your Plaid account

1. Sign up at [Plaid Dashboard](https://dashboard.plaid.com/signup).
2. Start with Sandbox and select the **Transactions** product. Sandbox contains
   fake data; it cannot import your Bank of America account.
3. For a real Bank of America connection, request **full Production access** and
   complete Plaid's OAuth registration, including the Bank of America requirements
   shown in your Dashboard. Limited Production excludes Bank of America.
   Approval, institution access, and commercial terms are controlled by Plaid;
   this repository cannot grant them. Review pricing before activating production.

References: [OAuth prerequisites](https://plaid.com/docs/link/oauth/),
[Limited Production restrictions](https://plaid.com/docs/quickstart/glossary/),
[billing](https://plaid.com/docs/account/billing/).

## 2. Configure LifeHub on your server

Copy `.env.example` to `.env` (PowerShell: `Copy-Item .env.example .env`).
Edit `.env` locally; do not paste credentials into chat or commit them to GitHub.

- Set `LIFEHUB_USERNAME` and a long, unique `LIFEHUB_PASSWORD`. Your browser
  will show its built-in sign-in prompt. Basic authentication must be used over
  HTTPS for any connection beyond localhost.
- Generate `LIFEHUB_ENCRYPTION_KEY` after installing requirements:

  ```powershell
  .venv/Scripts/python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
  ```

  Alternatively, with Docker available:

  ```sh
  docker compose build
  docker compose run --rm --no-deps lifehub python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
  ```

  Put that value in `.env` and keep a separate private backup. Access tokens are
  encrypted with it. Changing or losing the key breaks existing bank connections.
  Transaction descriptions and amounts remain ordinary SQLite records; secure
  your server disk and backups as you would other personal financial records.
- Set `PLAID_CLIENT_ID` and `PLAID_SECRET` using your Dashboard's **Sandbox**
  credentials, and leave `PLAID_ENV=sandbox` for testing.
- Set `LIFEHUB_PUBLIC_URL` to the exact origin you open in your browser, e.g.
  `http://localhost:8000` for Sandbox. Do not include a path or trailing slash.
- In Plaid Dashboard's API/redirect settings, allowlist the exact redirect URI:
  `http://localhost:8000/expenses/oauth` for local Sandbox testing.

Run `docker compose up -d --build`, open LifeHub, sign in, and open **Money →
Connect bank**. Use Plaid Sandbox test credentials as directed by Link (the
standard non-OAuth flow uses `user_good` / `pass_good`). Test an OAuth institution
in Sandbox as well to verify the return to `/expenses/oauth` on your host.
Do not use your real bank login in Sandbox.

For local Python development, load the same configuration with
`uvicorn core.main:app --reload --env-file .env`. Use a single server process;
sync coordination is process-local, and this is a single-owner application.

## 3. Enable your real account after approval

1. Put LifeHub behind an HTTPS reverse proxy on a domain you control, with the
   login configured. Keep Docker's default localhost port binding and run the
   proxy on that host. Preserve Authorization and forward the original host
   and scheme; only trust forwarded headers from your proxy.
2. Set `LIFEHUB_PUBLIC_URL=https://your-domain.example` and allowlist
   `https://your-domain.example/expenses/oauth` in Plaid Dashboard.
3. After Plaid approves full Production/OAuth access, change `PLAID_ENV` to
   `production` and use the **Production** secret. Keep the same encryption key.
4. Recreate the container with `docker compose up -d --build` and open LifeHub
   using that HTTPS address. Choose **Money → Connect bank → Bank of America**,
   authorize at the bank, and choose the accounts to share.

Sandbox connections and imported transactions are hidden in Production, and
vice versa. Disconnect Sandbox items before switching if you want to delete
their test records. Manual records appear in either mode.

## Sync behavior and totals

- The first request asks for up to 90 days of history. Actual availability
  depends on Plaid and the institution; history can arrive asynchronously.
- Background sync runs at startup and hourly while the container is running.
  `PLAID_SYNC_INTERVAL_SECONDS` can change this (minimum 300 seconds). **Sync now**
  imports the latest data already available at Plaid; it does not force the bank
  to refresh. Polling may incur usage charges under your Plaid plan.
- No public webhook receiver is needed. Sync uses `/transactions/sync` cursors,
  handles additions/modifications/removals, and commits complete paginated
  updates atomically. Repeated syncs do not duplicate the same transaction ID.
- Totals use posted USD transactions for the selected month. Income uses Plaid's
  income category, spending subtracts refunds, and transfers are excluded.
  Credit-card payments categorized by Plaid as credit-card payments are transfers.
  Review types: unknown deposits are initially treated as refunds, so change
  them to Income or Transfer as appropriate. You can override each bank row's
  type, and the override survives updates to that transaction ID.
- Pending and non-USD transactions are visible but excluded from totals.
  There is no currency conversion. The app does not automatically match manual
  entries to bank imports or detect every transfer between accounts.
- Failure preserves previous records and the last successful sync timestamp.
  Use **Reconnect** if your bank needs renewed authorization.
- **Disconnect** revokes the Plaid Item and deletes its local connection and
  imported transactions. Manual records are retained. If access to Plaid fails,
  records are retained so you can retry. You can also manage permissions at
  your bank and through Plaid's consumer portal.

Back up `data/lifehub.db` with the container stopped, and back up your encryption
key separately. No bank credentials or personal data belong in GitHub.
