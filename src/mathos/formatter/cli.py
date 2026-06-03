import argparse
from pathlib import Path
from .logger import get_logger
from .discovery import discover_formatters

logger = get_logger()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Markdown formatter for the mathematics knowledge base")
    parser.add_argument("--dir", type=str, required=True, help="Directory containing markdown files")

    formatters = discover_formatters()
    mode_choices = list(formatters.keys())
    mode_help = "Formatting mode: " + " | ".join(mode_choices)

    parser.add_argument("--mode", type=str,
                        choices=mode_choices,
                        help=mode_help)
    parser.add_argument("--backup", action="store_true", help="Create .bak files before modifying")
    parser.add_argument("--dry-run", action="store_true", help="Report files that would change without writing them")
    parser.add_argument("--toc-lines", type=int, default=600, help="Number of lines to extract as TOC (default: 600)")

    args = parser.parse_args(argv)

    if not args.mode:
        print("未指定转换模式。检测到以下已存在的格式修改方案：")
        for i, m in enumerate(mode_choices, 1):
            print(f"{i}. {m}")
        print("0. 都不适用，创建新规则")

        while True:
            try:
                choice = input("请选择要调用的方案序号 (0-N): ")
                choice_idx = int(choice)
                if choice_idx == 0:
                    return _launch_rule_builder(args.dir, args.backup, args.dry_run, args.toc_lines)
                if 1 <= choice_idx <= len(mode_choices):
                    args.mode = mode_choices[choice_idx - 1]
                    break
                else:
                    print(f"无效序号，请输入 0 到 {len(mode_choices)} 之间的数字。")
            except ValueError:
                print("无效输入，请输入数字。")

    return 0 if run_formatter(args.dir, args.mode, args.backup, dry_run=args.dry_run) else 1


def _launch_rule_builder(dir_path: str, backup: bool, dry_run: bool, toc_lines: int):
    """Interactive Rule Builder: generate a new formatter via LLM."""
    from .rule_builder import RuleBuilder

    name = input("请输入新格式化器的名称 (英文, 如 beijing-algebra): ").strip()
    if not name:
        print("名称不能为空。")
        return 1

    try:
        rb = RuleBuilder(target_dir=Path(dir_path), name=name, toc_lines=toc_lines)
    except ValueError as e:
        print(f"错误: {e}")
        return 1

    # Phase 1: Heading rules
    max_retries = 3
    phase1_code = None
    for attempt in range(max_retries):
        print(f"\n[Phase 1] 正在从第一个 .md 文件提取目录 (前{toc_lines}行)...")
        print("正在发送到 LLM 分析目录结构...")
        try:
            code = rb.phase1_heading_rules()
        except Exception as e:
            print(f"LLM 调用失败: {e}")
            return 1

        is_valid, error = rb._validate_code(code)
        if not is_valid:
            print(f"⚠️  生成的代码无效: {error}")
            if attempt < max_retries - 1:
                print("正在重新生成...")
                continue
            else:
                print("已达最大重试次数，请手动编写格式化器。")
                return 1

        print("\n✅ LLM 已生成标题规则。请审核：")
        print("─" * 60)
        print(code)
        print("─" * 60)

        choice = input("\n确认使用这些规则? [Y/n/r(重新生成)]: ").strip().lower()
        if choice in ('', 'y', 'yes'):
            phase1_code = code
            break
        elif choice == 'r':
            continue
        else:
            print("已取消。")
            return 0

    if phase1_code is None:
        print("已达最大重试次数。")
        return 1

    # Phase 2: Beautification rules
    phase2_code = None
    for attempt in range(max_retries):
        print(f"\n[Phase 2] 正在提取第一个 H1 章节内容...")
        print("正在发送到 LLM 生成美化规则...")
        try:
            code = rb.phase2_beautification_rules(phase1_code)
        except Exception as e:
            print(f"LLM 调用失败: {e}")
            return 1

        is_valid, error = rb._validate_code(code)
        if not is_valid:
            print(f"⚠️  生成的代码无效: {error}")
            if attempt < max_retries - 1:
                print("正在重新生成...")
                continue
            else:
                print("跳过美化规则，仅使用标题规则。")
                phase2_code = phase1_code
                break

        print("\n✅ LLM 已添加美化规则。请审核：")
        print("─" * 60)
        print(code)
        print("─" * 60)

        choice = input("\n确认? [Y/n/r(重新生成)]: ").strip().lower()
        if choice in ('', 'y', 'yes'):
            phase2_code = code
            break
        elif choice == 'r':
            continue
        else:
            print("跳过美化规则，仅使用标题规则。")
            phase2_code = phase1_code
            break

    # Save and run
    final_code = phase2_code or phase1_code
    saved_path = rb._save_formatter(final_code)
    mode_name = name.replace("_", "-")
    print(f"\n✅ 已保存: {saved_path}")
    print(f"✅ 已注册模式: {mode_name}")
    print(f"\n正在以 dry-run 模式运行新格式化器...")

    return 0 if run_formatter(dir_path, mode_name, backup, dry_run=True) else 1


def run_formatter(dir_path: str, mode: str, backup: bool = False, dry_run: bool = False):
    root = Path(dir_path).expanduser().resolve()
    formatters = discover_formatters()
    logger.info(f"Starting formatter on {root} with mode={mode}, dry_run={dry_run}")

    if not root.exists():
        logger.error(f"Invalid path: {root}")
        return False

    if mode not in formatters:
        logger.error(f"Unknown mode: {mode}. Available: {', '.join(formatters.keys())}")
        return False

    formatter = formatters[mode]()

    processed_count = 0
    updated_count = 0

    if root.is_file():
        files = [root] if root.suffix.lower() == '.md' else []
    else:
        files = root.rglob("*.md")

    for p in files:
        if any(part.startswith('.') for part in p.parts):
            continue

        processed_count += 1
        success = formatter.process_file(p, backup=backup, dry_run=dry_run)
        if success:
            updated_count += 1

    action = "would update" if dry_run else "updated"
    logger.info(f"Formatting complete. Processed {processed_count} files, {action} {updated_count} files.")
    return True


if __name__ == "__main__":
    raise SystemExit(main())
