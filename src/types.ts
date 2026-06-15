export interface LibraryGame {
  appid: number;
  name: string;
  playtime_forever: number;       // total minutes played
  playtime_2weeks: number;        // minutes played in last 2 weeks
  img_icon_url: string;           // hash for icon CDN URL
  img_logo_url: string;
  has_community_visible_stats: boolean;
}

export interface InstalledGame {
  appid: number;
  name: string;
  installdir: string;
  sizeOnDisk: number;             // bytes
  stateFlags: number;
  lastUpdated: number;            // unix timestamp
  libraryPath: string;            // which steam library folder
}

export interface LibraryFolder {
  path: string;
  label: string;
  contentid: string;
  totalsize: number;
  apps: number[];                 // app IDs in this folder
}

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

export interface PlayerAchievement {
  apiname: string;
  achieved: number;               // 0 or 1
  unlocktime: number;
  name: string;
  description: string;
}

export interface GameSessionCandidate {
  appid: number;
  name: string;
  playtime_minutes: number;
  achievementProgress: number;    // 0-100 percentage
  ratingPercent: number;
  estimatedHours: number;
  isInstalled: boolean;
}

export interface MarketPrice {
  lowestPrice: string;            // e.g. "$1.23"
  medianPrice: string;
  volume: number;
  currency: string;
  lastUpdated: string;
}

export interface PriceHistoryEntry {
  date: string;
  price: number;
  discount: boolean;
}

export interface CountryPrice {
  currency: string;
  initial: number;                // price in smallest unit
  final: number;
  discount_percent: number;
  individual: number;             // non-bundle price
}

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
