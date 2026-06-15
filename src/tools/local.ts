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
    "扫描本地 Steam 文件夹，列出所有已安装的游戏。无需 API Key，直接读取本地 VDF 文件。",
    {
      library_path: z
        .string()
        .optional()
        .describe("指定 Steam 库路径，不填则自动检测"),
    },
    async ({ library_path }) => {
      const sp = library_path || steamPath;
      const games = scanInstalledGames(sp);

      if (games.length === 0) {
        return textResult(`未找到已安装的游戏。检测路径：${sp}\n\n尝试手动指定 library_path 或检查 Steam 是否安装。`);
      }

      const totalSize = games.reduce((sum, g) => sum + g.sizeOnDisk, 0);
      const totalSizeGB = formatGigabytes(totalSize);

      const lines = games
        .sort((a, b) => a.name.localeCompare(b.name, "zh-CN"))
        .map((g) => {
          const gameSizeGB = formatGigabytes(g.sizeOnDisk);
          const updated = g.lastUpdated
            ? new Date(g.lastUpdated * 1000).toLocaleDateString("zh-CN")
            : "未知";
          return `- **${g.name}** (AppID: ${g.appid})
  📀 ${gameSizeGB} GB | 最后更新: ${updated} | 库: ${path.basename(g.libraryPath)}`;
        });

      return textResult(`💿 **已安装游戏** (${games.length} 款，共 ${totalSizeGB} GB)

${lines.join("\n")}

💡 使用 launch_game 启动游戏。`);
    }
  );

  server.tool(
    "list_library_folders",
    "列出所有 Steam 游戏库文件夹的位置及占用情况。",
    {},
    async () => {
      const folders = getLibraryFolders(steamPath);

      if (folders.length === 0) {
        return textResult("未找到 Steam 库文件夹。请检查 Steam 是否正确安装。");
      }

      const lines = folders.map((f) => {
        const folderSizeGB = formatGigabytes(f.totalsize);
        return `- **${f.label || "默认库"}** (${f.apps.length} 款游戏)
  📁 ${f.path}
  📀 占用: ${folderSizeGB} GB`;
      });

      return textResult(`📁 **Steam 库文件夹** (${folders.length} 个)

${lines.join("\n")}

总游戏数: ${folders.reduce((s, f) => s + f.apps.length, 0)}`);
    }
  );

  server.tool(
    "get_screenshots",
    "列出本地 Steam 截图文件夹中的截图。",
    {
      appid: z
        .number()
        .optional()
        .describe("按游戏 AppID 筛选，不填则列出所有"),
      limit: z
        .number()
        .optional()
        .default(20)
        .describe("返回数量上限"),
    },
    async ({ appid, limit }) => {
      const screenshotsPath = path.join(steamPath, "userdata");

      if (!fs.existsSync(screenshotsPath)) {
        return textResult("未找到截图文件夹。请确认 Steam 已安装并至少截过一次图。");
      }

      const screenshots = scanScreenshotFiles(screenshotsPath, appid);

      const filtered = screenshots
        .sort((a, b) => b.created.getTime() - a.created.getTime())
        .slice(0, limit);

      if (filtered.length === 0) {
        return textResult(appid ? `未找到 AppID ${appid} 的截图。` : "未找到任何截图。");
      }

      const lines = filtered.map((s) => {
        const sizeKB = (s.size / 1024).toFixed(0);
        return `- 🖼️ ${s.fileName} (AppID: ${s.appid})
  📅 ${s.created.toLocaleDateString("zh-CN")} | ${sizeKB} KB
  📁 ${s.fullPath}`;
      });

      return textResult(`📸 **Steam 截图** (${filtered.length} 张)

${lines.join("\n")}`);
    }
  );

  server.tool(
    "list_shortcuts",
    "列出本地 Steam 添加的非 Steam 快捷方式游戏。",
    {
      steam_id: z
        .string()
        .optional()
        .describe("SteamID64（需提供才能找到对应 shortcuts.vdf）"),
    },
    async ({ steam_id }) => {
      if (!steam_id) {
        return textResult("需要提供 steam_id 才能读取快捷方式。");
      }

      const shortcuts = readShortcuts(steamPath, steam_id);

      if (shortcuts.length === 0) {
        return textResult("未找到非 Steam 快捷方式。");
      }

      const lines = shortcuts.map(
        (s) =>
          `- **${s.name}** (虚拟 AppID: ${s.appid})\n  📁 ${s.exe}`
      );

      return textResult(`🔗 **非 Steam 快捷方式** (${shortcuts.length} 个)

${lines.join("\n")}`);
    }
  );
}
