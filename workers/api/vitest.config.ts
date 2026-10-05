import { cloudflareTest, readD1Migrations } from '@cloudflare/vitest-pool-workers';
import { defineConfig } from 'vitest/config';

export default defineConfig(async () => {
  const migrations = await readD1Migrations('./migrations');
  return {
    plugins: [
      cloudflareTest({
        wrangler: { configPath: './wrangler.toml' },
        miniflare: {
          bindings: {
            TEST_MIGRATIONS: migrations,
            // Pinned so a local .dev.vars (EMAIL_MODE=log) cannot change test behavior.
            EMAIL_MODE: 'resend',
            RESEND_API_KEY: 'test-key',
          },
        },
      }),
    ],
  };
});
