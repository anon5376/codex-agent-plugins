import { spawn } from "node:child_process";
import { createRequire } from "node:module";
import { mkdtemp, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";


const require = createRequire(import.meta.url);
let playwright;
try {
  playwright = require("playwright");
} catch (error) {
  const runtimeModules = process.env.CODEX_NODE_MODULES;
  if (!runtimeModules) {
    throw new Error("Playwright is required for this optional smoke test. Install it or set CODEX_NODE_MODULES to a directory containing playwright.", { cause: error });
  }
  playwright = require(path.join(runtimeModules, "playwright"));
}
const { chromium } = playwright;
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const temporary = await mkdtemp(path.join(os.tmpdir(), "autonomous-operator-browser-"));
const dataDir = path.join(temporary, "data");
const projectDir = path.join(temporary, "project");
await mkdir(projectDir);
await writeFile(path.join(projectDir, "context.txt"), "browser fixture\n", "utf8");

let server;
let browser;

function waitForServerUrl(child) {
  return new Promise((resolve, reject) => {
    let output = "";
    const timer = setTimeout(() => reject(new Error(`server URL timeout: ${output}`)), 8000);
    child.stdout.setEncoding("utf8");
    child.stderr.setEncoding("utf8");
    child.stdout.on("data", (chunk) => {
      output += chunk;
      const match = output.match(/http:\/\/127\.0\.0\.1:\d+/);
      if (match) {
        clearTimeout(timer);
        resolve(match[0]);
      }
    });
    child.stderr.on("data", (chunk) => {
      output += chunk;
    });
    child.on("exit", (code) => {
      clearTimeout(timer);
      reject(new Error(`server exited ${code}: ${output}`));
    });
  });
}

function check(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

async function visibleText(locator) {
  await locator.waitFor({ state: "visible" });
  return (await locator.textContent()) || "";
}

try {
  server = spawn(
    "python3",
    ["-u", "scripts/server.py", "--port", "0", "--data-dir", dataDir],
    { cwd: root, stdio: ["ignore", "pipe", "pipe"] }
  );
  const baseUrl = await waitForServerUrl(server);
  browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  await context.grantPermissions(["clipboard-read", "clipboard-write"], { origin: baseUrl });
  const page = await context.newPage();
  let missionSaveRequests = 0;
  let delayPreview = false;
  let delaySave = false;
  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const pathname = new URL(request.url()).pathname;
    if (
      request.method() === "POST" &&
      ((pathname === "/api/preview" && delayPreview) ||
        (pathname === "/api/missions" && delaySave))
    ) {
      await new Promise((resolve) => setTimeout(resolve, 300));
    }
    await route.continue();
  });
  page.on("request", (request) => {
    if (request.method() === "POST" && new URL(request.url()).pathname === "/api/missions") {
      missionSaveRequests += 1;
    }
  });

  await page.goto(baseUrl, { waitUntil: "networkidle" });
  await page.locator("#mission-form").waitFor({ state: "visible" });
  check((await page.locator(".profile-route").innerText()).includes("Astra XHigh → Sol High → Luna Max"), "descending work route missing");
  check((await page.locator(".profile-route").innerText()).includes("Luna Max → Sol High → Astra XHigh"), "reverse review route missing");
  for (const detailsId of ["outcomes-details", "limits-details", "pro-details", "authority-details"]) {
    check(!(await page.locator("#" + detailsId).evaluate((element) => element.open)), `${detailsId} should start collapsed`);
  }

  await page.locator("#objective").fill("");
  await page.locator("#project_path").fill("relative/project");
  await page.locator("#authority-details > summary").click();
  await page.locator("#external_mode").selectOption("scoped");
  await page.locator("#authority-details").evaluate((element) => { element.open = false; });
  await page.locator("#review-button").click();
  check((await visibleText(page.locator("#objective-error"))).includes("required"), "objective validation was not visible");
  check((await visibleText(page.locator("#project-path-error"))).includes("absolute"), "project validation was not visible");
  check((await visibleText(page.locator("#external-scope-error"))).includes("scoped"), "scoped authority validation was not visible");
  check(await page.locator("#authority-details").evaluate((element) => element.open), "validation did not open the collapsed authority group containing an error");

  const objective = "Inspect the local browser fixture and prepare a bounded evidence note.";
  await page.locator("#objective").fill(objective);
  await page.locator("#title").fill("Browser smoke mission");
  await page.locator("#project_path").fill(projectDir);
  await page.locator('input[name="work_types"][value="research"]').check();
  await page.locator("#external_mode").selectOption("prepare");
  await page.locator("#review-button").click();
  await page.locator("#review-section").waitFor({ state: "visible" });
  const prompt = await page.locator("#prompt-output").innerText();
  check(prompt.includes(objective), "preview did not preserve objective");
  check(prompt.includes("Astra XHigh") && prompt.includes("Luna Max -> Sol High -> Astra XHigh"), "prompt did not preserve reverse review");

  await page.locator("#copy-button").click();
  const clipboard = await page.evaluate(() => navigator.clipboard.readText());
  check(clipboard === prompt, "copy action did not copy the generated prompt");

  await page.evaluate(() => {
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText: async () => { throw new Error("clipboard denied"); } }
    });
    document.execCommand = () => false;
  });
  await page.locator("#copy-button").click();
  await page.locator("#form-status").filter({ hasText: "Copy was unavailable" }).waitFor({ state: "visible" });
  check(await page.locator("#prompt-output").evaluate((element) => document.activeElement === element), "copy denial did not focus the selectable prompt fallback");

  const downloadPromise = page.waitForEvent("download");
  await page.locator("#download-button").click();
  const download = await downloadPromise;
  check(download.suggestedFilename() === "mission-prompt.txt", "prompt download filename changed");
  const downloadedPath = await download.path();
  check(downloadedPath, "prompt download produced no local file");
  check((await readFile(downloadedPath, "utf8")) === prompt, "downloaded prompt bytes differ from preview");

  await page.evaluate(() => {
    document.getElementById("save-button").click();
    document.getElementById("save-button").click();
  });
  await page.locator("#form-status").filter({ hasText: "Mission saved" }).waitFor({ state: "visible" });
  check(missionSaveRequests === 1, `expected one save request, saw ${missionSaveRequests}`);
  check(await page.locator("#save-button").isDisabled(), "saved prompt can be saved twice without editing");
  check((await visibleText(page.locator("#saved-state"))).includes("1 saved mission"), "saved mission list did not refresh");

  await page.locator("#objective").fill(objective + " Updated.");
  check(await page.locator("#review-section").isHidden(), "editing kept a stale prompt visible");
  check(await page.locator("#save-button").isDisabled(), "editing kept stale save eligibility");
  await page.locator("#review-button").click();
  await page.locator("#review-section").waitFor({ state: "visible" });
  check(!(await page.locator("#save-button").isDisabled()), "fresh review did not restore save eligibility");

  await page.reload({ waitUntil: "networkidle" });
  await page.locator("#mission-form").waitFor({ state: "visible" });
  check((await visibleText(page.locator("#saved-state"))).includes("1 saved mission"), "saved mission did not survive reload");
  await page.locator('[data-action="open"]').first().click();
  await page.locator("#review-section").waitFor({ state: "visible" });
  check((await page.locator("#objective").inputValue()) === objective, "open did not restore saved fields");
  check(await page.locator("#save-button").isDisabled(), "opening a saved mission allowed duplicate save");

  await page.locator('[data-action="reuse"]').first().click();
  await page.locator("#form-status").filter({ hasText: "reused" }).waitFor({ state: "visible" });
  check(await page.locator("#review-section").isHidden(), "reuse kept a stale saved prompt visible");
  check(await page.locator("#save-button").isDisabled(), "reuse kept stale save eligibility");

  delayPreview = true;
  await page.locator("#objective").fill("Preview request that will become stale.");
  const delayedPreviewRequest = page.waitForRequest((request) => request.method() === "POST" && new URL(request.url()).pathname === "/api/preview");
  await page.locator("#review-button").click();
  await delayedPreviewRequest;
  await page.locator("#objective").fill("Current mission after delayed preview edit.");
  await page.waitForTimeout(450);
  check(await page.locator("#review-section").isHidden(), "delayed preview restored a stale prompt after editing");
  check(await page.locator("#save-button").isDisabled(), "delayed preview restored stale save eligibility");
  check(!(await page.locator("#review-button").isDisabled()), "stale preview left Review prompt disabled");
  check(!(await page.locator("#form-status").innerText()).includes("Generating"), "stale preview left a false generating status");

  delayPreview = false;
  await page.locator("#review-button").click();
  await page.locator("#review-section").waitFor({ state: "visible" });
  check((await page.locator("#prompt-output").innerText()).includes("Current mission after delayed preview edit."), "fresh preview after race did not use current fields");

  delaySave = true;
  const delayedSaveRequest = page.waitForRequest((request) => request.method() === "POST" && new URL(request.url()).pathname === "/api/missions");
  await page.locator("#save-button").click();
  await delayedSaveRequest;
  await page.locator("#objective").fill("Current mission after delayed save edit.");
  await page.waitForTimeout(450);
  check(await page.locator("#review-section").isHidden(), "delayed save restored a stale prompt after editing");
  check(await page.locator("#save-button").isDisabled(), "delayed save attached stale saved state");
  check(!(await page.locator("#form-status").innerText()).includes("Mission saved"), "delayed save overwrote current edit status");

  await page.locator("#objective").focus();
  const outlineWidth = await page.locator("#objective").evaluate((element) => getComputedStyle(element).outlineWidth);
  check(outlineWidth !== "0px", "keyboard focus ring is not visible");

  await page.setViewportSize({ width: 390, height: 844 });
  await page.waitForTimeout(100);
  const overflow = await page.evaluate(() => ({
    documentWidth: document.documentElement.scrollWidth,
    viewportWidth: document.documentElement.clientWidth
  }));
  check(overflow.documentWidth <= overflow.viewportWidth, `phone page overflows horizontally: ${JSON.stringify(overflow)}`);
  check(await page.locator("#review-button").isVisible(), "primary action is missing at phone width");

  console.log("BROWSER_SMOKE_OK preview validation save reload open reuse copy-denial download-bytes stale-response focus responsive");
} finally {
  if (browser) {
    await browser.close();
  }
  if (server && server.exitCode === null) {
    server.kill("SIGTERM");
  }
  await rm(temporary, { recursive: true, force: true });
}
