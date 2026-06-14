"""用 Ollama 生成工具调用训练数据 — 扩充到 50+ 条"""
import json, time, urllib.request, os

OLLAMA_URL = "http://127.0.0.1:11434"

# MCP 工具列表及其描述
TOOLS = [
    {"name": "list_games", "desc": "列出 Steam 游戏库，可按游戏时长/名称/最近游玩排序", "args": "sort_by=playtime/name/recent, installed_only=true/false, limit=数量"},
    {"name": "get_achievements", "desc": "查询某游戏的成就进度", "args": "appid=游戏ID"},
    {"name": "get_friend_list", "desc": "获取 Steam 好友列表及在线状态", "args": "无"},
    {"name": "get_game_details", "desc": "获取游戏详细信息：价格、评价、配置要求等", "args": "appid=游戏ID, country=国家, language=语言"},
    {"name": "search_store", "desc": "在 Steam 商店搜索游戏", "args": "query=搜索词, country=CN, language=zh-CN"},
    {"name": "get_deals", "desc": "获取 Steam 当前促销游戏列表", "args": "country=CN, language=zh-CN"},
    {"name": "list_installed_games", "desc": "列出本地已安装的游戏", "args": "无"},
    {"name": "get_inventory", "desc": "查看 Steam 库存物品", "args": "appid=游戏ID, context_id=2"},
    {"name": "get_screenshots", "desc": "查看游戏截图", "args": "appid=游戏ID, limit=数量"},
    {"name": "find_game_for_session", "desc": "根据空闲时间推荐游戏", "args": "available_minutes=空闲分钟数, prefer_installed=true/false"},
]

# 每个工具生成多条不同场景的对话
SCENARIOS = [
    ("想了解库存", "get_inventory", 730),    # CS2
    ("搜恐怖游戏", "search_store", "horror survival"),
    ("搜开放世界", "search_store", "open world RPG"),
    ("查双人成行成就", "get_achievements", 1426210),
    ("查星露谷成就", "get_achievements", 413150),
    ("看巫师3详情", "get_game_details", 292030),
    ("看艾尔登法环详情", "get_game_details", 1245620),
    ("看CS2库存", "get_inventory", 730),
    ("20分钟游戏推荐", "find_game_for_session", 20),
    ("1小时游戏推荐", "find_game_for_session", 60),
    ("查已安装游戏", "list_installed_games", None),
    ("查看Dota2截图", "get_screenshots", 570),
    ("今天Steam促销", "get_deals", None),
    ("好友在玩什么", "get_friend_list", None),
    ("库里RPG游戏", "list_games", "RPG"),
    ("库里联机游戏", "list_games", "multiplayer"),
    ("搜种田游戏", "search_store", "farming sim cozy"),
    ("搜赛博朋克", "search_store", "cyberpunk"),
    ("查艾迪芬奇的记忆成就", "get_achievements", 501300),
    ("查星战绝地详情", "get_game_details", 1172380),
    ("15分钟游戏推荐", "find_game_for_session", 15),
    ("查泰拉瑞亚成就", "get_achievements", 105600),
    ("搜像素游戏", "search_store", "pixel art indie"),
    ("打折策略游戏", "get_deals", "strategy"),
    ("好友数最多的", "get_friend_list", None),
    ("库里最近玩的", "list_games", "recent"),
    ("查博德之门3详情", "get_game_details", 1086940),
    ("搜魂系游戏", "search_store", "souls-like challenging"),
    ("库里按名字排序", "list_games", "name"),
    ("45分钟游戏推荐", "find_game_for_session", 45),
]

def generate_one(tool_name: str, tool_desc: str, tool_args: str, scenario: str) -> dict | None:
    prompt = f"""你是 Steam 游戏助手「游戏精灵」。请模拟一段带工具调用的对话。

场景：用户说"{scenario}"
你应该调用工具：{tool_name}（{tool_desc}）
工具参数示例：{tool_args}

严格按照以下 JSON 格式输出（不要输出其他内容）：
{{"messages":[
  {{"role":"user","content":"用户的提问"}},
  {{"role":"assistant","content":"","tool_calls":[{{"id":"call_1","type":"function","function":{{"name":"TOOL_NAME","arguments":{{ARGUMENTS}}}}}}]}},
  {{"role":"tool","content":"工具返回的数据（编造合理的数据，格式参考真实Steam API返回）","tool_call_id":"call_1"}},
  {{"role":"assistant","content":"基于工具返回数据，用游戏精灵风格回复用户。热情幽默，带emoji，中文"}}
]}}

注意：
1. 把 TOOL_NAME 替换为 {tool_name}
2. 把 ARGUMENTS 替换为合适的参数（JSON格式）
3. tool.content 要编造合理的Steam数据
4. 最后一条assistant回复要有游戏精灵风格
"""

    payload = json.dumps({
        "model": "qwen3:8b",
        "messages": [{"role": "user", "content": prompt}],
        "stream": False, "temperature": 0.9,
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/chat", data=payload,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            content = json.loads(resp.read()).get("message", {}).get("content", "")
            start = content.find("{")
            end = content.rfind("}")
            if start == -1 or end == -1:
                return None
            data = json.loads(content[start:end+1])
            if "messages" in data and len(data["messages"]) >= 3:
                return data
    except Exception as e:
        print(f"  FAIL: {e}")
    return None


def main():
    output_file = "training_data/game_assistant_v3.jsonl"

    # Load existing v2 data
    existing = []
    v2_path = "training_data/game_assistant_v2.jsonl"
    if os.path.exists(v2_path):
        with open(v2_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    existing.append(line.strip())

    tool_count = sum(1 for l in existing if '"tool_call_id"' in l) // 2
    print(f"已有 {len(existing)} 条（含 {tool_count} 条工具调用）")
    print(f"目标: 额外生成 {len(SCENARIOS)} 条工具调用数据")
    print()

    generated = 0
    with open(output_file, "w", encoding="utf-8") as f:
        # Write existing
        for line in existing:
            f.write(line + "\n")

        for scenario, tool_name, arg_or_id in SCENARIOS:
            tool_desc = next((t["desc"] for t in TOOLS if t["name"] == tool_name), "")
            if isinstance(arg_or_id, int):
                tool_args = f'{{"appid": {arg_or_id}}}'
            elif isinstance(arg_or_id, str) and arg_or_id:
                tool_args = f'{{"query": "{arg_or_id}"}}' if tool_name == "search_store" else f'{{"sort_by": "{arg_or_id}"}}'
            else:
                tool_args = "{}"

            print(f"[{generated+1}/{len(SCENARIOS)}] {tool_name}: {scenario}...", end=" ")
            result = generate_one(tool_name, tool_desc, tool_args, scenario)
            if result:
                f.write(json.dumps(result, ensure_ascii=False) + "\n")
                f.flush()
                generated += 1
                print("OK")
            else:
                print("SKIP")
            time.sleep(1.5)

    # Count final
    final = []
    with open(output_file, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                final.append(line.strip())
    tool_total = sum(1 for l in final if '"tool_call_id"' in l) // 2
    print(f"\n完成: {len(final)} 条（含 {tool_total} 条工具调用）→ {output_file}")


if __name__ == "__main__":
    main()
