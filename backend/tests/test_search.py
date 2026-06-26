import pytest
from datetime import date, timedelta
import json
from app.config import Settings
from app.schemas import JobSearchRequest
from app.search import BLOCKED_SOURCES, SEARCH_SOURCES, NvidiaAPIError, _search_region, canonical_url, is_actual_job_url, merge_payloads, normalize, search_jobs

def test_canonical_url_removes_tracking():
    assert canonical_url("https://Jobs.Example.com/role/1/?utm_source=x#apply") == "https://jobs.example.com/role/1"

def test_canonical_url_rejects_non_http():
    with pytest.raises(ValueError): canonical_url("javascript:alert(1)")

def test_normalize_deduplicates_and_sorts():
    base = {"title":"Engineer","company":"Acme","location":"Remote","work_mode":"Remote","employment_type":"Full-time","salary":None,"experience":None,"posted_at":None,"skills":["Python"],"summary":"Build systems.","match_reason":"Relevant skills.","source":"Acme","apply_url":"https://acme.test/jobs/1"}
    result = normalize({"jobs":[dict(base,match_score=65),dict(base,match_score=90)],"searched_sources":["Acme"],"query_expansion":[]},15)
    assert result.total == 1
    assert result.jobs[0].match_score == 65

def test_normalize_cleans_literal_null_values():
    raw = {"title":"Engineer","company":"Acme","location":"Remote","work_mode":"null","employment_type":"null","salary":"null","experience":None,"posted_at":None,"skills":["Python"],"summary":"Build systems.","match_score":80,"match_reason":"Relevant skills.","source":"Acme","apply_url":"https://acme.test/jobs/2"}
    job = normalize({"jobs":[raw],"searched_sources":[],"query_expansion":[]}, 15).jobs[0]
    assert job.work_mode == "Not specified"
    assert job.employment_type == "Not specified"
    assert job.salary is None

def test_merge_payloads_combines_regional_results_and_metadata():
    merged = merge_payloads([
        {"jobs":[{"id":1}],"searched_sources":["Indeed"],"query_expansion":["Python Engineer"]},
        {"jobs":[{"id":2}],"searched_sources":["Indeed","Naukri"],"query_expansion":["Python Engineer","Django Developer"]},
    ])
    assert len(merged["jobs"]) == 2
    assert merged["searched_sources"] == ["Indeed", "Naukri"]
    assert merged["query_expansion"] == ["Python Engineer", "Django Developer"]

def test_normalize_rejects_undated_and_old_jobs_when_freshness_is_required():
    base = {"title":"Engineer","company":"Acme","location":"Remote","work_mode":"Remote","employment_type":"Full-time","salary":None,"experience":None,"skills":["Python"],"summary":"Build systems.","match_score":80,"match_reason":"Relevant skills.","source":"Acme"}
    fresh = dict(base, posted_at=date.today().isoformat(), apply_url="https://acme.test/jobs/fresh")
    old = dict(base, title="Old Engineer", posted_at=(date.today()-timedelta(days=8)).isoformat(), apply_url="https://acme.test/jobs/old")
    undated = dict(base, title="Undated Engineer", posted_at=None, apply_url="https://acme.test/jobs/undated")
    result = normalize({"jobs":[fresh, old, undated],"searched_sources":[],"query_expansion":[]}, 10, max_age_days=7)
    assert [job.title for job in result.jobs] == ["Engineer"]


@pytest.mark.asyncio
async def test_nvidia_search_uses_chat_completions_and_guided_json():
    payload = {"jobs": [], "searched_sources": [], "query_expansion": ["Python Engineer"]}

    class Response:
        status_code = 200
        def json(self):
            return {"choices": [{"message": {"content": json.dumps(payload)}}]}

    class Client:
        async def post(self, path, json):
            assert path == "chat/completions"
            assert json["model"] == "nvidia/nemotron-3-super-120b-a12b"
            assert json["messages"][0]["content"].startswith("You are CvolvePro")
            assert "Jobicy" not in json["messages"][0]["content"]
            assert "Himalayas" not in json["messages"][0]["content"]
            assert "LinkedIn" in json["messages"][1]["content"]
            assert "blocked_sources" in json["messages"][1]["content"]
            assert json["response_format"] == {"type": "json_object"}
            assert json["chat_template_kwargs"] == {"thinking": False}
            assert json["nvext"]["guided_json"]["type"] == "object"
            return Response()

    result = await _search_region(
        Client(),
        JobSearchRequest(query="Python developer", location="Pune"),
        Settings(nvidia_api_key="test"),
        "Pune, India",
    )
    assert result == payload


def test_allowed_sources_exclude_blocked_platforms():
    for source in BLOCKED_SOURCES:
        assert source not in SEARCH_SOURCES
    assert "LinkedIn" in SEARCH_SOURCES
    assert "Remote OK" in SEARCH_SOURCES
    assert "Dice" in SEARCH_SOURCES

def test_actual_job_url_filter_rejects_platform_search_pages():
    assert is_actual_job_url("LinkedIn", "https://www.linkedin.com/jobs/view/123")
    assert not is_actual_job_url("LinkedIn", "https://www.linkedin.com/jobs/search/?keywords=python")
    assert is_actual_job_url("Dice", "https://www.dice.com/job-detail/abc")
    assert not is_actual_job_url("Indeed", "https://www.indeed.com/jobs?q=python")


@pytest.mark.asyncio
async def test_search_jobs_prefers_live_verified_jobs(monkeypatch):
    request = JobSearchRequest(query="Python developer")
    expected = normalize({"jobs":[{
        "title":"Python Developer",
        "company":"Acme",
        "location":"Remote",
        "work_mode":"Remote",
        "employment_type":"Full-time",
        "salary":None,
        "experience":None,
        "posted_at":date.today().isoformat(),
        "skills":["Python"],
        "summary":"Build backend systems.",
        "match_score":90,
        "match_reason":"Strong fit.",
        "source":"NVIDIA NIM",
        "apply_url":"https://acme.test/jobs/python"
    }], "searched_sources":["NVIDIA NIM"], "query_expansion":["Python developer"]}, 10)

    async def fake_nvidia(*_):
        raise AssertionError("NVIDIA should not run when verified live jobs are available")

    async def fake_live(*_):
        return expected

    monkeypatch.setattr("app.search.search_jobs_with_nvidia", fake_nvidia)
    monkeypatch.setattr("app.search.search_live_job_boards", fake_live)
    monkeypatch.setattr("app.search.discover_allowed_platform_links", lambda *_: (_ for _ in ()).throw(ValueError("skip discovery")))
    result = await search_jobs(request, Settings(nvidia_api_key="test"))
    assert result.total == 1
    assert result.jobs[0].source == "NVIDIA NIM"


@pytest.mark.asyncio
async def test_search_jobs_keeps_live_results_when_nvidia_key_is_invalid(monkeypatch):
    async def fake_nvidia(*_):
        raise NvidiaAPIError("bad key", 401)

    live = normalize({"jobs":[{
        "title":"Python Developer",
        "company":"Acme",
        "location":"Remote",
        "work_mode":"Remote",
        "employment_type":"Full-time",
        "salary":None,
        "experience":None,
        "posted_at":date.today().isoformat(),
        "skills":["Python"],
        "summary":"Build backend systems.",
        "match_score":90,
        "match_reason":"Strong fit.",
        "source":"Dice",
        "apply_url":"https://www.dice.com/job-detail/python"
    }], "searched_sources":["Dice"], "query_expansion":["Python developer"]}, 10)

    async def fake_live(*_):
        return live

    monkeypatch.setattr("app.search.search_jobs_with_nvidia", fake_nvidia)
    monkeypatch.setattr("app.search.search_live_job_boards", fake_live)
    monkeypatch.setattr("app.search.discover_allowed_platform_links", lambda *_: (_ for _ in ()).throw(NvidiaAPIError("bad key", 401)))
    result = await search_jobs(JobSearchRequest(query="Python developer"), Settings(nvidia_api_key="bad"))
    assert result.total == 1
    assert result.jobs[0].source == "Dice"
