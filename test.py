from src.app.runtime import Runtime, build_runtime_config
cfg = build_runtime_config("configs/default.yaml", show=True)
Runtime(cfg).run()