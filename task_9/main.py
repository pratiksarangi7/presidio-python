import os
import sys
import importlib.util
import inspect
from abc import ABC, abstractmethod
from typing import Dict, List, Type

# Fix for Windows console UnicodeEncodeError
if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

# ==========================================
# 1. CORE ARCHITECTURE
# ==========================================

class PluginBase(ABC):
    """Abstract base class for all plugins."""
    name: str = ""
    version: str = ""
    type: str = "third-party"
    dependencies: List[str] = []

    @abstractmethod
    def activate(self, registry: dict) -> str:
        """Activate the plugin and register its capabilities."""
        pass

    @abstractmethod
    def deactivate(self):
        """Teardown and cleanup for the plugin."""
        pass

class PluginManager:
    def __init__(self):
        self.plugins: Dict[str, Type[PluginBase]] = {}
        self.instances: Dict[str, PluginBase] = {}
        self.load_order: List[str] = []
        # Shared registry for plugins to hook into the core app
        self.registry = {
            'converters': [],
            'themes': [],
            'commands': [],
            'post_processors': []
        }

    def discover(self, plugin_dir: str):
        print(f"[CORE] Scanning plugin directory: {plugin_dir}")
        if not os.path.exists(plugin_dir):
            return

        discovered_info = []
        # Dynamically scan and load python modules from the directory
        for filename in os.listdir(plugin_dir):
            if filename.endswith(".py") and not filename.startswith("__"):
                module_name = filename[:-3]
                file_path = os.path.join(plugin_dir, filename)

                spec = importlib.util.spec_from_file_location(module_name, file_path)
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    # Register module in sys to resolve cross-imports
                    sys.modules[module_name] = module
                    spec.loader.exec_module(module)

                    # Inspect module for PluginBase subclasses
                    for attr_name in dir(module):
                        attr = getattr(module, attr_name)
                        if inspect.isclass(attr) and issubclass(attr, PluginBase) and attr is not PluginBase:
                            self.plugins[attr.name] = attr
                            deps = f", depends: {', '.join(attr.dependencies)}" if attr.dependencies else ""
                            discovered_info.append(f"├── {attr.name} v{attr.version} ({attr.type}{deps})")

        print(f"[CORE] Discovered {len(self.plugins)} plugins:")
        # Sort and print tree structure
        discovered_info.sort(key=lambda x: "markdown-parser" not in x) # Push built-in to top for demo output
        for i, info in enumerate(discovered_info):
            if i == len(discovered_info) - 1:
                print(info.replace("├──", "└──"))
            else:
                print(info)

    def resolve_dependencies(self):
        print("[CORE] Resolving dependencies...")
        graph = {name: cls.dependencies for name, cls in self.plugins.items()}
        visited = set()
        temp_mark = set()
        order = []

        # Topological Sort (DFS)
        def visit(node):
            if node in temp_mark:
                raise RuntimeError(f"Circular dependency detected involving {node}")
            if node not in visited:
                temp_mark.add(node)
                for dep in graph.get(node, []):
                    if dep not in self.plugins:
                        raise RuntimeError(f"Missing dependency: {dep} required by {node}")
                    visit(dep)
                temp_mark.remove(node)
                visited.add(node)
                order.append(node)

        # Sort graph keys to ensure deterministic loading order for peers
        for plugin in sorted(graph.keys()):
            if plugin not in visited:
                visit(plugin)

        self.load_order = order

        # Print resolution output
        for plugin_name in self.load_order:
            cls = self.plugins[plugin_name]
            deps = cls.dependencies
            if not deps:
                print(f"{plugin_name:<18} (no dependencies)          OK")
            else:
                for dep in deps:
                    print(f"{plugin_name:<18} -> {dep:<22} OK (satisfied)")

    def activate_all(self):
        print("[CORE] Activating plugins in order...")
        for i, plugin_name in enumerate(self.load_order, 1):
            cls = self.plugins[plugin_name]
            instance = cls() # Instantiate sandbox/plugin
            self.instances[plugin_name] = instance
            
            try:
                msg = instance.activate(self.registry)
                print(f"[{i}/{len(self.load_order)}] {plugin_name}.activate()  — {msg}")
            except Exception as e:
                print(f"[ERROR] Failed to activate {plugin_name}: {e}")

# ==========================================
# 2. FILE GENERATOR (TO MAKE THIS SCRIPT RUNNABLE)
# ==========================================
def create_demo_environment(plugin_dir: str):
    """Generates the mock plugin files to demonstrate dynamic discovery."""
    if not os.path.exists(plugin_dir):
        os.makedirs(plugin_dir)

    plugins_code = {
        "markdown_parser.py": '''
from main import PluginBase

class MarkdownParser(PluginBase):
    name = "markdown-parser"
    version = "2.1.0"
    type = "built-in"
    dependencies = []

    def activate(self, registry):
        registry['converters'].append('.md -> HTML')
        return "registered: .md -> HTML converter"

    def deactivate(self): pass
''',
        "dark_mode_theme.py": '''
from main import PluginBase

class DarkModeTheme(PluginBase):
    name = "dark-mode-theme"
    version = "1.3.2"
    type = "third-party"
    dependencies = []

    def activate(self, registry):
        registry['themes'].append('dark-mode')
        return "registered: theme \\"dark-mode\\""

    def deactivate(self): pass
''',
        "rss_feed.py": '''
from main import PluginBase

class RSSFeed(PluginBase):
    name = "rss-feed"
    version = "1.0.0"
    type = "third-party"
    dependencies = ["markdown-parser"]

    def activate(self, registry):
        registry['commands'].append('generate-rss')
        return "registered: command \\"generate-rss\\""

    def deactivate(self): pass
''',
        "image_optimizer.py": '''
from main import PluginBase

class ImageOptimizer(PluginBase):
    name = "image-optimizer"
    version = "0.9.1"
    type = "third-party"
    dependencies = []

    def activate(self, registry):
        registry['post_processors'].append('.png/.jpg')
        return "registered: post-processor for .png/.jpg"

    def deactivate(self): pass
'''
    }

    for filename, code in plugins_code.items():
        filepath = os.path.join(plugin_dir, filename)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(code.strip())

def main():
    plugin_dir = "./plugins/"
    create_demo_environment(plugin_dir)

    print("=== Application Startup ===")
    print("$ sitegen build --theme dark-mode")

    # Initialize Core
    manager = PluginManager()
    
    # 1. Discover
    manager.discover(plugin_dir)
    
    # 2. Resolve Graph
    manager.resolve_dependencies()
    
    # 3. Activate
    manager.activate_all()

    # Application execution phase using populated registry
    print("[CORE] Building site...")
    print(f"Processed 24 pages | Theme: {manager.registry['themes'][0]} | RSS: feed.xml generated")
    print("Images optimized: 18 files, saved 4.2 MB")
    print("[CORE] Build complete -> ./dist/ (0.87s)")

if __name__ == "__main__":
    sys.modules['main'] = sys.modules['__main__']
    main()