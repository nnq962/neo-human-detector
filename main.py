import uvicorn
import numpy as np

# Compatibility for TensorRT 8.5.x + NumPy >= 1.24
if "bool" not in np.__dict__:
    np.bool = bool

if __name__ == "__main__":
    uvicorn.run(
        "api.server:app", 
        host="0.0.0.0", 
        port=9721,
        reload=False
    )