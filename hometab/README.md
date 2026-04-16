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

Edit `src/defaults.json` for default shortcuts and todos.

## Tech Stack

- Cloudflare Workers + Hono
- TypeScript
