from src.app.runtime import Runtime, build_runtime_config
cfg = build_runtime_config("configs/test.yaml", show=True)
Runtime(cfg).run()