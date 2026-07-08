from __future__ import annotations

from scripts.workspace.deploy_contracts import validate_deployment_identity_usage
from scripts.workspace.env_contracts import validate_role_env_templates
from scripts.workspace.image_contracts import validate_image_catalog
from scripts.workspace.repo_layout import validate_script_layout
from scripts.workspace.settings_contracts import validate_settings_load
from scripts.workspace.workflow_contracts import validate_workflow_action_pins


def main() -> None:
    validate_workflow_action_pins()
    validate_deployment_identity_usage()
    validate_script_layout()
    validate_image_catalog()
    validate_role_env_templates()
    validate_settings_load()
    print("workspace verification ok")


if __name__ == "__main__":
    main()
