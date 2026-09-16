"""Failure injection for write-once transfer and permission isolation."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("pricing_phase1", ROOT / "azure_databricks/scripts/phase1.py")
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


class MemoryFiles:
    def __init__(self):
        self.files = {}
        self.writes = 0
        self.fail_at = None

    def read(self, path):
        return self.files.get(path)

    def create(self, path, data):
        self.writes += 1
        if self.writes == self.fail_at:
            raise OSError("injected transfer interruption")
        if path in self.files:
            raise FileExistsError(path)
        self.files[path] = data


class TransferTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = MemoryFiles()
        entries = []
        for name, data, partition in [("src/example.py", b"print('ok')\n", "runtime"),
                                      ("artifacts/features.parquet", b"PAR1\0test", "restricted")]:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            entries.append({"path": name, "bytes": len(data), "sha256": p.digest(data),
                            "hash_mode": "raw_bytes", "partition": partition})
        self.plan = {"files": entries, "file_count": 2, "total_bytes": sum(e["bytes"] for e in entries),
                     "roots": {"runtime": "/Volumes/c/pricing_ml/r/release", "restricted": "/Volumes/c/pricing_bronze/r/release"},
                     "source_manifest": {"files": entries}, "phase0_manifest_sha256": "abc", "release_id": "release"}

    def test_complete_and_identical_rerun(self):
        result = p.transfer(self.store, self.root, self.plan)
        self.assertEqual(result["verified_files"], 2)
        self.assertEqual(result["objects_created"], 5)
        self.assertEqual(p.transfer(self.store, self.root, self.plan)["objects_created"], 0)

    def test_interrupted_transfer_has_no_pointer_and_resumes(self):
        self.store.fail_at = 4
        with self.assertRaises(OSError):
            p.transfer(self.store, self.root, self.plan)
        self.assertFalse(any(x.endswith("_VERIFIED.json") for x in self.store.files))
        self.store.fail_at = None
        self.assertEqual(p.transfer(self.store, self.root, self.plan)["verified_files"], 2)

    def test_remote_corruption_fails_without_overwrite(self):
        p.transfer(self.store, self.root, self.plan)
        path = self.plan["roots"]["runtime"] + "/src/example.py"
        self.store.files[path] = b"different content"
        with self.assertRaisesRegex(RuntimeError, "mismatched"):
            p.reconcile(self.store, self.plan)
        with self.assertRaisesRegex(RuntimeError, "mismatched"):
            p.transfer(self.store, self.root, self.plan)
        self.assertEqual(self.store.files[path], b"different content")

    def test_missing_remote_dependency_fails(self):
        p.transfer(self.store, self.root, self.plan)
        del self.store.files[self.plan["roots"]["restricted"] + "/artifacts/features.parquet"]
        with self.assertRaisesRegex(RuntimeError, "mismatched"):
            p.reconcile(self.store, self.plan)

    def test_local_corruption_fails_before_remote_writes(self):
        (self.root / "src/example.py").write_bytes(b"changed")
        with self.assertRaisesRegex(RuntimeError, "mismatch"):
            p.transfer(self.store, self.root, self.plan)
        self.assertEqual(self.store.writes, 0)

    def test_local_missing_file_fails_before_remote_writes(self):
        (self.root / "src/example.py").unlink()
        with self.assertRaises(FileNotFoundError):
            p.transfer(self.store, self.root, self.plan)
        self.assertEqual(self.store.writes, 0)

    def test_conflicting_manifest_fails_before_data_upload(self):
        self.store.files[self.plan["roots"]["restricted"] + "/_source_manifest.json"] = b"other release"
        with self.assertRaisesRegex(RuntimeError, "collision"):
            p.transfer(self.store, self.root, self.plan)

    def test_canonical_text_is_uploaded_as_exact_lf_bytes(self):
        entry = self.plan["files"][0]
        entry["hash_mode"] = "canonical_utf8_lf"
        (self.root / entry["path"]).write_bytes(b"print('ok')\r\n")
        p.transfer(self.store, self.root, self.plan)
        self.assertEqual(self.store.files[self.plan["roots"]["runtime"] + "/" + entry["path"]], b"print('ok')\n")

    def test_path_traversal_and_secrets_rejected(self):
        for path in ("../secret", "/etc/passwd", "src/../secret", "src\\bad.py", "C:/secret", ".env", "src/.env", "src//x.py"):
            with self.subTest(path=path), self.assertRaises(RuntimeError):
                p.safe_path(path)

    def test_pointer_not_written_if_readback_fails(self):
        original = self.store.create
        def corrupt(path, data):
            original(path, data)
            if path.endswith("example.py"):
                self.store.files[path] = b"broken upload"
        self.store.create = corrupt
        with self.assertRaises(RuntimeError):
            p.transfer(self.store, self.root, self.plan)
        self.assertFalse(any(x.endswith("_VERIFIED.json") for x in self.store.files))

    def test_runtime_has_no_raw_input_or_write_grants(self):
        cfg = json.loads(p.CONFIG_PATH.read_text())
        matrix = p.grant_matrix(cfg)
        for (kind, name), grants in matrix.items():
            if "pricing_bronze" in name:
                self.assertNotIn(cfg["app_application_id"], grants)
            if cfg["app_application_id"] in grants:
                self.assertNotIn("WRITE_VOLUME", grants[cfg["app_application_id"]])
            self.assertNotIn(cfg["negative_test_application_id"], grants)

    def test_missing_file_in_published_release_is_not_silently_repaired(self):
        p.transfer(self.store, self.root, self.plan)
        path = self.plan["roots"]["runtime"] + "/src/example.py"
        del self.store.files[path]
        with self.assertRaisesRegex(RuntimeError, "mismatched"):
            p.transfer(self.store, self.root, self.plan)
        self.assertNotIn(path, self.store.files)

    def test_verify_requires_publish_pointer(self):
        p.transfer(self.store, self.root, self.plan)
        del self.store.files[self.plan["roots"]["runtime"] + "/_VERIFIED.json"]
        with self.assertRaisesRegex(RuntimeError, "pointer"):
            p.verify_published(self.store, self.plan)

    def test_verify_requires_original_manifests(self):
        p.transfer(self.store, self.root, self.plan)
        self.store.files[self.plan["roots"]["restricted"] + "/_source_manifest.json"] = b"invalid"
        with self.assertRaisesRegex(RuntimeError, "manifest mismatch"):
            p.verify_published(self.store, self.plan)

    def test_concurrent_identical_upload_is_safe(self):
        def concurrent(path, data):
            self.store.files[path] = data
            raise FileExistsError(path)
        self.store.create = concurrent
        self.assertTrue(p.write_once(self.store, "/test", b"same"))

    def test_concurrent_different_upload_fails(self):
        def concurrent(path, data):
            self.store.files[path] = b"different"
            raise FileExistsError(path)
        self.store.create = concurrent
        with self.assertRaises(FileExistsError):
            p.write_once(self.store, "/test", b"same")

    def test_sealed_release_plan(self):
        cfg = json.loads(p.CONFIG_PATH.read_text())
        plan = p.make_plan(ROOT, cfg)
        self.assertEqual(plan["file_count"], 204)
        self.assertEqual(sum(x["partition"] == "restricted" for x in plan["files"]), 8)
        self.assertFalse(plan["compute_started"])


if __name__ == "__main__":
    unittest.main()
