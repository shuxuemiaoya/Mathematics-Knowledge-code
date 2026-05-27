import os
import re
import fitz  # PyMuPDF
from config import get_logger, MAX_PAGES_PER_CHUNK

logger = get_logger()

def sanitize_filename(filename):
    r"""过滤或替换路径/文件名中的非法字符 \/:*?"<>|"""
    # Assuming filename is just the basename
    return re.sub(r'[\/:*?"<>|]', '_', filename)

def scan_directory(root_dir):
    """
    递归扫描所有 .pdf 和 .docx 文件。忽略隐藏文件或临时文件（如 ~$*.docx）。
    返回一个任务列表, 包含需要处理的文件的绝对路径
    """
    tasks = []
    for dirpath, dirnames, filenames in os.walk(root_dir):
        # 忽略隐藏目录
        dirnames[:] = [d for d in dirnames if not d.startswith('.')]
        
        for filename in filenames:
            if filename.startswith('.') or filename.startswith('~$'):
                continue
                
            lower_name = filename.lower()
            if lower_name.endswith('.pdf') or lower_name.endswith('.docx'):
                tasks.append(os.path.join(dirpath, filename))
    return tasks

def get_output_paths(file_path, root_dir, out_dir):
    """
    计算相对路径并生成目标 md 路径和 images 文件夹路径。
    处理同名冲突：若同一目录下同时存在 a.pdf 和 a.docx，DOCX 的输出重命名为 a_docx.md
    """
    rel_path = os.path.relpath(file_path, root_dir)
    target_base = os.path.join(out_dir, rel_path)
    
    dirpath = os.path.dirname(target_base)
    basename = os.path.basename(target_base)
    name, ext = os.path.splitext(basename)
    
    # 过滤非法字符
    safe_name = sanitize_filename(name)
    
    md_filename = f"{safe_name}.md"
    
    if ext.lower() == '.docx':
        # 检查是否存在同名 pdf
        pdf_path = os.path.join(os.path.dirname(file_path), f"{name}.pdf")
        if os.path.exists(pdf_path):
            md_filename = f"{safe_name}_docx.md"
            
    out_md_path = os.path.join(dirpath, md_filename)
    out_image_dir = os.path.join(dirpath, "images")
    return out_md_path, out_image_dir

def should_skip(md_path):
    """状态恢复：支持断点续传。若目标 .md 文件已存在且大小大于 0，则跳过。"""
    if os.path.exists(md_path) and os.path.getsize(md_path) > 0:
        return True
    return False

def split_pdf_if_needed(pdf_path, temp_dir):
    """
    页数检查：若 PDF 页数超过指定阈值，使用 PyMuPDF 进行拆分。
    命名规范：拆分后的子 PDF 命名必须带有格式化的三位序号（如 chunk_001.pdf）。
    返回拆分后的文件列表。
    """
    doc = fitz.open(pdf_path)
    total_pages = len(doc)
    
    if total_pages <= MAX_PAGES_PER_CHUNK:
        doc.close()
        return [pdf_path]
        
    logger.info(f"PDF {pdf_path} has {total_pages} pages, splitting...")
    
    chunks = []
    chunk_idx = 1
    
    for start_page in range(0, total_pages, MAX_PAGES_PER_CHUNK):
        end_page = min(start_page + MAX_PAGES_PER_CHUNK - 1, total_pages - 1)
        
        chunk_doc = fitz.open()
        chunk_doc.insert_pdf(doc, from_page=start_page, to_page=end_page)
        
        chunk_filename = f"chunk_{chunk_idx:03d}.pdf"
        chunk_path = os.path.join(temp_dir, chunk_filename)
        chunk_doc.save(chunk_path)
        chunk_doc.close()
        
        chunks.append(chunk_path)
        chunk_idx += 1
        
    doc.close()
    return chunks

import shutil

def merge_md_files(chunks_data, output_md, output_image_dir):
    """
    chunks_data: list of tuples (md_file_path, extract_dir_path) sorted by chunk index.
    严格合并：合并 Markdown，并将临时目录内的所有其它文件（包括 images、json 等）拷贝到最终输出目录。
    """
    out_base_dir = os.path.dirname(output_md)
    os.makedirs(out_base_dir, exist_ok=True)
    
    with open(output_md, 'w', encoding='utf-8') as out_f:
        for idx, (md_file, extract_dir) in enumerate(chunks_data):
            if not os.path.exists(md_file):
                logger.warning(f"Expected part {md_file} not found for merging.")
                continue
                
            with open(md_file, 'r', encoding='utf-8') as in_f:
                content = in_f.read()
                
            if os.path.exists(extract_dir) and os.path.isdir(extract_dir):
                for root, dirs, files in os.walk(extract_dir):
                    rel_root = os.path.relpath(root, extract_dir)
                    if rel_root == '.':
                        target_dir = out_base_dir
                    else:
                        target_dir = os.path.join(out_base_dir, rel_root)
                        
                    os.makedirs(target_dir, exist_ok=True)
                    
                    for f in files:
                        if f == os.path.basename(md_file):
                            continue # 跳过已经读取的 md 文件
                            
                        # 根据用户需求，屏蔽掉 json/docx 等非图片中间文件
                        if not (rel_root == 'images' or rel_root.replace('\\', '/').startswith('images/')):
                            continue
                            
                        src_f = os.path.join(root, f)
                        
                        # 如果有多个 chunk，则重命名防止覆盖
                        if len(chunks_data) > 1:
                            new_name = f"chunk_{idx:03d}_{f}"
                            dst_f = os.path.join(target_dir, new_name)
                            
                            # 修复 Markdown 内部的图片路径
                            # rel_root == 'images'
                            if rel_root.replace('\\', '/').startswith('images'):
                                rel_path_old = os.path.join(rel_root, f).replace('\\', '/')
                                rel_path_new = os.path.join(rel_root, new_name).replace('\\', '/')
                                content = content.replace(rel_path_old, rel_path_new)
                        else:
                            dst_f = os.path.join(target_dir, f)
                            
                        shutil.copy2(src_f, dst_f)
            
            out_f.write(content)
            out_f.write("\n\n")
