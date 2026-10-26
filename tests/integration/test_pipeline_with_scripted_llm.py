"""Pipeline behavior that a dry-run cannot show, because every dry-run answer is the same stub."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

from ai_test_assistant.config import load_config
from ai_test_assistant.pipeline import run_pr_assistant


class ScriptedLlm:
    """Answers like a well-behaved model: a passing test module per generation, and
    the existing test file plus one test named after the module per update."""

    def __init__(self) -> None:
        self.prompts: list[str] = []

    def generate(self, system_instruction: str, prompt: str) -> str:
        self.prompts.append(prompt)
        update = re.search(
            r"Production module: (\S+).*Existing test file content:\n```\n(.*)\n```",
            prompt,
            re.DOTALL,
        )
        if update is None:
            return "def test_generated():\n    assert True\n"
        module, existing_code = update.groups()
        return f"{existing_code}\n\n\ndef test_updated_for_{module.replace('.', '_')}():\n    assert True\n"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def _write(repo: Path, rel: str, text: str) -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture(autouse=True)
def _no_settings_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("BASE_REF", "OUTPUT_DIR", "SUGGESTIONS_DIR", "REPORT_PATH",
                 "REPAIR_ATTEMPTS", "UPDATE_EXISTING_TESTS", "DRY_RUN"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture()
def shop_repo(tmp_path: Path) -> Path:
    """A feature branch that changes pricing.py and checkout.py; tests/test_shop.py covers both."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "dev@example.com")
    _git(repo, "config", "user.name", "dev")
    _write(repo, "shop/__init__.py", "")
    _write(repo, "shop/pricing.py", "def net_price(amount):\n    return round(amount, 2)\n")
    _write(repo, "shop/checkout.py", "def total(amounts):\n    return sum(amounts)\n")
    _write(
        repo,
        "tests/test_shop.py",
        "from shop.checkout import total\nfrom shop.pricing import net_price\n\n\n"
        "def test_total():\n    assert total([net_price(1)]) == 1\n",
    )
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "base")
    _git(repo, "checkout", "-q", "-b", "feature")
    _write(
        repo,
        "shop/pricing.py",
        "def net_price(amount):\n    return round(amount, 2)\n\n\n"
        "def gross_price(amount, vat):\n    return round(amount * (1 + vat), 2)\n",
    )
    _write(
        repo,
        "shop/checkout.py",
        "def total(amounts):\n    return sum(amounts)\n\n\n"
        "def count(amounts):\n    return len(amounts)\n",
    )
    _git(repo, "commit", "-q", "-am", "feature")
    return repo


def test_a_test_file_shared_by_two_changed_files_keeps_both_updates(shop_repo: Path) -> None:
    config = load_config(repo_root=shop_repo, cli_overrides={"base_ref": "main"})

    result = run_pr_assistant(config, llm=ScriptedLlm())

    suggestion = shop_repo / "reports" / "suggested-tests" / "tests" / "test_shop.py"
    suggested_code = suggestion.read_text(encoding="utf-8")
    assert "def test_updated_for_shop_checkout" in suggested_code
    assert "def test_updated_for_shop_pricing" in suggested_code
    assert [r.suggested_test_files for r in result.file_results] == [[suggestion.resolve()]] * 2


def test_generated_tests_never_count_as_existing_tests(shop_repo: Path) -> None:
    # Left over from a previous local run; tests/generated is not committed.
    _write(
        shop_repo,
        "tests/generated/test_shop_checkout_generated.py",
        "from shop.checkout import total\n\n\ndef test_from_an_earlier_run():\n    assert total([]) == 0\n",
    )
    llm = ScriptedLlm()
    config = load_config(repo_root=shop_repo, cli_overrides={"base_ref": "main"})

    run_pr_assistant(config, llm=llm)

    assert not any("test_from_an_earlier_run" in prompt for prompt in llm.prompts)
    assert not (shop_repo / "reports" / "suggested-tests" / "tests" / "generated").exists()
