import time
from pathlib import Path

import openvino as ov

core = ov.Core()
model_path = Path(r"C:\ProjectLucca\models\tts\kokoro-v1.0.onnx")

for bucket_len in [64, 128, 256]:
    print(f"\n--- Testing static bucket {bucket_len} on NPU ---")
    ov_model = core.read_model(model_path)
    ov_model.reshape({"tokens": [1, bucket_len], "style": [1, 256], "speed": [1]})
    try:
        t0 = time.time()
        compiled = core.compile_model(ov_model, "NPU")
        print(f"  [SUCCESS] Compiled bucket {bucket_len} on NPU in {time.time() - t0:.2f}s")
    except Exception as e:
        print(f"  [FAIL] Bucket {bucket_len} compilation on NPU failed: {e}")
