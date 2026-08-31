// Documentation integrity check — Markdown link/image resolution.
//
// - relative links/images must resolve to a file that exists in the repo
// - anchors (#fragment) are checked against the target file's headings
// - image embeds pointing at github.com/.../blob/... fail (they do not render)
// - http(s) links get a timed HEAD/GET; only a hard 404/410 or DNS failure
//   fails the build (403/429/5xx are reported as warnings)
//
// No project dependencies. Runs on the Node bundled with GitHub runners.

import {readFileSync, existsSync, readdirSync, statSync} from 'node:fs';
import {join, dirname, resolve, relative, extname} from 'node:path';
import {fileURLToPath} from 'node:url';

const repoRoot = resolve(fileURLToPath(new URL('.', import.meta.url)), '..', '..');
const SKIP_DIRS = new Set(['.git', 'node_modules', '.venv', 'dist', 'build', '__pycache__']);
const SOFT_HOSTS = ['github.com', 'www.github.com', 'git-scm.com', 'www.git-scm.com'];

function listMarkdown(dir) {
  const out = [];
  for (const entry of readdirSync(dir, {withFileTypes: true})) {
    if (SKIP_DIRS.has(entry.name)) continue;
    const full = join(dir, entry.name);
    if (entry.isDirectory()) out.push(...listMarkdown(full));
    else if (entry.name.toLowerCase().endsWith('.md')) out.push(full);
  }
  return out;
}

function slugify(heading) {
  return heading
    .toLowerCase()
    .replace(/[`*_~]/g, '')
    .replace(/<[^>]+>/g, '')
    .trim()
    .replace(/[^\w\- ]/g, '')
    .replace(/ /g, '-'); // GitHub does not collapse consecutive spaces
}

function headingSlugs(file) {
  const slugs = new Set();
  const counts = {};
  for (const line of readFileSync(file, 'utf8').split('\n')) {
    const m = /^#{1,6}\s+(.*?)\s*#*\s*$/.exec(line);
    if (!m) continue;
    let s = slugify(m[1]);
    if (s in counts) {
      counts[s] += 1;
      s = `${s}-${counts[s]}`;
    } else counts[s] = 0;
    slugs.add(s);
  }
  return slugs;
}

const LINK_RE = /(!?)\[[^\]]*\]\(\s*<?([^)\s>]+)>?(?:\s+"[^"]*")?\s*\)/g;
const failures = [];
const warnings = [];
const externalTargets = new Map();

const mdFiles = listMarkdown(repoRoot);
if (mdFiles.length === 0) {
  console.error('No Markdown files found.');
  process.exit(1);
}

for (const file of mdFiles) {
  const rel = relative(repoRoot, file).replace(/\\/g, '/');
  const text = readFileSync(file, 'utf8');
  let m;
  while ((m = LINK_RE.exec(text)) !== null) {
    const isImage = m[1] === '!';
    const raw = m[2];
    if (raw.startsWith('mailto:') || raw.startsWith('tel:')) continue;

    if (/^https?:\/\//i.test(raw)) {
      if (isImage && /github\.com\/[^)]*\/blob\//i.test(raw)) {
        failures.push(`${rel}: image uses a GitHub blob URL (will not render): ${raw}`);
        continue;
      }
      if (!externalTargets.has(raw)) externalTargets.set(raw, []);
      externalTargets.get(raw).push(rel);
      continue;
    }

    // pure anchor -> same file
    if (raw.startsWith('#')) {
      const anchor = decodeURIComponent(raw.slice(1)).toLowerCase();
      if (anchor && !headingSlugs(file).has(anchor)) {
        warnings.push(`${rel}: anchor not found -> ${raw}`);
      }
      continue;
    }

    const [pathPart, anchor] = raw.split('#');
    const cleaned = decodeURIComponent(pathPart.split('?')[0]);
    if (cleaned === '') continue;
    const abs = resolve(dirname(file), cleaned);
    if (!existsSync(abs)) {
      failures.push(`${rel}: broken relative link -> ${raw}`);
      continue;
    }
    if (anchor && statSync(abs).isFile() && extname(abs).toLowerCase() === '.md') {
      const a = decodeURIComponent(anchor).toLowerCase();
      if (a && !headingSlugs(abs).has(a)) {
        warnings.push(`${rel}: anchor '#${anchor}' not found in ${cleaned}`);
      }
    }
  }
}

async function checkUrl(url) {
  const host = (() => {
    try {
      return new URL(url).host;
    } catch {
      return '';
    }
  })();
  const soft = SOFT_HOSTS.some((h) => host === h || host.endsWith('.' + h));
  const ac = new AbortController();
  const timer = setTimeout(() => ac.abort(), 15000);
  try {
    const res = await fetch(url, {
      redirect: 'follow',
      signal: ac.signal,
      headers: {'user-agent': 'docs-integrity-check'},
    });
    if (res.status === 404 || res.status === 410) {
      (soft ? warnings : failures).push(`${soft ? 'soft host ' : 'dead link '}(${res.status}): ${url}`);
    } else if (!res.ok) {
      warnings.push(`non-OK ${res.status} (not failing): ${url}`);
    }
  } catch (err) {
    (soft ? warnings : failures).push(`${soft ? 'soft host ' : ''}unreachable (${err.name}): ${url}`);
  } finally {
    clearTimeout(timer);
  }
}

const urls = [...externalTargets.keys()];
console.log(`Checked ${mdFiles.length} Markdown file(s); ${urls.length} external URL(s).`);
if (process.env.SKIP_EXTERNAL !== '1') {
  await Promise.all(urls.map(checkUrl));
}

for (const w of warnings) console.log(`WARN  ${w}`);
for (const f of failures) console.log(`FAIL  ${f}`);
if (failures.length) {
  console.error(`\n${failures.length} failure(s).`);
  process.exit(1);
}
console.log(`\nOK${warnings.length ? ` (${warnings.length} warning(s))` : ''}`);
