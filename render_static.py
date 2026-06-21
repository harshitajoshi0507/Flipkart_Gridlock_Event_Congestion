from pathlib import Path
from jinja2 import Environment, FileSystemLoader
import shutil

BASE = Path(__file__).parent
env = Environment(loader=FileSystemLoader(str(BASE / "templates")))
pages = ["index.html", "map.html", "predict.html", "analytics.html"]
OUT = BASE / "docs"
OUT.mkdir(exist_ok=True)

for p in pages:
    try:
        tpl = env.get_template(p)
        # Render with minimal context used by templates
        html = tpl.render(active="")
        (OUT / p).write_text(html, encoding="utf-8")
    except Exception as e:
        print(f"Warning: failed to render {p}: {e}")

# copy static folder
shutil.rmtree(OUT / "static", ignore_errors=True)
if (BASE / "static").exists():
    shutil.copytree(BASE / "static", OUT / "static")

print("Rendered static site to docs/")
