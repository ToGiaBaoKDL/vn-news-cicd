from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

INFRA_SCRIPTS = Path(__file__).resolve().parents[2] / "vn-news-infra" / "scripts"


def load_runtime_secret_tfvars() -> ModuleType:
    module_path = INFRA_SCRIPTS / "runtime_secret_tfvars.py"
    spec = importlib.util.spec_from_file_location("runtime_secret_tfvars", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_merge_runtime_secret_ocids_preserves_existing_role_secrets(tmp_path: Path) -> None:
    runtime_secret_tfvars = load_runtime_secret_tfvars()
    tfvars = tmp_path / "terraform.tfvars"
    tfvars.write_text(
        """
runtime_secret_ocids = {
  data = [
    "ocid1.vaultsecret.oc1..dataold",
  ]
  control = [
    "ocid1.vaultsecret.oc1..controlold",
  ]
  processing = []
}
""".lstrip(),
        encoding="utf-8",
    )

    runtime_secret_tfvars.merge_runtime_secret_ocids(
        tfvars,
        {
            "data": ["ocid1.vaultsecret.oc1..datanew"],
            "processing": ["ocid1.vaultsecret.oc1..processingnew"],
        },
    )

    assert runtime_secret_tfvars.read_runtime_secret_ocids(tfvars) == {
        "data": [
            "ocid1.vaultsecret.oc1..dataold",
            "ocid1.vaultsecret.oc1..datanew",
        ],
        "control": ["ocid1.vaultsecret.oc1..controlold"],
        "processing": ["ocid1.vaultsecret.oc1..processingnew"],
    }


def test_merge_runtime_secret_ocids_deduplicates_secret_ids(tmp_path: Path) -> None:
    runtime_secret_tfvars = load_runtime_secret_tfvars()
    tfvars = tmp_path / "terraform.tfvars"

    runtime_secret_tfvars.merge_runtime_secret_ocids(
        tfvars,
        {"data": ["ocid1.vaultsecret.oc1..secret", "ocid1.vaultsecret.oc1..secret"]},
    )

    assert runtime_secret_tfvars.read_runtime_secret_ocids(tfvars)["data"] == [
        "ocid1.vaultsecret.oc1..secret"
    ]
