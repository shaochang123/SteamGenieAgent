// ============================================================================
// Steam Genie MCP — Type Definitions
// ============================================================================

/** A game entry from the Steam library */
export interface LibraryGame {
  appid: number;
  name: string;
  playtime_forever: number;       // total minutes played
  playtime_2weeks: number;        // minutes played in last 2 weeks
  img_icon_url: string;           // hash for icon CDN URL
  img_logo_url: string;
  has_community_visible_stats: boolean;
}

/** Installed game from local VDF manifest */
export interface InstalledGame {
  appid: number;
  name: string;
  installdir: string;
  sizeOnDisk: number;             // bytes
  stateFlags: number;
  lastUpdated: number;            // unix timestamp
  libraryPath: string;            // which steam library folder
}

/** A Steam library folder from libraryfolders.vdf */
export interface LibraryFolder {
  path: string;
  label: string;
  contentid: string;
  totalsize: number;
  apps: number[];                 // app IDs in this folder
}

/** Friend entry */
export interface SteamFriend {
  steamid: string;
  relationship: string;           // "friend" | "requestrecipient" | "requestsent"
  friend_since: number;
  personaname?: string;
  avatarfull?: string;
  personastate?: number;          // 0=offline, 1=online, 2=busy, 3=away, 4=snooze, 5=looking-to-trade, 6=looking-to-play
  profileurl?: string;
  gameextrainfo?: string;         // in-game title if playing
  gameid?: string;                // in-game appid
}

/** Player achievement */
export interface PlayerAchievement {
  apiname: string;
  achieved: number;               // 0 or 1
  unlocktime: number;
  name: string;
  description: string;
}

/** Game with achievement/play data for session matching */
export interface GameSessionCandidate {
  appid: number;
  name: string;
  playtime_minutes: number;
  achievementProgress: number;    // 0-100 percentage
  positiveRatings: number;
  totalRatings: number;
  ratingPercent: number;
  estimatedHours: number;
  isInstalled: boolean;
}

/** Inventory item for CS2/Dota2 */
export interface InventoryItem {
  appid: number;
  contextid: string;
  assetid: string;
  classid: string;
  instanceid: string;
  amount: number;
  name: string;
  marketHashName: string;
  iconUrl: string;
  tradable: boolean;
  marketable: boolean;
  price?: MarketPrice;
}

/** Steam market price data */
export interface MarketPrice {
  lowestPrice: string;            // e.g. "$1.23"
  medianPrice: string;
  volume: number;
  currency: string;
  lastUpdated: string;
}

/** Store search result */
export interface StoreSearchResult {
  appid: number;
  name: string;
  type: string;                   // "game" | "dlc" | "demo" etc.
  currentPrice: number;           // in CNY (or user currency)
  originalPrice: number;
  discountPercent: number;
  headerImage: string;
  releaseDate: string;
  platforms: {
    windows: boolean;
    mac: boolean;
    linux: boolean;
  };
  metacritic?: { score: number; url: string };
  reviewSummary: string;          // e.g. "Very Positive"
  reviewPercent: number;
}

/** Price history entry */
export interface PriceHistoryEntry {
  date: string;
  price: number;
  discount: boolean;
}

/** Screenshot from local Steam data */
export interface SteamScreenshot {
  appid: number;
  gameName: string;
  filename: string;
  fullPath: string;
  width: number;
  height: number;
  created: number;
  size: number;
}

/** Steam config / server options */
export interface SteamGenieOptions {
  steamApiKey?: string;
  steamId?: string;
  steamPath?: string;             // custom Steam installation path
  currency?: string;              // default "CNY"
  language?: string;              // default "zh-CN"
}

/** Steam store country-specific price data */
export interface CountryPrice {
  currency: string;
  initial: number;                // price in smallest unit
  final: number;
  discount_percent: number;
  individual: number;             // non-bundle price
}

/** Full store app details */
export interface StoreAppDetails {
  appid: number;
  name: string;
  type: string;
  is_free: boolean;
  short_description: string;
  header_image: string;
  developers: string[];
  publishers: string[];
  price_overview: CountryPrice | null;
  platforms: { windows: boolean; mac: boolean; linux: boolean };
  metacritic?: { score: number; url: string };
  categories: Array<{ id: number; description: string }>;
  genres: Array<{ id: string; description: string }>;
  release_date: { coming_soon: boolean; date: string };
  recommendations: { total: number };
  achievements: { total: number };
}
