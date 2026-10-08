# Talaab web

Vite + React + Leaflet + Recharts UI for Talaab's pond-risk replay.

## Run

```bash
npm install
npm run dev
```

Open the Vite URL shown in the terminal.

## Data modes

By default the app reads `public/mock/ponds.json` and performs a local backtest when the As-of slider moves through the available Sentinel-2 scenes.

To use the AWS API instead, create `.env.local` with:

```env
VITE_TALAAB_API_URL=https://kbvkerr0kc.execute-api.us-west-2.amazonaws.com
```

Then the app calls `GET /ponds?region=latur-2024&asOf=YYYY-MM-DD` and `POST /plan` as the backend comes online.

## Web stack

- Vite + React
- Leaflet with OpenStreetMap attribution and optional Esri satellite tiles
- Recharts for pond area history
- ReactMarkdown for the plan response
