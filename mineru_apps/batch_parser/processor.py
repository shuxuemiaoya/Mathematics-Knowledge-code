import os
import time
import tempfile
import shutil
import uuid
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from config import get_logger, MAX_PARALLEL_TASKS, POLL_INTERVAL
from core.client import MinerUClient
from batch_parser.file_utils import (
    get_output_paths,
    should_skip,
    split_pdf_if_needed,
    merge_md_files
)

logger = get_logger()
progress_lock = threading.Lock()

class Processor:
    def __init__(self, root_dir, out_dir, base_src_dir, tasks):
        self.root_dir = root_dir
        self.out_dir = out_dir
        self.base_src_dir = base_src_dir
        self.tasks = tasks
        self.client = MinerUClient()
        self.total = len(tasks)
        self.success = 0
        self.failed = 0
        self.skipped = 0

    def run(self):
        logger.info(f"Starting processing of {self.total} files...")
        with ThreadPoolExecutor(max_workers=MAX_PARALLEL_TASKS) as executor:
            futures = {executor.submit(self.process_document, task): task for task in self.tasks}
            
            for future in as_completed(futures):
                task = futures[future]
                try:
                    future.result()
                except Exception as e:
                    logger.error(f"Fatal error processing {task}: {e}")
                    with progress_lock:
                        self.failed += 1
                        self._log_progress()

        logger.info("All tasks completed.")

    def _log_progress(self):
        processed = self.success + self.failed + self.skipped
        logger.info(f"Progress: [{processed}/{self.total}] - Success: {self.success}, Failed: {self.failed}, Skipped: {self.skipped}")

    def process_document(self, file_path):
        output_md, output_image_dir = get_output_paths(file_path, self.base_src_dir, self.out_dir)
        
        if should_skip(output_md):
            logger.info(f"Skipping {file_path}, target {output_md} already exists.")
            with progress_lock:
                self.skipped += 1
                self._log_progress()
            return

        is_docx = file_path.lower().endswith('.docx')
        
        temp_dir = tempfile.mkdtemp(prefix="mineru_")
        try:
            chunks = []
            if is_docx:
                chunks = [file_path]
            else:
                chunks = split_pdf_if_needed(file_path, temp_dir)

            # Process in batches of 50 (API limit)
            batch_size = 50
            all_extracted_mds = [None] * len(chunks)
            
            for i in range(0, len(chunks), batch_size):
                chunk_batch = chunks[i:i+batch_size]
                self._process_chunk_batch(chunk_batch, is_docx, temp_dir, all_extracted_mds, i)

            # Check if all successful
            if all(data is not None for data in all_extracted_mds):
                merge_md_files(all_extracted_mds, output_md, output_image_dir)
                with progress_lock:
                    self.success += 1
                    logger.info(f"Successfully processed {file_path} -> {output_md}")
                    self._log_progress()
            else:
                raise Exception("Not all chunks were successfully processed.")
                
        except Exception as e:
            logger.error(f"Failed processing document {file_path}: {e}")
            with progress_lock:
                self.failed += 1
                self._log_progress()
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def _process_chunk_batch(self, chunk_batch, is_docx, temp_dir, all_extracted_mds, offset):
        files_info = []
        for j, chunk_path in enumerate(chunk_batch):
            chunk_name = os.path.basename(chunk_path)
            # Disable OCR for DOCX
            files_info.append({
                "name": chunk_name,
                "is_ocr": not is_docx,
                "data_id": f"{uuid.uuid4().hex}_{j}"
            })

        logger.info(f"Requesting batch upload URLs for {len(chunk_batch)} files...")
        batch_id, file_urls = self.client.get_batch_upload_urls(files_info)
        
        # Upload files
        for j, chunk_path in enumerate(chunk_batch):
            logger.info(f"[Uploading] {chunk_path}")
            success = self.client.upload_file(file_urls[j], chunk_path)
            if not success:
                raise Exception(f"Upload failed for {chunk_path}")

        # Poll for results
        logger.info(f"[Polling] batch_id={batch_id}")
        self._poll_and_download(batch_id, len(chunk_batch), temp_dir, all_extracted_mds, offset)

    def _poll_and_download(self, batch_id, expected_count, temp_dir, all_extracted_mds, offset):
        completed = set()
        while len(completed) < expected_count:
            results = self.client.poll_batch_results(batch_id)
            
            for j, res in enumerate(results):
                if j in completed:
                    continue
                    
                state = res.get("state")
                file_name = res.get("file_name")
                
                if state == "done":
                    zip_url = res.get("full_zip_url")
                    if zip_url:
                        logger.info(f"[Downloading] {file_name} zip...")
                        # Extract to a unique subfolder to avoid collisions
                        extract_dir = os.path.join(temp_dir, f"extract_{offset+j}")
                        os.makedirs(extract_dir, exist_ok=True)
                        md_path = self.client.download_and_extract_zip(zip_url, extract_dir)
                        if md_path:
                            all_extracted_mds[offset+j] = (md_path, extract_dir)
                            completed.add(j)
                        else:
                            raise Exception(f"full.md not found in zip for {file_name}")
                    else:
                        raise Exception(f"Missing zip_url for completed task {file_name}")
                elif state == "failed":
                    err_msg = res.get("err_msg", "Unknown error")
                    raise Exception(f"Task failed for {file_name}: {err_msg}")
                    
            if len(completed) < expected_count:
                time.sleep(POLL_INTERVAL)
