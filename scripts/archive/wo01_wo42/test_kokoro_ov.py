import time
from pathlib import Path

import numpy as np
import openvino as ov

core = ov.Core()
model_path = Path(r"C:\ProjectLucca\models\tts\kokoro-v1.0.onnx")
print("Reading Kokoro ONNX model into OpenVINO...")
t0 = time.time()
ov_model = core.read_model(model_path)
print(f"Read model in {time.time() - t0:.2f}s")
print("Inputs:")
for inp in ov_model.inputs:
    print(f"  {inp.any_name}: shape={inp.partial_shape}, dtype={inp.element_type}")

devices_to_test = ["GPU.0", "NPU", "CPU"]
for dev in devices_to_test:
    print(f"\nTesting compilation on {dev}...")
    try:
        t_c = time.time()
        compiled = core.compile_model(ov_model, dev)
        print(f"  [SUCCESS] Compiled on {dev} in {time.time() - t_c:.2f}s")
    except Exception as e:
        print(f"  [FAIL] Compilation on {dev} failed: {e}")
