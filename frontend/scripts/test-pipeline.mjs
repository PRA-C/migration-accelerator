import { chromium } from "playwright";

const UI_URL = "http://127.0.0.1:5173";
const opts = {
  use_llm: false,
  skip_provision: true,
  skip_migrate: true,
  skip_recon: true,
  skip_tests: true,
  skip_docs: true,
  integration_tests: false,
  preset: "full",
};

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage();
await page.goto(UI_URL, { waitUntil: "domcontentloaded", timeout: 15000 });

const health = await page.evaluate(async () => {
  const r = await fetch("/api/health");
  return r.json();
});
console.log("health", health);

const xhrResult = await page.evaluate(async (pipelineOpts) => {
  function consume(buffer, onEvent) {
    const normalized = buffer.replace(/\r\n/g, "\n");
    const parts = normalized.split("\n\n");
    const rest = parts.pop() || "";
    for (const part of parts) {
      if (!part.trim() || part.startsWith(":")) continue;
      const dataLine = part.split("\n").find((l) => l.startsWith("data:"));
      if (!dataLine) continue;
      try {
        onEvent(JSON.parse(dataLine.replace(/^data:\s?/, "")));
      } catch {
        /* ignore */
      }
    }
    return rest;
  }

  return new Promise((resolve, reject) => {
    let eventCount = 0;
    let totalBytes = 0;
    let readCount = 0;
    let progressBytes = 0;
    let buffer = "";
    let offset = 0;

    const xhr = new XMLHttpRequest();
    xhr.open("POST", "http://127.0.0.1:8000/api/pipeline/stream");
    xhr.setRequestHeader("Content-Type", "application/json");
    xhr.setRequestHeader("Accept", "text/event-stream");

    const ingest = (chunk) => {
      if (!chunk) return;
      readCount += 1;
      totalBytes += chunk.length;
      buffer = consume(buffer + chunk, () => {
        eventCount += 1;
      });
    };

    xhr.onreadystatechange = () => {
      if (xhr.readyState === 3 || xhr.readyState === 4) {
        const chunk = xhr.responseText.slice(offset);
        progressBytes += chunk.length;
        ingest(chunk);
        offset = xhr.responseText.length;
      }
      if (xhr.readyState === 4) {
        if (buffer.trim()) {
          consume(`${buffer}\n\n`, () => {
            eventCount += 1;
          });
        }
        resolve({
          status: xhr.status,
          eventCount,
          totalBytes,
          readCount,
          progressBytes,
          responseLen: xhr.responseText.length,
        });
      }
    };

    xhr.onerror = () => reject(new Error("xhr error"));
    xhr.send(JSON.stringify(pipelineOpts));
  });
}, opts);

console.log("direct_xhr", xhrResult);

await page.goto(UI_URL, { waitUntil: "networkidle", timeout: 15000 });
const btn = page.getByRole("button", { name: "▶ Full pipeline" });
await btn.click();
await page.waitForTimeout(2500);
const pct = (await page.locator(".flow-pct").textContent())?.trim();
console.log("ui_progress_pct", pct);

await browser.close();

if (xhrResult.eventCount === 0) process.exit(1);
if (!pct || pct === "0%") process.exit(2);
console.log("PASS");
