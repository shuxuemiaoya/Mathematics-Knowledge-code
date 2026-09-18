"""Read-only production-code review probes; every mutation is in a temp directory."""
from __future__ import annotations
import argparse
import contextlib
import importlib.util
import io
import json
import sys
import tempfile
import zipfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path('/Users/oven/Documents/Mathematics-Knowledge-code/Book to Obsidian Wiki Graph')
sys.dont_write_bytecode = True

def load(name, relative):
    path = ROOT / relative
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')

runtime_tests = load('review_runtime_tests', 'skills/book-to-obsidian-wiki-graph/tests/test_pipeline_runtime.py')
runtime = runtime_tests.MODULE
audit_tests = load('review_audit_tests', 'skills/book-graph-audit/tests/test_audit.py')
audit = audit_tests.audit_tool
fmt = load('review_format', 'skills/book-graph-markdown/scripts/standardize_markdown.py')
concept = load('review_concept', 'skills/book-graph-concepts/scripts/apply_concept_candidates.py')
pdf = load('review_pdf', 'skills/book-pdf-to-markdown/scripts/book_pdf_to_markdown.py')
meta = load('review_metadata', 'skills/book-graph-metadata/scripts/tag_book_metadata.py')
toc_formatter = load('review_toc_formatter', 'skills/book-toc-formatting/scripts/format_toc_headings.py')
results = {}

before = '# 条件\n\n条件为 $x>0$。\n\n结论为 $x=1$。\n'
after = '# 条件\n\n结论为 $x=2$。\n'
results['R1_deleted_condition_changed_formula'] = fmt.invariants(before, after)

with tempfile.TemporaryDirectory() as td:
    source,vault,book,profile,coverage,concepts = audit_tests.GraphAuditTests().make_profiled_book(Path(td).resolve())
    note = book/'主题/集合.md'
    note.write_text(note.read_text()+'\n原书中的必要条件是 $x>0$。\n')
    source.write_text(note.read_text())
    source_hash = audit.sha256_file(source)
    for path in (profile, coverage, concepts):
        payload = json.loads(path.read_text())
        if path == profile: payload['source']['sha256'] = source_hash
        else: payload['source_sha256'] = source_hash
        dump(path,payload)
    kw = dict(source=source,profile_path=profile,coverage_manifest=coverage,concept_manifest=concepts,stage='final')
    baseline = audit.audit_book(book,vault,**kw)
    note.write_text(note.read_text().replace('\n原书中的必要条件是 $x>0$。\n',''))
    changed = audit.audit_book(book,vault,**kw)
    results['R1_final_audit_after_body_loss'] = {'before':baseline['status'],'after':changed['status'],'errors':changed['errors']}

with tempfile.TemporaryDirectory() as td:
    root=Path(td)
    source=root/'source.pdf'; source.write_bytes(b'fake PDF; parsing mocked')
    part=pdf.PdfPart(source,1,1,1,100,'part-1')
    class FakeClient:
        def __init__(self,settings): pass
        def request_upload_urls(self,parts): return 'batch',['mock-upload']
        def upload(self,url,part): pass
        def poll(self,batch): return [{'data_id':'part-1','state':'done','full_zip_url':'mock-result'}]
        def download(self,url,target):
            target.parent.mkdir(parents=True,exist_ok=True)
            with zipfile.ZipFile(target,'w') as z:
                z.writestr('full.md','# 仅第1页\n\n只有一页的内容。\n')
                z.writestr('source_content_list.json',json.dumps([{'page_idx':0,'type':'text','text':'只有一页'}]))
    args=argparse.Namespace(overwrite=False)
    with patch.object(pdf,'pdf_page_count',return_value=100),patch.object(pdf,'prepare_parts',return_value=[part]),patch.object(pdf,'load_settings',return_value=None),patch.object(pdf,'MineruClient',FakeClient):
        r=pdf.convert(source,root/'output.md',None,args)
    results['R2_missing_OCR_pages']={'status':r['status'],'page_count':r['page_count'],'returned_page_ids':[0],'validation':r['validation']}

with tempfile.TemporaryDirectory() as td:
    source,vault,book,profile=runtime_tests.PipelineRuntimeTests().make_profile(Path(td))
    state=runtime.init_state(profile)
    runtime.begin_stage(state,'markdown-registration',[])
    runtime.validate_resume(state)
    try: runtime.begin_stage(state,'markdown-registration',[])
    except Exception as e: results['R3_interrupted_running_stage']={'state':state['stages'][1]['status'],'retry_error':str(e)}

with tempfile.TemporaryDirectory() as td:
    root=Path(td); book=root/'vault/book'; source=book/'知识点/集合.md'; source.parent.mkdir(parents=True)
    source.write_text('# 集合\n\n把一些元素组成的总体叫做集合。\n')
    profile=root/'profile.json'; coverage=root/'coverage.json'; candidates=root/'candidates.json'; manifest=root/'manifest.json'
    dump(profile,{'source':{'sha256':'a'*64},'paths':{'vault_root':str(root/'vault'),'book_root':str(book)},'categories':[{'role':'concept','directory':'概念','enabled':True}],'links':{'note_mode':'vault-root'}})
    dump(coverage,{'units':[{'target':'知识点/集合.md','source_key':'set'}]})
    dump(candidates,{'status':'approved','concepts':[{'name':'集合','definition_source':'知识点/集合.md','definition_start_line':3,'definition_end_line':3,'anchor_text':'总体叫做集合','reviewed':True}]})
    real_write=concept.atomic_write
    def fail_source_write(path,text):
        if path==source: raise OSError('simulated interruption after concept write')
        return real_write(path,text)
    with patch.object(concept,'atomic_write',side_effect=fail_source_write):
        try: concept.apply_candidates(profile,coverage,candidates,manifest)
        except OSError: pass
    try: concept.apply_candidates(profile,coverage,candidates,manifest)
    except Exception as e: results['R3_concept_partial_commit']={'concept_exists':(book/'概念/集合.md').exists(),'manifest_exists':manifest.exists(),'source_linked':'[集合]' in source.read_text(),'retry_error':str(e)}

with tempfile.TemporaryDirectory() as td:
    source,vault,book,profile=runtime_tests.PipelineRuntimeTests().make_profile(Path(td))
    state=runtime.init_state(profile)
    runtime.begin_stage(state,'markdown-registration',[])
    runtime.complete_stage(state,'markdown-registration',[('file',source)])
    runtime.begin_stage(state,'toc-formatting',[])
    raw_hash=runtime.sha256_file(source)
    candidate=profile.parent/'formatted.md'
    toc=profile.parent/'toc.json'; report=profile.parent/'toc-report.json'
    dump(toc,{'schema_version':1,'profile':str(profile.resolve()),'source_sha256':raw_hash,'input_markdown_sha256':raw_hash,'toc_source_ranges':[],'entries':[{'key':'example','title':'Example','level':1}]})
    with contextlib.redirect_stdout(io.StringIO()):
        assert toc_formatter.main([str(source),str(toc),str(candidate),'--profile',str(profile),'--report',str(report)]) == 0
    candidate.write_text('# replaced AFTER the passed report\n')
    runtime.complete_stage(state,'toc-formatting',[('file',candidate),('toc-manifest',toc),('toc-format-report',report)])
    results['R4_stale_toc_report']={'stage_status':state['stages'][2]['status'],'report_matches_file':json.loads(report.read_text())['candidate_markdown_sha256']==runtime.sha256_file(candidate)}

with tempfile.TemporaryDirectory() as td:
    root=Path(td); book=root/'book'; book.mkdir(); note=book/'集合.md'
    note.write_text('---\naliases:\n  - 集合别称\ntags:\n  - math\n---\n\n# 集合\n\n正文。\n')
    profile=root/'profile.json'; report=root/'report.json'
    dump(profile,{'book':{'title':'数学 必修第二册','edition':''},'source':{'sha256':'a'*64},'paths':{'book_root':str(book),'staging_root':str(root)}})
    r=meta.process_book_metadata(book,profile,report)
    results['R5_metadata_list_loss']={'status':r['status'],'aliases_value_preserved':'集合别称' in note.read_text(),'tags_value_preserved':'math' in note.read_text(),'grade_for_required_volume_2':meta.infer_grade('数学 必修第二册','')}

with tempfile.TemporaryDirectory() as td:
    root=Path(td).resolve()
    sys.path.insert(0,str(ROOT/'skills/book-graph-intake/scripts'))
    intake=load('review_intake','skills/book-graph-intake/scripts/make_book_profile.py')
    source=root/'source.md'; source.write_text('# 普通知识读物\n\n这是完整正文。\n')
    book=root/'vault/book'; stage=root/'stage'; stage.mkdir()
    profile=stage/'profile.json'
    p=intake.create_profile(source,root/'vault',book,'普通知识读物',book_kind='general',staging_root=stage)
    p['canvas']['enabled']=False
    dump(profile,p)
    (book/'内容').mkdir(parents=True)
    (book/'内容/读物.md').write_text(source.read_text())
    coverage=stage/'coverage.json'
    dump(coverage,{'schema_version':1,'profile':str(profile),'source_sha256':p['source']['sha256'],'units':[{'source_key':'content','source_order':1,'status':'assigned','target':'内容/读物.md'}]})
    r=audit.audit_book(book,root/'vault',profile_path=profile,coverage_manifest=coverage,stage='concepts')
    results['R6_disabled_concepts_for_general_book']={'enabled_roles':[c['role'] for c in p['categories'] if c['enabled']],'status':r['status'],'errors':r['errors']}

print(json.dumps(results,ensure_ascii=False,indent=2))
