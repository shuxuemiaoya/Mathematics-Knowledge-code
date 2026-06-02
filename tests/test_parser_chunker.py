from math_knowledge_tools.parser.chunker import MarkdownChunker

def test_markdown_chunker_rkdt_and_callout():
    md_content = """# 第一章 集合
## 1.1 集合的概念
正文段落1
> [!think] 思考
> 这是一段多行的思考
>    这里有缩进的代码或列表
> 不应该被拆分
正文段落2
"""
    
    chunker = MarkdownChunker()
    chunks = chunker.parse(md_content)
    
    assert len(chunks) == 3
    
    # Chunk 0: Text block
    assert chunks[0]["type"] == "text"
    assert chunks[0]["parent_hierarchy"] == ["第一章 集合", "1.1 集合的概念"]
    assert chunks[0]["content"] == "正文段落1"
    
    # Chunk 1: Callout block (intact)
    assert chunks[1]["type"] == "callout"
    assert chunks[1]["callout_type"] == "think"
    assert "这是一段多行的思考\n   这里有缩进的代码或列表\n不应该被拆分" in chunks[1]["content"]
    assert chunks[1]["parent_hierarchy"] == ["第一章 集合", "1.1 集合的概念"]
    
    # Chunk 2: Text block
    assert chunks[2]["content"] == "正文段落2"
