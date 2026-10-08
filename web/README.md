# Talaab web

Vite + React + Leaflet + Recharts map for Talaab. Built by Ranit and wired to the live API.

## Run

```bash
npm install
npm run dev        # http://localhost:5173
npm run build      # production build in dist/ (Amplify runs this, see ../amplify.yml)
```

## Data

The app always talks to the Talaab API, by default the live AWS one
(`https://kbvkerr0kc.execute-api.us-west-2.amazonaws.com`). To point it elsewhere (e.g. a local
backend), create `.env.local` with `VITE_TALAAB_API_URL=...`. There is no countdown maths in the
browser: every status, range and flag comes from `backend/logic/`.

| Screen | API |
|---|---|
| Region switch (Latur today · LIVE / Latur 2024 · REPLAY) and the as-of slider | `GET /regions` (synthetic test data is hidden) |
| Map, pond list, pond detail, water-area chart | `GET /ponds?region=&asOf=` |
| Plan (English / मराठी) | `POST /plan`, polled every 5 s while `status` is `generating` |
| Accuracy | `GET /backtest?region=latur-2024` |

## Stack

- Vite + React
- Leaflet with OpenStreetMap tiles (optional Esri satellite)
- Recharts for the pond area history
- react-markdown + remark-gfm for the plan
