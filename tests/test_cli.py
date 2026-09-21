import pytest

from openbenchmarks_document_processing.cli import build_parser, main


def test_lists_workflow(capsys):
    assert main(["list-workflows"]) == 0
    assert "redline-parsing" in capsys.readouterr().out


def test_full_run_requires_approval(tmp_path):
    args = build_parser().parse_args([
        "run", "--arms", "oracle", "--full", "--run-dir", str(tmp_path / "run")
    ])
    assert args.full is True
    with pytest.raises(SystemExit, match="require --approve-full"):
        main(["run", "--arms", "oracle", "--full", "--run-dir", str(tmp_path / "run")])


def test_rejects_private_reference_arm():
    try:
        build_parser().parse_args(["smoke", "--arms", "accepted"])
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("accepted must not be exposed by the public CLI")
