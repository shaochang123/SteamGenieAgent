import asyncio
import re
from typing import Any

from config import steam_country, steam_language
from http_utils import append_query, async_fetch_json, async_fetch_text


STEAM_API_BASE = "https://api.steampowered.com"
STEAM_COMMUNITY_BASE = "https://steamcommunity.com"
STEAM_STORE_BASE = "https://store.steampowered.com"


def _player_status_label(state: int) -> str:
    mapping = {
        0: "离线",
        1: "在线",
        2: "忙碌",
        3: "离开",
        4: "打盹",
        5: "想交易",
        6: "想组队",
    }
    return mapping.get(state, "未知")


def _community_status_label(state: str) -> str:
    mapping = {
        "offline": "离线",
        "online": "在线",
        "in-game": "游戏中",
        "away": "离开",
        "busy": "忙碌",
        "snooze": "打盹",
        "looking to trade": "想交易",
        "looking to play": "想组队",
    }
    return mapping.get((state or "").strip().lower(), state or "未知")


def _game_image(appid: int, image_hash: str, kind: str = "capsule") -> str:
    if not image_hash:
      return ""
    if kind == "icon":
      return f"https://media.steampowered.com/steamcommunity/public/images/apps/{appid}/{image_hash}.jpg"
    return f"https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/{appid}/capsule_616x353.jpg"


def _extract_tag(xml: str, tag_name: str) -> str:
    match = re.search(rf"<{tag_name}>(.*?)</{tag_name}>", xml, re.DOTALL | re.IGNORECASE)
    if not match:
        return ""
    value = match.group(1).strip()
    cdata_match = re.match(r"<!\[CDATA\[(.*)\]\]>", value, re.DOTALL)
    return cdata_match.group(1).strip() if cdata_match else value


class SteamService:
    def __init__(self, settings: dict[str, Any]) -> None:
        self.settings = settings or {}
        steam = self.settings.get("steam", {})
        self.api_key = (steam.get("apiKey") or "").strip()
        self.steam_id = (steam.get("steamId") or "").strip()
        self.country = (steam.get("country") or steam_country).strip() or steam_country
        self.language = (steam.get("language") or steam_language).strip() or steam_language
        self.proxy = (steam.get("proxy") or "").strip() or None

    @property
    def has_steam_id(self) -> bool:
        return bool(self.steam_id)

    @property
    def has_api_key(self) -> bool:
        return bool(self.api_key)

    def _friendly_api_error(self, error: Exception) -> str:
        message = str(error)
        lowered = message.lower()
        if "forbidden" in lowered or "verify your" in lowered or "key=" in lowered:
            return "Steam API Key 无效或没有访问权限，请检查当前用户的 Steam API Key。"
        if "not found" in lowered:
            return "没有找到这个 Steam 用户，请检查 SteamID64。"
        return message

    # ------------------------------------------------------------------
    # Async methods (used by async FastAPI endpoints)
    # ------------------------------------------------------------------

    async def _async_fetch_public_profile(self) -> dict[str, Any]:
        if not self.has_steam_id:
            raise RuntimeError("请先配置 SteamID64。")

        xml = await async_fetch_text(
            f"{STEAM_COMMUNITY_BASE}/profiles/{self.steam_id}?xml=1", proxy=self.proxy
        )
        steam_id = _extract_tag(xml, "steamID64") or self.steam_id
        persona_name = _extract_tag(xml, "steamID") or steam_id
        avatar_url = _extract_tag(xml, "avatarFull")
        profile_url = _extract_tag(xml, "profileURL") or f"{STEAM_COMMUNITY_BASE}/profiles/{steam_id}"
        online_state = _extract_tag(xml, "onlineState")
        state_message = _extract_tag(xml, "stateMessage")
        current_game = _extract_tag(xml, "inGameInfo")

        return {
            "steamId": steam_id,
            "personaName": persona_name,
            "avatarUrl": avatar_url,
            "profileUrl": profile_url,
            "status": _community_status_label(state_message or online_state),
            "currentGame": current_game,
        }

    async def async_get_overview(self) -> dict[str, Any]:
        if not self.has_steam_id:
            return {
                "configured": False,
                "message": "请先配置当前用户的 SteamID64，才能查询玩家状态。",
                "profile": None,
                "stats": None,
                "recentGames": [],
            }

        public_profile = None
        public_error = ""
        try:
            public_profile = await self._async_fetch_public_profile()
        except Exception as exc:
            public_error = f"无法读取公开资料: {exc}"

        if not self.has_api_key:
            return {
                "configured": public_profile is not None,
                "message": (
                    "当前仅显示公开资料。配置 Steam API Key 后可继续获取拥有游戏数和最近游戏。"
                    if public_profile
                    else public_error or "请配置 Steam API Key 和 SteamID64。"
                ),
                "profile": public_profile,
                "stats": None,
                "recentGames": [],
            }

        try:
            # Fetch all three Steam API endpoints in parallel
            summary_task = async_fetch_json(
                append_query(
                    f"{STEAM_API_BASE}/ISteamUser/GetPlayerSummaries/v0002/",
                    key=self.api_key,
                    steamids=self.steam_id,
                ),
                proxy=self.proxy,
            )
            owned_task = async_fetch_json(
                append_query(
                    f"{STEAM_API_BASE}/IPlayerService/GetOwnedGames/v0001/",
                    key=self.api_key,
                    steamid=self.steam_id,
                    include_appinfo="1",
                    include_played_free_games="1",
                ),
                proxy=self.proxy,
            )
            recent_task = async_fetch_json(
                append_query(
                    f"{STEAM_API_BASE}/IPlayerService/GetRecentlyPlayedGames/v0001/",
                    key=self.api_key,
                    steamid=self.steam_id,
                ),
                proxy=self.proxy,
            )

            summary, owned_games_raw, recent_games_raw = await asyncio.gather(
                summary_task, owned_task, recent_task
            )

            player = (summary.get("response", {}).get("players") or [None])[0]
            if not player:
                raise RuntimeError("没有找到这个 Steam 用户，请检查 SteamID64。")

            owned_games = owned_games_raw.get("response", {})
            recent_games = recent_games_raw.get("response", {})

            recent_items = []
            for item in (recent_games.get("games") or [])[:4]:
                recent_items.append(
                    {
                        "appid": item.get("appid"),
                        "name": item.get("name", ""),
                        "playtime2WeeksHours": round(item.get("playtime_2weeks", 0) / 60, 1),
                        "playtimeForeverHours": round(item.get("playtime_forever", 0) / 60, 1),
                        "iconUrl": _game_image(item.get("appid", 0), item.get("img_icon_url", ""), "icon"),
                        "headerImage": _game_image(item.get("appid", 0), item.get("img_logo_url", "")),
                    }
                )

            return {
                "configured": True,
                "message": "",
                "profile": {
                    "steamId": player.get("steamid", ""),
                    "personaName": player.get("personaname", ""),
                    "avatarUrl": player.get("avatarfull", ""),
                    "profileUrl": player.get("profileurl", ""),
                    "status": _player_status_label(int(player.get("personastate", 0))),
                    "currentGame": player.get("gameextrainfo", ""),
                },
                "stats": {
                    "ownedGamesCount": owned_games.get("game_count", 0),
                    "recentGamesCount": recent_games.get("total_count", 0),
                    "recentPlaytimeHours": round(
                        sum(item.get("playtime_2weeks", 0) for item in recent_games.get("games", [])) / 60,
                        1,
                    ),
                },
                "recentGames": recent_items,
            }
        except Exception as exc:
            return {
                "configured": public_profile is not None,
                "message": (
                    f"{self._friendly_api_error(exc)} 已切换为公开资料模式。"
                    if public_profile
                    else self._friendly_api_error(exc)
                ),
                "profile": public_profile,
                "stats": None,
                "recentGames": [],
            }

    async def async_get_deals(self) -> dict[str, Any]:
        try:
            url = append_query(
                f"{STEAM_STORE_BASE}/api/featuredcategories/",
                cc=self.country,
                l=self.language,
            )
            payload = await async_fetch_json(url, proxy=self.proxy)
            specials = payload.get("specials", {}).get("items", [])
            items = []
            for item in specials[:6]:
                items.append(
                    {
                        "appid": item.get("id"),
                        "name": item.get("name", ""),
                        "discountPercent": item.get("discount_percent", 0),
                        "finalPrice": round(item.get("final_price", 0) / 100, 2),
                        "originalPrice": round(item.get("original_price", 0) / 100, 2),
                        "currency": item.get("currency", self.country),
                        "headerImage": item.get("header_image", ""),
                        "storeUrl": f"https://store.steampowered.com/app/{item.get('id')}/",
                    }
                )
            return {
                "configured": True,
                "message": "",
                "items": items,
            }
        except Exception as exc:
            return {
                "configured": False,
                "message": f"无法获取商店卡片: {exc}",
                "items": [],
            }
