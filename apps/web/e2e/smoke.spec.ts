import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    if (!sessionStorage.getItem("e2e-cleared")) {
      localStorage.clear();
      sessionStorage.setItem("e2e-cleared", "1");
    }
  });
  await page.goto("/");
});

test("shell renders with header, prompts rail and disabled input", async ({ page }) => {
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await expect(page.getByLabel("Ask a question about the video")).toBeDisabled();
});

test("theme toggle switches the document theme", async ({ page }) => {
  const html = page.locator("html");
  await expect(html).toHaveAttribute("data-theme", /.+/);
  const before = await html.getAttribute("data-theme");
  await page.getByRole("button", { name: /theme/i }).first().click();
  await expect.poll(() => html.getAttribute("data-theme")).not.toBe(before);
});

test("select a sample video, ask a question, get a reply", async ({ page }) => {
  await page
    .getByRole("button", { name: /select video/i })
    .first()
    .click();
  await page.getByText("Synthetic traffic").first().click();

  const input = page.getByLabel("Ask a question about the video");
  await expect(input).toBeEnabled();
  await input.fill("how many cars in the first 30 seconds?");
  await input.press("Enter");

  const log = page.getByRole("log", { name: "Conversation" });
  await expect(log).toContainText("how many cars in the first 30 seconds?");
  await expect(log.getByRole("button", { name: "Regenerate" })).toBeAttached({ timeout: 15_000 });
});

async function ask(page: import("@playwright/test").Page, q: string) {
  await page
    .getByRole("button", { name: /select video/i })
    .first()
    .click();
  await page.getByText("Synthetic traffic").first().click();
  const input = page.getByLabel("Ask a question about the video");
  await input.fill(q);
  await input.press("Enter");
}

test("stop mid-stream marks the answer as stopped", async ({ page }) => {
  await ask(page, "how many cars in the first 30 seconds?");
  await page.locator("#chat-stop").click();
  await expect(page.getByRole("log")).toContainText("Stopped.");
});

test("regenerate re-answers, and chat survives a reload", async ({ page }) => {
  await ask(page, "how many trucks?");
  const log = page.getByRole("log");
  const regen = log.getByRole("button", { name: "Regenerate" });
  await expect(regen).toBeAttached({ timeout: 15_000 });
  await regen.click({ force: true });
  await expect(regen).toBeAttached({ timeout: 15_000 });
  await page.reload();
  await expect(page.getByRole("log")).toContainText("how many trucks?");
});
