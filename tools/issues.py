#!/usr/bin/env python3
"""Collect the upstream issues that came from the corpus and how their fixes are going.

Writes site/issues.json. Sources:
  - every issue URL in known.json;
  - every "link" in results/*.jsonl that points to an issue;
  - issues in the repositories below whose text says "stress corpus" or "stress-corpus".

For each issue it reads the issue and its timeline from the GitHub REST API (read only, public
repositories). A pull request counts as linked when it mentions the issue (the timeline shows
every "Fixes #N" or "#N" in a pull request as a cross reference). The whole run uses about
two calls per issue plus three searches, far below 300. If a call fails, the earlier value from
the previous issues.json is kept.

Set GITHUB_TOKEN (or GH_TOKEN). Standard library only.
"""
import glob
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import FAILURES, ROOT, load_items  # noqa: E402
from cluster import kind, normalise  # noqa: E402

SEARCH_REPOS = ["tangency-labs/solidcraft", "dutchman-cad/dutchman", "cadmpeg/cadmpeg"]
OWN_REPO = "dutchman-cad/stress-corpus"
MAX_CALLS = 250
ISSUE_URL = re.compile(r"^https://github\.com/([\w.-]+/[\w.-]+)/issues/(\d+)/?$")
OUT = os.path.join(ROOT, "site", "issues.json")


def cause_key(r):
    return " | ".join((r.get("pipeline", ""), kind(r["outcome"]), normalise(r["signature"])))


def known_map():
    path = os.path.join(ROOT, "known.json")
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def sources():
    """Return {issue url: {"items": set of ids, "from": set of source names}}."""
    out = {}

    def add(url, src, ids=()):
        m = ISSUE_URL.match(url.strip())
        if not m:
            return
        u = f"https://github.com/{m.group(1)}/issues/{m.group(2)}"
        e = out.setdefault(u, {"items": set(), "from": set()})
        e["from"].add(src)
        e["items"].update(ids)

    known = known_map()
    by_url = {}
    for key, urls in known.items():
        for u in str(urls).split():
            by_url.setdefault(u, set()).add(key)
            add(u, "known")
    key_urls = {k: [u for u in str(v).split()] for k, v in known.items()}
    for path in sorted(glob.glob(os.path.join(ROOT, "results", "*.jsonl"))):
        with open(path, encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(r, dict):
                    continue
                if isinstance(r.get("link"), str) and r["link"]:
                    add(r["link"], "link", [r.get("id")])
                if r.get("outcome") in FAILURES and r.get("signature"):
                    for u in key_urls.get(cause_key(r), []):
                        add(u, "known", [r.get("id")])
    return out


class Api:
    def __init__(self):
        self.token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""
        self.calls = 0

    def get(self, path):
        if self.calls >= MAX_CALLS:
            raise RuntimeError("call budget used up")
        self.calls += 1
        req = urllib.request.Request("https://api.github.com" + path, headers={
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "stress-corpus-site",
            **({"Authorization": "Bearer " + self.token} if self.token else {})})
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.load(resp)


def search_issues(api, repo):
    found = []
    q = f'repo:{repo} is:issue ("stress corpus" OR "stress-corpus") in:body'
    for page in (1, 2, 3):
        data = api.get("/search/issues?per_page=100&page=%d&q=%s" % (page, urllib.parse.quote(q)))
        found += [it["html_url"] for it in data.get("items", [])]
        if len(data.get("items", [])) < 100:
            break
    return found


def pr_state(src):
    pr = src.get("pull_request") or {}
    if pr.get("merged_at"):
        return "merged"
    return "open" if src.get("state") == "open" else "closed"


def linked_prs(api, repo, number):
    prs = {}
    for page in (1, 2, 3):
        events = api.get(f"/repos/{repo}/issues/{number}/timeline?per_page=100&page={page}")
        for ev in events:
            if ev.get("event") != "cross-referenced":
                continue
            src = (ev.get("source") or {}).get("issue") or {}
            if not src.get("pull_request"):
                continue
            url = src.get("html_url", "")
            if f"/{OWN_REPO}/" in url:
                continue
            prs[url] = {"url": url, "number": src.get("number"), "title": src.get("title", ""),
                        "state": pr_state(src)}
        if len(events) < 100:
            break
    return list(prs.values())


def load_cache():
    try:
        with open(OUT, encoding="utf-8") as f:
            return {i["url"]: i for i in json.load(f).get("issues", [])}
    except (OSError, ValueError, KeyError, TypeError):
        return {}


def main():
    api = Api()
    src = sources()
    cache = load_cache()
    for repo in SEARCH_REPOS:
        try:
            for u in search_issues(api, repo):
                e = src.setdefault(u, {"items": set(), "from": set()})
                e["from"].add("search")
        except Exception as e:  # keep what we have
            print(f"search in {repo} failed: {e}", file=sys.stderr)
    issues, failed = [], 0
    for url in sorted(src, key=lambda u: (u.split("/")[3:5], int(u.rsplit("/", 1)[1]))):
        m = ISSUE_URL.match(url)
        repo, number = m.group(1), int(m.group(2))
        old = cache.get(url, {})
        try:
            info = api.get(f"/repos/{repo}/issues/{number}")
            prs = linked_prs(api, repo, number)
            if info.get("pull_request"):
                continue  # a link to a pull request, not an issue
            rec = {"url": url, "repo": repo, "number": number, "title": info.get("title", ""),
                   "state": info.get("state", "open"), "prs": prs}
        except Exception as e:
            failed += 1
            print(f"{url}: {e}", file=sys.stderr)
            if not old:
                continue
            rec = {k: old.get(k) for k in ("url", "repo", "number", "title", "state", "prs")}
        rec["items"] = sorted(i for i in src[url]["items"] if i)
        rec["from"] = sorted(src[url]["from"])
        issues.append(rec)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"updated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
                   "calls": api.calls, "issues": issues}, f, ensure_ascii=False, indent=1)
    print(f"{len(issues)} issues, {sum(1 for i in issues if i['prs'])} with a PR, "
          f"{api.calls} API calls, {failed} failed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
