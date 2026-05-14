from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from polymarket_cli.config import WatchlistConfig


class LaunchdService:
    def __init__(self, project_dir: Path) -> None:
        self.project_dir = project_dir
        self.launch_agents_dir = Path.home() / "Library/LaunchAgents"
        self.launch_agents_dir.mkdir(parents=True, exist_ok=True)

    def plist_path(self, watchlist_name: str) -> Path:
        return self.launch_agents_dir / f"com.polymarket.{watchlist_name}.plist"

    def render_plist(self, watchlist: WatchlistConfig) -> str:
        uv_path = shutil.which("uv") or "uv"
        label = f"com.polymarket.{watchlist.name}"
        return f"""<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<!DOCTYPE plist PUBLIC \"-//Apple//DTD PLIST 1.0//EN\" \"http://www.apple.com/DTDs/PropertyList-1.0.dtd\">
<plist version=\"1.0\">
<dict>
  <key>Label</key>
  <string>{label}</string>
  <key>ProgramArguments</key>
  <array>
    <string>{uv_path}</string>
    <string>run</string>
    <string>polymarket</string>
    <string>run-job</string>
    <string>{watchlist.name}</string>
  </array>
  <key>WorkingDirectory</key>
  <string>{self.project_dir}</string>
  <key>StartInterval</key>
  <integer>{watchlist.poll_minutes * 60}</integer>
  <key>RunAtLoad</key>
  <true/>
  <key>StandardOutPath</key>
  <string>{self.project_dir / 'logs' / (watchlist.name + '.out.log')}</string>
  <key>StandardErrorPath</key>
  <string>{self.project_dir / 'logs' / (watchlist.name + '.err.log')}</string>
</dict>
</plist>
"""

    def install(self, watchlist: WatchlistConfig) -> Path:
        path = self.plist_path(watchlist.name)
        path.write_text(self.render_plist(watchlist), encoding="utf-8")
        subprocess.run(["launchctl", "unload", str(path)], check=False)
        subprocess.run(["launchctl", "load", str(path)], check=True)
        return path

    def remove(self, watchlist_name: str) -> Path:
        path = self.plist_path(watchlist_name)
        if path.exists():
            subprocess.run(["launchctl", "unload", str(path)], check=False)
            path.unlink()
        return path
