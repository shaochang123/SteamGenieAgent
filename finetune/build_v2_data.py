"""生成 v2 训练数据：200 条聊天 + 工具调用示例"""
import json, os

TOOL_EXAMPLES = [
    # --- list_games ---
    {"messages": [
        {"role": "user", "content": "我玩的什么游戏时长最多"},
        {"role": "assistant", "content": "好的，让我查一下你的 Steam 游戏库！🎮",
         "tool_calls": [{"id": "call_1", "type": "function",
            "function": {"name": "list_games", "arguments": {"sort_by": "playtime", "limit": 5}}}]},
        {"role": "tool", "content": "1. Portal - 3h | 近两周 0h\n2. Left 4 Dead 2 - 2h | 近两周 1h\n3. Dota 2 - 1.5h | 近两周 0h",
         "tool_call_id": "call_1"},
        {"role": "assistant", "content": "你的游戏时长冠军是 **Portal**（3小时）！🎉 传送门虽然短但经典啊。第二是求生之路2（2h），最近还有在玩哦～"}
    ]},
    {"messages": [
        {"role": "user", "content": "列出我库里所有游戏"},
        {"role": "assistant", "content": "",
         "tool_calls": [{"id": "call_2", "type": "function",
            "function": {"name": "list_games", "arguments": {"sort_by": "name", "limit": 50}}}]},
        {"role": "tool", "content": "共 41 款游戏\n1. Portal (AppID: 400)\n2. Left 4 Dead 2 (AppID: 550)\n3. Dota 2 (AppID: 570)",
         "tool_call_id": "call_2"},
        {"role": "assistant", "content": "你的库里一共有 41 款游戏！📚 Portal、求生之路2 和 Dota 2 排前三。想看哪款的详情？"}
    ]},
    # --- get_friend_list ---
    {"messages": [
        {"role": "user", "content": "我的 Steam 好友在线情况"},
        {"role": "assistant", "content": "",
         "tool_calls": [{"id": "call_3", "type": "function",
            "function": {"name": "get_friend_list", "arguments": {}}}]},
        {"role": "tool", "content": "好友列表 (共 25 人):\n1. PlayerOne - 在线\n2. GameMaster - 游戏中 (CS2)\n3. AFK_King - 离开",
         "tool_call_id": "call_3"},
        {"role": "assistant", "content": "你的 25 个好友中：\n🟢 PlayerOne 在线\n🎮 GameMaster 正在打 CS2\n🟡 AFK_King 挂机中\n\n想找人开黑吗？😏"}
    ]},
    # --- get_achievements ---
    {"messages": [
        {"role": "user", "content": "Portal 我解锁了多少成就"},
        {"role": "assistant", "content": "",
         "tool_calls": [{"id": "call_4", "type": "function",
            "function": {"name": "get_achievements", "arguments": {"appid": 400}}}]},
        {"role": "tool", "content": "成就进度: 5/15 (33%)\n最近解锁: Lab Rat - 获取完全充能的引力枪",
         "tool_call_id": "call_4"},
        {"role": "assistant", "content": "Portal 你解了 5/15 个成就（33%）。🎯 还有不少隐藏成就等着你去发现呢！"}
    ]},
    # --- search_store ---
    {"messages": [
        {"role": "user", "content": "有没有类似黑帝斯的游戏推荐"},
        {"role": "assistant", "content": "",
         "tool_calls": [{"id": "call_5", "type": "function",
            "function": {"name": "search_store", "arguments": {"query": "Hades roguelike action", "country": "CN", "language": "zh-CN"}}}]},
        {"role": "tool", "content": "搜索 'Hades roguelike action':\n1. Dead Cells (AppID: 588650)\n2. Curse of the Dead Gods (AppID: 1123770)\n3. Have a Nice Death (AppID: 1740720)",
         "tool_call_id": "call_5"},
        {"role": "assistant", "content": "黑帝斯粉丝看过来！🔥 这几款你绝对会爱：\n1. **死亡细胞** — 爽快肉鸽+横版动作\n2. **诅咒魔神的命运** — 暗黑画风+诅咒系统\n3. **好好去死** — 死神打工记，画风超有趣\n\n都是 Steam 90%+ 好评！"}
    ]},
    # --- get_deals ---
    {"messages": [
        {"role": "user", "content": "Steam 现在有什么打折游戏"},
        {"role": "assistant", "content": "",
         "tool_calls": [{"id": "call_6", "type": "function",
            "function": {"name": "get_deals", "arguments": {"country": "CN", "language": "zh-CN"}}}]},
        {"role": "tool", "content": "特惠促销:\n1. Portal 2 - ¥7 (-90%)\n2. The Witcher 3 - ¥38 (-70%)\n3. Slay the Spire - ¥24 (-60%)",
         "tool_call_id": "call_6"},
        {"role": "assistant", "content": "现在的折扣力度很可以！🤑\n🎯 Portal 2 只要 ¥7（-90%）— 白送级别\n⚔️ 巫师3 ¥38（-70%）— 几百小时的内容\n🃏 杀戮尖塔 ¥24（-60%）— 肉鸽卡牌天花板\n\n看上哪个了？"}
    ]},
    # --- get_game_details ---
    {"messages": [
        {"role": "user", "content": "Portal 2 现在卖多少钱"},
        {"role": "assistant", "content": "",
         "tool_calls": [{"id": "call_7", "type": "function",
            "function": {"name": "get_game_details", "arguments": {"appid": 620, "country": "CN", "language": "zh-CN"}}}]},
        {"role": "tool", "content": "Portal 2 (AppID: 620)\n价格: ¥42\nMetacritic: 95\n发行日期: 2011-04-19\n类型: 动作, 冒险",
         "tool_call_id": "call_7"},
        {"role": "assistant", "content": "Portal 2 目前 ¥42 💰 Metacritic 95 分神作！虽然老游戏但放到今天依然是解谜天花板。打折时经常降到 ¥7，建议蹲一下～"}
    ]},
    # --- list_installed_games ---
    {"messages": [
        {"role": "user", "content": "我电脑上装了哪些游戏"},
        {"role": "assistant", "content": "",
         "tool_calls": [{"id": "call_8", "type": "function",
            "function": {"name": "list_installed_games", "arguments": {}}}]},
        {"role": "tool", "content": "已安装游戏:\n1. Left 4 Dead 2 (AppID: 550) - D:/SteamLibrary\n2. Portal (AppID: 400) - C:/Program Files (x86)/Steam",
         "tool_call_id": "call_8"},
        {"role": "assistant", "content": "你电脑上装了 2 款游戏：\n📀 Left 4 Dead 2 — D 盘\n📀 Portal — C 盘 Steam 默认目录\n\n磁盘空间还够吗？😅"}
    ]},
    # --- get_inventory ---
    {"messages": [
        {"role": "user", "content": "我的 Steam 库存里有什么"},
        {"role": "assistant", "content": "",
         "tool_calls": [{"id": "call_9", "type": "function",
            "function": {"name": "get_inventory", "arguments": {"appid": 730, "context_id": 2}}}]},
        {"role": "tool", "content": "CS2 库存 (共 15 件):\n1. AK-47 | 红线 (久经沙场) - ¥89\n2. 武器箱 x3\n3. M4A1-S | 守护者 (略有磨损) - ¥12",
         "tool_call_id": "call_9"},
        {"role": "assistant", "content": "你的 CS2 库存有 15 件物品：\n🔫 AK-47 | 红线 — ¥89\n📦 武器箱 x3\n🎯 M4A1-S | 守护者 — ¥12\n\n有想出手的东西吗？我帮你查价格！"}
    ]},
    # --- find_game_for_session ---
    {"messages": [
        {"role": "user", "content": "我有半小时空闲，推荐玩什么"},
        {"role": "assistant", "content": "",
         "tool_calls": [{"id": "call_10", "type": "function",
            "function": {"name": "find_game_for_session", "arguments": {"available_minutes": 30, "prefer_installed": True}}}]},
        {"role": "tool", "content": "推荐:\n1. Portal (已安装, 通关 3h) 综合 85/100\n2. Left 4 Dead 2 (已安装, 战役 15-30min/章) 综合 80/100",
         "tool_call_id": "call_10"},
        {"role": "assistant", "content": "半小时的话我推荐这两个：\n⭐ **Portal** — 一个关卡刚好 15-20 分钟，解谜成就感拉满\n🌟 **Left 4 Dead 2** — 打一把战役刚好半小时，爽完就收\n\n两个都已安装，直接开玩！🎮"}
    ]},
    # --- 对话中不需要工具 ---
    {"messages": [
        {"role": "user", "content": "空洞骑士值得买吗"},
        {"role": "assistant", "content": "空洞骑士绝对是 2D 动作游戏的巅峰之一！🎮\n\n值得买的理由：\n🪲 手绘美术风格 — 每一帧都是壁纸级\n⚔️ 战斗系统 — 简洁但深度十足，越打越爽\n🏰 地图设计 — 环环相扣的探索体验\n💀 难度 — 硬核但公平，死 100 次也不会想删游戏\n📜 剧情 — 碎片化叙事，每发现一个秘密都充满惊喜\n\nSteam 好评率 97%，史低 ¥24。你玩过黑魂或银河战士吗？喜欢那种难但公平的游戏直接闭眼入！"}
    ]},
    {"messages": [
        {"role": "user", "content": "帮我看看有没有双人游戏推荐"},
        {"role": "assistant", "content": "双人游戏的快乐是单机给不了的！不过在给你安利之前，先了解一下你的需求～\n\n你们喜欢哪种类型？合作解谜、生存建造、还是动作射击？告诉我更多，我帮你精准推荐！🎯"}
    ]},
]

# ------------------------------------------------
os.makedirs("training_data", exist_ok=True)

# Read existing chat data
existing = []
existing_path = "training_data/game_assistant_data.jsonl"
if os.path.exists(existing_path):
    with open(existing_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                existing.append(line)

# Write v2 file
v2_path = "training_data/game_assistant_v2.jsonl"
with open(v2_path, "w", encoding="utf-8") as f:
    for line in existing:
        f.write(line + "\n")
    for ex in TOOL_EXAMPLES:
        f.write(json.dumps(ex, ensure_ascii=False) + "\n")

print(f"game_assistant_v2.jsonl: {len(existing) + len(TOOL_EXAMPLES)} 条")
print(f"  聊天数据: {len(existing)} 条")
print(f"  工具调用: {len(TOOL_EXAMPLES)} 条")
