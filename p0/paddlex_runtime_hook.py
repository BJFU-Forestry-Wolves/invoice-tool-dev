"""Provide an offline-only ModelScope facade for the frozen CPU build."""

import sys
import types


def _inference_only(*_args, **_kwargs):
    raise RuntimeError("Training and dataset APIs are unavailable in the OCR inference build")


modelscope = types.ModuleType("modelscope")
modelscope.snapshot_download = _inference_only
sys.modules[modelscope.__name__] = modelscope
