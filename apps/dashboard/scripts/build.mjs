import { spawnSync } from 'node:child_process';
import { copyFileSync, existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const dist = path.join(root, 'dist');
const packageJson = JSON.parse(readFileSync(path.join(root, 'package.json'), 'utf8'));
const sha = (process.env.STRATIDE_UI_BUILD_SHA || '').trim() || 'local';
const version = packageJson.version;

rmSync(dist, { recursive: true, force: true });
mkdirSync(path.join(dist, 'assets'), { recursive: true });

const esbuildBin = path.join(root, 'node_modules', 'esbuild', 'bin', 'esbuild');
const args = [
  'src/main.tsx',
  '--bundle',
  '--outfile=dist/assets/app.js',
  '--format=esm',
  '--target=es2022',
  '--minify',
  '--charset=utf8',
  '--jsx=automatic',
  '--log-level=info',
  '--legal-comments=eof',
  '--define:process.env.NODE_ENV="production"',
  `--define:__UI_VERSION__="${version}"`,
  `--define:__BUILD_SHA__="${sha}"`,
];
const result = spawnSync(process.execPath, [esbuildBin, ...args], {
  cwd: root,
  stdio: 'inherit',
  windowsHide: true,
});
if (result.error) {
  console.error(result.error.message);
  process.exit(1);
}
if (result.status !== 0) process.exit(result.status ?? 1);

for (const [from, to] of [
  [path.join(root, 'index.html'), path.join(dist, 'index.html')],
]) copyFileSync(from, to);

if (!existsSync(path.join(dist, 'assets', 'app.css'))) {
  console.error('构建失败：esbuild 未生成 assets/app.css');
  process.exit(1);
}

const sizes = ['app.js', 'app.css'].map((name) => {
  const body = readFileSync(path.join(dist, 'assets', name));
  return `${name} ${(body.length / 1024).toFixed(1)} KiB`;
});
console.log(`Stratide UI build ${version} (${sha}) · ${sizes.join(' · ')}`);
