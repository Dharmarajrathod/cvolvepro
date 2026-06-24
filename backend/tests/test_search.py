import pytest
from datetime import date, timedelta
import json
from app.config import Settings
from app.schemas import JobSearchRequest
from app.search import _search_region, canonical_url, merge_payloads, normalize

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
