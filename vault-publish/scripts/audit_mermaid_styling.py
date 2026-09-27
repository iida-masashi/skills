# -*- coding: utf-8 -*-
"""
VaultおよびQuartz内の全MarkdownドキュメントにおけるMermaidダイアグラムのアクセシビリティ監査スクリプト。
ダークテーマ下でノードの白文字（color:#ffffff）が担保されているかを機械的に検証する。
"""
import re
import sys
from pathlib import Path

def audit_mermaid_styling(vault_path: str) -> int:
    vault = Path(vault_path)
    md_files = sorted([f for f in vault.rglob("*.md") if not any(x in str(f) for x in [".git", ".trash", "sources"])])
    
    issues_found = 0
    pattern_block = re.compile(r"```mermaid\s*\n(.*?)\n```", re.DOTALL)
    node_pattern = re.compile(r'^\s*([A-Za-z0-9_]+)\["([^"]+)"\]', re.MULTILINE)
    
    for f in md_files:
        content = f.read_text(encoding="utf-8")
        blocks = pattern_block.findall(content)
        for b_idx, block in enumerate(blocks, 1):
            nodes = node_pattern.findall(block)
            unstyled = [nid for nid, label in nodes if "color:#ffffff" not in label and "color: #ffffff" not in label]
            if unstyled:
                issues_found += len(unstyled)
                rel = f.relative_to(vault)
                print(f"[ISSUE] {rel} (Diagram #{b_idx}): {len(unstyled)} nodes lack color:#ffffff styling ({unstyled})")
                
    if issues_found == 0:
        print("All Mermaid diagrams are 100% compliant with high-contrast accessibility standards!")
    else:
        print(f"Total unstyled Mermaid nodes found: {issues_found}")
        
    return issues_found

if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else r"D:\Vault\cosme"
    res = audit_mermaid_styling(target)
    sys.exit(0 if res == 0 else 1)
