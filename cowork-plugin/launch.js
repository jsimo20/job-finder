// Starts Playwright MCP with its upload folder at <home>/job-finder/.playwright-mcp,
// whatever the OS calls the home folder.
const { spawn } = require("child_process");
const os = require("os");
const path = require("path");

const outputDir = path.join(os.homedir(), "job-finder", ".playwright-mcp");
const quote = (arg) => `"${arg}"`;
// A shell lets npx resolve to npx.cmd on Windows; quoting keeps a home path with spaces whole.
const command = ["npx", "@playwright/mcp@0.0.79", "--output-dir", quote(outputDir)].join(" ");
const child = spawn(command, { stdio: "inherit", shell: true });

child.on("exit", (code, signal) => process.exit(code ?? (signal ? 1 : 0)));
for (const sig of ["SIGINT", "SIGTERM"]) process.on(sig, () => child.kill(sig));
