# HomeTab

A minimal Cloudflare Workers new tab page with shortcuts, todos, password auth, and a tabs sync API.

## Quick Start

```bash
pnpm install
pnpm dev
```

The dev server runs with Wrangler, usually at `http://127.0.0.1:8787`.

## Deploy

```bash
pnpm run deploy
```

## Data and Backups

HomeTab stores user data in Cloudflare KV:

- auth data: `auth:default`
- shortcuts: `shortcuts:default`
- todos: `todos:default`
- search engines: `searchEngines:default`
- tabs data: per-machine KV records

### Regular Production Backup

Run this periodically to export production KV data:

```bash
pnpm wrangler login
node scripts/kv.mjs export --remote
```

The export writes a timestamped file, for example:

```text
defaults-2026-04-24T12-30-45.json
```

Keep backup files private. They may contain `passwordHash`, shortcuts, todos, and other personal data.

### Local Backup

```bash
node scripts/kv.mjs export --local
```

### Restore / Import

Create or edit `defaults.json` first. You can start from the example file:

```bash
cp defaults.example.json defaults.json
```

Import into local KV:

```bash
node scripts/kv.mjs import defaults.json --local
```

Import into production KV:

```bash
node scripts/kv.mjs import defaults.json --remote
```

### Parse Browser Bookmarks

Convert a browser bookmarks HTML export into HomeTab defaults JSON:

```bash
node scripts/kv.mjs parse favourites.html
node scripts/kv.mjs parse favourites.html --folder "Bookmarks Bar"
```

## Reset Data

To reset the app password and user data, delete the relevant KV keys in the Cloudflare Dashboard.

For password reset only, delete:

```text
auth:default
```

## API

### Tabs API

All tabs endpoints require auth.

- `POST /api/tabs`
  - Body: `{ "machine_id": "home-pc", "content": "..." }`
  - Stores tabs content per machine in KV.
- `GET /tabs`
  - Returns an overview page of all machines.
- `GET /tabs?machine_id=<id>`
  - Returns a single-machine tabs page.

### Get a Bearer Token

```bash
bash scripts/get-token.sh
```

The script prompts for the HomeTab password and prints a bearer token for client applications.

By default it calls `http://127.0.0.1:8787`. Override with `BASE_URL`:

```bash
BASE_URL=https://your-domain.example bash scripts/get-token.sh
```

## Configuration Notes

- `wrangler.toml` contains the Worker name, KV binding, and route.
- `defaults.example.json` is safe to commit; real exported defaults/backups should stay private.

## Tech Stack

- Cloudflare Workers
- Hono
- TypeScript
- Wrangler
