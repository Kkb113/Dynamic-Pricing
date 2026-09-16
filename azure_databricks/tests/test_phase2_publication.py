import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from databricks.sdk.errors import NotFound
from phase2_live import MARKER, materialize, object_snapshot


class FakeSQL:
    def __init__(self, mismatch=0):
        self.calls = []
        self.mismatch = mismatch

    def run(self, query):
        self.calls.append(query)
        if "EXCEPT ALL" in query:
            return [[str(self.mismatch)]]
        return [["5"]]


class PublicationTests(unittest.TestCase):
    def test_first_deployment_can_have_no_schemas(self):
        def missing(*args):
            raise NotFound("schema does not exist")
        self.assertEqual(object_snapshot(SimpleNamespace(tables=SimpleNamespace(list=missing))), {})

    def client(self, seal="seal", absent=False):
        def get(name):
            if absent:
                raise NotFound("missing")
            return SimpleNamespace(comment=MARKER, owner="admins", properties={"pricing.contract_seal": seal})
        return SimpleNamespace(tables=SimpleNamespace(get=get))

    def test_identical_rerun_never_writes(self):
        sql = FakeSQL()
        self.assertEqual(materialize(self.client(), sql, "cat.schema.t", "SELECT 1", "seal", "admins"), 5)
        self.assertFalse(any(q.startswith("CREATE") or q.startswith("ALTER") for q in sql.calls))

    def test_create_then_full_bidirectional_reconcile(self):
        sql = FakeSQL()
        materialize(self.client(absent=True), sql, "cat.schema.t", "SELECT 1", "seal", "admins")
        self.assertTrue(sql.calls[0].startswith("CREATE TABLE"))
        self.assertEqual(sql.calls[2].count("EXCEPT ALL"), 2)

    def test_changed_contract_fails_without_sql(self):
        sql = FakeSQL()
        with self.assertRaisesRegex(RuntimeError, "different contract"):
            materialize(self.client("old"), sql, "cat.schema.t", "SELECT 1", "seal", "admins")
        self.assertEqual(sql.calls, [])

    def test_corrupt_published_data_not_overwritten(self):
        sql = FakeSQL(mismatch=1)
        with self.assertRaisesRegex(RuntimeError, "content mismatch"):
            materialize(self.client(), sql, "cat.schema.t", "SELECT 1", "seal", "admins")
        self.assertFalse(any("REPLACE" in q or "INSERT" in q for q in sql.calls))

    def test_union_source_is_parenthesized_before_difference(self):
        sql = FakeSQL()
        materialize(self.client(), sql, "cat.schema.t", "SELECT 1 UNION ALL SELECT 2", "seal", "admins")
        self.assertEqual(sql.calls[0].count("FROM (SELECT 1 UNION ALL SELECT 2) AS expected_rows"), 2)


if __name__ == "__main__":
    unittest.main()
