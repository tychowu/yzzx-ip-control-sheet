"""Small, dependency-free repository checks. Never print secret values."""

import argparse
from pathlib import Path
import re
import subprocess
from urllib.parse import unquote


def git(*args):
    return subprocess.check_output(["git", *args], text=True).strip()


def version_tuple(value):
    return tuple(map(int, value.split(".")))


def check(root, base=None):
    errors = []
    files = git("ls-files", "--cached", "--others", "--exclude-standard", "-z").split("\0")

    for name in filter(None, files):
        path = root / name
        if not path.is_file():
            continue

        parts = {part.lower() for part in Path(name).parts}
        if parts & {"output", "references-private", "node_modules", ".venv"}:
            errors.append(f"Forbidden tracked file: {name}")
        if (path.name.startswith(".env") and path.name != ".env.example") or path.suffix.lower() in {".pem", ".key"}:
            errors.append(f"Forbidden tracked file: {name}")
        if any(word in path.name for word in ["角色控制", "换装控制", "人物控制", "参考照片"]):
            errors.append(f"Possible private person asset: {name}")
        if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".heic"}:
            errors.append(f"Image must not be tracked in this workflow repository: {name}")

        if path.suffix.lower() in {".md", ".py", ".yml", ".yaml", ".json", ".mjs", ".txt"}:
            text = path.read_text(encoding="utf-8")
            patterns = [
                r"gh[pousr]_[A-Za-z0-9]{30,}",
                r"github_pat_[A-Za-z0-9_]{30,}",
                r"sk-[A-Za-z0-9_-]{32,}",
                r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
            ]
            if any(re.search(pattern, text) for pattern in patterns):
                errors.append(f"Possible secret in: {name}")

        if path.suffix.lower() == ".md":
            text = path.read_text(encoding="utf-8")
            for link in re.findall(r"\]\(([^\n]+?)\)", text):
                link = link.strip().strip("<>")
                if re.match(r"^[a-zA-Z][\w+.-]*:", link) or link.startswith(("#", "/", "~")) or "<" in link:
                    continue
                target = unquote(link.split("#")[0])
                if target and not (path.parent / target).exists():
                    errors.append(f"Broken link in {name}: {target}")

    required = ["SKILL.md", "VERSION", "CHANGELOG.md", "CONTRIBUTING.md"]
    for name in required:
        if not (root / name).is_file():
            errors.append(f"Missing required file: {name}")

    version = (root / "VERSION").read_text(encoding="utf-8").strip()
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        errors.append("Invalid VERSION; expected X.Y.Z")
    else:
        changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
        heading = re.search(rf"^## {re.escape(version)} · .+$", changelog, re.MULTILINE)
        if not heading:
            errors.append("Current version missing from CHANGELOG.md")
        else:
            following = changelog[heading.end():]
            section = following.split("\n## ", 1)[0]
            if not re.search(r"^[-*] \S", section, re.MULTILINE):
                errors.append("Current version must list update items in CHANGELOG.md")

    if base and re.fullmatch(r"[0-9a-fA-F]{40}", base) and set(base) != {"0"}:
        old = subprocess.run(["git", "show", f"{base}:VERSION"], capture_output=True, text=True)
        if old.returncode == 0 and re.fullmatch(r"\d+\.\d+\.\d+", version):
            old_version = old.stdout.strip()
            if re.fullmatch(r"\d+\.\d+\.\d+", old_version) and version_tuple(version) <= version_tuple(old_version):
                errors.append("Bump VERSION above the base version before publishing changes")

    return errors


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base")
    args = parser.parse_args()
    repository_root = Path(__file__).resolve().parents[1]
    import os

    os.chdir(repository_root)
    problems = check(repository_root, args.base)
    for problem in problems:
        print(problem)
    print(f"{len(problems)} error(s)")
    raise SystemExit(bool(problems))
