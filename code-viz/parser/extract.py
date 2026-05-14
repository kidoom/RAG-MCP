#!/usr/bin/env python3
"""AST-based metadata extractor for Modular RAG MCP Server.

Walks src/ directory, parses every .py file, and outputs a single JSON document
containing module dependencies, class hierarchies, factory registries, and call flows.

Usage:
    python parser/extract.py [--output metadata.json]
"""

import ast
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

ROOT = Path(__file__).resolve().parent.parent.parent
SRC = ROOT / "src"

# Known package roots (no "src." prefix in imports)
PKG_ROOTS = {"core", "libs", "ingestion", "mcp_server", "observability", "dashboard"}


def file_to_module(filepath: Path) -> str:
    """Convert a .py file path to its dotted module name (relative to src/)."""
    try:
        rel = filepath.resolve().relative_to(SRC.resolve())
    except ValueError:
        return ""
    parts = list(rel.parts)
    if parts[-1] == "__init__.py":
        parts = parts[:-1]
    else:
        parts[-1] = parts[-1].replace(".py", "")
    return ".".join(parts)


def resolve_import(module_name: str, current_module: str, level: int = 0) -> Optional[str]:
    """Resolve a potentially relative import to an absolute module name.

    Handles:
      - Absolute: 'src.core.types' -> 'core.types'
      - Absolute without src: 'core.types' -> 'core.types'
      - Relative: level=1, name='dense_retriever' from 'core.query_engine.hybrid_search'
        -> 'core.query_engine.dense_retriever'
      - Builtins/third-party: return None
    """
    # Strip leading 'src.' prefix if present
    if module_name and module_name.startswith("src."):
        module_name = module_name[4:]

    # Relative import
    if level > 0:
        parts = current_module.split(".")
        if level > len(parts):
            return None
        base = ".".join(parts[:-level])
        return f"{base}.{module_name}" if module_name else base

    # Absolute import — only keep if it starts with a known package root
    if module_name:
        top = module_name.split(".")[0]
        if top in PKG_ROOTS:
            return module_name
    return None


class ModuleVisitor(ast.NodeVisitor):
    """Walk a single .py file AST to extract structural metadata."""

    def __init__(self, module_id: str, filepath: str, package: str):
        self.module_id = module_id
        self.filepath = filepath
        self.package = package
        self.imports: List[str] = []
        self.classes: List[Dict] = []
        self.functions: List[Dict] = []
        self.docstring: str = ""
        self._current_class: Optional[str] = None

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            resolved = resolve_import(alias.name, self.module_id)
            if resolved:
                self.imports.append(resolved)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        module = node.module or ""
        level = node.level or 0
        resolved = resolve_import(module, self.module_id, level)
        if resolved:
            self.imports.append(resolved)
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef):
        prev = self._current_class
        self._current_class = node.name
        bases = []
        for base in node.bases:
            if isinstance(base, ast.Name):
                bases.append(base.id)
            elif isinstance(base, ast.Attribute):
                bases.append(ast.unparse(base))

        methods: List[str] = []
        method_calls: List[Dict] = []
        all_calls: List[str] = []
        for item in node.body:
            if isinstance(item, ast.FunctionDef):
                methods.append(item.name)
                call_visitor = CallExtractor(self.module_id)
                call_visitor.visit(item)
                ordered = list(dict.fromkeys(call_visitor.calls))
                method_calls.append({"name": item.name, "calls": ordered})
                all_calls.extend(call_visitor.calls)

        doc = ast.get_docstring(node) or ""
        self.classes.append({
            "name": node.name,
            "bases": bases,
            "methods": methods,
            "method_calls": method_calls,
            "calls": sorted(set(all_calls)),
            "docstring": doc[:200],
        })
        self.generic_visit(node)
        self._current_class = prev

    def visit_FunctionDef(self, node: ast.FunctionDef):
        if self._current_class is None:
            call_visitor = CallExtractor(self.module_id)
            call_visitor.visit(node)
            ordered = list(dict.fromkeys(call_visitor.calls))
            self.functions.append({
                "name": node.name,
                "calls": ordered,
            })
        self.generic_visit(node)


class CallExtractor(ast.NodeVisitor):
    """Extract calls to known project classes/methods from a function body."""

    def __init__(self, current_module: str):
        self.current_module = current_module
        self.calls: List[str] = []

    def visit_Call(self, node: ast.Call):
        target = None
        if isinstance(node.func, ast.Name):
            target = node.func.id
        elif isinstance(node.func, ast.Attribute):
            if isinstance(node.func.value, ast.Name):
                target = f"{node.func.value.id}.{node.func.attr}"
            elif isinstance(node.func.value, ast.Attribute):
                # chain like: self.retriever.search()
                target = ast.unparse(node.func)
        if target:
            self.calls.append(target)
        self.generic_visit(node)


class FactoryDetector(ast.NodeVisitor):
    """Detect factory registrations and the import map they create."""

    def __init__(self, filepath: str):
        self.filepath = filepath
        self.registrations: List[Tuple[str, str]] = []  # (key, class_name)
        self.base_class: Optional[str] = None

    def visit_ClassDef(self, node: ast.ClassDef):
        # Check if this is a Factory class
        if "Factory" in node.name:
            for item in ast.walk(node):
                # Look for: self._registry["key"] = ImplClass or registry["key"] = ImplClass
                if isinstance(item, ast.Assign):
                    for target in item.targets:
                        if isinstance(target, ast.Subscript):
                            if isinstance(target.slice, ast.Constant):
                                key = target.slice.value
                                if isinstance(item.value, ast.Call):
                                    if isinstance(item.value.func, ast.Name):
                                        self.registrations.append((key, item.value.func.id))
                                elif isinstance(item.value, ast.Name):
                                    self.registrations.append((key, item.value.id))
                # Also check for dict literal: _registry = {"key": Class, ...}
                if isinstance(item, ast.AnnAssign) or isinstance(item, ast.Assign):
                    if isinstance(item.value, ast.Dict):
                        for k, v in zip(item.value.keys, item.value.values):
                            if isinstance(k, ast.Constant) and isinstance(v, ast.Name):
                                self.registrations.append((str(k.value), v.id))
        self.generic_visit(node)


def parse_file(filepath: Path) -> Optional[Dict]:
    """Parse a single .py file and return its metadata."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            source = f.read()
        tree = ast.parse(source)
    except (SyntaxError, UnicodeDecodeError):
        return None

    module_id = file_to_module(filepath)
    if not module_id:
        return None
    package = module_id.split(".")[0]

    visitor = ModuleVisitor(module_id, str(filepath.relative_to(ROOT)), package)
    visitor.visit(tree)

    # Global docstring
    doc = ast.get_docstring(tree) or ""

    return {
        "id": module_id,
        "path": str(filepath.resolve().relative_to(ROOT)).replace("\\", "/"),
        "package": package,
        "imports": sorted(set(visitor.imports)),
        "classes": visitor.classes,
        "functions": visitor.functions,
        "docstring": doc[:200],
    }


def find_factories() -> Dict[str, Dict]:
    """Scan libs/ for factory files and extract registration tables."""
    factories = {}
    libs_dir = SRC / "libs"
    if not libs_dir.exists():
        return factories

    for factory_file in libs_dir.rglob("*_factory.py"):
        try:
            with open(factory_file, "r", encoding="utf-8") as f:
                source = f.read()
            tree = ast.parse(source)
        except (SyntaxError, UnicodeDecodeError):
            continue

        detector = FactoryDetector(str(factory_file))
        detector.visit(tree)

        # Determine provider category from file path
        # e.g., libs/llm/llm_factory.py -> llm
        rel = factory_file.resolve().relative_to(libs_dir.resolve())
        category = rel.parts[0] if len(rel.parts) > 1 else "unknown"

        if detector.registrations:
            factories[category] = {
                "file": str(factory_file.relative_to(ROOT)).replace("\\", "/"),
                "registrations": [
                    {"key": k, "class": v} for k, v in detector.registrations
                ],
            }

    return factories


def infer_origin_default_branch(root: Path) -> str:
    """Short branch name tracked by refs/remotes/origin/HEAD, else main."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), "symbolic-ref", "--short",
             "refs/remotes/origin/HEAD"],
            capture_output=True,
            text=True,
            timeout=8,
        )
        ref = (proc.stdout or "").strip()
        if proc.returncode == 0 and ref.startswith("origin/"):
            return ref.split("/", 1)[1].strip()
    except (OSError, subprocess.TimeoutExpired, IndexError):
        pass
    return "main"


def infer_github_dev_spec_markdown_url(root: Path) -> Tuple[Optional[str], str]:
    """Return (blob URL or None, branch used).

    Parses remote.origin.url for github.com HTTPS or git@ SSH.
    Supports optional user override via CODE_VIZ_DEV_SPEC_BRANCH env.
    """
    branch_override = (
        os.environ.get("CODE_VIZ_DEV_SPEC_BRANCH") or "").strip()
    branch = branch_override if branch_override else infer_origin_default_branch(
        root)

    try:
        proc = subprocess.run(
            ["git", "-C", str(root), "config", "--get", "remote.origin.url"],
            capture_output=True,
            text=True,
            timeout=8,
        )
        raw = (proc.stdout or "").strip()
        if proc.returncode != 0 or not raw:
            return None, branch
        ssh = re.match(r"git@github\.com:([^/]+)/([^/]+?)(?:\.git)?$", raw)
        https = re.match(
            r"https?://github\.com/([^/]+)/([^/#?]+)", raw)
        m = ssh or https
        if not m:
            return None, branch
        owner, repo = m.group(1), m.group(2).strip().rstrip("/")
        if repo.endswith(".git"):
            repo = repo[:-4]
        url = (
            f"https://github.com/{owner}/{repo}/blob/{branch}/DEV_SPEC.md")
        return url, branch
    except (OSError, subprocess.TimeoutExpired, IndexError):
        return None, branch


def build_call_flows(modules: List[Dict]) -> Dict[str, List[Dict]]:
    """Build query and ingestion call flow steps from parsed modules.

    This uses a semi-automated approach: find key pipeline modules and
    extract their internal method call order.
    """
    mod_map = {m["id"]: m for m in modules}

    # Query pipeline modules in expected order
    query_order = [
        "mcp_server.tools.query_knowledge_hub",
        "core.query_engine.query_processor",
        "core.query_engine.hybrid_search",
        "core.query_engine.dense_retriever",
        "core.query_engine.sparse_retriever",
        "libs.vector_store.chroma_store",
        "ingestion.storage.bm25_indexer",
        "core.query_engine.fusion",
        "core.query_engine.reranker",
        "core.response.response_builder",
    ]

    ingestion_order = [
        "ingestion.pipeline",
        "libs.loader.pdf_loader",
        "ingestion.chunking.document_chunker",
        "ingestion.transform.chunk_refiner",
        "ingestion.transform.metadata_enricher",
        "ingestion.transform.image_captioner",
        "ingestion.embedding.batch_processor",
        "ingestion.embedding.dense_encoder",
        "ingestion.embedding.sparse_encoder",
        "ingestion.storage.vector_upserter",
        "ingestion.storage.bm25_indexer",
    ]

    def build_steps(order, flow_name):
        steps = []
        for i, mod_id in enumerate(order):
            m = mod_map.get(mod_id)
            if not m:
                continue
            classes_info = []
            for cls in m.get("classes", []):
                classes_info.append({
                    "name": cls["name"],
                    "methods": cls.get("methods", []),
                    "calls": cls.get("calls", []),
                })
            steps.append({
                "step": i + 1,
                "module_id": mod_id,
                "path": m["path"],
                "package": m["package"],
                "classes": classes_info,
                "docstring": m.get("docstring", ""),
            })
        return steps

    return {
        "query": build_steps(query_order, "query"),
        "ingestion": build_steps(ingestion_order, "ingestion"),
    }


def build_provider_tree(modules: List[Dict], factories: Dict) -> Dict[str, List[Dict]]:
    """Build class hierarchy trees for each provider category."""
    # Map class name -> module info
    class_map: Dict[str, Dict] = {}
    for m in modules:
        for cls in m.get("classes", []):
            class_map[cls["name"]] = {
                "class_name": cls["name"],
                "module_id": m["id"],
                "path": m["path"],
                "package": m["package"],
                "bases": cls.get("bases", []),
                "methods": cls.get("methods", []),
                "is_abstract": "ABC" in cls.get("bases", []) or cls["name"].startswith("Base"),
            }

    provider_categories = {
        "llm": ["BaseLLM", "LLMFactory"],
        "embedding": ["BaseEmbedding", "EmbeddingFactory"],
        "vector_store": ["BaseVectorStore", "VectorStoreFactory"],
        "reranker": ["BaseReranker", "RerankerFactory"],
        "splitter": ["BaseSplitter", "SplitterFactory"],
        "evaluator": ["BaseEvaluator", "EvaluatorFactory"],
        "loader": ["BaseLoader"],
    }

    trees = {}
    for category, base_names in provider_categories.items():
        nodes = []
        edges = []
        base_class = None

        for base_name in base_names:
            if base_name in class_map:
                base_class = base_name
                break

        if not base_class:
            continue

        # Add base class as root
        base_info = class_map[base_class]
        nodes.append({
            "id": base_class,
            "label": base_class,
            "path": base_info["path"],
            "type": "abstract",
            "category": category,
        })

        # Find all subclasses
        for cls_name, info in class_map.items():
            if cls_name == base_class:
                continue
            for b in info["bases"]:
                if b == base_class or any(
                    b == bn for bn in base_names
                ):
                    nodes.append({
                        "id": cls_name,
                        "label": cls_name,
                        "path": info["path"],
                        "type": "concrete" if not info["is_abstract"] else "abstract",
                        "category": category,
                    })
                    edges.append({
                        "source": base_class,
                        "target": cls_name,
                    })
                    break

        # Add factory registrations as extra metadata
        factory_data = factories.get(category, {})
        for reg in factory_data.get("registrations", []):
            reg_node_id = f"reg:{category}:{reg['key']}"
            nodes.append({
                "id": reg_node_id,
                "label": f'"{reg["key"]}"',
                "path": factory_data.get("file", ""),
                "type": "registry",
                "category": category,
            })
            if reg["class"] in [n["id"] for n in nodes]:
                edges.append({
                    "source": reg_node_id,
                    "target": reg["class"],
                    "label": "instantiates",
                })

        if nodes:
            trees[category] = {"nodes": nodes, "edges": edges}

    return trees


def extract_mcp_from_ast() -> Tuple[List[Dict], Dict]:
    """Parse MCP tool specs from tools/__init__.py without importing project deps."""

    def literal_eval_node(node: ast.AST):
        if node is None:
            return None
        if isinstance(node, ast.Constant):
            return node.value
        src = ast.unparse(node)
        return ast.literal_eval(src)

    mcp_tools: List[Dict] = []
    tools_init = SRC / "mcp_server" / "tools" / "__init__.py"
    if tools_init.exists():
        tree = ast.parse(tools_init.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            ok = (isinstance(fn, ast.Name) and fn.id == "ToolSpec") or (
                isinstance(fn, ast.Attribute) and fn.attr == "ToolSpec"
            )
            if not ok:
                continue
            kw = {k.arg: k.value for k in node.keywords if k.arg}
            try:
                name = literal_eval_node(kw.get("name"))
                description = literal_eval_node(kw.get("description"))
                schema = literal_eval_node(kw.get("input_schema"))
                handler_node = kw.get("handler")
                handler_name = ""
                if isinstance(handler_node, ast.Name):
                    handler_name = handler_node.id
                if isinstance(name, str) and isinstance(description, str):
                    mcp_tools.append({
                        "name": name,
                        "description": description,
                        "input_schema": schema if isinstance(schema, dict) else {},
                        "handler_module": (
                            f"mcp_server.tools.{handler_name}" if handler_name else ""
                        ),
                        "handler_name": handler_name,
                    })
            except (SyntaxError, TypeError, ValueError):
                continue

    protocol_meta = {
        "protocol_version": "2024-11-05",
        "server_name": "modular-rag-mcp-server",
        "server_version": "0.1.0",
        "rpc_methods": [
            {"method": "initialize", "note": "Negotiate protocol version and server capabilities."},
            {"method": "tools/list", "note": "Return JSON Schema for each exposed tool."},
            {"method": "tools/call", "note": "Execute a tool by name with arguments object."},
        ],
    }
    proto_py = SRC / "mcp_server" / "protocol_handler.py"
    if proto_py.exists():
        ptree = ast.parse(proto_py.read_text(encoding="utf-8"))
        for node in ptree.body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1:
                t = node.targets[0]
                if isinstance(t, ast.Name):
                    try:
                        val = literal_eval_node(node.value)
                    except (SyntaxError, TypeError, ValueError):
                        continue
                    if t.id == "PROTOCOL_VERSION" and isinstance(val, str):
                        protocol_meta["protocol_version"] = val
                    elif t.id == "SERVER_NAME" and isinstance(val, str):
                        protocol_meta["server_name"] = val
                    elif t.id == "SERVER_VERSION" and isinstance(val, str):
                        protocol_meta["server_version"] = val

    return mcp_tools, protocol_meta


def main():
    output_path = ROOT / "code-viz" / "public" / "metadata.json"

    modules = []
    py_files = sorted(SRC.rglob("*.py"))

    for fp in py_files:
        # Skip __pycache__ and test directories
        if "__pycache__" in fp.parts:
            continue
        data = parse_file(fp)
        if data:
            modules.append(data)

    factories = find_factories()
    call_flows = build_call_flows(modules)
    provider_trees = build_provider_tree(modules, factories)

    # Build import edge list for module graph
    mod_ids = {m["id"] for m in modules}
    import_edges = []
    for m in modules:
        for imp in m["imports"]:
            if imp in mod_ids and imp != m["id"]:
                import_edges.append({
                    "source": m["id"],
                    "target": imp,
                })

    mcp_tools, protocol_meta = extract_mcp_from_ast()

    dev_spec_url: Optional[str]
    branch_for_spec: str
    dev_spec_url, branch_for_spec = infer_github_dev_spec_markdown_url(ROOT)

    code_viz: Dict[str, Any] = {}
    code_viz["origin_default_branch"] = branch_for_spec
    if dev_spec_url:
        code_viz["dev_spec_markdown_url"] = dev_spec_url

    result = {
        "modules": modules,
        "import_edges": import_edges,
        "call_flows": call_flows,
        "provider_trees": provider_trees,
        "factories": {
            k: {"file": v["file"], "registrations": v["registrations"]}
            for k, v in factories.items()
        },
        "mcp_tools": mcp_tools,
        "protocol": protocol_meta,
        "code_viz": code_viz,
        "stats": {
            "total_modules": len(modules),
            "total_classes": sum(len(m.get("classes", [])) for m in modules),
            "total_functions": sum(len(m.get("functions", [])) for m in modules),
            "total_import_edges": len(import_edges),
            "packages": sorted(set(m["package"] for m in modules)),
        },
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"Extracted: {result['stats']['total_modules']} modules, "
          f"{result['stats']['total_classes']} classes, "
          f"{len(call_flows['query'])} query steps, "
          f"{len(call_flows['ingestion'])} ingestion steps, "
          f"{len(provider_trees)} provider trees")
    print(f"Output: {output_path}")


if __name__ == "__main__":
    main()
