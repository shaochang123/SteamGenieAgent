import type { MarketPrice, PriceHistoryEntry } from "../types.js";
import { fetchSteamJson } from "./http.js";

const CACHE_TTL = {
  PRICE: 60_000,          // 1 minute for current prices
  HISTORY: 300_000,       // 5 minutes for price history
  SEARCH: 120_000,        // 2 minutes for search results
};

const STEAM_CURRENCY_CODES: Record<string, number> = {
  USD: 1, GBP: 2, EUR: 3, CHF: 4, RUB: 5,
  PLN: 6, BRL: 7, JPY: 8, SEK: 9, IDR: 10,
  MYR: 11, PHP: 12, SGD: 13, THB: 14, VND: 15,
  KRW: 16, TRY: 17, UAH: 18, MXN: 19, CAD: 20,
  AUD: 21, NZD: 22, CNY: 23, INR: 24, CLP: 25,
  PEN: 26, COP: 27, ZAR: 28, HKD: 29, TWD: 30,
  SAR: 31, AED: 32, ARS: 34, ILS: 35, BYN: 36,
  KZT: 37, KWD: 38, QAR: 39, CRC: 40, UYU: 41,
  NOK: 162, ISK: 164,
};

interface CacheEntry<T> {
  data: T;
  timestamp: number;
}

interface MarketInventoryItem {
  assetid: string;
  classid: string;
  instanceid: string;
  amount: number;
  marketHashName: string;
  iconUrl: string;
  tradable: boolean;
  marketable: boolean;
}

interface FeaturedDeal {
  appid: number;
  name: string;
  discountPercent: number;
  originalPrice: number;
  finalPrice: number;
  currency: string;
  largeCapsuleImage: string;
}

function uniqueTerms(query: string): string[] {
  const cleaned = query
    .replace(/[《》“”"]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  const withoutReviewWords = cleaned
    .replace(/\b(reviews?|ratings?|scores?)\b/gi, " ")
    .replace(/(评价|评测|评分|怎么样|咋样)/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  const withoutLeadingArticle = withoutReviewWords.replace(/^(the|a|an)\s+/i, "");
  return Array.from(
    new Set([cleaned, withoutReviewWords, withoutLeadingArticle].filter(Boolean))
  );
}

export class SteamMarketService {
  private currency: string;
  private cache = new Map<string, CacheEntry<unknown>>();

  constructor(currency = "CNY") {
    this.currency = currency;
  }

  private cacheGet<T>(key: string, ttl: number): T | null {
    const entry = this.cache.get(key);
    if (entry && Date.now() - entry.timestamp < ttl) {
      return entry.data as T;
    }
    return null;
  }

  private cacheSet<T>(key: string, data: T): void {
    this.cache.set(key, { data, timestamp: Date.now() });
  }

  async getItemPrice(
    marketHashName: string,
    appid = 730
  ): Promise<MarketPrice | null> {
    const cacheKey = `price:${appid}:${marketHashName}`;
    const cached = this.cacheGet<MarketPrice>(cacheKey, CACHE_TTL.PRICE);
    if (cached) return cached;

    const params = new URLSearchParams({
      appid: String(appid),
      currency: this.getCurrencyCode(),
      market_hash_name: marketHashName,
    });
    const url = `https://steamcommunity.com/market/priceoverview/?${params.toString()}`;

    try {
      const data = await fetchSteamJson<{
        success: boolean;
        lowest_price?: string;
        median_price?: string;
        volume?: string;
      }>(url);

      if (!data.success) return null;

      const price: MarketPrice = {
        lowestPrice: data.lowest_price || "N/A",
        medianPrice: data.median_price || "N/A",
        volume: parseInt(data.volume || "0", 10) || 0,
        currency: this.currency,
        lastUpdated: new Date().toISOString(),
      };

      this.cacheSet(cacheKey, price);
      return price;
    } catch {
      return null;
    }
  }

  async getMultipleItemPrices(
    items: Array<{ name: string; appid: number }>
  ): Promise<Map<string, MarketPrice>> {
    const results = new Map<string, MarketPrice>();
    // Steam doesn't have a batch endpoint, so we fetch sequentially with a small delay
    for (const item of items) {
      const price = await this.getItemPrice(item.name, item.appid);
      if (price) results.set(item.name, price);
      // small delay to avoid rate limiting
      await new Promise((r) => setTimeout(r, 200));
    }
    return results;
  }

  async getInventory(
    steamId: string,
    appid: number,
    contextId = "2"
  ): Promise<MarketInventoryItem[]> {
    // Ensure Steam ID is 64-bit
    const id64 = steamId.startsWith("7656") ? steamId : `7656119${BigInt(steamId) + 7960265728n}`;

    const url = `https://steamcommunity.com/inventory/${id64}/${appid}/${contextId}?l=english&count=5000`;

    try {
      const data = await fetchSteamJson<{
        success: boolean;
        assets?: Array<{
          assetid: string;
          classid: string;
          instanceid: string;
          amount: string;
        }>;
        descriptions?: Array<{
          classid: string;
          instanceid: string;
          market_hash_name: string;
          icon_url: string;
          tradable: number;
          marketable: number;
        }>;
      }>(url);

      if (!data.success || !data.assets || !data.descriptions) return [];

      const descMap = new Map<string, (typeof data.descriptions)[0]>();
      for (const desc of data.descriptions) {
        const key = `${desc.classid}_${desc.instanceid}`;
        descMap.set(key, desc);
      }

      return data.assets.map((asset) => {
        const desc = descMap.get(`${asset.classid}_${asset.instanceid}`);
        return {
          assetid: asset.assetid,
          classid: asset.classid,
          instanceid: asset.instanceid,
          amount: parseInt(asset.amount, 10) || 1,
          marketHashName: desc?.market_hash_name || "Unknown",
          iconUrl: desc?.icon_url
            ? `https://community.cloudflare.steamstatic.com/economy/image/${desc.icon_url}`
            : "",
          tradable: desc?.tradable === 1,
          marketable: desc?.marketable === 1,
        };
      });
    } catch {
      return [];
    }
  }

  async getPriceHistory(
    appid: number
  ): Promise<PriceHistoryEntry[]> {
    const cacheKey = `history:${appid}`;
    const cached = this.cacheGet<PriceHistoryEntry[]>(cacheKey, CACHE_TTL.HISTORY);
    if (cached) return cached;

    try {
      const storeUrl = `https://store.steampowered.com/api/appdetails?appids=${appid}&cc=CN&filters=price_overview`;
      const data = await fetchSteamJson<Record<
        string,
        {
          success: boolean;
          data: {
            price_overview?: {
              currency: string;
              initial: number;
              final: number;
              discount_percent: number;
            };
          };
        }
      >>(storeUrl);

      const entry = data[String(appid)];
      if (!entry?.success || !entry.data.price_overview) return [];

      const price = entry.data.price_overview;
      const today = new Date().toISOString().split("T")[0];
      const history: PriceHistoryEntry[] = [
        {
          date: today,
          price: price.final / 100,
          discount: price.discount_percent > 0,
        },
      ];

      if (price.initial !== price.final) {
        history.push({
          date: today,
          price: price.initial / 100,
          discount: false,
        });
      }

      this.cacheSet(cacheKey, history);
      return history;
    } catch {
      return [];
    }
  }

  async searchStore(
    query: string,
    country = "CN",
    language = "zh-CN"
  ): Promise<Array<{ appid: number; name: string }>> {
    const cacheKey = `search:${query}:${country}:${language}`;
    const cached = this.cacheGet<Array<{ appid: number; name: string }>>(
      cacheKey,
      CACHE_TTL.SEARCH
    );
    if (cached) return cached;

    for (const term of uniqueTerms(query)) {
      const results = await this.fetchStoreSearch(term, country, language);
      if (results.length > 0) {
        this.cacheSet(cacheKey, results);
        return results;
      }
    }
    return [];
  }

  private async fetchStoreSearch(
    query: string,
    country: string,
    language: string
  ): Promise<Array<{ appid: number; name: string }>> {
    const params = new URLSearchParams({ term: query, cc: country, l: language });
    const url = `https://store.steampowered.com/api/storesearch/?${params.toString()}`;

    try {
      const data = await fetchSteamJson<{
        success?: boolean;
        total?: number;
        items?: Array<{ id: number; name: string; type?: string }>;
      }>(url);
      if (data.success === false || !Array.isArray(data.items)) return [];
      return data.items
        .filter((item) => item.id && item.name && (!item.type || item.type === "app"))
        .map((item) => ({ appid: item.id, name: item.name }));
    } catch {
      return [];
    }
  }

  async getFeaturedDeals(
    country = "CN",
    language = "zh-CN"
  ): Promise<FeaturedDeal[]> {
    const cacheKey = `featured:${country}`;
    const cached = this.cacheGet<FeaturedDeal[]>(cacheKey, CACHE_TTL.SEARCH);
    if (cached) return cached;

    const url = `https://store.steampowered.com/api/featuredcategories/?cc=${country}&l=${language}`;

    try {
      const data = await fetchSteamJson<{
        specials?: {
          items: Array<{
            id: number;
            name: string;
            discount_percent: number;
            original_price: number;
            final_price: number;
            currency: string;
            large_capsule_image: string;
          }>;
        };
      }>(url);

      const deals = (data.specials?.items || []).map((item) => ({
        appid: item.id,
        name: item.name,
        discountPercent: item.discount_percent,
        originalPrice: item.original_price / 100,
        finalPrice: item.final_price / 100,
        currency: item.currency,
        largeCapsuleImage: item.large_capsule_image,
      }));
      this.cacheSet(cacheKey, deals);
      return deals;
    } catch {
      return [];
    }
  }

  private getCurrencyCode(): string {
    return String(STEAM_CURRENCY_CODES[this.currency] || STEAM_CURRENCY_CODES.CNY);
  }
}
