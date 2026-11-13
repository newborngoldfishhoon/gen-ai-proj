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
4. Deploy. The Docker image includes the Chromium browser and system dependencies
   matching the pinned Playwright version.

PDF export uses the completed report's rendered HTML and CSS. Chromium waits for web fonts and images, then prints A4 pages with backgrounds and page numbers.
