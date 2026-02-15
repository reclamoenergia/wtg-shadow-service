# Wind Shadow Studio

Piattaforma multi-servizi con servizio principale **Wind Shadow Studio** per simulazione annuale ombre turbine, preview mappa, pricing commerciale, pagamento post-calcolo e download protetti.

## Stack

- **Frontend**: Next.js + TypeScript + TailwindCSS (cartella `web/`)
- **Backend**: FastAPI + SQLAlchemy + Alembic (`api/`)
- **DB**: PostgreSQL (docker-compose) o SQLite fallback locale
- **Raster**: ASC + GeoTIFF (rasterio)
- **Coordinate**: pyproj
- **PDF**: ReportLab
- **Pagamento**: Stripe Checkout + webhook (con mock fallback)

## Avvio rapido

### 1) Backend

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn api.main:app --reload --port 8000
```

### 2) Frontend

```bash
cd web
npm install
npm run dev
```

### 3) PostgreSQL opzionale

```bash
docker compose up -d postgres
```

Impostare `DATABASE_URL=postgresql+psycopg2://windshadow:windshadow@localhost:5432/windshadow` per usare Postgres.

## API principali

- `POST /api/jobs` crea job asincrono
- `GET /api/jobs/{job_id}` stato/progresso/summary/quote/preview
- `POST /api/jobs/{job_id}/checkout` crea checkout Stripe o mock
- `POST /api/stripe/webhook` fulfillment post-pagamento
- `GET /download/{job_id}/{kind}` download protetti (asc, geotiff, report_pdf, calendar_csv/json)

## I18N

- Default italiano
- Override con campo payload `lang`
- Fallback EN se chiave mancante
- Dizionari: `web/i18n/it.json`, `web/i18n/en.json`

## Assunzioni implementative

1. **Area > 20x20 km**: invece di chiedere conferma (flow interattivo non disponibile lato API single-shot), il backend riduce automaticamente a 20x20km centrata sul bbox richiesto e imposta `price_quote.area_reduced=true`.
2. **Email opzionale**: il campo è salvato in DB ma l'invio reale è lasciato a integrazione SMTP provider-specifica (non incluso).
3. **Calendar add-on**: è generato come output commerciale semplificato con intervalli rappresentativi per punto; struttura pronta per integrazione con motore analitico dedicato.
4. **Stripe**: se variabili Stripe mancanti, checkout mock (`/mock-checkout/{job_id}`) per flusso locale.
5. **Progress reale**: progressione aggiornata in DB per step principali (queued/prepare/compute/outputs/done).
6. **PDF mappa**: il report include preview heatmap PNG e metadati commerciali richiesti.
7. **Cleanup**: scadenza job 24h (`JOB_EXPIRY_HOURS`), cancellazione fisica file demandata a cron esterno opzionale.
8. **Motore ombre**: usa motore esistente nel repository con timestep 15 minuti e scenario worst-case.

## CI/CD minima suggerita

- Job CI: lint + test backend + build frontend
- Deploy: container backend/frontend separati con DB managed

