import requests
import time
import zipfile
import io
import os
from config import get_logger, MINERU_API_KEY, BASE_URL, MAX_RETRIES
from core.endpoints import MinerUEndpoints

logger = get_logger()

class MinerUClient:
    def __init__(self):
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {MINERU_API_KEY}"
        }

    def _retry_request(self, method, url, **kwargs):
        for attempt in range(MAX_RETRIES):
            try:
                response = requests.request(method, url, **kwargs)
                
                # Check for 429 Too Many Requests or other 5xx errors
                if response.status_code == 429 or int(response.status_code) >= 500:
                    wait_time = 2 ** attempt
                    logger.warning(f"HTTP {response.status_code} on {url}. Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                    continue
                    
                response.raise_for_status()
                return response
            except requests.exceptions.RequestException as e:
                if attempt == MAX_RETRIES - 1:
                    logger.error(f"Failed to {method} {url} after {MAX_RETRIES} attempts: {e}")
                    raise
                wait_time = 2 ** attempt
                logger.warning(f"Request error on {url}: {e}. Retrying in {wait_time}s...")
                time.sleep(wait_time)

    def get_batch_upload_urls(self, files_info):
        """
        files_info: list of dicts [{"name": "file.pdf", "is_ocr": True}]
        """
        url = MinerUEndpoints.get_batch_upload_urls()
        data = {
            "files": files_info,
            "model_version": "vlm"
        }
        
        response = self._retry_request("POST", url, headers=self.headers, json=data)
        result = response.json()
        
        if result.get("code") == 0:
            return result["data"]["batch_id"], result["data"]["file_urls"]
        else:
            raise Exception(f"Failed to get batch upload URLs: {result.get('msg')}")

    def upload_file(self, upload_url, file_path):
        for attempt in range(MAX_RETRIES):
            try:
                with open(file_path, 'rb') as f:
                    response = requests.put(upload_url, data=f)
                
                if response.status_code in (200, 201):
                    return True
                    
                wait_time = 2 ** attempt
                logger.warning(f"Failed to upload {file_path}, HTTP {response.status_code}. Retrying in {wait_time}s...")
                time.sleep(wait_time)
            except Exception as e:
                if attempt == MAX_RETRIES - 1:
                    logger.error(f"Failed to upload {file_path} after {MAX_RETRIES} attempts: {e}")
                    raise
                wait_time = 2 ** attempt
                logger.warning(f"Upload error {file_path}: {e}. Retrying in {wait_time}s...")
                time.sleep(wait_time)
        return False

    def poll_batch_results(self, batch_id):
        url = MinerUEndpoints.get_batch_results(batch_id)
        response = self._retry_request("GET", url, headers=self.headers)
        result = response.json()
        
        if result.get("code") == 0:
            return result["data"]["extract_result"]
        else:
            raise Exception(f"Failed to get batch results: {result.get('msg')}")

    def download_and_extract_zip(self, zip_url, output_dir, target_filename="full.md"):
        response = self._retry_request("GET", zip_url)
        md_path = None
        with zipfile.ZipFile(io.BytesIO(response.content)) as z:
            z.extractall(output_dir)
            for zip_info in z.infolist():
                if zip_info.filename.endswith(target_filename):
                    md_path = os.path.join(output_dir, zip_info.filename)
        return md_path
