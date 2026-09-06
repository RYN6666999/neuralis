import os, json, time, logging
from pathlib import Path

EVIDENCE_DIR = Path.home() / "Developer/neuralis/data/audit_evidence"
AUDIT_LOG = Path.home() / "Developer/neuralis/agency-audit.jsonl"
RETENTION_DAYS = 7

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("janitor")

def clean():
    logger.info("開始執行 EVIDENCE 清理與維護...")
    for path in EVIDENCE_DIR.glob("*"):
        # 清除 PASS 的任務證據 (保留 FAIL 的用於分析)
        if path.is_dir():
            manifest = path / "manifest.json"
            if manifest.exists():
                try:
                    data = json.loads(manifest.read_text())
                    # 簡單邏輯：若已 PASS 超過 7 天則清理
                    if data.get("status") == "PASS" and (time.time() - path.stat().st_mtime > RETENTION_DAYS * 86400):
                        import shutil
                        shutil.rmtree(path)
                        logger.info(f"清理過期證據: {path.name}")
                except Exception as e:
                    logger.error(f"清理錯誤 {path}: {e}")

if __name__ == "__main__":
    clean()
