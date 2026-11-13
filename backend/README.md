# Backend setup

Install Python dependencies and the matching Playwright Chromium browser before starting the API:

```powershell
python -m pip install -r requirements.txt
python -m playwright install chromium
```

On Linux deployment images, install the browser and its system libraries during the image build:

```sh
python -m playwright install --with-deps chromium
```

## Render deployment

PDF export needs Chromium and its Linux dependencies. For Render, deploy this
backend with the included Dockerfile instead of the native Python runtime:

1. Open the web service's **Settings** page, then **Build & Deploy** → **Source** → **Edit**.
2. Select the same Git repository and branch, and choose the **Docker** runtime.
3. Keep the root directory set to `backend` and set the Dockerfile path to `Dockerfile`.
4. Deploy. The container applies Alembic migrations before starting the API and
   includes Chromium and system dependencies matching the pinned Playwright version.

PDF export uses the completed report's rendered HTML and CSS. Chromium waits for web fonts and images, then prints A4 pages with backgrounds and page numbers.

## Google sign-in and private run history

The backend validates Supabase access tokens with Supabase Auth and uses the
verified Supabase user UUID as the owner of each saved run. It does not need or
use a Supabase service-role key. The ownership migration enables row-level
security on the run, task, tool-call, and source tables; guest runs are temporary
and expire after 24 hours.

Configure these values in Render's backend environment:

```text
SUPABASE_URL=https://<project-ref>.supabase.co
SUPABASE_ANON_KEY=<Supabase publishable or anon key>
```

Configure the same public project URL and publishable/anon key as
`VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY` in Vercel. These are public
client configuration values, not service-role secrets.

In Supabase:

1. Enable Google under **Authentication → Sign In / Providers** and enter the
   OAuth client ID and secret from Google Cloud. Keep the OAuth client secret
   in Supabase; never put it in Vercel or frontend code.
2. Set the Auth **Site URL** to the deployed Vercel site.
3. Add the Vercel site URL and `http://localhost:5173` to the allowed redirect
   URLs. Set the Google OAuth redirect URI to the callback URL shown by
   Supabase.

The Docker start command runs `alembic upgrade head` before serving requests, so
the new owner columns and row-level-security policies are installed on deploy.
Signed-in users only see their own runs. Guest runs are accessible only with a
random session token held in that browser tab, are omitted from history, and are
deleted after expiry. Existing unowned runs are not visible to signed-in users.
