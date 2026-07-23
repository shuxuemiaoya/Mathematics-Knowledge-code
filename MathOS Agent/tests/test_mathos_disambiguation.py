import importlib.util
import sys
import json
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "skills" / "mathos-segmentation" / "scripts" / "mathos_disambiguation.py"

spec = importlib.util.spec_from_file_location("mathos_disambiguation", SCRIPT_PATH)
dis = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules["mathos_disambiguation"] = dis
spec.loader.exec_module(dis)


def test_module_exposes_stage_constants():
    assert dis.STAGE_NAME == "disambiguation"
    assert dis.SKILL_NAME == "skills/mathos-segmentation"


def test_extract_headings_with_parent_h1():
    markdown = """# 第一章 集合与常用逻辑用语
## 1.1 集合的概念
### 1.1.1 集合与元素
## 小结
# 第二章 函数
## 复习参考题
"""
    headings = dis.extract_headings_with_parent_h1(markdown)
    assert len(headings) == 4
    
    assert headings[0]["title"] == "集合的概念"
    assert headings[0]["full_title"] == "1.1 集合的概念"
    assert headings[0]["parent_h1"] == "第一章 集合与常用逻辑用语"
    assert headings[0]["level"] == 2
    
    assert headings[1]["title"] == "集合与元素"
    assert headings[1]["full_title"] == "1.1.1 集合与元素"
    assert headings[1]["parent_h1"] == "第一章 集合与常用逻辑用语"
    assert headings[1]["level"] == 3
    
    assert headings[2]["title"] == "小结"
    assert headings[2]["full_title"] == "小结"
    assert headings[2]["parent_h1"] == "第一章 集合与常用逻辑用语"
    assert headings[2]["level"] == 2
    
    assert headings[3]["title"] == "复习参考题"
    assert headings[3]["full_title"] == "复习参考题"
    assert headings[3]["parent_h1"] == "第二章 函数"
    assert headings[3]["level"] == 2


def test_apply_disambiguation_rewrites():
    markdown = "# 第一章 集合\n## 小结\n## 1.1 概念\n## 复习参考题\n"
    rewrites = [
        {"line_index": 1, "original_text": "小结", "new_text": "集合 小结"},
        {"line_index": 3, "original_text": "复习参考题", "new_text": "集合 复习参考题"}
    ]
    new_markdown = dis.apply_disambiguation_rewrites(markdown, rewrites)
    assert new_markdown == "# 第一章 集合\n## 集合 小结\n## 1.1 概念\n## 集合 复习参考题\n"


def test_run_llm_disambiguation_success(tmp_path, monkeypatch):
    vault_root = tmp_path / "vault"
    source = vault_root / "book.md"
    source.parent.mkdir(parents=True)
    original_content = "# 第一章 集合\n## 小结\n"
    source.write_text(original_content, encoding="utf-8")
    
    env_file = vault_root / ".env"
    env_file.write_text("DEEPSEEK_API_KEY=testkey\nDEEPSEEK_MODEL=testmodel\nDEEPSEEK_BASE_URL=https://api.test.com\n", encoding="utf-8")
    
    class DummyClient:
        def __init__(self, settings):
            assert settings.api_key == "testkey"
            assert settings.model == "testmodel"
            assert settings.base_url == "https://api.test.com"
        def chat(self, system_prompt, user_payload, response_format=None):
            return json.dumps({
                "rewrites": [
                    {"line_index": 1, "original_text": "小结", "new_text": "集合 小结"}
                ]
            })
            
    monkeypatch.setattr(dis.provider, "DeepSeekProviderClient", DummyClient)
    
    count, new_text = dis.run_llm_disambiguation(source, vault_root, env_file)
    assert count == 1
    assert new_text == "# 第一章 集合\n## 集合 小结\n"
    
    # Verify backup is created with original content
    backup_path = source.with_suffix(source.suffix + ".bak")
    assert backup_path.is_file()
    assert backup_path.read_text(encoding="utf-8") == original_content
    
    # Verify in-place overwrite
    assert source.read_text(encoding="utf-8") == "# 第一章 集合\n## 集合 小结\n"


def test_main_requires_yes(tmp_path, capsys):
    vault_root = tmp_path / "vault"
    source = vault_root / "book.md"
    source.parent.mkdir(parents=True)
    source.write_text("# 第一章 集合\n## 小结\n", encoding="utf-8")

    exit_code = dis.main([str(source), "--vault-root", str(vault_root)])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 1
    assert payload["status"] == "failed"
    assert "without --yes" in payload["error"]


def test_main_success(tmp_path, capsys, monkeypatch):
    vault_root = tmp_path / "vault"
    source = vault_root / "book.md"
    source.parent.mkdir(parents=True)
    source.write_text("# 第一章 集合\n## 小结\n", encoding="utf-8")

    env_file = vault_root / ".env"
    env_file.write_text("DEEPSEEK_API_KEY=testkey\nDEEPSEEK_MODEL=testmodel\nDEEPSEEK_BASE_URL=https://api.test.com\n", encoding="utf-8")

    class DummyClient:
        def __init__(self, settings):
            pass
        def chat(self, system_prompt, user_payload, response_format=None):
            return json.dumps({
                "rewrites": [
                    {"line_index": 1, "original_text": "小结", "new_text": "集合 小结"}
                ]
            })

    monkeypatch.setattr(dis.provider, "DeepSeekProviderClient", DummyClient)

    exit_code = dis.main([str(source), "--vault-root", str(vault_root), "--env", str(env_file), "--yes"])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 0
    assert payload["status"] == "completed"
    assert payload["heading_disambiguation_count"] == 1
    assert source.read_text(encoding="utf-8") == "# 第一章 集合\n## 集合 小结\n"
