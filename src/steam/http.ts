import { HttpsProxyAgent } from "https-proxy-agent";
import fetch, { type RequestInit } from "node-fetch";

const STEAM_HEADERS = {
  Accept: "application/json,text/javascript,*/*;q=0.1",
  "User-Agent": "Mozilla/5.0 SteamMcp/1.0",
};

let proxyAgent: HttpsProxyAgent<string> | null | undefined;

function proxyUrl(): string {
  return (
    process.env.HTTPS_PROXY ||
    process.env.HTTP_PROXY ||
    process.env.https_proxy ||
    process.env.http_proxy ||
    ""
  );
}

function getProxyAgent(): HttpsProxyAgent<string> | null {
  if (proxyAgent !== undefined) return proxyAgent;
  const url = proxyUrl();
  proxyAgent = url ? new HttpsProxyAgent(url) : null;
  return proxyAgent;
}

function steamFetchOptions(): RequestInit {
  const agent = getProxyAgent();
  return {
    ...(agent ? { agent } as RequestInit : {}),
    headers: STEAM_HEADERS,
  };
}

export async function fetchSteamJson<T>(url: string): Promise<T> {
  const response = await fetch(url, steamFetchOptions());
  if (!response.ok) {
    throw new Error(`Steam request failed ${response.status}: ${response.statusText}`);
  }
  return response.json() as Promise<T>;
}
