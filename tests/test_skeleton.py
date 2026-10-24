import subprocess

from conftest import REPO


def git_head_or_dev():
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True, timeout=10
        )
    except OSError:
        return "dev"
    commit = result.stdout.strip()
    return commit if result.returncode == 0 and commit else "dev"


def test_health_says_ok(start_service):
    service = start_service()
    status, content_type, body = service.request("GET", "/health")
    assert status == 200
    assert content_type == "application/json"
    assert body == {"status": "ok"}


def test_build_id_is_the_runtime_candidate_when_set(start_service):
    service = start_service({"FACTORY_RUNTIME_CANDIDATE": "cand-123"})
    status, content_type, body = service.request("GET", "/build-id")
    assert status == 200
    assert content_type == "application/json"
    assert body == {"build_id": "cand-123"}


def test_build_id_is_the_git_commit_without_a_candidate(start_service):
    service = start_service(drop_env=["FACTORY_RUNTIME_CANDIDATE"])
    status, _, body = service.request("GET", "/build-id")
    assert status == 200
    assert body == {"build_id": git_head_or_dev()}


def test_empty_candidate_falls_back_to_the_git_commit(start_service):
    service = start_service({"FACTORY_RUNTIME_CANDIDATE": ""})
    status, _, body = service.request("GET", "/build-id")
    assert status == 200
    assert body == {"build_id": git_head_or_dev()}


def test_unknown_path_is_a_json_404(start_service):
    service = start_service()
    status, content_type, body = service.request("GET", "/nope")
    assert status == 404
    assert content_type == "application/json"
    assert isinstance(body["error"], str)


def test_other_methods_are_a_json_404(start_service):
    service = start_service()
    for method in ("POST", "PUT", "DELETE", "PATCH", "FOO"):
        status, content_type, body = service.request(method, "/health")
        assert status == 404, method
        assert content_type == "application/json", method
        assert isinstance(body["error"], str), method


def test_data_file_is_never_created(start_service):
    service = start_service()
    assert service.request("GET", "/health")[0] == 200
    assert service.request("GET", "/build-id")[0] == 200
    assert not service.data_path.exists()
