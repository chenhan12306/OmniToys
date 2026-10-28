"""
PowerRename Module for OmniToys.
Replicates Microsoft PowerToys PowerRename with:
- Search & Replace (simple and regular expressions)
- Match case, match all occurrences
- Target options: Name only, Extension only, Name + Extension
- Case transformation (Uppercase, Lowercase, Title Case, Capitalize)
- Numbering and enumeration
- Real-time preview and safe batch renaming with Undo support

Safety additions:
- Rejects path separators / invalid Windows names / reserved device names
- Verifies the source really lives inside the selected folder
- Two-phase rename (source -> temp -> target), so case-only renames and
  chained renames (A->B, B->C) both work and can be rolled back.
"""

import os
import re
import uuid
from typing import Dict, Any, List, Optional, Tuple
from ..base_module import ToyModule

_INVALID_WIN_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def is_safe_basename(name: str) -> bool:
    """True when *name* is a single, valid Windows file name component."""
    if not name or name in (".", ".."):
        return False
    if os.path.basename(name) != name:
        return False
    if _INVALID_WIN_CHARS.search(name):
        return False
    if name.endswith((" ", ".")):
        return False
    stem = name.split(".")[0].strip().upper()
    if stem in _RESERVED_NAMES:
        return False
    return True


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
        enum_placement: str = "suffix",  # "prefix", "suffix"
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
            icon="rename",
        )
        # List of batches, each batch is [(new_path, old_path)]
        self.undo_stack: List[List[Tuple[str, str]]] = []

    def default_config(self) -> Dict[str, Any]:
        return {
            "enabled": True,
            "default_regex": False,
            "default_apply_to": "name_only",
        }

    def start(self):
        pass

    def stop(self):
        pass

    def get_state(self) -> Dict[str, Any]:
        return {
            "undo_available": len(self.undo_stack) > 0,
            "undo_depth": len(self.undo_stack),
        }

    # ------------------------------------------------------------------ scan
    def scan_directory(
        self, folder_path: str, recursive: bool = False
    ) -> List[Dict[str, Any]]:
        """Scans a directory and returns file metadata."""
        if not folder_path or not os.path.isdir(folder_path):
            return []

        results: List[Dict[str, Any]] = []
        try:
            if recursive:
                for root, _, files in os.walk(folder_path):
                    for f in files:
                        full_path = os.path.join(root, f)
                        name, ext = os.path.splitext(f)
                        results.append(
                            {
                                "full_path": full_path,
                                "original_name": f,
                                "name_without_ext": name,
                                "ext": ext,
                                "dir": root,
                            }
                        )
            else:
                for item in sorted(os.listdir(folder_path)):
                    full_path = os.path.join(folder_path, item)
                    if os.path.isfile(full_path):
                        name, ext = os.path.splitext(item)
                        results.append(
                            {
                                "full_path": full_path,
                                "original_name": item,
                                "name_without_ext": name,
                                "ext": ext,
                                "dir": folder_path,
                            }
                        )
        except Exception as e:
            print(f"[PowerRename] Error scanning {folder_path}: {e}")
        return results

    # --------------------------------------------------------------- preview
    def compute_preview(
        self, items: List[Dict[str, Any]], rule_dict: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Computes renamed names for files based on the given rule."""
        rule = RenameRule(**rule_dict)
        preview_list: List[Dict[str, Any]] = []
        counter = rule.enum_start

        for item in items:
            orig = item["original_name"]
            name_part = item["name_without_ext"]
            ext_part = item["ext"]

            new_name_part = name_part
            new_ext_part = ext_part

            if rule.apply_to == "name_only":
                target_str = name_part
            elif rule.apply_to == "ext_only":
                target_str = ext_part[1:] if ext_part.startswith(".") else ext_part
            else:
                target_str = orig

            if rule.search_pattern:
                transformed = self._apply_search_replace(target_str, rule)
            else:
                transformed = target_str

            transformed = self._apply_formatting(transformed, rule.text_formatting)

            if rule.apply_to == "name_only":
                new_name_part = transformed
            elif rule.apply_to == "ext_only":
                new_ext_part = f".{transformed}" if transformed else ""
            else:
                new_name_part, new_ext_part = os.path.splitext(transformed)

            if rule.add_enumeration:
                num_str = str(counter).zfill(max(1, rule.enum_padding))
                counter += 1
                if rule.enum_placement == "prefix":
                    new_name_part = f"{num_str}_{new_name_part}"
                else:
                    new_name_part = f"{new_name_part}_{num_str}"

            final_name = f"{new_name_part}{new_ext_part}"
            changed = final_name != orig
            valid = is_safe_basename(final_name)

            preview_list.append(
                {
                    "full_path": item["full_path"],
                    "dir": item["dir"],
                    "original_name": orig,
                    "new_name": final_name,
                    "changed": changed,
                    "valid": valid,
                    "selected": changed and valid,
                }
            )

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

        if not rule.match_case:
            try:
                return re.sub(
                    re.escape(pattern), lambda _m: repl, text, count=count, flags=re.IGNORECASE
                )
            except Exception:
                return text
        if rule.match_all:
            return text.replace(pattern, repl)
        return text.replace(pattern, repl, 1)

    def _apply_formatting(self, text: str, formatting: str) -> str:
        if formatting == "uppercase":
            return text.upper()
        if formatting == "lowercase":
            return text.lower()
        if formatting == "title_case":
            return text.title()
        if formatting == "capitalize":
            return text.capitalize()
        return text

    # ---------------------------------------------------------------- rename
    def _prepare_tasks(
        self, rename_tasks: List[Dict[str, Any]]
    ) -> Tuple[List[Dict[str, Any]], List[str]]:
        """Validates tasks and returns normalized source/target paths."""
        prepared: List[Dict[str, Any]] = []
        errors: List[str] = []
        seen_sources = set()
        seen_targets = set()

        for task in rename_tasks:
            old_raw = task.get("full_path")
            new_name = task.get("new_name")
            folder = task.get("dir") or (os.path.dirname(old_raw) if old_raw else "")
            if not old_raw or not new_name or not folder:
                continue

            folder_abs = os.path.abspath(folder)
            old_abs = os.path.abspath(old_raw)

            try:
                if os.path.normcase(os.path.commonpath([folder_abs, old_abs])) != os.path.normcase(folder_abs):
                    errors.append(f"源文件不在目标文件夹内: {old_raw}")
                    continue
            except ValueError:
                errors.append(f"源文件与目标文件夹不在同一磁盘: {old_raw}")
                continue

            if not is_safe_basename(new_name):
                errors.append(f"非法的新文件名: {new_name}")
                continue

            new_abs = os.path.join(folder_abs, new_name)
            old_key = os.path.normcase(old_abs)
            new_key = os.path.normcase(new_abs)

            if old_key == new_key and old_abs == new_abs:
                continue  # nothing to do
            if old_key in seen_sources:
                errors.append(f"重复的源文件: {old_raw}")
                continue
            if not os.path.exists(old_abs):
                errors.append(f"源文件不存在: {old_raw}")
                continue
            if new_key in seen_targets:
                errors.append(f"多个文件会重命名为同一名称: {new_name}")
                continue

            seen_sources.add(old_key)
            seen_targets.add(new_key)
            prepared.append(
                {
                    "old": old_abs,
                    "new": new_abs,
                    "old_key": old_key,
                    "new_key": new_key,
                    "folder": folder_abs,
                    "name": new_name,
                }
            )

        # A target may exist only when it is one of the sources that will move away.
        source_keys = {t["old_key"] for t in prepared}
        allowed: List[Dict[str, Any]] = []
        for task in prepared:
            if os.path.exists(task["new"]) and task["new_key"] != task["old_key"]:
                if task["new_key"] not in source_keys:
                    errors.append(f"目标文件已存在: {task['name']}")
                    continue
            allowed.append(task)
        return allowed, errors

    def _two_phase_rename(
        self, operations: List[Tuple[str, str]], folder_of: Dict[str, str]
    ) -> Tuple[List[Tuple[str, str]], List[str]]:
        """
        Moves every source to a unique temp name, then temp -> destination.
        Returns ([(destination, source)], errors).
        """
        temp_pairs: List[Tuple[str, str, str]] = []  # (source, temp, destination)
        errors: List[str] = []

        for source, destination in operations:
            folder = folder_of.get(source, os.path.dirname(source))
            temp = os.path.join(folder, f".omnitoys_tmp_{uuid.uuid4().hex}")
            try:
                os.rename(source, temp)
                temp_pairs.append((source, temp, destination))
            except Exception as exc:
                errors.append(f"重命名失败 '{os.path.basename(source)}': {exc}")

        completed: List[Tuple[str, str]] = []
        for source, temp, destination in temp_pairs:
            try:
                os.rename(temp, destination)
                completed.append((destination, source))
            except Exception as exc:
                errors.append(f"重命名失败 '{os.path.basename(destination)}': {exc}")
                try:
                    if not os.path.exists(source):
                        os.rename(temp, source)
                except Exception:
                    pass

        return completed, errors

    def execute_rename(self, rename_tasks: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Executes safe file renaming on disk with two-phase moves + undo."""
        tasks, errors = self._prepare_tasks(rename_tasks)
        folder_of = {t["old"]: t["folder"] for t in tasks}
        completed, move_errors = self._two_phase_rename(
            [(t["old"], t["new"]) for t in tasks], folder_of
        )
        errors.extend(move_errors)

        if completed:
            self.undo_stack.append(completed)
        if len(self.undo_stack) > 50:
            self.undo_stack.pop(0)

        return {
            "status": "ok" if not errors else "partial",
            "success_count": len(completed),
            "errors": errors,
            "undo_available": len(self.undo_stack) > 0,
        }

    def undo_last_rename(self) -> Dict[str, Any]:
        """Rolls back the last executed batch rename."""
        if not self.undo_stack:
            return {"status": "error", "message": "没有可撤销的重命名记录"}

        last_batch = self.undo_stack.pop()
        operations: List[Tuple[str, str]] = []
        errors: List[str] = []

        for new_path, old_path in reversed(last_batch):
            if not os.path.exists(new_path):
                errors.append(f"文件已不存在: {new_path}")
                continue
            if os.path.exists(old_path) and os.path.normcase(old_path) != os.path.normcase(new_path):
                errors.append(f"原文件名已被占用: {os.path.basename(old_path)}")
                continue
            operations.append((new_path, old_path))

        folder_of = {source: os.path.dirname(source) for source, _ in operations}
        reverted, move_errors = self._two_phase_rename(operations, folder_of)
        errors.extend(move_errors)
        reverted_count = len(reverted)
        if reverted_count:
            self.undo_stack.append([(new, old) for old, new in reverted])

        return {
            "status": "ok" if not errors else "partial",
            "reverted_count": reverted_count,
            "errors": errors,
            "undo_available": len(self.undo_stack) > 0,
        }

    # ---------------------------------------------------------------- actions
    def handle_action(self, action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if action == "scan":
            folder = payload.get("folder", "")
            recursive = bool(payload.get("recursive", False))
            files = self.scan_directory(folder, recursive=recursive)
            return {"status": "ok", "files": files}

        elif action == "preview":
            items = payload.get("items", [])
            rules = payload.get("rules", {})
            try:
                preview = self.compute_preview(items, rules)
            except Exception as exc:
                return {"status": "error", "message": str(exc)}
            return {"status": "ok", "preview": preview}

        elif action == "apply":
            tasks = payload.get("tasks", [])
            return self.execute_rename(tasks)

        elif action == "undo":
            return self.undo_last_rename()

        return {"status": "unknown_action"}
