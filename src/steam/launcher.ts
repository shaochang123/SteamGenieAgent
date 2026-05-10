// ============================================================================
// Game Launcher — launch Steam games via steam:// protocol
// ============================================================================

import { exec } from "node:child_process";
import * as path from "node:path";
import * as fs from "node:fs";
import { detectSteamPath } from "./vdf.js";

/** Launch a Steam game by app ID */
export function launchGame(appid: number): Promise<{ success: boolean; message: string }> {
  return new Promise((resolve) => {
    const url = `steam://run/${appid}`;

    let command: string;
    switch (process.platform) {
      case "win32":
        command = `start "" "${url}"`;
        break;
      case "darwin":
        command = `open "${url}"`;
        break;
      default:
        command = `xdg-open "${url}"`;
        break;
    }

    exec(command, (error) => {
      if (error) {
        // Fallback: try running via steam.exe directly
        const steamPath = detectSteamPath();
        const steamExe = process.platform === "win32"
          ? path.join(steamPath, "Steam.exe")
          : process.platform === "darwin"
            ? path.join(steamPath, "Contents", "MacOS", "steam_osx")
            : path.join(steamPath, "steam.sh");

        if (fs.existsSync(steamExe)) {
          const fallbackCmd = process.platform === "win32"
            ? `"${steamExe}" steam://run/${appid}`
            : `${steamExe} steam://run/${appid}`;

          exec(fallbackCmd, (err2) => {
            if (err2) {
              resolve({
                success: false,
                message: `Failed to launch app ${appid}: ${err2.message}. You can manually open steam://run/${appid}`,
              });
            } else {
              resolve({
                success: true,
                message: `Launched app ${appid} via Steam executable`,
              });
            }
          });
        } else {
          resolve({
            success: false,
            message: `Failed to launch app ${appid}: ${error.message}. Steam not found at ${steamPath}. Try opening steam://run/${appid} manually.`,
          });
        }
      } else {
        resolve({ success: true, message: `Launched app ${appid}` });
      }
    });
  });
}

/** Open a Steam URL (store page, profile, community, etc.) */
export function openSteamUrl(urlType: "store" | "community" | "profile", id: string | number): Promise<{ success: boolean; message: string }> {
  return new Promise((resolve) => {
    let url: string;
    switch (urlType) {
      case "store":
        url = `steam://store/${id}`;
        break;
      case "community":
        url = `steam://url/CommunityHub/${id}`;
        break;
      case "profile":
        url = `steam://url/SteamIDPage/${id}`;
        break;
    }

    let command: string;
    switch (process.platform) {
      case "win32":
        command = `start "" "${url}"`;
        break;
      case "darwin":
        command = `open "${url}"`;
        break;
      default:
        command = `xdg-open "${url}"`;
        break;
    }

    exec(command, (error) => {
      if (error) {
        resolve({
          success: false,
          message: `Failed to open ${urlType}: ${error.message}`,
        });
      } else {
        resolve({ success: true, message: `Opened ${urlType} page` });
      }
    });
  });
}
