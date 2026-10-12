import { defineConfig, devices } from '@playwright/test';

// Each parallel run sets its own port. The operator's `inv dev` holds 4321,
// and a run must never attach to another run's server, hence
// reuseExistingServer: false.
const port = Number(process.env.WATCH_E2E_PORT ?? 4329);
const baseURL = `http://127.0.0.1:${port}`;

// Build output and test artifacts go under an ignored cache path, per port:
// a peer's build in the same checkout empties dist/ at its start, which
// would pull the files out from under this preview server.
const cacheDir = `node_modules/.cache/watch-e2e/${port}`;
const outDir = `${cacheDir}/dist`;

export default defineConfig({
  testDir: 'tests/e2e',
  outputDir: `${cacheDir}/test-results`,
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  reporter: process.env.CI ? [['github'], ['list']] : 'list',
  use: {
    baseURL,
    trace: 'retain-on-failure',
    serviceWorkers: 'block',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: {
    command: `npm run build -- --outDir ${outDir} && npm run preview -- --outDir ${outDir} --port ${port} --host 127.0.0.1`,
    url: `${baseURL}/watch`,
    // Fixture data keeps the run offline even when a key is in .env.
    env: { WATCH_DATA: 'fixture' },
    reuseExistingServer: false,
    // A full site build runs first.
    timeout: 300_000,
    stdout: 'ignore',
    stderr: 'pipe',
  },
});
