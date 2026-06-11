#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Collect beginner-friendly GitHub projects for AI video and creator workflows.

This script uses only the Python standard library. It searches GitHub, scores
repositories with simple transparent rules, and writes the result into
index.html so the project can be published as a single GitHub Pages file.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
INDEX_PATH = ROOT / "index.html"

SEARCH_TERMS = [
    ("AI video", "视频生成"),
    ("video generation", "视频生成"),
    ("text to video", "视频生成"),
    ("image to video", "视频生成"),
    ("anime video", "动漫视频"),
    ("digital human", "数字人"),
    ("talking avatar", "数字人"),
    ("TTS", "配音"),
    ("subtitle", "字幕剪辑"),
    ("auto video", "短视频自动化"),
    ("ffmpeg", "字幕剪辑"),
]

CATEGORY_KEYWORDS = [
    ("动漫视频", ["anime", "animation", "animate", "cartoon", "manga", "toon"]),
    ("数字人", ["digital human", "avatar", "talking head", "talking avatar", "lip sync", "lipsync", "face"]),
    ("配音", ["tts", "text to speech", "voice", "speech", "dubbing", "audio", "narration"]),
    ("字幕剪辑", ["subtitle", "caption", "transcribe", "ffmpeg", "edit", "clip", "video editor"]),
    ("短视频自动化", ["short video", "auto video", "automated video", "social media", "reels", "tiktok", "youtube shorts"]),
    ("视频生成", ["video generation", "text to video", "image to video", "ai video", "generate video", "diffusion"]),
]

HARD_KEYWORDS = [
    "cuda",
    "gpu",
    "training",
    "train your own",
    "distributed",
    "kubernetes",
    "compile",
]

COST_KEYWORDS = [
    "api key",
    "openai",
    "elevenlabs",
    "azure",
    "replicate",
    "runway",
    "paid",
    "subscription",
]

BEGINNER_HINTS = [
    "webui",
    "web ui",
    "gui",
    "demo",
    "colab",
    "docker",
    "one-click",
    "easy",
    "simple",
    "windows",
]

LOW_HARDWARE_HINTS = [
    "web",
    "browser",
    "online",
    "cloud",
    "api",
    "prompt",
    "prompts",
    "awesome",
    "collection",
    "guide",
    "tutorial",
    "no gpu",
    "cpu",
    "windows",
]

HIGH_HARDWARE_KEYWORDS = [
    "cuda",
    "gpu",
    "nvidia",
    "vram",
    "comfyui",
    "stable diffusion",
    "diffusion model",
    "local model",
    "training",
    "train your own",
    "4090",
    "pytorch",
]

BAD_KEYWORDS = [
    "crypto",
    "nft",
    "porn",
    "adult",
    "casino",
    "betting",
]

DATA_PATTERN = re.compile(
    r'(<script id="project-data" type="application/json">\s*)(.*?)(\s*</script>)',
    re.DOTALL,
)


def github_request(url: str) -> dict[str, Any]:
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "ai-video-github-radar",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print(f"GitHub API error {exc.code}: {body[:300]}", file=sys.stderr)
        return {"items": []}
    except Exception as exc:
        print(f"Request failed: {exc}", file=sys.stderr)
        return {"items": []}


def search_repositories(term: str) -> list[dict[str, Any]]:
    cutoff = (dt.datetime.now(dt.UTC) - dt.timedelta(days=540)).date().isoformat()
    query = f'"{term}" in:name,description,readme pushed:>={cutoff} archived:false'
    params = urllib.parse.urlencode(
        {
            "q": query,
            "sort": "updated",
            "order": "desc",
            "per_page": "20",
        }
    )
    url = f"https://api.github.com/search/repositories?{params}"
    data = github_request(url)
    return data.get("items", [])


def clean_text(value: str | None, max_length: int = 180) -> str:
    value = (value or "").strip()
    value = re.sub(r"\s+", " ", value)
    if len(value) > max_length:
        return value[: max_length - 1].rstrip() + "…"
    return value


def text_blob(repo: dict[str, Any]) -> str:
    parts = [
        repo.get("name", ""),
        repo.get("full_name", ""),
        repo.get("description", ""),
        repo.get("language", ""),
        repo.get("homepage", ""),
        " ".join(repo.get("topics", []) or []),
    ]
    return " ".join(str(part) for part in parts if part).lower()


def infer_category(repo: dict[str, Any], fallback: str) -> str:
    blob = text_blob(repo)
    for category, words in CATEGORY_KEYWORDS:
        if any(word in blob for word in words):
            return category
    return fallback


def estimate_cost(repo: dict[str, Any]) -> str:
    blob = text_blob(repo)
    license_info = repo.get("license") or {}
    has_license = bool(license_info.get("spdx_id") and license_info.get("spdx_id") != "NOASSERTION")
    if any(word in blob for word in COST_KEYWORDS):
        return "可能需要 API 费用"
    if any(word in blob for word in ["cuda", "gpu", "comfyui", "diffusion", "local model"]):
        return "可能需要显卡"
    if has_license:
        return "免费开源优先"
    return "需查看许可证"


def estimate_hardware(repo: dict[str, Any]) -> str:
    blob = text_blob(repo)
    low_hint = any(word in blob for word in LOW_HARDWARE_HINTS)
    high_hint = any(word in blob for word in HIGH_HARDWARE_KEYWORDS)
    if high_hint and not low_hint:
        return "高：可能需要显卡，老笔记本暂不推荐"
    if any(word in blob for word in ["docker", "python", "cli", "command line", "ffmpeg"]):
        return "中：普通电脑可先看教程，运行可能要折腾"
    return "低：老笔记本也适合先学习"


def estimate_difficulty(repo: dict[str, Any]) -> str:
    blob = text_blob(repo)
    stars = int(repo.get("stargazers_count") or 0)
    if any(word in blob for word in HARD_KEYWORDS):
        return "暂时偏难"
    if stars >= 500 and any(word in blob for word in BEGINNER_HINTS):
        return "小白可试"
    if any(word in blob for word in ["docker", "python", "cli", "command line"]):
        return "需要一点命令行"
    return "小白可先看"


def chinese_summary(repo: dict[str, Any], category: str, hardware: str) -> str:
    blob = text_blob(repo)
    if "prompt" in blob and any(word in blob for word in ["video", "seedance", "anime", "image"]):
        return "这是 AI 视频/图片提示词案例库，不吃电脑配置，适合先学习别人怎么写提示词。"
    if "awesome" in blob or "collection" in blob:
        return "这是资料合集类项目，主要用来找工具和教程，不需要安装，适合收藏慢慢看。"
    if category == "视频生成":
        return "这是 AI 视频生成相关项目，能帮助你了解文生视频、图生视频或自动生成视频的工具。"
    if category == "动漫视频":
        return "这是动漫视频或动画生成相关项目，适合学习 AI 动漫、角色动画和提示词案例。"
    if category == "数字人":
        return "这是数字人/虚拟人相关项目，常用于做会说话的头像、口型同步或虚拟主播。"
    if category == "配音":
        return "这是配音或语音相关项目，可能用于文字转语音、自动配音、声音处理或口播内容。"
    if category == "字幕剪辑":
        return "这是字幕、剪辑或视频处理工具，和自媒体实操更接近，适合做字幕、转写、剪辑辅助。"
    if category == "短视频自动化":
        return "这是短视频自动化工具，可能帮你把文字、图片、配音和素材组合成视频流程。"
    if hardware.startswith("低"):
        return "这是轻量级 AI 自媒体相关项目，适合先收藏、阅读说明和尝试在线演示。"
    return "这是 AI 自媒体相关项目，建议先看 README 和演示，不急着安装到电脑。"


def score_repo(repo: dict[str, Any], category: str) -> int:
    blob = text_blob(repo)
    score = 0
    stars = int(repo.get("stargazers_count") or 0)
    watchers = int(repo.get("watchers_count") or 0)
    forks = int(repo.get("forks_count") or 0)
    open_issues = int(repo.get("open_issues_count") or 0)

    score += min(stars // 50, 30)
    score += min(forks // 30, 10)
    score += min(watchers // 100, 5)
    score += 12 if repo.get("license") else 0
    score += 8 if repo.get("homepage") else 0
    score += 8 if repo.get("topics") else 0
    score += 10 if any(word in blob for word in BEGINNER_HINTS) else 0
    score += 10 if category in ["字幕剪辑", "配音", "短视频自动化"] else 0
    hardware = estimate_hardware(repo)
    if hardware.startswith("低"):
        score += 20
    elif hardware.startswith("中"):
        score += 5
    else:
        score -= 35

    pushed = repo.get("pushed_at") or ""
    try:
        pushed_date = dt.datetime.fromisoformat(pushed.replace("Z", "+00:00"))
        days_old = (dt.datetime.now(dt.UTC) - pushed_date).days
        if days_old <= 30:
            score += 15
        elif days_old <= 180:
            score += 10
        elif days_old <= 540:
            score += 4
    except ValueError:
        pass

    if open_issues > stars and stars < 300:
        score -= 8
    if any(word in blob for word in HARD_KEYWORDS):
        score -= 12
    if any(word in blob for word in BAD_KEYWORDS):
        score -= 40
    if not clean_text(repo.get("description")):
        score -= 30

    return max(score, 0)


def recommendation_reason(repo: dict[str, Any], category: str, cost: str, difficulty: str) -> str:
    stars = int(repo.get("stargazers_count") or 0)
    reasons = []
    if stars >= 1000:
        reasons.append("关注度高")
    elif stars >= 100:
        reasons.append("有一定使用基础")
    if repo.get("license"):
        reasons.append("开源许可证清楚")
    if repo.get("homepage"):
        reasons.append("有演示或主页")
    if difficulty in ["小白可试", "小白可先看"]:
        reasons.append("适合先了解")
    if "API" not in cost and "显卡" not in cost:
        reasons.append("成本门槛较低")
    if category in ["字幕剪辑", "配音", "短视频自动化"]:
        reasons.append("更接近自媒体实操")
    if estimate_hardware(repo).startswith("低"):
        reasons.append("老笔记本友好")
    return "、".join(reasons[:3]) or "方向相关，适合收藏观察"


def first_step(repo: dict[str, Any], difficulty: str, hardware: str) -> str:
    if hardware.startswith("低"):
        return "先打开项目页面，看 README、截图或在线演示，判断是不是你今晚想学的方向。"
    if hardware.startswith("高"):
        return "先只收藏和看效果，不建议在老笔记本上安装运行。"
    if difficulty == "小白可试":
        return "先打开 GitHub 页面，找 README 里的 Demo、Web UI 或安装说明。"
    if difficulty == "需要一点命令行":
        return "先只看 README 的效果图和示例命令，暂时不要急着安装。"
    if difficulty == "暂时偏难":
        return "先收藏，今晚只看项目截图和介绍，了解它能做什么。"
    return "先阅读项目简介和 README，判断它是不是你想学的方向。"


def normalize_repo(repo: dict[str, Any], fallback_category: str) -> dict[str, Any] | None:
    description = clean_text(repo.get("description"))
    if not description:
        return None

    blob = text_blob(repo)
    if any(word in blob for word in BAD_KEYWORDS):
        return None

    category = infer_category(repo, fallback_category)
    cost = estimate_cost(repo)
    difficulty = estimate_difficulty(repo)
    hardware = estimate_hardware(repo)
    score = score_repo(repo, category)

    if hardware.startswith("高"):
        return None

    if score < 15:
        return None

    return {
        "name": repo.get("full_name") or repo.get("name"),
        "url": repo.get("html_url"),
        "description": description,
        "stars": int(repo.get("stargazers_count") or 0),
        "language": repo.get("language") or "未知",
        "updated_at": (repo.get("pushed_at") or repo.get("updated_at") or "")[:10],
        "category": category,
        "difficulty": difficulty,
        "hardware": hardware,
        "chinese_summary": chinese_summary(repo, category, hardware),
        "cost": cost,
        "score": score,
        "reason": recommendation_reason(repo, category, cost, difficulty),
        "first_step": first_step(repo, difficulty, hardware),
    }


def collect_projects() -> list[dict[str, Any]]:
    repos_by_url: dict[str, dict[str, Any]] = {}
    token = os.environ.get("GITHUB_TOKEN", "").strip()

    for index, (term, fallback_category) in enumerate(SEARCH_TERMS, start=1):
        print(f"[{index}/{len(SEARCH_TERMS)}] Searching: {term}")
        for repo in search_repositories(term):
            item = normalize_repo(repo, fallback_category)
            if not item:
                continue
            existing = repos_by_url.get(item["url"])
            if not existing or item["score"] > existing["score"]:
                repos_by_url[item["url"]] = item
        if not token:
            time.sleep(6.5)
        else:
            time.sleep(0.5)

    projects = sorted(
        repos_by_url.values(),
        key=lambda item: (item["score"], item["stars"], item["updated_at"]),
        reverse=True,
    )
    return projects[:60]


def load_index() -> str:
    if not INDEX_PATH.exists():
        raise FileNotFoundError(f"Missing {INDEX_PATH}. Create index.html first.")
    return INDEX_PATH.read_text(encoding="utf-8")


def write_index(payload: dict[str, Any]) -> None:
    index_html = load_index()
    data = json.dumps(payload, ensure_ascii=False, indent=2)
    if not DATA_PATTERN.search(index_html):
        raise RuntimeError("Could not find project-data script tag in index.html")
    updated = DATA_PATTERN.sub(lambda match: f"{match.group(1)}{data}{match.group(3)}", index_html)
    INDEX_PATH.write_text(updated, encoding="utf-8", newline="\n")


def main() -> int:
    projects = collect_projects()
    payload = {
        "generated_at": dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "count": len(projects),
        "projects": projects,
    }
    write_index(payload)
    print(f"Updated {INDEX_PATH.name} with {len(projects)} projects.")
    if projects:
        print("Top projects:")
        for project in projects[:5]:
            print(f"- {project['name']} ({project['stars']} stars) [{project['category']}]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
