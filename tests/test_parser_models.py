from math_knowledge_tools.parser.models import Concept, Citation, MicroConcept

def test_knowledge_object_schema():
    cite = Citation(page=42, text_quote="函数是描述客观世界...")
    
    mc = MicroConcept(
        id="MC_001",
        title="函数的定义",
        parent="C_001",
        content="设A、B是非空的数集...",
        citations=[cite]
    )
    
    # Check parent linkage (strict parent only)
    assert mc.parent == "C_001"
    assert not hasattr(mc, "grandparent")
    
    # Check lateral relations (empty default)
    assert mc.prerequisites == []
    
    # Check JSON-LD type
    d = mc.model_dump(by_alias=True)
    assert d["@type"] == "MicroConcept"
