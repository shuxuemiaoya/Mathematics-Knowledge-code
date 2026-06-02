import argparse
import sys
from pathlib import Path
from .chunker import MarkdownChunker
from .vault_builder import VaultBuilder

def main(argv=None):
    parser = argparse.ArgumentParser(description="Markdown to Zettelkasten Vault Builder")
    parser.add_argument("--input", type=str, required=True, help="Input markdown file")
    parser.add_argument("--output", type=str, required=True, help="Output vault directory")
    
    args = parser.parse_args(argv)
    
    input_file = Path(args.input).expanduser().resolve()
    output_dir = Path(args.output).expanduser().resolve()
    
    if not input_file.exists() or not input_file.is_file():
        print(f"Error: Input file does not exist: {input_file}", file=sys.stderr)
        return 1
        
    print(f"Parsing {input_file}...")
    md_content = input_file.read_text(encoding="utf-8")
    
    chunker = MarkdownChunker()
    chunks = chunker.parse(md_content)
    print(f"Extracted {len(chunks)} chunks.")
    
    print(f"Building vault at {output_dir}...")
    builder = VaultBuilder(str(output_dir))
    builder.build_from_chunks(chunks)
    print("Vault built successfully.")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
