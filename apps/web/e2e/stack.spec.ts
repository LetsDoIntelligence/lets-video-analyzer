import { expect, test } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { existsSync, mkdtempSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

/**
 * Full-stack flow against the real API. Needs the API on :8000 and the web app built with
 * NEXT_PUBLIC_USE_MOCKS=false. Run via `npm run test:e2e:stack` (see README).
 */
test.skip(process.env.E2E_STACK !== "1", "full-stack test: set E2E_STACK=1");

const API = process.env.E2E_API_URL ?? "http://localhost:8000";

test.beforeEach(async ({ request }) => {
  // Start from an empty library.
  const videos = (await (await request.get(`${API}/v1/videos`)).json()) as { id: string }[];
  for (const v of videos) await request.delete(`${API}/v1/videos/${v.id}`);
});

test("upload to the API, play, ask, reload keeps it, delete removes it", async ({ page }) => {
  // Reuse the synthetic sample as the "uploaded" file.
  const file = path.resolve(__dirname, "../public/samples/synthetic-traffic.mp4");
  expect(readFileSync(file).length).toBeGreaterThan(1000);

  await page.goto("/");
  await page.locator("#video-file-input").setInputFiles(file);

  // Selected automatically after upload; the toolbar shows the stored video.
  await expect(page.locator("#video-select")).toContainText("synthetic-traffic", { timeout: 20_000 });
  await expect(page.getByLabel("Ask a question about the video")).toBeEnabled();

  // The server analyses the upload in the background and the toolbar badge follows it.
  const badge = page.locator("#index-badge");
  await expect(badge).toBeVisible();
  await expect(badge).not.toContainText(/Queued|Analyzing/, { timeout: 90_000 });
  // With the real model (E2E_YOLO=1) it must finish successfully and report what it found.
  if (process.env.E2E_YOLO === "1") await expect(badge).toContainText(/Analyzed · \d+ objects?/);

  // Playback comes from the API's Range-streaming endpoint.
  const src = await page.locator("video").getAttribute("src");
  expect(src).toContain(`${API}/v1/videos/`);
  await expect.poll(() => page.locator("video").evaluate((v: HTMLVideoElement) => v.duration)).toBeGreaterThan(50);

  // The answer streams from the backend.
  const input = page.getByLabel("Ask a question about the video");
  await input.fill("how many cars in the first 30 seconds?");
  await input.press("Enter");
  const log = page.getByRole("log");
  await expect(log).toContainText(/I counted|I didn't find|analy[sz]ed/i, { timeout: 15_000 });

  // It survives a reload (the list is fetched from the API, not held in the tab).
  await page.reload();
  await page.locator("#video-select").click();
  await expect(page.getByRole("option", { name: /synthetic-traffic/ })).toBeVisible();
  await page.getByRole("option", { name: /synthetic-traffic/ }).click();

  // Delete from the toolbar: gone from the API too.
  await page.locator("#video-unload").click();
  await expect.poll(async () => (await (await page.request.get(`${API}/v1/videos`)).json()).length).toBe(0);
});

test("an unreadable file is rejected with the server's reason", async ({ page }) => {
  const dir = mkdtempSync(path.join(tmpdir(), "lets-"));
  const bad = path.join(dir, "broken.mp4");
  execFileSync(process.execPath, ["-e", `require('fs').writeFileSync(${JSON.stringify(bad)}, 'not a video'.repeat(200))`]);

  await page.goto("/");
  await page.locator("#video-file-input").setInputFiles(bad);
  await expect(page.getByText(/couldn't be read as a video/i)).toBeVisible({ timeout: 15_000 });
  expect(((await (await page.request.get(`${API}/v1/videos`)).json()) as unknown[]).length).toBe(0);
});

test("real model: counts from the stored tracks and draws boxes over the video", async ({ page }) => {
  test.skip(process.env.E2E_YOLO !== "1", "needs the real detector: set E2E_YOLO=1");
  test.setTimeout(240_000);
  const file = path.resolve(__dirname, "../../../test_video/Test Video.mp4");
  test.skip(!existsSync(file), "test_video/Test Video.mp4 is not present");

  await page.goto("/");
  await page.locator("#video-file-input").setInputFiles(file);
  await expect(page.locator("#index-badge")).toContainText(/Analyzed · \d+ objects?/, {
    timeout: 180_000,
  });

  // The answer comes from the tracks, not the simulator.
  const input = page.getByLabel("Ask a question about the video");
  await input.fill("how many cars in the first 30 seconds?");
  await input.press("Enter");
  const log = page.getByRole("log");
  await expect(log).toContainText(/I counted \d+ cars?/, { timeout: 15_000 });
  await expect(log).not.toContainText("simulated");

  // Jump to a moment that has a detection and check that boxes get painted.
  const id = (await (await page.request.get(`${API}/v1/videos`)).json())[0].id as string;
  const d = await (await page.request.get(`${API}/v1/videos/${id}/detections?start=0&end=30`)).json();
  const t = d.tracks[0].points[0][0] as number;
  await page.locator("video").evaluate((v: HTMLVideoElement, at) => (v.currentTime = at), t);
  const painted = () =>
    page.getByTestId("detection-overlay").evaluate((c: HTMLCanvasElement) => {
      const data = c.getContext("2d")!.getImageData(0, 0, c.width, c.height).data;
      for (let i = 3; i < data.length; i += 4) if (data[i] > 0) return true;
      return false;
    });
  await expect.poll(painted, { timeout: 10_000 }).toBe(true);
  await page.screenshot({ path: "test-results/overlay.png" });

  // The toggle hides them.
  await page.locator("#player-boxes").click();
  await expect(page.getByTestId("detection-overlay")).toHaveCount(0);
});