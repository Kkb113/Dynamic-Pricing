import json

from audit.report_builder import load_test_evidence


def test_machine_generated_test_evidence_is_accepted_when_source_matches(tmp_path):
    path=tmp_path/"test_results.json"
    path.write_text(json.dumps({"source":"pytest_sessionfinish","status":"PASS","exit_code":0,"passed":56,"failed":0,"source_tree_sha256":"abc"}))
    evidence=load_test_evidence(path,"abc")
    assert evidence["status"]=="PASS" and evidence["passed"]==56


def test_test_evidence_is_rejected_when_source_tree_is_stale(tmp_path):
    path=tmp_path/"test_results.json"
    path.write_text(json.dumps({"source":"pytest_sessionfinish","status":"PASS","exit_code":0,"source_tree_sha256":"old"}))
    evidence=load_test_evidence(path,"new")
    assert evidence["status"]=="STALE"


def test_hand_authored_test_summary_is_rejected(tmp_path):
    path=tmp_path/"test_results.json"
    path.write_text(json.dumps({"status":"PASS","passed":999,"failed":0,"source_tree_sha256":"abc"}))
    evidence=load_test_evidence(path,"abc")
    assert evidence["status"]=="INVALID"
