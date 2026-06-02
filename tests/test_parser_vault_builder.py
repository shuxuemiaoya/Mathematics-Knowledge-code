import os
from pathlib import Path
from math_knowledge_tools.parser.vault_builder import VaultBuilder

def test_vault_builder(tmp_path):
    chunks = [
        {"type": "text", "content": "这是第一章的介绍", "parent_hierarchy": ["第一章 集合"]},
        {"type": "text", "content": "这是1.1的介绍", "parent_hierarchy": ["第一章 集合", "1.1 集合的概念"]},
        {"type": "callout", "callout_type": "example", "content": "> [!example] 例1\n> 解答", "parent_hierarchy": ["第一章 集合", "1.1 集合的概念"]}
    ]
    
    builder = VaultBuilder(str(tmp_path), mode="highschool_textbook")
    builder.build_from_chunks(chunks, root_name="my_book")
    
    # 验证目录被正确创建
    assert (tmp_path / "知识点").exists()
    assert (tmp_path / "题").exists()
    
    # 验证 Root MOC
    root_file = tmp_path / "知识点" / "my_book.md"
    assert root_file.exists()
    root_content = root_file.read_text(encoding="utf-8")
    assert "[[第一章 集合]]" in root_content
    
    # 验证第一章 MOC
    ch1_file = tmp_path / "知识点" / "第一章 集合.md"
    assert ch1_file.exists()
    ch1_content = ch1_file.read_text(encoding="utf-8")
    assert "[[1.1 集合的概念]]" in ch1_content
    assert "这是第一章的介绍" in ch1_content
    
    # 验证 1.1 MOC
    sec1_file = tmp_path / "知识点" / "1.1 集合的概念.md"
    assert sec1_file.exists()
    sec1_content = sec1_file.read_text(encoding="utf-8")
    assert "[[例1]]" in sec1_content
    assert "这是1.1的介绍" in sec1_content
    
    # 验证例题文件
    ex_file = tmp_path / "题" / "例1.md"
    assert ex_file.exists()
    ex_content = ex_file.read_text(encoding="utf-8")
    assert "> [!example] 例1" in ex_content
