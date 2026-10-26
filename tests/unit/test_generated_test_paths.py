"""Generated test file names must be unique per source path."""

from __future__ import annotations

from pathlib import Path

from ai_test_assistant.test_generator import generated_test_path_for


def test_same_stem_sources_get_distinct_names(tmp_path: Path) -> None:
    output_dir = tmp_path / "tests" / "generated"
    (tmp_path / "app").mkdir()
    (tmp_path / "lib").mkdir()
    app_models = tmp_path / "app" / "models.py"
    lib_models = tmp_path / "lib" / "models.py"
    app_models.write_text("", encoding="utf-8")
    lib_models.write_text("", encoding="utf-8")

    app_path = generated_test_path_for(app_models, output_dir, tmp_path)
    lib_path = generated_test_path_for(lib_models, output_dir, tmp_path)

    assert app_path != lib_path
    assert app_path.name == "test_app_models_generated.py"
    assert lib_path.name == "test_lib_models_generated.py"


def test_root_level_source_keeps_simple_name(tmp_path: Path) -> None:
    source = tmp_path / "calculator.py"
    source.write_text("", encoding="utf-8")

    path = generated_test_path_for(source, tmp_path / "out", tmp_path)

    assert path.name == "test_calculator_generated.py"


def test_source_outside_repo_falls_back_to_file_name(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    outside = tmp_path / "elsewhere" / "util.py"
    outside.parent.mkdir()
    outside.write_text("", encoding="utf-8")

    path = generated_test_path_for(outside, repo / "out", repo)

    assert path.name == "test_util_generated.py"
