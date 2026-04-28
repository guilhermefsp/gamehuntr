import codecs
import subprocess

env_path = r"D:\The Brain\raw\projects\boardgame-tracker\.env"
project_path = r"D:\The Brain\raw\projects\boardgame-tracker"

with codecs.open(env_path, "r", encoding="utf-8-sig") as f:
    for line in f:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        print(f"Adding {key}...")
        result = subprocess.run(
            ["vercel.cmd", "env", "add", key, "production", "--cwd", project_path, "--yes"],
            input=value,
            text=True,
            encoding="utf-8",
            capture_output=True,
        )
        if "Added" in result.stdout:
            print("  OK")
        else:
            print(f"  ERROR: {result.stdout} {result.stderr}")
