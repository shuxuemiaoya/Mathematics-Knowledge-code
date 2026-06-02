import os
import argparse
import logging
from dotenv import load_dotenv

from .extractor import DeepSeekExtractor
from .batch_runner import OntologyBatchRunner

def main():
    load_dotenv()
    
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    parser = argparse.ArgumentParser(description="Run ontology extraction using DeepSeek API.")
    parser.add_argument("--vault_dir", type=str, required=True, help="Path to the markdown vault directory.")
    args = parser.parse_args()
    
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        logging.error("DEEPSEEK_API_KEY environment variable is missing.")
        return
    
    try:
        extractor = DeepSeekExtractor(api_key=api_key)
        runner = OntologyBatchRunner(vault_dir=args.vault_dir, extractor=extractor)
        runner.run()
    except Exception as e:
        logging.error(f"Failed to run ontology extraction: {e}")

if __name__ == "__main__":
    main()
