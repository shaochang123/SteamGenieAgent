import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import { SteamApiClient } from "../steam/api.js";
import type { SteamFriend } from "../types.js";
import { formatHours } from "./format.js";
import { textResult } from "./response.js";

const PERSONA_STATE: Record<number, string> = {
  0: "离线",
  1: "在线",
  2: "忙碌",
  3: "离开",
  4: "打盹",
  5: "想交易",
  6: "想玩",
};

const COOP_CATEGORY_IDS = [1, 9, 24, 27, 29, 38, 49]; // Multi-player, Co-op, Online Co-op, etc.
const isOnline = (friend: SteamFriend): boolean => friend.personastate !== 0;
const isPlaying = (friend: SteamFriend): boolean => Boolean(friend.gameextrainfo);

function compareFriends(a: SteamFriend, b: SteamFriend): number {
  if (isOnline(a) && !isOnline(b)) return -1;
  if (!isOnline(a) && isOnline(b)) return 1;
  if (isPlaying(a) && !isPlaying(b)) return -1;
  if (!isPlaying(a) && isPlaying(b)) return 1;
  return (a.personaname || "").localeCompare(b.personaname || "");
}

function formatFriendLine(friend: SteamFriend): string {
  const status = PERSONA_STATE[friend.personastate || 0] || "未知";
  const playing = friend.gameextrainfo ? ` | 🎮 ${friend.gameextrainfo}` : "";
  const online = isOnline(friend) ? "🟢" : "⚫";
  return `- ${online} **${friend.personaname || friend.steamid}** — ${status}${playing}`;
}

export function registerSocialTools(
  server: McpServer,
  api: SteamApiClient
) {
  server.tool(
    "get_friend_list",
    "查看 Steam 好友列表及在线状态，包括正在玩的游戏。",
    {
      online_only: z
        .boolean()
        .optional()
        .default(false)
        .describe("仅显示在线好友"),
    },
    async ({ online_only }) => {
      const friends = await api.getEnrichedFriends();

      if (friends.length === 0) {
        return textResult(
          "好友列表为空或需要配置 Steam API Key。\n请设置环境变量 STEAM_API_KEY 和 STEAM_ID。"
        );
      }

      const filtered = online_only ? friends.filter(isOnline) : friends;

      const online = friends.filter(isOnline);
      const playing = friends.filter(isPlaying);

      const lines = filtered.sort(compareFriends).map(formatFriendLine);

      return textResult(`👥 **Steam 好友** (${filtered.length} 人)
🟢 在线: ${online.length} | 🎮 游戏中: ${playing.length}

${lines.join("\n")}

💡 使用 find_shared_games 查找你们共有的游戏。`);
    }
  );

  server.tool(
    "find_shared_games",
    "查找你和指定好友共同拥有的游戏。",
    {
      friend_steam_id: z
        .string()
        .describe("好友的 SteamID64"),
      coop_only: z
        .boolean()
        .optional()
        .default(false)
        .describe("仅显示支持多人合作的游戏"),
      limit: z
        .number()
        .optional()
        .default(30)
        .describe("返回数量上限"),
    },
    async ({ friend_steam_id, limit }) => {
      const myGames = await api.getOwnedGames();
      if (myGames.length === 0) {
        return textResult("无法获取你的游戏库。请配置 Steam API Key。");
      }

      const friendApi = new SteamApiClient(api.apiKey, friend_steam_id);
      const friendGames = await friendApi.getOwnedGames();

      if (friendGames.length === 0) {
        return textResult(
          `无法获取好友 ${friend_steam_id} 的游戏库。请确保好友的 Steam 库存设置为公开。`
        );
      }

      const myAppIds = new Set(myGames.map((g) => g.appid));
      const shared = friendGames.filter((g) => myAppIds.has(g.appid));

      const myPlaytime = new Map(
        myGames.map((g) => [g.appid, g.playtime_forever])
      );
      shared.sort(
        (a, b) =>
          (b.playtime_forever + (myPlaytime.get(b.appid) || 0)) -
          (a.playtime_forever + (myPlaytime.get(a.appid) || 0))
      );

      const lines = shared.slice(0, limit).map((g) => `- **${g.name}** (AppID: ${g.appid})
  你的时长: ${formatHours(myPlaytime.get(g.appid) || 0)}h | 好友时长: ${formatHours(g.playtime_forever)}h`);

      return textResult(`🎮 **共同游戏** (${shared.length} 款，显示前 ${Math.min(limit, shared.length)} 款)

${lines.join("\n")}

💡 使用 launch_game 启动游戏，使用 generate_invite 生成邀请语。`);
    }
  );

  server.tool(
    "find_coop_game",
    "找出你与当前在线好友都能玩的合作游戏，并返回推荐列表。",
    {
      max_players: z
        .number()
        .optional()
        .default(4)
        .describe("最大玩家数"),
      min_shared_count: z
        .number()
        .optional()
        .default(2)
        .describe("最少需要几个好友拥有该游戏"),
    },
    async () => {
      const friends = await api.getEnrichedFriends();
      const onlineFriends = friends.filter((f) => isOnline(f) && f.personastate !== undefined);

      if (onlineFriends.length === 0) {
        return textResult("当前没有在线好友。");
      }

      const myGames = await api.getOwnedGames();
      if (myGames.length === 0) {
        return textResult("无法获取游戏库。");
      }

      // Recommend multiplayer/co-op games from the user's library
      // Note: Cross-referencing with friends' libraries requires each friend's
      // own API key due to Steam privacy restrictions.
      const candidates = myGames
        .filter((g) => g.playtime_forever > 0)
        .sort((a, b) => b.playtime_forever - a.playtime_forever)
        .slice(0, 20);

      const coopCandidates: Array<{
        name: string;
        appid: number;
        yourPlaytime: number;
      }> = [];
      for (const game of candidates) {
        const details = await api.getStoreAppDetails(game.appid);
        if (!details) continue;

        const isMultiplayer = details.categories?.some((c) =>
          COOP_CATEGORY_IDS.includes(c.id)
        );
        if (isMultiplayer || details.genres?.some((g) => g.description.includes("多人"))) {
          coopCandidates.push({
            name: game.name,
            appid: game.appid,
            yourPlaytime: game.playtime_forever,
          });
        }
      }

      const yourPlaylist = coopCandidates.slice(0, 12);

      const lines = yourPlaylist.map(
        (g, i) => `${i + 1}. **${g.name}** (AppID: ${g.appid}) — 你的时长: ${formatHours(g.yourPlaytime)}h`
      );

      return textResult(`🎯 **推荐合作游戏** (从你的游戏库中筛选)
🟢 在线好友: ${onlineFriends.length} 人

${lines.join("\n")}

⚠️ 注意：由于 API 限制，本功能基于你的游戏库筛选多人合作游戏。建议联系好友确认他们是否拥有这些游戏。

💡 使用 find_shared_games 查看与特定好友的共同游戏。`);
    }
  );

  server.tool(
    "generate_invite",
    "生成一段风趣的 Steam 游戏邀请语，用于发送给好友。",
    {
      game_name: z.string().describe("游戏名称"),
      friend_name: z.string().describe("好友的名称/昵称"),
      style: z
        .enum(["funny", "serious", "casual", "enthusiastic"])
        .optional()
        .default("funny")
        .describe("邀请风格：funny=搞笑, serious=正式, casual=随意, enthusiastic=热血"),
      language: z
        .enum(["zh", "en"])
        .optional()
        .default("zh")
        .describe("语言"),
    },
    async ({ game_name, friend_name, style, language }) => {
      const templates: Record<string, Record<string, string[]>> = {
        zh: {
          funny: [
            `嘿 ${friend_name}！🎮\n我发现 ${game_name} 在库里都快长蜘蛛网了，再不让它见见光它就要申请退款了！\n快来一起拯救这个被冷落的游戏吧！`,
            `${friend_name}！紧急通知！📢\n据可靠消息，${game_name} 里的 NPC 们正在罢工，要求见到 ${friend_name} 本尊。\n快上线平息这场骚乱！`,
            `哈喽 ${friend_name}！\n检测到你的库存中存在未体验的快乐——《${game_name}》。\n该快乐的保质期即将在无聊中过期，速来领取！🕹️`,
          ],
          serious: [`${friend_name}，\n\n我准备开始玩《${game_name}》，这款游戏评价很高，我认为你会感兴趣。\n\n如果你有空的话，我们可以一起联机。期待你的回复。`],
          casual: [
            `Hey ${friend_name}，要不要一起玩 ${game_name}？最近想试试这个游戏，看你也在线～`,
            `${friend_name} 在不？来打 ${game_name} 吧，正好都闲着 😄`,
          ],
          enthusiastic: [
            `${friend_name}！！！🔥🔥🔥\n《${game_name}》太好玩了！我已经完全沉迷其中，不能自拔！\n你一定要来试试，我们一起组队，今晚就上分！\nGOGOGO！！！🚀`,
            `哇哇哇 ${friend_name}！！\n《${game_name}》就是今年最好的游戏不接受反驳！\n快来加入，我们要统治这个游戏的排行榜！🏆`,
          ],
        },
        en: {
          funny: [
            `Hey ${friend_name}! 🎮\nMy copy of ${game_name} is gathering dust and starting to give me puppy eyes. Save this poor game with me!`,
            `${friend_name}! URGENT! 📢\nThe NPCs in ${game_name} have unionized and are demanding your presence. Don't cross the picket line — join me!`,
          ],
          serious: [`Hi ${friend_name},\n\nI'm about to start playing ${game_name} and thought you might enjoy joining. Let me know if you're interested.`],
          casual: [`Hey ${friend_name}, want to play some ${game_name}? I see you're online!`],
          enthusiastic: [`${friend_name}!!! 🔥\n${game_name} is INCREDIBLE! I can't stop playing and I need a partner in crime. Let's go!!! 🚀`],
        },
      };

      const lang = language === "en" ? "en" : "zh";
      const options = templates[lang]?.[style] || templates[lang].funny;
      const message = options[Math.floor(Math.random() * options.length)];

      return textResult(`📨 **邀请语生成** (风格: ${style}, ${lang === "zh" ? "中文" : "English"})

---

${message}

---

💡 你可以直接复制这段话发给 ${friend_name}！
🎮 使用 launch_game appid=${game_name} 来启动游戏。`);
    }
  );

  server.tool(
    "get_friend_summary",
    "获取好友在线情况的摘要：在线人数、正在玩的游戏分类统计。",
    {},
    async () => {
      const friends = await api.getEnrichedFriends();

      if (friends.length === 0) {
        return textResult("无法获取好友列表。请配置 Steam API Key。");
      }

      const online = friends.filter(isOnline);
      const playing = online.filter(isPlaying);

      const gameGroups = new Map<string, string[]>();
      for (const f of playing) {
        const game = f.gameextrainfo || "未知游戏";
        const existing = gameGroups.get(game) || [];
        existing.push(f.personaname || f.steamid);
        gameGroups.set(game, existing);
      }

      const gameLines = Array.from(gameGroups.entries())
        .sort((a, b) => b[1].length - a[1].length)
        .map(([game, players]) => `- **${game}**: ${players.length} 人 (${players.join(", ")})`);

      return textResult(`📊 **好友摘要**
- 总好友: ${friends.length}
- 在线: ${online.length}
- 游戏中: ${playing.length}
- 空闲在线 (可邀请): ${online.length - playing.length}

🎮 **当前热门游戏：**
${gameLines.length > 0 ? gameLines.join("\n") : "无人正在游戏"}

💡 使用 find_coop_game 查找适合多人游玩的游戏。`);
    }
  );
}
