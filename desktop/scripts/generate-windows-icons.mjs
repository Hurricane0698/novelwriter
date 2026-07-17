import { copyFileSync, readdirSync, rmSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { spawnSync } from 'node:child_process'

const desktopRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const source = join(desktopRoot, 'assets', 'novwr-mark.svg')
const iconDirectory = join(desktopRoot, 'src-tauri', 'icons')
const uiIcon = join(desktopRoot, 'ui', 'novwr-mark.svg')
const tauri = join(
  desktopRoot,
  'node_modules',
  '.bin',
  process.platform === 'win32' ? 'tauri.cmd' : 'tauri',
)
const keep = new Set([
  '32x32.png',
  '128x128.png',
  '128x128@2x.png',
  'icon.ico',
  'icon.png',
])

const result = spawnSync(
  tauri,
  ['icon', source, '--output', iconDirectory],
  {
    cwd: desktopRoot,
    shell: process.platform === 'win32',
    stdio: 'inherit',
  },
)
if (result.error) {
  throw result.error
}
if (result.status !== 0) {
  process.exit(result.status ?? 1)
}

for (const entry of readdirSync(iconDirectory, { withFileTypes: true })) {
  if (!keep.has(entry.name)) {
    rmSync(join(iconDirectory, entry.name), { force: true, recursive: true })
  }
}

copyFileSync(source, uiIcon)
