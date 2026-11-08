import json

from conftest import load


def test_env_file_config_goes_to_environ_and_credentials_stay_private(tmp_path, monkeypatch):
    env_file = tmp_path / "agent.env"
    env_file.write_text("# comment\nANTHROPIC_API_KEY=sk-ant-from-file-123456\nUTA_REPEAT=5\nUTA_MODEL=\n")
    monkeypatch.setenv("UTA_ENV_FILE", str(env_file))
    for key in ("ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN", "UTA_REPEAT", "UTA_MODEL"):
        monkeypatch.delenv(key, raising=False)

    pipeline = load("pipeline")

    assert pipeline.os.environ["UTA_REPEAT"] == "5"
    assert pipeline.DEFAULTS["repeat"] == 5
    assert "ANTHROPIC_API_KEY" not in pipeline.os.environ
    assert "UTA_MODEL" not in pipeline.os.environ
    assert pipeline.auth_available() == "ANTHROPIC_API_KEY"


def test_shell_credential_wins_over_env_file(tmp_path, monkeypatch):
    env_file = tmp_path / "agent.env"
    env_file.write_text("ANTHROPIC_API_KEY=\n")
    monkeypatch.setenv("UTA_ENV_FILE", str(env_file))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-from-shell-123456")

    pipeline = load("pipeline")

    assert pipeline.secret_env() == {"ANTHROPIC_API_KEY": "sk-ant-from-shell-123456"}


def test_redact_removes_key_values_and_credential_patterns(tmp_path, monkeypatch):
    monkeypatch.setenv("UTA_ENV_FILE", str(tmp_path / "none.env"))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "super-secret-value-42")
    pipeline = load("pipeline")
    out = tmp_path / "out"
    (out / "transcript").mkdir(parents=True)
    (out / "report.json").write_text(json.dumps({"summary": "key super-secret-value-42"}))
    (out / "transcript/s.jsonl").write_text("ghp_" + "a" * 30 + "\n")
    (out / "agent-stderr.log").write_text("clean\n")

    assert pipeline.redact(out) == 2
    assert "super-secret" not in (out / "report.json").read_text()
    assert "ghp_" not in (out / "transcript/s.jsonl").read_text()


def test_local_run_fails_when_the_agent_could_not_run(tmp_path, monkeypatch):
    monkeypatch.setenv("UTA_ENV_FILE", str(tmp_path / "none.env"))
    pipeline = load("pipeline")
    (tmp_path / "decision.json").write_text(json.dumps({"run_agent": True}))
    (tmp_path / "agent-status.json").write_text(json.dumps({"ran": False, "reason": "no model credentials"}))
    assert pipeline.local_exit_code(tmp_path) == 2

    (tmp_path / "agent-status.json").write_text(json.dumps({"ran": True, "exit_code": 0}))
    (tmp_path / "verify.json").write_text(json.dumps({"status": "failed"}))
    assert pipeline.local_exit_code(tmp_path) == 4

    (tmp_path / "verify.json").write_text(json.dumps({"status": "passed"}))
    assert pipeline.local_exit_code(tmp_path) == 0


def test_gate_stage_fails_closed_on_encoded_secret_in_patch(tmp_path, monkeypatch):
    import base64
    secret = "sk-ant-api03-very-secret-value-0123456789"
    monkeypatch.setenv("UTA_ENV_FILE", str(tmp_path / "none.env"))
    monkeypatch.setenv("ANTHROPIC_API_KEY", secret)
    pipeline = load("pipeline")
    for leaked in (secret, secret[::-1], base64.b64encode(b"xy" + secret.encode()).decode(), secret.encode().hex()):
        assert pipeline.secret_leaks(f"+X = '{leaked}'\n"), leaked
    assert pipeline.secret_leaks("+assert True\n") == []

    out = tmp_path / "out"
    (out / "head/backend/tests").mkdir(parents=True)
    (out / "workspace/backend/tests").mkdir(parents=True)
    encoded = base64.b64encode(secret.encode()).decode()
    (out / "workspace/backend/tests/test_x.py").write_text(f"X = '{encoded}'\n")

    class Args:
        pass
    args = Args()
    args.out = out
    gate = pipeline.stage_gate(args)

    assert gate["accepted"] is False
    assert "credential" in gate["problems"][0]
    assert (out / "agent.patch").read_text() == ""
