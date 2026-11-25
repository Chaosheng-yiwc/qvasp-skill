/**
 * qvasp-skill — DeepSeek Harness bundle providing:
 *   1. the `qvasp` skill (synced to the user's skill library at startup,
 *      x-version gated so user edits survive plugin upgrades);
 *   2. the `qvasp` MCP server (stdio, 17 tools: qvasp_run, workflow_*,
 *      structure_check, result_*, reference_lookup, literature_record,
 *      report_build, diagnose_log, aux_*), mounted dynamically with
 *      package-resolved paths.
 *
 * Pure plugin: only public seams (`tools` via the nested MCP entry), zero
 * DSH core changes, zero runtime dependencies.
 *
 * Why dynamic mounting instead of a static cordis.patch.yml insert:
 * `command`/`args` of an MCP stdio entry must be machine-specific absolute
 * paths (the python interpreter + the bundled qvasp_mcp.py). Patch configs
 * are literal strings — the host never rewrites them relative to the
 * package directory — so a static patch would break on every machine except
 * the author's. Mounting from `apply()` lets us compute both paths from
 * `import.meta.url` at runtime, on any machine, with any python found on
 * PATH (env: QVASP_PYTHON overrides; falls back python3 → python).
 * @module qvasp-skill
 */

import { cpSync, existsSync, mkdirSync, readFileSync, readdirSync, rmSync, statSync, writeFileSync } from 'node:fs'
import { createHash } from 'node:crypto'
import { spawnSync } from 'node:child_process'
import { homedir, platform } from 'node:os'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'

/** Package root (the directory containing package.json / server / skills). */
const PKG = fileURLToPath(new URL('.', import.meta.url))

/** Bundled skill directories (names must stay in sync with skills/). */
const BUILTIN_SKILLS = ['qvasp']

/** Default user skill library (~/.agents/skills), same as dsh-memory-evolve. */
const DEFAULT_SKILL_DIR = join(homedir(), '.agents', 'skills')

const MCP_ENTRY_ID = 'qvasp-mcp'

/**
 * Places a python is commonly installed to but not necessarily on the PATH the
 * host process inherited. Checked after `python`/`python3` on PATH.
 */
const COMMON_PYTHON_DIRS = [
  join(homedir(), 'anaconda3'),
  join(homedir(), 'miniconda3'),
  join(homedir(), 'miniforge3'),
  join(homedir(), 'AppData', 'Local', 'Programs', 'Python'),
  'C:\\ProgramData\\anaconda3',
  'C:\\ProgramData\\miniconda3',
  '/opt/homebrew/bin',
  '/usr/local/bin',
  '/usr/bin',
]

/** Read `x-version` from a SKILL.md frontmatter; CRLF tolerant; default 0. */
function skillVersion(text) {
  const m = String(text).match(/^---\r?\n[\s\S]*?^x-version:[ \t]*(\d+)[ \t]*\r?$/m)
  return m ? Number(m[1]) : 0
}

/** Content hash marker, kept beside the skill dir so the skill stays pristine. */
const hashMarker = (userSkillsDir, name) => join(userSkillsDir, `.${name}.skill-hash`)

function treeHash(dir) {
  // Hash file names + contents so a changed reference file also counts.
  const h = createHash('md5')
  const walk = (d) => {
    for (const name of readdirSync(d).sort()) {
      const p = join(d, name)
      const st = statSync(p)
      if (st.isDirectory()) walk(p)
      else h.update(name).update(readFileSync(p))
    }
  }
  walk(dir)
  return h.digest('hex')
}

/**
 * Sync bundled skills into the user skill library.
 * Target missing -> copy. Target x-version lower -> overwrite whole dir.
 * Target unchanged since we installed it (hash marker matches) but the package
 * shipped different bytes -> overwrite, so a forgotten version bump cannot
 * leave stale docs installed. Target edited by the user -> untouched.
 * @param {string} pluginSkillsDir - package-internal skills/ directory
 * @param {string} userSkillsDir - user skill library directory
 * @returns {Array<{name:string, action:'synced'|'unchanged'|'missing'}>}
 */
export function syncBuiltinSkills(pluginSkillsDir, userSkillsDir) {
  const results = []
  for (const name of BUILTIN_SKILLS) {
    const srcDir = join(pluginSkillsDir, name)
    const srcFile = join(srcDir, 'SKILL.md')
    if (!existsSync(srcFile)) {
      results.push({ name, action: 'missing' })
      continue
    }
    const destDir = join(userSkillsDir, name)
    const destFile = join(destDir, 'SKILL.md')
    const srcText = readFileSync(srcFile, 'utf8')
    let action = 'unchanged'
    let needsCopy = !existsSync(destFile)
      || skillVersion(srcText) > skillVersion(readFileSync(destFile, 'utf8'))
    if (!needsCopy && treeHash(srcDir) !== treeHash(destDir)) {
      // Content differs while the version did not go up. Only refresh if the
      // installed copy is exactly what we put there last time.
      const marker = hashMarker(userSkillsDir, name)
      const recorded = existsSync(marker) ? readFileSync(marker, 'utf8').trim() : null
      if (recorded && recorded === treeHash(destDir)) needsCopy = true
    }
    if (needsCopy) {
      rmSync(destDir, { recursive: true, force: true })
      mkdirSync(destDir, { recursive: true })
      cpSync(srcDir, destDir, { recursive: true })
      writeFileSync(hashMarker(userSkillsDir, name), treeHash(destDir) + '\n')
      action = 'synced'
    } else if (!existsSync(hashMarker(userSkillsDir, name))) {
      // Content already matches: record the hash so a later package change can
      // be detected even if the version is not bumped.
      writeFileSync(hashMarker(userSkillsDir, name), treeHash(destDir) + '\n')
    }
    results.push({ name, action })
  }
  return results
}

/**
 * Resolve the full MCP client entry config for this machine.
 * Exported for tests.
 * @param {object} [config] plugin config (qvaspBin / workroot / scheduler / python)
 */
export function mcpEntryConfig(config = {}) {
  const candidates = []
  if (config.python) candidates.push(config.python)
  if (process.env.QVASP_PYTHON) candidates.push(process.env.QVASP_PYTHON)
  const names = platform() === 'win32' ? ['python', 'python3'] : ['python3', 'python']
  candidates.push(...names)
  // Python is frequently installed but absent from the PATH the host inherits
  // (conda on Windows, /usr/bin on macOS, Homebrew, the python.org launcher).
  // Without these, a machine that can run the server still gets no MCP tools.
  for (const dir of COMMON_PYTHON_DIRS) {
    const exe = platform() === 'win32' ? 'python.exe' : 'python3'
    candidates.push(join(dir, exe))
  }
  let python = null
  for (const cmd of candidates) {
    const r = spawnSync(cmd, ['--version'], { encoding: 'utf8', timeout: 8000 })
    if (r.status === 0) { python = cmd; break }
  }
  const serverScript = join(PKG, 'server', 'qvasp_mcp.py')
  if (!python || !existsSync(serverScript)) return null
  return {
    id: MCP_ENTRY_ID,
    name: '@deepseek-ai/dsh-mcp-client',
    config: {
      transport: 'stdio',
      serverName: 'qvasp',
      command: python,
      args: [serverScript],
      failOnStartupError: false,
      env: {
        ...(config.qvaspBin ? { QVASP_BIN: config.qvaspBin } : {}),
        ...(config.workroot ? { QVASP_WORKROOT: config.workroot } : {}),
        ...(config.scheduler ? { QVASP_SCHEDULER: config.scheduler } : {}),
      },
    },
  }
}

export function apply(ctx, config = {}) {
  // 1. Sync the bundled skill into the user skill library. Failure must not
  //    block the rest of the plugin (same discipline as dsh-memory-evolve).
  try {
    const results = syncBuiltinSkills(join(PKG, 'skills'), config.skillDir ?? DEFAULT_SKILL_DIR)
    for (const r of results) {
      if (r.action === 'missing') console.warn(`qvasp-skill: bundled skill ${r.name} missing SKILL.md`)
    }
  } catch (error) {
    console.warn('qvasp-skill: skill sync failed:', error?.message ?? error)
  }

  // 2. Mount the MCP client entry with runtime-resolved paths. Idempotent:
  //    if an entry with this id already exists (persisted from a previous
  //    boot), update it instead of creating a duplicate.
  ctx.effect(() => {
    const entry = mcpEntryConfig(config)
    if (!entry) {
      console.warn(
        'qvasp-skill: no python interpreter found (set QVASP_PYTHON or put python on PATH);'
        + ' MCP tools will not be available. The qvasp skill itself still works.',
      )
      return
    }
    const loader = ctx.loader
    if (loader?.create) {
      try {
        loader.resolve(MCP_ENTRY_ID)
        // Already mounted (persisted journal or duplicate boot) — update in place.
        loader.update(MCP_ENTRY_ID, { id: entry.id, name: entry.name, config: entry.config })
        return
      } catch {
        // resolve() throws when absent -> create it.
      }
      loader.create({ id: entry.id, name: entry.name, config: entry.config })
    } else {
      console.warn('qvasp-skill: loader service not reachable; MCP entry not mounted')
    }
    return () => {
      try { loader?.remove?.(MCP_ENTRY_ID) } catch { /* already gone */ }
    }
  }, 'qvasp-skill: mcp entry')
}
