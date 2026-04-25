# HomeTab

A minimal custom new tab page with shortcuts and todos.

## Development

```bash
pnpm install
pnpm dev
```

## Deploy

```bash
pnpm run deploy
```

## Reset Data

Go to Cloudflare Dashboard → KV → Delete `user:default` key.

## Configuration

- Data is initialized from empty arrays in KV when first setup runs.
- Copy `defaults.example.json` to `defaults.json` and customize it.
- Use the KV management script to import/export data:

```bash
# Import defaults.json to local KV (for development)
node scripts/kv.mjs import --local

# Import defaults.json to remote KV (for production)
node scripts/kv.mjs import --remote

# Export KV data to timestamped file (prevents overwriting)
node scripts/kv.mjs export --local
# Output: defaults-2026-04-24T12-30-45.json

# Parse browser bookmarks HTML to defaults.json
node scripts/kv.mjs parse favourites.html
node scripts/kv.mjs parse favourites.html --folder "Bookmarks Bar"
```

## Tech Stack

- Cloudflare Workers + Hono
- TypeScript
