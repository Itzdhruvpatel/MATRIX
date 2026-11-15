# Putting Matrix online

Three free services work together:

- **Supabase** keeps the database.
- **Render** runs the Python server.
- **Vercel** shows the website and passes every `/api` request to Render, so the browser sees one site.
- **GitHub Actions** loads new market data every evening.

Your own computer keeps working as before (SQLite) unless you set `DATABASE_URL`.

## 1. Supabase (database)

1. Create a project at supabase.com. Pick the Mumbai region if offered. Save the database password somewhere safe.
2. Open **Connect** and copy the **Session pooler** connection string. It looks like
   `postgresql://postgres.xxxx:PASSWORD@aws-0-ap-south-1.pooler.supabase.com:5432/postgres`.
3. Copy your current data into Supabase (takes a few minutes). In PowerShell, inside the Matrix folder:

   ```powershell
   $env:DATABASE_URL = "postgresql://...your string..."
   python -m matrix.migrate
   ```

   The variable only lasts for that PowerShell window, so your computer goes back to its own
   SQLite file afterwards. Never paste the string into a file that is committed.

## 2. Render (server)

1. Create an account at render.com and connect your GitHub account.
2. **New > Blueprint**, pick the MATRIX repository. Render reads `render.yaml`.
3. When asked, fill in:
   - `DATABASE_URL`: the Supabase string from step 1
   - `MATRIX_OWNER`: your own username (only this account sees stock ratings)
4. Wait for the deploy, then copy your Render address, for example `https://matrix-api-ab12.onrender.com`.

The free Render plan sleeps after 15 minutes without visitors. The first visit after that takes about a minute.

## 3. Vercel (website)

1. In `vercel.json`, replace `YOUR-RENDER-APP.onrender.com` with your Render address from step 2, commit and push.
2. Create an account at vercel.com, **Add New > Project**, import the MATRIX repository, and deploy with the default settings.
3. Open the Vercel address. You should see the Matrix login page.

## 4. GitHub Actions (daily data)

1. On GitHub, open the repository's **Settings > Secrets and variables > Actions**.
2. **New repository secret**: name `DATABASE_URL`, value the Supabase string.
3. Open the **Actions** tab, pick **Daily market data**, press **Run workflow** once to test it.

If the run fails while downloading from NSE, NSE may be blocking GitHub's servers. In that case run
`python -m matrix.pipeline --days 1` on your own computer each evening with `DATABASE_URL` set.

## Settings

| Variable | Meaning |
|---|---|
| `DATABASE_URL` | PostgreSQL connection string. Not set means local SQLite. |
| `MATRIX_OWNER` | The only username that sees Matrix Scores, ratings and the Prediction Ledger. Empty means everyone. |
| `MATRIX_SIGNUP` | `1` lets new people create accounts. |
| `MATRIX_SECRET` | Signs login cookies. Render creates one for you. |
| `MATRIX_SECURE_COOKIE` | `1` sends the login cookie over HTTPS only. |
| `MATRIX_TRUST_PROXY` | `1` when running behind Vercel or Render, so login limits apply per visitor. |
| `MATRIX_SCHEDULER` | `0` online (GitHub Actions loads the data instead). |
