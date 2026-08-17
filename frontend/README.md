# NEO Human Detector frontend

Frontend React/TypeScript cho dashboard cấu hình và màn hình camera công khai.
Vite proxy API/WebSocket tới FastAPI khi phát triển; bản production được build
vào `frontend/dist` và do FastAPI phục vụ same-origin.

## Chạy phát triển

```bash
cp .env.example .env
npm install
npm run dev
```

`VITE_API_BASE_URL` chỉ dùng làm đích proxy khi chạy Vite. Không đặt mật khẩu
trong `.env`; dashboard đăng nhập qua backend và cookie session `HttpOnly`.

Các route chính:

- `/live`: màn hình camera public, gồm bbox và robot overlay nếu có dữ liệu.
- `/`: dashboard riêng tư, được bọc bởi `ConfigGuard`.
- `/cameras/:id`: cấu hình camera, zone và điểm phục vụ.
- `/calibration/cameras/:id`: hiệu chỉnh camera.
- `/detection`, `/re-id`, `/uart`: cấu hình các subsystem tương ứng.

## Quality gate

```bash
npm run check
```

Lệnh này chạy ESLint, Vitest và production build. Có thể chạy riêng:

```bash
npm run lint
npm run test:run
npm run typecheck
npm run build
```
