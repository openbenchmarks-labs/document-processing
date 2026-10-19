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


def test_full_run_defaults_to_three_by_three_with_separate_judge():
    args = build_parser().parse_args(["run", "--arms", "oracle", "--full"])
    assert (args.repeats, args.asks) == (3, 3)
    assert args.model != args.judge_model


def test_smoke_defaults_to_single_shot():
    args = build_parser().parse_args(["smoke", "--arms", "oracle"])
    assert (args.repeats, args.asks) == (1, 1)


def test_resume_reruns_arms_with_unscored_answers(tmp_path, monkeypatch):
    import json

    from openbenchmarks_document_processing import cli

    calls = []
    run_dir = tmp_path / "run"
    run_dir.mkdir()

    def fake_run_arm(arm, *_args, **_kwargs):
        calls.append(arm)
        return {"arm": arm, "score": {"unscored": 0}, "rows": [], "cost": {}}

    monkeypatch.setattr(cli.dataset, "fetch", lambda *_a, **_k: tmp_path)
    monkeypatch.setattr(cli.dataset, "load", lambda *_a, **_k: ([], {}))
    monkeypatch.setattr(cli, "make_llm_client", lambda: None)
    monkeypatch.setattr(cli.runner, "run_arm", fake_run_arm)
    monkeypatch.setattr(cli.runner, "derive", lambda *_a, **_k: {"ranking": []})
    main(["smoke", "--arms", "oracle,blind", "--run-dir", str(run_dir)])
    result = json.loads((run_dir / "result.json").read_text())
    result["arms"][0]["score"]["unscored"] = 2   # oracle lost two answers
    (run_dir / "result.json").write_text(json.dumps(result))
    calls.clear()
    main(["smoke", "--arms", "oracle,blind", "--run-dir", str(run_dir)])
    assert calls == ["oracle"]
    arms = json.loads((run_dir / "result.json").read_text())["arms"]
    assert sorted(a["arm"] for a in arms) == ["blind", "oracle"]
