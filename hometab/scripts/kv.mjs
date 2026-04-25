#!/usr/bin/env node
import { execFileSync } from "node:child_process"
import { readFileSync, writeFileSync, existsSync, mkdtempSync, rmSync } from "node:fs"
import { resolve, basename, join } from "node:path"
import { tmpdir } from "node:os"
import { createHash } from "node:crypto"

const KV_NAMESPACE_ID = "709a287f1fa145e787e279cbf2c9133b"
const DEFAULT_USER_ID = "default"

const KV_KEYS = {
  auth: (userId) => `auth:${userId}`,
  shortcuts: (userId) => `shortcuts:${userId}`,
  todos: (userId) => `todos:${userId}`,
  searchEngines: (userId) => `searchEngines:${userId}`,
}

let tempDir = null

function getTempDir() {
  if (!tempDir) {
    tempDir = mkdtempSync(join(tmpdir(), "hometab-kv-"))
  }
  return tempDir
}

function cleanup() {
  if (tempDir) {
    try {
      rmSync(tempDir, { recursive: true })
    } catch {}
  }
}

process.on("exit", cleanup)

function log(msg) {
  console.log(`[hometab-kv] ${msg}`)
}

function error(msg) {
  console.error(`[hometab-kv] ERROR: ${msg}`)
  process.exit(1)
}

function runWrangler(args, options = {}) {
  try {
    const result = execFileSync("pnpm", ["wrangler", ...args], {
      encoding: "utf-8",
      stdio: options.silent ? "pipe" : "inherit",
      shell: true,
      ...options,
    })
    return result
  } catch (e) {
    if (options.silent) throw e
    error(`wrangler command failed: ${e.message}`)
  }
}

function parseBookmarksHtml(htmlPath, targetFolder = "Speed Dial") {
  const content = readFileSync(htmlPath, "utf-8")
  
  const folderPattern = new RegExp(
    `<DT><H3[^>]*>${escapeRegex(targetFolder)}</H3>\\s*<DL><p>(.*?)</DL><p>`,
    "s"
  )
  const folderMatch = content.match(folderPattern)
  
  if (!folderMatch) {
    error(`Folder "${targetFolder}" not found in ${htmlPath}`)
  }
  
  const folderContent = folderMatch[1]
  const linkPattern = /<DT><A HREF="([^"]+)"[^>]*>([^<]+)<\/A>/g
  const shortcuts = []
  let match
  let id = Date.now()
  
  while ((match = linkPattern.exec(folderContent)) !== null) {
    shortcuts.push({
      id: String(id++),
      name: match[2],
      url: match[1],
    })
  }
  
  return shortcuts
}

function escapeRegex(str) {
  return str.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")
}

async function importDefaults(jsonPath, options) {
  const { local, remote } = options
  
  if (!existsSync(jsonPath)) {
    error(`File not found: ${jsonPath}`)
  }
  
  const data = JSON.parse(readFileSync(jsonPath, "utf-8"))
  
  log(`Loading defaults from ${jsonPath}`)
  log(`  shortcuts: ${data.shortcuts?.length || 0}`)
  log(`  todos: ${data.todos?.length || 0}`)
  log(`  searchEngines: ${data.searchEngines?.length || 0}`)
  
  const kvData = [
    { key: KV_KEYS.shortcuts(DEFAULT_USER_ID), value: JSON.stringify(data.shortcuts || []) },
    { key: KV_KEYS.todos(DEFAULT_USER_ID), value: JSON.stringify(data.todos || []) },
    { key: KV_KEYS.searchEngines(DEFAULT_USER_ID), value: JSON.stringify(data.searchEngines || []) },
  ]
  if (data.passwordHash) {
    kvData.push({
      key: KV_KEYS.auth(DEFAULT_USER_ID),
      value: JSON.stringify({ passwordHash: data.passwordHash }),
    })
  }
  
  const tempDir = getTempDir()
  
  for (const { key, value } of kvData) {
    const tempFile = join(tempDir, `${key.replace(/:/g, "_")}.json`)
    writeFileSync(tempFile, value)
    
    const args = ["kv", "key", "put", "--namespace-id", KV_NAMESPACE_ID, key, "--path", tempFile]
    if (local) args.push("--local")
    
    log(`Writing ${key}...`)
    runWrangler(args)
  }
  
  log(`${local ? "Local" : "Remote"} KV updated!`)
}

async function exportDefaults(outputPath, options) {
  const { local, remote } = options
  
  if (local && remote) {
    error("Cannot export from both local and remote at the same time")
  }
  
  const source = local ? "local" : "remote"
  log(`Exporting from ${source} KV...`)
  
  const args = ["kv", "key", "get", "--namespace-id", KV_NAMESPACE_ID]
  if (local) args.push("--local")
  if (remote) args.push("--remote")
  
  const getData = (key) => {
    try {
      const result = execFileSync("pnpm", ["wrangler", ...args, key], {
        encoding: "utf-8",
        stdio: "pipe",
        shell: true,
      })
      return JSON.parse(result)
    } catch (e) {
      if (remote && e.message?.includes("CLOUDFLARE_API_TOKEN")) {
        error("Not authenticated for remote KV. Run `wrangler login` first or set CLOUDFLARE_API_TOKEN environment variable.")
      }
      return null
    }
  }
  
  const data = {
    passwordHash: "",
    shortcuts: getData(KV_KEYS.shortcuts(DEFAULT_USER_ID)) || [],
    todos: getData(KV_KEYS.todos(DEFAULT_USER_ID)) || [],
    searchEngines: getData(KV_KEYS.searchEngines(DEFAULT_USER_ID)) || [],
  }
  
  const authData = getData(KV_KEYS.auth(DEFAULT_USER_ID))
  if (authData?.passwordHash) {
    data.passwordHash = authData.passwordHash
  }
  
  writeFileSync(outputPath, JSON.stringify(data, null, 2))
  log(`Exported to ${outputPath}`)
}

async function parseBookmarks(htmlPath, outputPath, targetFolder) {
  log(`Parsing bookmarks from ${htmlPath}`)
  log(`Target folder: ${targetFolder}`)
  
  const shortcuts = parseBookmarksHtml(htmlPath, targetFolder)
  
  log(`Found ${shortcuts.length} shortcuts`)
  
  const data = {
    passwordHash: "",
    todos: [],
    searchEngines: [],
    shortcuts,
  }
  
  if (outputPath) {
    writeFileSync(outputPath, JSON.stringify(data, null, 2))
    log(`Written to ${outputPath}`)
  } else {
    console.log(JSON.stringify(data, null, 2))
  }
}

function printHelp() {
  console.log(`
hometab-kv - Manage hometab KV data

Usage:
  node scripts/kv.mjs <command> [options]

Commands:
  import [json]           Import JSON to KV (default: defaults.json)
  export [json]           Export KV data to JSON (default: defaults-<timestamp>.json)
  parse <html> [json]     Parse browser bookmarks HTML to JSON (default: defaults.json)

Options:
  --local                 Use local KV (wrangler dev)
  --remote                Use remote KV (production)
  --folder <name>         Target folder name for bookmark parsing (default: "Speed Dial")

Examples:
  node scripts/kv.mjs import --local
  node scripts/kv.mjs import --remote
  node scripts/kv.mjs import my-data.json --local
  node scripts/kv.mjs export --local
  node scripts/kv.mjs export --remote
  node scripts/kv.mjs parse favourites.html
  node scripts/kv.mjs parse favourites.html --folder "Bookmarks Bar"
`)
}

async function main() {
  const args = process.argv.slice(2)
  
  if (args.length === 0 || args[0] === "--help" || args[0] === "-h") {
    printHelp()
    process.exit(0)
  }
  
  const command = args[0]
  const options = { local: false, remote: false }
  let targetFolder = "Speed Dial"
  
  const positionalArgs = []
  for (let i = 1; i < args.length; i++) {
    if (args[i] === "--local") options.local = true
    else if (args[i] === "--remote") options.remote = true
    else if (args[i] === "--folder") targetFolder = args[++i]
    else if (!args[i].startsWith("--")) positionalArgs.push(args[i])
  }
  
  switch (command) {
    case "import": {
      const jsonPath = positionalArgs[0] || "defaults.json"
      if (!options.local && !options.remote) {
        error("Must specify --local or --remote")
      }
      await importDefaults(resolve(jsonPath), options)
      break
    }
    
    case "export": {
      let outputPath = positionalArgs[0]
      if (!outputPath) {
        const timestamp = new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19)
        outputPath = `defaults-${timestamp}.json`
      }
      if (!options.local && !options.remote) {
        options.local = true
      }
      await exportDefaults(resolve(outputPath), options)
      break
    }
    
    case "parse": {
      const htmlPath = positionalArgs[0]
      if (!htmlPath) {
        error("Usage: parse <html> [json] [--folder <name>]")
      }
      const outputPath = positionalArgs[1] || "defaults.json"
      await parseBookmarks(resolve(htmlPath), resolve(outputPath), targetFolder)
      break
    }
    
    default:
      error(`Unknown command: ${command}`)
  }
}

main().catch((e) => error(e.message))
