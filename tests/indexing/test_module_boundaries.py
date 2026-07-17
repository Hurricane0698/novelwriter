from __future__ import annotations

from pathlib import Path

import app.core.indexing.state_proto as state_proto_module
import app.core.indexing.state_proto_executor as state_proto_executor_module
import app.core.indexing.state_proto_runtime as state_proto_runtime_module


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_state_proto_facade_maps_to_precise_runtime_and_executor_modules():
    assert state_proto_module.execute_state_proto_build is state_proto_executor_module.execute_state_proto_build
    assert state_proto_module.StateProtoIndex is state_proto_runtime_module.StateProtoIndex
    assert "_detect_script_mode" in state_proto_module.__all__
    assert "execute_state_proto_build" in state_proto_module.__all__
    assert "StateProtoIndex" in state_proto_module.__all__
    assert not hasattr(state_proto_module, "build_state_proto_artifacts")
    assert not hasattr(state_proto_module, "discover_target_specs")
    assert not hasattr(state_proto_module, "STATE_PROTO_EXECUTOR_BACKEND_PYTHON_REFERENCE")


def test_internal_callers_use_precise_state_proto_modules_instead_of_compat_facade():
    forbidden_imports = {
        "app/core/bootstrap.py": "from app.core.indexing.state_proto import",
        "app/core/seed_demo.py": "from app.core.indexing.state_proto import",
        "app/core/indexing/__init__.py": "from .state_proto import",
        "app/core/indexing/lifecycle.py": "from .state_proto import",
        "app/core/indexing/window_index.py": "from .state_proto import",
    }

    for relative_path, forbidden in forbidden_imports.items():
        text = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
        assert forbidden not in text, f"{relative_path} should import a precise state-proto module"


def test_demo_seed_delegates_state_proto_builds_to_the_worker():
    text = (REPO_ROOT / "app/core/seed_demo.py").read_text(encoding="utf-8")

    assert "execute_state_proto_build" not in text
    assert "enqueue_window_index_rebuild_job" in text
