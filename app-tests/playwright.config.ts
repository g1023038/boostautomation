import { defineConfig } from '@playwright/test';

// TODO: replace with the real LambdaTest capabilities (browser/device matrix,
// build name, lt:options) once we've seen an existing script -- this is a
// minimal placeholder so the pipeline has something runnable.
export default defineConfig({
  testDir: './tests',
  reporter: [['junit', { outputFile: 'results.xml' }]],
  use: {
    connectOptions: {
      wsEndpoint: `wss://cdp.lambdatest.com/playwright?capabilities=${encodeURIComponent(
        JSON.stringify({
          browserName: 'Chrome',
          browserVersion: 'latest',
          'LT:Options': {
            platform: 'Windows 11',
            build: 'qa-automation-pipeline',
            name: 'app-tests',
            user: process.env.LT_USERNAME,
            accessKey: process.env.LT_ACCESS_KEY,
          },
        })
      )}`,
    },
  },
});
