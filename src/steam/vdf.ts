// ============================================================================
// VDF Parser — reads Valve Data Format files from local Steam installation
// ============================================================================

import * as fs from "node:fs";
import * as path from "node:path";
import * as os from "node:os";
import type { InstalledGame, LibraryFolder } from "../types.js";

/** Detect the default Steam installation path for the current platform */
export function detectSteamPath(): string {
  switch (process.platform) {
    case "win32":
      return path.join(
        process.env["ProgramFiles(x86)"] || "C:\\Program Files (x86)",
        "Steam"
      );
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

/** Return the steamapps directory */
export function getSteamAppsPath(steamPath: string): string {
  return path.join(steamPath, "steamapps");
}

/**
 * Parse a VDF-formatted string into a plain object.
 * Handles nested objects, quoted strings, and unquoted integers.
 */
export function parseVdf(content: string): Record<string, unknown> {
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

/** Read and parse libraryfolders.vdf to get all library folders */
export function getLibraryFolders(steamPath: string): LibraryFolder[] {
  const vdfPath = path.join(getSteamAppsPath(steamPath), "libraryfolders.vdf");
  if (!fs.existsSync(vdfPath)) return [];

  const content = fs.readFileSync(vdfPath, "utf-8");
  const parsed = parseVdf(content) as Record<string, unknown>;
  const folders = parsed["libraryfolders"] || parsed["LibraryFolders"] || parsed;

  const results: LibraryFolder[] = [];
  for (const [key, value] of Object.entries(folders as Record<string, unknown>)) {
    if (!isNaN(Number(key)) && typeof value === "object" && value !== null) {
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
  return results;
}

function collectAppIds(apps: Record<string, unknown> | undefined): number[] {
  if (!apps) return [];
  return Object.keys(apps)
    .filter((k) => !isNaN(Number(k)))
    .map(Number);
}

/** Parse a single appmanifest_*.acf file */
export function parseAppManifest(manifestPath: string): InstalledGame | null {
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

/** Scan all library folders for installed game manifests */
export function scanInstalledGames(steamPath: string): InstalledGame[] {
  const folders = getLibraryFolders(steamPath);
  const games: InstalledGame[] = [];

  for (const folder of folders) {
    const appsDir = path.join(folder.path, "steamapps");
    if (!fs.existsSync(appsDir)) continue;

    let entries: fs.Dirent[];
    try {
      entries = fs.readdirSync(appsDir, { withFileTypes: true });
    } catch {
      continue;
    }

    for (const entry of entries) {
      if (!entry.isFile()) continue;
      const match = entry.name.match(/^appmanifest_(\d+)\.acf$/);
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

/** Get the shortcuts.vdf path for a given user */
export function getShortcutsPath(steamPath: string, steamId: string): string {
  // shortcuts.vdf is stored per-user in steam/userdata/<steamid3>/config/
  const steamId3 = BigInt(steamId) & 0xffffffffn;
  return path.join(steamPath, "userdata", String(steamId3), "config", "shortcuts.vdf");
}

/** Read and parse shortcuts.vdf */
export function readShortcuts(steamPath: string, steamId: string): Array<{ appid: number; name: string; exe: string }> {
  const p = getShortcutsPath(steamPath, steamId);
  if (!fs.existsSync(p)) return [];

  try {
    const buf = fs.readFileSync(p);
    const parsed = parseShortcutsVdf(buf);
    return parsed;
  } catch {
    return [];
  }
}

/** Custom parser for shortcuts.vdf binary format */
function parseShortcutsVdf(buf: Buffer): Array<{ appid: number; name: string; exe: string }> {
  // shortcuts.vdf uses a custom binary-ish format
  // First 4 bytes: signature (0x00)
  // Then a series of string key-value pairs, null-terminated
  // We do a best-effort parse using a simpler approach for recent Steam versions
  const results: Array<{ appid: number; name: string; exe: string }> = [];

  try {
    const content = buf.toString("utf-8");
    // Newer Steam shortcuts.vdf is plain VDF
    const parsed = parseVdf(content) as Record<string, unknown>;
    const shortcuts = parsed["shortcuts"] as Record<string, unknown> | undefined;
    if (shortcuts) {
      for (const [key, value] of Object.entries(shortcuts)) {
        if (!isNaN(Number(key)) && typeof value === "object" && value !== null) {
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
      const launchOptions = readString();
      const icon = readString();

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
