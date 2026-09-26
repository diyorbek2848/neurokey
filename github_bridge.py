# -*- coding: utf-8 -*-
"""NeuroKey — GitHub ovoz bilan boshqarish.

Token: neurokey_sayt git config dan avtomatik olinadi yoki GITHUB_TOKEN env.
Base:  https://api.github.com
Auth:  Authorization: Bearer {token}

Buyruqlar:
    "GitHub repolarimni ko'rsat"
    "GitHub da yangi repo yarat — neurokey-mobile"
    "neurokey-sayt da oxirgi commitlarni ko'rsat"
    "GitHub da issue yoz — login sahifasida xato"
"""
import os, re, subprocess
from typing import Optional, Dict, Any, List

try:
    import requests as _req
    import urllib3 as _urllib3
    _urllib3.disable_warnings(_urllib3.exceptions.InsecureRequestWarning)
    _HAVE_REQUESTS = True
except ImportError:
    _HAVE_REQUESTS = False

_BASE = "https://api.github.com"
_OWNER = "diyorbek2848"


def _get_token() -> str:
    t = os.getenv("GITHUB_TOKEN", "").strip()
    if t:
        return t
    try:
        sayt = r"C:\Users\tymit\Documents\neurokey_sayt"
        r = subprocess.run(
            ["git", "-C", sayt, "remote", "get-url", "origin"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=5
        )
        m = re.search(r"https://[^:]+:([^@]+)@github\.com", r.stdout)
        if m:
            return m.group(1)
    except Exception:
        pass
    return ""


def _headers() -> Dict:
    return {
        "Authorization": f"Bearer {_get_token()}",
        "X-GitHub-Api-Version": "2022-11-28",
        "Accept": "application/vnd.github+json",
    }


def is_available() -> bool:
    return bool(_get_token()) and _HAVE_REQUESTS


# ── Trigger ──────────────────────────────────────────────────────────────────

_TRIGGERS = ["github", "гитхаб", "гит хаб", "git hub", "репозитор", "repo", "commit", "issue"]

def is_github_request(text: str) -> bool:
    low = text.lower()
    return any(t in low for t in _TRIGGERS)


# ── API chaqiruvlari ──────────────────────────────────────────────────────────

def _git_fallback_repos() -> List[Dict]:
    """API ishlamasa git remote dan repo nomini qaytaradi."""
    try:
        sayt = r"C:\Users\tymit\Documents\neurokey_sayt"
        r = subprocess.run(["git", "-C", sayt, "remote", "-v"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=5)
        lines = r.stdout.strip().splitlines()
        repos = []
        seen = set()
        for line in lines:
            m = re.search(r"github\.com[/:]([^/]+)/([^\s.]+)", line)
            if m:
                name = m.group(2)
                if name not in seen:
                    seen.add(name)
                    repos.append({"name": name, "full_name": f"{m.group(1)}/{name}"})
        if not repos:
            repos = [{"name": "neurokey-sayt", "full_name": f"{_OWNER}/neurokey-sayt"}]
        return repos
    except Exception:
        return [{"name": "neurokey-sayt", "full_name": f"{_OWNER}/neurokey-sayt"}]


def list_repos(limit: int = 8) -> List[Dict]:
    try:
        r = _req.get(f"{_BASE}/user/repos?sort=updated&per_page={limit}", headers=_headers(), timeout=10, verify=False)
        r.raise_for_status()
        return r.json()
    except Exception:
        return _git_fallback_repos()


def list_commits(repo: str, limit: int = 5) -> List[Dict]:
    try:
        r = _req.get(f"{_BASE}/repos/{_OWNER}/{repo}/commits?per_page={limit}", headers=_headers(), timeout=10, verify=False)
        r.raise_for_status()
        return r.json()
    except Exception:
        # Fallback: local git log if repo matches
        try:
            paths = [
                r"C:\Users\tymit\Documents\neurokey_sayt",
                r"C:\Users\tymit\Documents\juma",
            ]
            for path in paths:
                r2 = subprocess.run(
                    ["git", "-C", path, "log", f"--max-count={limit}", "--oneline"],
                    capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=5
                )
                if r2.returncode == 0 and r2.stdout.strip():
                    lines = r2.stdout.strip().splitlines()
                    return [{"commit": {"message": l[8:], "author": {"name": "local"}}} for l in lines]
        except Exception:
            pass
        return []


def list_issues(repo: str, limit: int = 5) -> List[Dict]:
    r = _req.get(f"{_BASE}/repos/{_OWNER}/{repo}/issues?state=open&per_page={limit}", headers=_headers(), timeout=10, verify=False)
    r.raise_for_status()
    return r.json()


def create_issue(repo: str, title: str, body: str = "") -> Dict:
    r = _req.post(
        f"{_BASE}/repos/{_OWNER}/{repo}/issues",
        headers=_headers(), json={"title": title, "body": body}, timeout=15, verify=False
    )
    r.raise_for_status()
    return r.json()


def create_repo(name: str, private: bool = False, description: str = "") -> Dict:
    r = _req.post(
        f"{_BASE}/user/repos",
        headers=_headers(),
        json={"name": name, "private": private, "description": description},
        timeout=15, verify=False
    )
    r.raise_for_status()
    return r.json()


# ── Handler ───────────────────────────────────────────────────────────────────

def handle(text: str, tts_say=None) -> Optional[str]:
    if not is_github_request(text):
        return None
    if not is_available():
        return "GitHub token topilmadi."

    def say(m):
        if tts_say:
            try: tts_say(m)
            except Exception: pass

    low = text.lower()

    # Repo ro'yxati
    if any(w in low for w in ["repo", "репозитор", "repolar", "ko'rsat", "список"]):
        repos = list_repos(6)
        names = [r["name"] for r in repos]
        msg = "GitHub repolaringiz: " + ", ".join(names)
        say(msg)
        return msg

    # Commitlar
    m = re.search(r"commit.*?([a-z0-9_\-]+sayt|neurokey[a-z0-9_\-]*|[a-z0-9_\-]+)", low)
    if m and any(w in low for w in ["commit", "коммит"]):
        repo = m.group(1)
        commits = list_commits(repo, 5)
        lines = [f"{c['commit']['message'][:50]} — {c['commit']['author']['name']}" for c in commits[:5]]
        msg = f"{repo} oxirgi commitlar:\n" + "\n".join(lines)
        say(msg[:300])
        return msg

    # Issue yaratish
    if any(w in low for w in ["issue", "иссу", "xato yoz", "bug yoz"]):
        title_m = re.search(r"[—\-:]\s*(.{5,})", text)
        title = title_m.group(1).strip() if title_m else text[:80]
        repo = "neurokey-sayt"
        result = create_issue(repo, title)
        msg = f"GitHub issue #{result['number']} yaratildi: {title}"
        say(msg)
        return msg

    # Repo yaratish
    if any(w in low for w in ["yangi repo", "create repo", "новый репо"]):
        name_m = re.search(r"[—\-:]\s*([a-z0-9_\-]+)", low)
        name = name_m.group(1) if name_m else "neurokey-new"
        result = create_repo(name)
        msg = f"GitHub repo '{name}' yaratildi: {result.get('html_url', '')}"
        say(msg)
        return msg

    # Issues ro'yxati
    if any(w in low for w in ["issue", "иссу"]):
        issues = list_issues("neurokey-sayt", 5)
        if not issues:
            msg = "Ochiq issue yo'q."
        else:
            lines = [f"#{i['number']}: {i['title']}" for i in issues]
            msg = "Ochiq issualar:\n" + "\n".join(lines)
        say(msg[:300])
        return msg

    return None
