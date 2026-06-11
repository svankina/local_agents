"""Create bench/sandbox/work-<task>/ fixture repos. Usage: python3 make_sandbox.py <task-id> -> prints workdir."""

import pathlib
import shutil
import sys

FIXTURES = {
    "fix-test": {
        "calc/__init__.py": "",
        "calc/ops.py": "def add(a, b):\n    return a - b  # bug\n\ndef mul(a, b):\n    return a * b\n",
        "test_ops.py": "from calc.ops import add, mul\n\ndef test_add():\n    assert add(2, 3) == 5\n\ndef test_mul():\n    assert mul(2, 3) == 6\n",
        "TASK.md": "The test suite fails. Find and fix the bug. Do not change the tests.",
    },
    "bulk-rename": {
        "app/db.py": "def fetch_record(rid):\n    return {'id': rid}\n",
        "app/api.py": "from app.db import fetch_record\n\ndef get(rid):\n    return fetch_record(rid)\n",
        "app/cli.py": "from app.db import fetch_record\n\nif __name__ == '__main__':\n    import sys; print(fetch_record(sys.argv[1]))\n",
        "app/__init__.py": "",
        "TASK.md": "Rename the function fetch_record to load_record everywhere in this repo, updating all callers.",
    },
    "csv-script": {
        "sales.csv": "region,amount\nwest,120\neast,80\nwest,200\nsouth,50\n",
        "TASK.md": "Write a script sum_by_region.py that reads sales.csv and prints each region with its total amount, one 'region,total' line per region, sorted by region name.",
    },
    "code-qa": {
        "pipeline.py": "import queue\n\nclass Router:\n    def __init__(self, workers):\n        self.q = queue.Queue(maxsize=64)\n        self.workers = workers\n\n    def dispatch(self, event):\n        if event.get('priority') == 'high':\n            self.workers[0].handle(event)\n        else:\n            self.q.put(event, timeout=5)\n",
        "TASK.md": "Answer in ANSWERS.md: 1) What happens to a high-priority event? 2) What is the queue's maxsize? 3) What exception risk exists in dispatch for normal events?",
    },
    "add-flag": {
        "tool.py": "import sys\n\ndef main(argv):\n    name = argv[1] if len(argv) > 1 else 'world'\n    print(f'hello {name}')\n\nif __name__ == '__main__':\n    main(sys.argv)\n",
        "TASK.md": "Add a --shout flag to tool.py: when passed anywhere in argv, output is uppercased. Flag must not be treated as the name.",
    },
}


def main():
    task = sys.argv[1]
    root = pathlib.Path(__file__).parent / "sandbox" / f"work-{task}"
    if root.exists():
        shutil.rmtree(root)
    for rel, content in FIXTURES[task].items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
    print(root)


if __name__ == "__main__":
    main()
