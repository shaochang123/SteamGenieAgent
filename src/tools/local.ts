import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import {
  scanInstalledGames,
  getLibraryFolders,
  readShortcuts,
} from "../steam/vdf.js";
import * as fs from "node:fs";
import * as path from "node:path";
import { formatGigabytes } from "./format.js";
import { textResult } from "./response.js";

const SCREENSHOT_EXTENSIONS = new Set([".jpg", ".jpeg", ".png", ".bmp"]);

type ScreenshotFile = {
  appid: number;
  fileName: string;
  fullPath: string;
  size: number;
  created: Date;
};

function scanScreenshotFiles(userdataPath: string, appid?: number): ScreenshotFile[] {
  const screenshots: ScreenshotFile[] = [];

  try {
    for (const user of fs.readdirSync(userdataPath, { withFileTypes: true })) {
      if (!user.isDirectory()) continue;
      const remotePath = path.join(userdataPath, user.name, "760", "remote");
      if (!fs.existsSync(remotePath)) continue;

      const apps = appid
        ? [String(appid)]
        : fs.readdirSync(remotePath, { withFileTypes: true })
            .filter((entry) => entry.isDirectory())
            .map((entry) => entry.name);

      for (const app of apps) {
        const dir = path.join(remotePath, app, "screenshots");
        if (!fs.existsSync(dir)) continue;

        for (const file of fs.readdirSync(dir, { withFileTypes: true })) {
          if (!file.isFile()) continue;
          if (!SCREENSHOT_EXTENSIONS.has(path.extname(file.name).toLowerCase())) continue;

          const fullPath = path.join(dir, file.name);
          const stat = fs.statSync(fullPath);
          screenshots.push({
            appid: parseInt(app, 10),
            fileName: file.name,
            fullPath,
            size: stat.size,
            created: stat.birthtime,
          });
        }
      }
    }
  } catch {
    return [];
  }

  return screenshots;
}

export function registerLocalTools(server: McpServer, steamPath: string) {
  server.tool(
    "list_installed_games",
    "Scan local Steam library folders and list installed games without requiring a Steam API key.",
    {
      library_path: z
        .string()
        .optional()
        .describe("Optional Steam library path. If omitted, the configured or detected Steam path is used."),
    },
    async ({ library_path }) => {
      const sp = library_path || steamPath;
      const games = scanInstalledGames(sp);

      if (games.length === 0) {
        return textResult(`No installed games were found. Detected path: ${sp}\n\nPass library_path manually or verify that Steam is installed.`);
      }

      const totalSize = games.reduce((sum, g) => sum + g.sizeOnDisk, 0);
      const totalSizeGB = formatGigabytes(totalSize);

      const lines = games
        .sort((a, b) => a.name.localeCompare(b.name))
        .map((g) => {
          const gameSizeGB = formatGigabytes(g.sizeOnDisk);
          const updated = g.lastUpdated
            ? new Date(g.lastUpdated * 1000).toLocaleDateString("en-US")
            : "Unknown";
          return `- **${g.name}** (AppID: ${g.appid})
  Size: ${gameSizeGB} GB | Last updated: ${updated} | Library: ${path.basename(g.libraryPath)}`;
        });

      return textResult(`Installed games (${games.length}, total ${totalSizeGB} GB)\n\n${lines.join("\n")}\n\nUse launch_game to start a game.`);
    }
  );

  server.tool(
    "list_library_folders",
    "List local Steam library folders with game counts and disk usage.",
    {},
    async () => {
      const folders = getLibraryFolders(steamPath);

      if (folders.length === 0) {
        return textResult("No Steam library folders were found. Verify that Steam is installed correctly.");
      }

      const lines = folders.map((f) => {
        const folderSizeGB = formatGigabytes(f.totalsize);
        return `- **${f.label || "Default library"}** (${f.apps.length} games)
  Path: ${f.path}
  Disk usage: ${folderSizeGB} GB`;
      });

      return textResult(`Steam library folders (${folders.length})\n\n${lines.join("\n")}\n\nTotal games: ${folders.reduce((s, f) => s + f.apps.length, 0)}`);
    }
  );

  server.tool(
    "get_screenshots",
    "List local Steam screenshots from the configured Steam userdata folder.",
    {
      appid: z
        .number()
        .optional()
        .describe("Optional Steam AppID filter. If omitted, screenshots for all games are returned."),
      limit: z
        .number()
        .optional()
        .default(20)
        .describe("Maximum number of screenshots to return."),
    },
    async ({ appid, limit }) => {
      const screenshotsPath = path.join(steamPath, "userdata");

      if (!fs.existsSync(screenshotsPath)) {
        return textResult("Steam screenshot folder was not found. Verify that Steam is installed and that screenshots exist.");
      }

      const screenshots = scanScreenshotFiles(screenshotsPath, appid);

      const filtered = screenshots
        .sort((a, b) => b.created.getTime() - a.created.getTime())
        .slice(0, limit);

      if (filtered.length === 0) {
        return textResult(appid ? `No screenshots found for AppID ${appid}.` : "No screenshots found.");
      }

      const lines = filtered.map((s) => {
        const sizeKB = (s.size / 1024).toFixed(0);
        return `- ${s.fileName} (AppID: ${s.appid})
  Date: ${s.created.toLocaleDateString("en-US")} | ${sizeKB} KB
  Path: ${s.fullPath}`;
      });

      return textResult(`Steam screenshots (${filtered.length})\n\n${lines.join("\n")}`);
    }
  );

  server.tool(
    "list_shortcuts",
    "List local non-Steam shortcuts added to Steam.",
    {
      steam_id: z
        .string()
        .optional()
        .describe("SteamID64. Required to locate the user's shortcuts.vdf file."),
    },
    async ({ steam_id }) => {
      if (!steam_id) {
        return textResult("steam_id is required to read non-Steam shortcuts.");
      }

      const shortcuts = readShortcuts(steamPath, steam_id);

      if (shortcuts.length === 0) {
        return textResult("No non-Steam shortcuts were found.");
      }

      const lines = shortcuts.map(
        (s) =>
          `- **${s.name}** (virtual AppID: ${s.appid})\n  Executable: ${s.exe}`
      );

      return textResult(`Non-Steam shortcuts (${shortcuts.length})\n\n${lines.join("\n")}`);
    }
  );
}
