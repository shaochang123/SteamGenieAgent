"""
利用已有 Ollama 模型批量生成更多游戏助手训练数据
运行前确保 Ollama 正在运行且 qwen3:8b 已拉取
"""

import json
import os
import time

# ============================================================
# 配置
# ============================================================

OUTPUT_FILE = "training_data/game_assistant_data.jsonl"
OLLAMA_MODEL = "qwen3:8b"           # 用来生成数据的模型
TARGET_COUNT = 200                  # 目标样本数
OLLAMA_URL = "http://127.0.0.1:11434"

# 种子话题 — 覆盖游戏助手各种场景
SEED_TOPICS = [
    "推荐类似《巫师3》的RPG游戏",
    "恐怖游戏推荐，不要太吓人的",
    "适合情侣一起玩的游戏",
    "Steam评分最高但画质差的游戏",
    "横版动作游戏推荐",
    "适合上班摸鱼玩的游戏",
    "策略游戏推荐，文明6那样的",
    "独立游戏推荐，最近有什么好的",
    "FPS游戏推荐，不要氪金的",
    "像素游戏推荐",
    "今年最值得期待的游戏",
    "Steam打折规律是什么",
    "怎么判断一个EA阶段的游戏值不值得买",
    "游戏玩不过来了怎么办",
    "推荐些音乐好听的游戏",
    "卡牌游戏推荐",
    "剧情向单机游戏推荐",
    "适合老年人玩的游戏",
    "有什么游戏适合和孩子一起玩",
    "性价比最高的3A游戏",
    "Steam退款流程是什么",
    "怎么在Steam找到隐藏的好游戏",
    "推荐些免费但是好玩的游戏",
    "游戏画面设置怎么调最流畅",
    "怎么清理Steam下载缓存",
    "Xbox手柄和PS手柄哪个适合PC游戏",
    "推荐的游戏录制软件",
    "Steam创意工坊是什么",
    "游戏存档怎么备份到云端",
    "怎么加入Steam测试版",
    "推荐的赛车游戏",
    "生存类游戏推荐",
    "roguelike游戏推荐",
    "解谜游戏推荐",
    "养成类游戏推荐",
    "沙盒建造游戏推荐",
    "ARPG和传统RPG有什么区别",
    "推荐些适合直播的游戏",
    "国产独立游戏推荐",
    "动作冒险游戏推荐",
    "多结局游戏推荐",
    "赛博朋克风格游戏推荐",
    "有深刻哲学主题的游戏",
    "游戏里的彩蛋分享",
    "画风治愈的游戏推荐",
    "玩到停不下来的休闲游戏",
    "有宠物系统的游戏推荐",
    "战斗系统做得好的游戏",
    "世界观最宏大的游戏",
    "游戏里的搞笑时刻",
]

# ============================================================


def load_existing(filepath: str) -> list[dict]:
    """加载已有数据"""
    if not os.path.exists(filepath):
        return []
    data = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    data.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return data


def generate_one(topic: str, angle: str = "") -> dict | None:
    """用 Ollama 生成一条训练数据"""
    angle_hint = f"\n这次请换一个完全不同的切入角度（{angle}）来提问和回答。" if angle else ""

    prompt = f"""你是一个资深的Steam游戏助手，名叫「游戏精灵」，说话风格幽默风趣，像资深玩家聊天。

现在请模拟一段你和玩家的对话，话题是："{topic}"{angle_hint}

要求：
1. 玩家提问一句话（role: user），必须和话题相关但换个问法，不要和之前的雷同
2. 你回答一段话（role: assistant），要求：
   - 语气热情幽默，像朋友聊天
   - 加入emoji
   - 给出具体游戏推荐或建议
   - 100-250字左右
3. 输出格式为严格的JSON（不要有其他内容）：
{{"messages":[{{"role":"user","content":"玩家的问题"}},{{"role":"assistant","content":"你的回答"}}]}}
"""

    import urllib.request

    payload = json.dumps({
        "model": OLLAMA_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "temperature": 0.95,
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            content = result.get("message", {}).get("content", "")

            start = content.find("{")
            end = content.rfind("}")
            if start == -1 or end == -1:
                print(f"  [WARN] 无法解析 JSON，跳过")
                return None

            json_str = content[start:end+1]
            data = json.loads(json_str)

            if "messages" in data and len(data["messages"]) == 2:
                return data
            print(f"  [WARN]  格式不正确，跳过")
            return None

    except Exception as e:
        print(f"  [ERR] 请求失败: {e}")
        return None


# 每轮用不同的生成角度，让同话题产出多样化的对话
ANGLES = [
    "从新手入门的视角",
    "从硬核老玩家的视角",
    "从预算有限的穷玩党视角",
    "从时间碎片化的上班族视角",
    "从喜欢独立游戏的文艺玩家视角",
    "从只玩3A大作的画面党视角",
    "从怀旧老游戏的复古玩家视角",
    "从喜欢联机的社交玩家视角",
    "从追求速通的技术流视角",
    "从只看剧情的休闲党视角",
]


def main():
    print("== 训练数据批量生成器（多轮循环版） ==")
    print(f"   目标: {TARGET_COUNT} 条")
    print(f"   当前模型: {OLLAMA_MODEL}")
    print(f"   种子话题: {len(SEED_TOPICS)} 个")
    print(f"   每轮角度: {len(ANGLES)} 种")
    print()

    # 加载已有数据
    existing = load_existing(OUTPUT_FILE)
    total = len(existing)
    print(f"   已有数据: {total} 条")
    print()

    if total >= TARGET_COUNT:
        print("[OK] 数据已达标，无需扩充")
        return

    round_num = 0
    with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
        while total < TARGET_COUNT:
            round_num += 1
            angle = ANGLES[(round_num - 1) % len(ANGLES)]
            print(f"--- 第 {round_num} 轮（角度: {angle}）---")

            generated_this_round = 0
            for topic in SEED_TOPICS:
                if total >= TARGET_COUNT:
                    break

                total += 1
                print(f"  [{total}/{TARGET_COUNT}] {topic[:40]}...")

                result = generate_one(topic, angle)

                if result:
                    f.write(json.dumps(result, ensure_ascii=False) + "\n")
                    f.flush()
                    generated_this_round += 1
                else:
                    total -= 1  # 生成失败不计入

                time.sleep(1.5)

            print(f"  本轮成功: {generated_this_round}/{len(SEED_TOPICS)}")
            print()

            if generated_this_round == 0:
                print("[WARN] 本轮全部失败，停止生成。检查 Ollama 是否正常运行")
                break

    final_count = len(load_existing(OUTPUT_FILE))
    print(f"[OK] 完成！共 {final_count} 条训练数据 -> {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
