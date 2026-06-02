from math_knowledge_tools.parser.vault_models import ObsidianNode
from math_knowledge_tools.parser.categorizer import Categorizer

def test_obsidian_node():
    node = ObsidianNode(title="1.1 集合的概念", content="正文", category="知识点")
    node.add_link("定义-集合")
    
    md_content = node.to_markdown()
    assert "# 1.1 集合的概念" in md_content
    assert "正文" in md_content
    assert "[[定义-集合]]" in md_content

def test_categorizer():
    cat = Categorizer()
    
    # Text chunks (including H1/H2) go to 知识点
    c1 = cat.categorize({"type": "text", "content": "一些正文", "parent_hierarchy": ["1.1"]})
    assert c1 == "知识点"
    
    # Callouts
    c2 = cat.categorize({"type": "callout", "callout_type": "example", "content": "> [!example] 例1", "parent_hierarchy": ["1.1"]})
    assert c2 == "题"
    
    c3 = cat.categorize({"type": "callout", "callout_type": "think", "content": "> [!think] 思考", "parent_hierarchy": ["1.1"]})
    assert c3 == "思维或技巧"
