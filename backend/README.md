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

PDF export uses the completed report's rendered HTML and CSS. Chromium waits for web fonts and images, then prints A4 pages with backgrounds and page numbers.
