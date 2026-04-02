# Amsterdam Strain Finder

## Agent Teams
Enable agent teams via settings.json before starting.
Spawn one agent per module. Build order:
1. DB (no dependencies)
2. Scraper + OCR (parallel, depend on DB)
3. API (depends on Scraper + OCR)
4. Frontend (depends on API)

## Source
Target site: https://www.coffeeshopmenus.org
Index page: https://www.coffeeshopmenus.org/ams_index.html
Shop pages: https://www.coffeeshopmenus.org/cs-{slug}.html
Latest image: first <img> after <hr> on each shop page

## Run Commands
python -m scraper.scrape                        # test scraper, prints jobs
python -m ocr.extract --image /tmp/test.jpg     # test OCR on one image
uvicorn api.main:app --reload --port 8000        # run API
python scheduler/runner.py                       # start scheduler
cd frontend && npm run dev                       # frontend on port 3000

## Environment Variables
ANTHROPIC_API_KEY=
DATABASE_URL=sqlite:///./dev.db
ADMIN_API_KEY=
NEXT_PUBLIC_API_URL=http://localhost:8000

## Rules
- Never delete rows from coffeeshops table
- Always store raw Claude JSON in menu_snapshots.raw_json
- Crawl delay: 1.5s between shop page requests
- OCR model: claude-sonnet-4-20250514
- BeautifulSoup parser: html.parser (not lxml — old site HTML is non-standard)
- Frontend design: match strain-finder-ui.jsx exactly, wire to real API
