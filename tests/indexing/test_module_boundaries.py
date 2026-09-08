from __future__ import annotations

import app.core.indexing.state_proto as state_proto_module
import app.core.indexing.state_proto_executor as state_proto_executor_module
import app.core.indexing.state_proto_runtime as state_proto_runtime_module


def test_state_proto_facade_maps_to_precise_runtime_and_executor_modules():
    assert state_proto_module.execute_state_proto_build is state_proto_executor_module.execute_state_proto_build
    assert state_proto_module.StateProtoIndex is state_proto_runtime_module.StateProtoIndex
    assert "_detect_script_mode" in state_proto_module.__all__
    assert "execute_state_proto_build" in state_proto_module.__all__
    assert "StateProtoIndex" in state_proto_module.__all__
    assert not hasattr(state_proto_module, "build_state_proto_artifacts")
    assert not hasattr(state_proto_module, "discover_target_specs")
    assert not hasattr(state_proto_module, "STATE_PROTO_EXECUTOR_BACKEND_PYTHON_REFERENCE")
