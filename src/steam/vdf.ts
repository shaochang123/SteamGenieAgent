import * as fs from "node:fs";
import * as path from "node:path";
import * as os from "node:os";
import type { InstalledGame, LibraryFolder } from "../types.js";

const APP_MANIFEST_RE = /^appmanifest_(\d+)\.acf$/;
type SteamShortcut = { appid: number; name: string; exe: string };

function isNumericKey(key: string): boolean {
  return !Number.isNaN(Number(key));
}

function readDir(dir: string): fs.Dirent[] {
  try { return fs.readdirSync(dir, { withFileTypes: true }); } catch { return []; }
}

export function detectSteamPath(): string {
  const configuredPath = process.env.STEAM_PATH?.trim();
  if (configuredPath) return configuredPath;

  switch (process.platform) {
    case "win32": {
      const candidates = [
        path.join(process.env["ProgramFiles(x86)"] || "C:\\Program Files (x86)", "Steam"),
        path.join(process.env.ProgramFiles || "C:\\Program Files", "Steam"),
        "D:\\Steam",
        "E:\\Steam",
      ];
      return candidates.find(isSteamInstallPath) || candidates[0];
    }
    case "darwin":
      return path.join(
        os.homedir(),
        "Library",
        "Application Support",
        "Steam"
      );
    default: // linux
      return path.join(os.homedir(), ".local", "share", "Steam");
  }
}

function isSteamInstallPath(candidate: string): boolean {
  return (
    fs.existsSync(path.join(candidate, "steamapps")) ||
    fs.existsSync(path.join(candidate, "Steam.exe")) ||
    fs.existsSync(path.join(candidate, "steam.sh"))
  );
}

function getSteamAppsPath(steamPath: string): string {
  const normalized = path.normalize(steamPath);
  if (path.basename(normalized).toLowerCase() === "steamapps") {
    return normalized;
  }
  return path.join(normalized, "steamapps");
}

/**
 * Parse a VDF-formatted string into a plain object.
 * Handles nested objects, quoted strings, and unquoted integers.
 */
function parseVdf(content: string): Record<string, unknown> {
  let i = 0;
  return parseObject();

  function skipWhitespace() {
    while (i < content.length && /\s/.test(content[i])) i++;
  }

  function parseObject(): Record<string, unknown> {
    const obj: Record<string, unknown> = {};
    skipWhitespace();
    if (content[i] === "{") i++; // skip opening brace
    skipWhitespace();

    while (i < content.length && content[i] !== "}") {
      const key = parseString();
      skipWhitespace();
      const value = parseValue();
      obj[key] = value;
      skipWhitespace();
    }

    if (i < content.length && content[i] === "}") i++; // skip closing brace
    return obj;
  }

  function parseValue(): unknown {
    skipWhitespace();
    if (content[i] === "{") {
      i++;
      const obj = parseObject();
      skipWhitespace();
      return obj;
    }
    if (content[i] === '"') {
      return parseString();
    }
    return parseUnquoted();
  }

  function parseString(): string {
    // accept both '//' comments and valid strings
    if (content[i] !== '"') throw new Error(`Expected " at position ${i}, got '${content[i]}'`);
    i++; // skip opening quote
    let result = "";
    while (i < content.length) {
      if (content[i] === "\\") {
        i++;
        if (content[i] === '"') result += '"';
        else if (content[i] === "\\") result += "\\";
        else if (content[i] === "n") result += "\n";
        else result += content[i];
        i++;
      } else if (content[i] === '"') {
        i++; // skip closing quote
        return result;
      } else {
        result += content[i];
        i++;
      }
    }
    throw new Error("Unterminated string");
  }

  function parseUnquoted(): string {
    let result = "";
    while (i < content.length && !/\s/.test(content[i]) && content[i] !== "}") {
      result += content[i];
      i++;
    }
    return result;
  }
}

export function getLibraryFolders(steamPath: string): LibraryFolder[] {
  const vdfPath = path.join(getSteamAppsPath(steamPath), "libraryfolders.vdf");
  if (!fs.existsSync(vdfPath)) {
    const appsDir = getSteamAppsPath(steamPath);
    if (!fs.existsSync(appsDir)) return [];
    return [buildLibraryFolderFromAppsDir(appsDir)];
  }

  const content = fs.readFileSync(vdfPath, "utf-8");
  const parsed = parseVdf(content) as Record<string, unknown>;
  const folders = parsed["libraryfolders"] || parsed["LibraryFolders"] || parsed;

  const results: LibraryFolder[] = [];
  for (const [key, value] of Object.entries(folders as Record<string, unknown>)) {
    if (isNumericKey(key) && typeof value === "object" && value !== null) {
      const folder = value as Record<string, unknown>;
      results.push({
        path: String(folder.path || ""),
        label: String(folder.label || ""),
        contentid: String(folder.contentid || ""),
        totalsize: Number(folder.totalsize) || 0,
        apps: collectAppIds(folder.apps as Record<string, unknown>),
      });
    }
  }
  if (results.length > 0) return results;
  return [buildLibraryFolderFromAppsDir(getSteamAppsPath(steamPath))];
}

function buildLibraryFolderFromAppsDir(appsDir: string): LibraryFolder {
  return {
    path: path.dirname(appsDir),
    label: "Default",
    contentid: "",
    totalsize: 0,
    apps: collectManifestAppIds(appsDir),
  };
}

function collectManifestAppIds(appsDir: string): number[] {
  return readDir(appsDir)
    .filter((entry) => entry.isFile())
    .map((entry) => entry.name.match(APP_MANIFEST_RE))
    .filter((match): match is RegExpMatchArray => Boolean(match))
    .map((match) => Number(match[1]));
}

function collectAppIds(apps: Record<string, unknown> | undefined): number[] {
  if (!apps) return [];
  return Object.keys(apps)
    .filter(isNumericKey)
    .map(Number);
}

function parseAppManifest(manifestPath: string): InstalledGame | null {
  try {
    const content = fs.readFileSync(manifestPath, "utf-8");
    const parsed = parseVdf(content) as Record<string, unknown>;
    const state = (parsed["AppState"] || parsed) as Record<string, unknown>;

    return {
      appid: Number(state.appid) || 0,
      name: String(state.name || "Unknown"),
      installdir: String(state.installdir || ""),
      sizeOnDisk: Number(state.SizeOnDisk || state.sizeondisk || 0),
      stateFlags: Number(state.StateFlags || state.stateflags || 0),
      lastUpdated: Number(state.LastUpdated || state.lastupdated || 0),
      libraryPath: path.dirname(manifestPath),
    };
  } catch {
    return null;
  }
}

export function scanInstalledGames(steamPath: string): InstalledGame[] {
  const folders = getLibraryFolders(steamPath);
  const games: InstalledGame[] = [];

  for (const folder of folders) {
    const appsDir = path.join(folder.path, "steamapps");
    if (!fs.existsSync(appsDir)) continue;

    for (const entry of readDir(appsDir)) {
      if (!entry.isFile()) continue;
      const match = entry.name.match(APP_MANIFEST_RE);
      if (!match) continue;

      const manifest = parseAppManifest(path.join(appsDir, entry.name));
      if (manifest) {
        manifest.libraryPath = folder.path;
        games.push(manifest);
      }
    }
  }

  return games;
}

function getShortcutsPath(steamPath: string, steamId: string): string {
  // shortcuts.vdf is stored per-user in steam/userdata/<steamid3>/config/
  const steamId3 = BigInt(steamId) & 0xffffffffn;
  return path.join(steamPath, "userdata", String(steamId3), "config", "shortcuts.vdf");
}

export function readShortcuts(steamPath: string, steamId: string): SteamShortcut[] {
  const p = getShortcutsPath(steamPath, steamId);
  if (!fs.existsSync(p)) return [];

  try {
    return parseShortcutsVdf(fs.readFileSync(p));
  } catch {
    return [];
  }
}

function parseShortcutsVdf(buf: Buffer): SteamShortcut[] {
  // shortcuts.vdf uses a custom binary-ish format
  // First 4 bytes: signature (0x00)
  // Then a series of string key-value pairs, null-terminated
  // We do a best-effort parse using a simpler approach for recent Steam versions
  const results: SteamShortcut[] = [];

  try {
    const content = buf.toString("utf-8");
    // Newer Steam shortcuts.vdf is plain VDF
    const parsed = parseVdf(content) as Record<string, unknown>;
    const shortcuts = parsed["shortcuts"] as Record<string, unknown> | undefined;
    if (shortcuts) {
      for (const [key, value] of Object.entries(shortcuts)) {
        if (isNumericKey(key) && typeof value === "object" && value !== null) {
          const entry = value as Record<string, unknown>;
          results.push({
            appid: Number(entry.appid) || -Number(key),
            name: String(entry.AppName || entry.appname || "Unknown"),
            exe: String(entry.Exe || entry.exe || ""),
          });
        }
      }
    }
  } catch {
    // fallback: try binary parsing (older Steam format)
    let pos = 0;
    const readString = (): string => {
      const end = buf.indexOf(0, pos);
      if (end === -1) return "";
      const s = buf.subarray(pos, end).toString("utf-8");
      pos = end + 1;
      return s;
    };

    const MAX_SHORTCUTS = 500;
    while (pos < buf.length - 1 && results.length < MAX_SHORTCUTS) {
      const name = readString();
      if (!name || name.length === 0) break;
      const exe = readString();
      if (!exe) break;
      const appName = readString();
      readString(); // launch options
      readString(); // icon

      results.push({
        appid: -1 * (results.length + 1),
        name: name || appName || exe,
        exe: exe,
      });

      let skipped = 0;
      while (pos < buf.length && skipped < 10) {
        const b = buf[pos];
        pos++;
        if (b === 0) {
          const next = buf[pos];
          if (next !== undefined && next >= 32 && next < 127) {
            break;
          }
        }
      }
    }
  }

  return results;
}
