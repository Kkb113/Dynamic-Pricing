"""Compare-and-check pricing aliases; no compute, deletion of versions or endpoint."""
import argparse
import json
from phase1 import CONFIG_PATH, Cloud, require
from phase3 import plan
from phase3_live import authentication


def operate(action, expected_current=None, target_version=None):
    from mlflow import MlflowClient
    cfg = json.loads(CONFIG_PATH.read_text())
    cloud = Cloud(cfg)
    name = plan()["model_name"]
    model = cloud.client.registered_models.get(name, include_aliases=True)
    current = next((x.version_num for x in model.aliases or [] if x.alias_name == "Champion"), 0)
    if action != "status":
        require(expected_current is not None and expected_current == current, "Champion changed; inspect before mutation")
        if target_version is not None:
            require(target_version != current, "Target is already Champion")
            with authentication(cloud.client, cfg["host"]):
                version = MlflowClient(registry_uri="databricks-uc").get_model_version(name, str(target_version))
                require(version.status == "READY" and version.tags.get("pricing.acceptance") == "PASS" and
                        version.tags.get("pricing.release_seal"), "Target has not passed immutable release acceptance")
            cloud.client.registered_models.set_alias(name, "Champion", target_version)
        else:
            require(action == "rollback" and current > 0, "Promotion requires an accepted target version")
            cloud.client.registered_models.delete_alias(name, "Champion")
        after = cloud.client.registered_models.get(name, include_aliases=True)
        current = next((x.version_num for x in after.aliases or [] if x.alias_name == "Champion"), 0)
        require(current == (target_version or 0), "Alias readback did not match requested release")
    return {"status": "PASS", "action": action, "model_name": name, "champion_version": current,
            "compute_started": False, "versions_deleted": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["status", "promote", "rollback"])
    parser.add_argument("--expected-current", type=int)
    parser.add_argument("--target-version", type=int)
    args = parser.parse_args()
    print(json.dumps(operate(args.action, args.expected_current, args.target_version), indent=2))
