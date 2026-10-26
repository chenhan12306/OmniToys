"""
PowerRename Module for OmniToys.
Replicates Microsoft PowerToys PowerRename with:
- Search & Replace (simple and regular expressions)
- Match case, match all occurrences
- Target options: Name only, Extension only, Name + Extension
- Case transformation (Uppercase, Lowercase, Title Case, Capitalize)
- Numbering and enumeration
- Real-time preview and safe batch renaming with Undo support
"""

import os
import re
from typing import Dict, Any, List, Optional, Tuple
from ..base_module import ToyModule


class RenameRule:
    def __init__(
        self,
        search_pattern: str = "",
        replace_with: str = "",
        use_regex: bool = False,
        match_case: bool = False,
        match_all: bool = True,
        apply_to: str = "name_only",  # "name_only", "ext_only", "full"
        text_formatting: str = "none",  # "none", "uppercase", "lowercase", "title_case", "capitalize"
        add_enumeration: bool = False,
        enum_start: int = 1,
        enum_padding: int = 1,  # padding digits, e.g. 2 -> "01", 3 -> "001"
        enum_placement: str = "suffix"  # "prefix", "suffix"
    ):
        self.search_pattern = search_pattern
        self.replace_with = replace_with
        self.use_regex = use_regex
        self.match_case = match_case
        self.match_all = match_all
        self.apply_to = apply_to
        self.text_formatting = text_formatting
        self.add_enumeration = add_enumeration
        self.enum_start = enum_start
        self.enum_padding = enum_padding
        self.enum_placement = enum_placement


class PowerRenameModule(ToyModule):
    def __init__(self):
        super().__init__(
            module_id="power_rename",
            name="批量重命名 (PowerRename)",
            description="微软 PowerToys 同款高级文件批量重命名工具。支持正则替换、大小写智能转换、自动编号与实时重命名预览。",
            icon="rename"
        )
        self.undo_stack: List[List[Tuple[str, str]]] = []  # List of [(new_path, old_path)]

    def default_config(self) -> Dict[str, Any]:
        return {
            "enabled": True,
            "default_regex": False,
            "default_apply_to": "name_only"
        }

    def start(self):
        pass

    def stop(self):
        pass

    def get_state(self) -> Dict[str, Any]:
        return {
            "undo_available": len(self.undo_stack) > 0,
            "undo_depth": len(self.undo_stack)
        }

    def scan_directory(self, folder_path: str, recursive: bool = False) -> List[Dict[str, Any]]:
        """Scans a directory and returns file metadata."""
        if not os.path.exists(folder_path) or not os.path.isdir(folder_path):
            return []

        results = []
        try:
            if recursive:
                for root, _, files in os.walk(folder_path):
                    for f in files:
                        full_path = os.path.join(root, f)
                        name, ext = os.path.splitext(f)
                        results.append({
                            "full_path": full_path,
                            "original_name": f,
                            "name_without_ext": name,
                            "ext": ext,
                            "dir": root
                        })
            else:
                for item in sorted(os.listdir(folder_path)):
                    full_path = os.path.join(folder_path, item)
                    if os.path.isfile(full_path):
                        name, ext = os.path.splitext(item)
                        results.append({
                            "full_path": full_path,
                            "original_name": item,
                            "name_without_ext": name,
                            "ext": ext,
                            "dir": folder_path
                        })
        except Exception as e:
            print(f"[PowerRename] Error scanning {folder_path}: {e}")
        return results

    def compute_preview(self, items: List[Dict[str, Any]], rule_dict: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Computes renamed names for files based on the given rule."""
        rule = RenameRule(**rule_dict)
        preview_list = []
        counter = rule.enum_start

        for item in items:
            orig = item["original_name"]
            name_part = item["name_without_ext"]
            ext_part = item["ext"]

            new_name_part = name_part
            new_ext_part = ext_part

            # Target handling: name_only, ext_only, full
            if rule.apply_to == "name_only":
                target_str = name_part
            elif rule.apply_to == "ext_only":
                # strip leading dot for transformation
                target_str = ext_part[1:] if ext_part.startswith(".") else ext_part
            else:
                target_str = orig

            # Apply Search & Replace
            if rule.search_pattern:
                transformed = self._apply_search_replace(target_str, rule)
            else:
                transformed = target_str

            # Apply Text Formatting
            transformed = self._apply_formatting(transformed, rule.text_formatting)

            # Reconstruct filename
            if rule.apply_to == "name_only":
                new_name_part = transformed
            elif rule.apply_to == "ext_only":
                new_ext_part = f".{transformed}" if transformed else ""
            else:
                # full name replaced
                new_name_part, new_ext_part = os.path.splitext(transformed)

            # Apply Enumeration
            if rule.add_enumeration:
                num_str = str(counter).zfill(rule.enum_padding)
                counter += 1
                if rule.enum_placement == "prefix":
                    new_name_part = f"{num_str}_{new_name_part}"
                else:
                    new_name_part = f"{new_name_part}_{num_str}"

            final_name = f"{new_name_part}{new_ext_part}"
            changed = (final_name != orig)

            preview_list.append({
                "full_path": item["full_path"],
                "dir": item["dir"],
                "original_name": orig,
                "new_name": final_name,
                "changed": changed,
                "selected": changed
            })

        return preview_list

    def _apply_search_replace(self, text: str, rule: RenameRule) -> str:
        pattern = rule.search_pattern
        repl = rule.replace_with
        flags = 0 if rule.match_case else re.IGNORECASE
        count = 0 if rule.match_all else 1

        if rule.use_regex:
            try:
                return re.sub(pattern, repl, text, count=count, flags=flags)
            except Exception:
                return text
        else:
            if not rule.match_case:
                # Case-insensitive string replacement using regex escape
                esc_pat = re.escape(pattern)
                return re.sub(esc_pat, repl, text, count=count, flags=re.IGNORECASE)
            else:
                if rule.match_all:
                    return text.replace(pattern, repl)
                else:
                    return text.replace(pattern, repl, 1)

    def _apply_formatting(self, text: str, formatting: str) -> str:
        if formatting == "uppercase":
            return text.upper()
        elif formatting == "lowercase":
            return text.lower()
        elif formatting == "title_case":
            return text.title()
        elif formatting == "capitalize":
            return text.capitalize()
        return text

    def execute_rename(self, rename_tasks: List[Dict[str, str]]) -> Dict[str, Any]:
        """
        Executes safe file renaming on disk.
        rename_tasks: [{'full_path': '...', 'dir': '...', 'new_name': '...'}, ...]
        """
        success_count = 0
        errors = []
        applied_undo_steps: List[Tuple[str, str]] = []

        for task in rename_tasks:
            old_path = task.get("full_path")
            folder = task.get("dir")
            new_name = task.get("new_name")
            if not old_path or not folder or not new_name:
                continue

            new_path = os.path.join(folder, new_name)
            if old_path == new_path:
                continue

            # Check target collision
            if os.path.exists(new_path) and os.path.abspath(old_path) != os.path.abspath(new_path):
                errors.append(f"目标文件已存在: {new_name}")
                continue

            try:
                os.rename(old_path, new_path)
                applied_undo_steps.append((new_path, old_path))
                success_count += 1
            except Exception as e:
                errors.append(f"重命名失败 '{os.path.basename(old_path)}': {e}")

        if applied_undo_steps:
            self.undo_stack.append(applied_undo_steps)

        return {
            "status": "ok" if not errors else "partial",
            "success_count": success_count,
            "errors": errors,
            "undo_available": len(self.undo_stack) > 0
        }

    def undo_last_rename(self) -> Dict[str, Any]:
        """Rolls back the last executed batch rename."""
        if not self.undo_stack:
            return {"status": "error", "message": "没有可撤销的重命名记录"}

        last_batch = self.undo_stack.pop()
        reverted_count = 0
        errors = []

        # Process in reverse order
        for new_path, old_path in reversed(last_batch):
            if os.path.exists(new_path):
                try:
                    os.rename(new_path, old_path)
                    reverted_count += 1
                except Exception as e:
                    errors.append(f"撤销失败 '{os.path.basename(new_path)}': {e}")

        return {
            "status": "ok",
            "reverted_count": reverted_count,
            "errors": errors,
            "undo_available": len(self.undo_stack) > 0
        }

    def handle_action(self, action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if action == "scan":
            folder = payload.get("folder", "")
            recursive = payload.get("recursive", False)
            files = self.scan_directory(folder, recursive=recursive)
            return {"status": "ok", "files": files}

        elif action == "preview":
            items = payload.get("items", [])
            rules = payload.get("rules", {})
            preview = self.compute_preview(items, rules)
            return {"status": "ok", "preview": preview}

        elif action == "apply":
            tasks = payload.get("tasks", [])
            res = self.execute_rename(tasks)
            return res

        elif action == "undo":
            return self.undo_last_rename()

        return {"status": "unknown_action"}
