/**
 * Neo Human Detector — Frontend Logic
 * Fabric.js canvas with polygon ROI management
 */

const API_BASE = window.location.origin;
let globalConfig = {};
let fabricCanvas = null;
let originalImgW = 1920, originalImgH = 1080;
let selectedAreaIdx = null;
let isDrawingMode = false;
let isVertexEditMode = false;
let tempPoints = [];       // {x,y} in canvas coords
let tempCircles = [];      // fabric.Circle markers
let previewLine = null;    // dashed preview line
let lastClickMs = 0;

// ─── Realtime SLAM WebSocket ───────────────────────────────────
let slamWs = null;          // WebSocket instance
let slamRealtimeOn = false; // trạng thái switch

const AREA_COLORS = [
    { fill: 'rgba(59,125,248,0.22)', stroke: '#3b7df8' },
    { fill: 'rgba(22,163,74,0.22)', stroke: '#16a34a' },
    { fill: 'rgba(217,119,6,0.22)', stroke: '#d97706' },
    { fill: 'rgba(220,38,38,0.22)', stroke: '#dc2626' },
    { fill: 'rgba(124,58,237,0.22)', stroke: '#7c3aed' },
    { fill: 'rgba(236,72,153,0.22)', stroke: '#ec4899' },
];

// =====================================================
// INIT
// =====================================================
document.addEventListener('DOMContentLoaded', () => {
    initSegControls();
    initSlider();
    initSourceInput();
    initUartInputs();
    initCanvas();
    initKeyboard();
    initSystem();
});

async function initSystem() {
    try {
        const res = await fetch(`${API_BASE}/api/config`);
        if (!res.ok) throw new Error('HTTP ' + res.status);
        const config = await res.json();
        applyConfigToUI(config);
        updateStatusBar(true);
    } catch (e) {
        updateStatusBar(false);
        showToast('Không thể kết nối server API', 'error');
    }
    // Auto-load snapshot on startup
    refreshSnapshot();
}

function updateStatusBar(online) {
    document.getElementById('statusDot').className = 'status-dot ' + (online ? 'online' : 'error');
    document.getElementById('statusLabel').textContent = online ? 'Đã kết nối' : 'Mất kết nối';
}

async function updateAIStatus() {
    const dot = document.getElementById('aiStatusDot');
    const label = document.getElementById('aiStatusLabel');
    try {
        const res = await fetch(`${API_BASE}/api/detector/status`);
        if (!res.ok) throw new Error();
        const data = await res.json();
        const running = data.is_running === true;
        dot.className = 'status-dot ' + (running ? 'online' : 'idle');
        label.textContent = 'AI: ' + (running ? 'Đang chạy' : 'Đã dừng');
    } catch {
        dot.className = 'status-dot error';
        label.textContent = 'AI: Lỗi';
    }
}

// Poll AI status mỗi 5 giây
setInterval(updateAIStatus, 5000);
updateAIStatus();

// =====================================================
// SECTION 1 — CONFIG CONTROLS
// =====================================================
function initSegControls() {
    document.querySelectorAll('.seg-control').forEach(group => {
        group.querySelectorAll('.seg-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                group.querySelectorAll('.seg-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                updateYAMLPreview();
            });
        });
    });
}

function initSlider() {
    const slider = document.getElementById('cfg-conf');
    if (!slider) return;
    slider.addEventListener('input', () => {
        updateConfBadge(slider.value);
        updateYAMLPreview();
    });
}

function initSourceInput() {
    const src = document.getElementById('cfg-source');
    if (src) src.addEventListener('input', updateYAMLPreview);
    
    const vidStride = document.getElementById('cfg-vid-stride');
    if (vidStride) vidStride.addEventListener('input', updateYAMLPreview);
}

function initUartInputs() {
    const port = document.getElementById('cfg-uart-port');
    if (port) port.addEventListener('input', updateYAMLPreview);
    const baud = document.getElementById('cfg-uart-baudrate');
    if (baud) baud.addEventListener('change', updateYAMLPreview);
}

function setSegValue(groupId, value) {
    const g = document.getElementById(groupId);
    if (!g) return;
    g.querySelectorAll('.seg-btn').forEach(b => b.classList.toggle('active', b.dataset.value === String(value)));
}

function getSegValue(groupId) {
    const g = document.getElementById(groupId);
    if (!g) return null;
    const a = g.querySelector('.seg-btn.active');
    return a ? a.dataset.value : null;
}

function updateConfBadge(v) {
    const b = document.getElementById('confValueBadge');
    if (b) b.textContent = parseFloat(v).toFixed(2);
}

function applyConfigToUI(config) {
    const det = config.detector ?? {};
    const uart = config.uart ?? {};

    setSegValue('cfg-roi', det.zone_check_mode ?? 'center');
    setSegValue('cfg-auto-start', config.auto_start ?? false);
    setSegValue('cfg-verbose', det.verbose ?? false);
    
    const vidStride = document.getElementById('cfg-vid-stride');
    if (vidStride) vidStride.value = det.vid_stride ?? 1;
    const slider = document.getElementById('cfg-conf');
    if (slider) { slider.value = det.conf ?? 0.65; updateConfBadge(slider.value); }
    const src = document.getElementById('cfg-source');
    if (src) src.value = det.source ?? '';
    const uartPort = document.getElementById('cfg-uart-port');
    if (uartPort) uartPort.value = uart.port ?? '/dev/ttyS4';
    const uartBaud = document.getElementById('cfg-uart-baudrate');
    if (uartBaud) uartBaud.value = String(uart.baudrate ?? 115200);
    globalConfig = JSON.parse(JSON.stringify(config));
    updateYAMLPreview();
    renderAreaList();
}

function buildConfigFromUI() {
    return {
        auto_start: getSegValue('cfg-auto-start') === 'true',
        detector: {
            source: document.getElementById('cfg-source')?.value?.trim() ?? '',
            conf: parseFloat(parseFloat(document.getElementById('cfg-conf')?.value ?? 0.65).toFixed(2)),
            zone_check_mode: getSegValue('cfg-roi'),
            vid_stride: parseInt(document.getElementById('cfg-vid-stride')?.value ?? '1'),
            verbose: getSegValue('cfg-verbose') === 'true',
        },
        uart: {
            port: document.getElementById('cfg-uart-port')?.value?.trim() ?? '/dev/ttyS4',
            baudrate: parseInt(document.getElementById('cfg-uart-baudrate')?.value ?? '115200'),
        },
        zones: globalConfig.zones ?? []
    };
}

// =====================================================
// SECTION 2 — FABRIC.JS CANVAS
// =====================================================
function initCanvas() {
    const wrapper = document.getElementById('canvasWrapper');
    const W = wrapper.clientWidth || 640;
    const H = wrapper.clientHeight || 440;

    fabricCanvas = new fabric.Canvas('roiCanvas', {
        width: W, height: H,
        selection: true,
        preserveObjectStacking: true,
    });

    fabricCanvas.on('mouse:down', onMouseDown);
    fabricCanvas.on('mouse:move', onMouseMove);
    fabricCanvas.on('object:modified', onPolygonModified);
    fabricCanvas.on('selection:created', onSelectionChanged);
    fabricCanvas.on('selection:updated', onSelectionChanged);
    fabricCanvas.on('selection:cleared', onSelectionCleared);
}

function initKeyboard() {
    document.addEventListener('keydown', e => {
        if (e.key === 'Escape') {
            if (isDrawingMode) cancelDrawing();
            else if (isVertexEditMode) disableVertexEdit();
        }
    });
}

// Coordinate helpers
function imgToCanvas(ix, iy) {
    return { x: ix * fabricCanvas.width / originalImgW, y: iy * fabricCanvas.height / originalImgH };
}
function canvasToImg(cx, cy) {
    return [Math.round(cx * originalImgW / fabricCanvas.width), Math.round(cy * originalImgH / fabricCanvas.height)];
}

// Get absolute canvas coords of polygon vertices after transforms
function getAbsolutePoints(polygon) {
    const mat = polygon.calcTransformMatrix();
    return polygon.points.map(p => fabric.util.transformPoint(
        { x: p.x - polygon.pathOffset.x, y: p.y - polygon.pathOffset.y }, mat
    ));
}

// =====================================================
// SNAPSHOT LOADING
// =====================================================
async function refreshSnapshot() {
    const loadingEl = document.getElementById('canvasLoading');
    const errorEl = document.getElementById('canvasError');
    const metaEl = document.getElementById('snapshotMeta');
    const btn = document.getElementById('btnRefreshSnapshot');

    loadingEl.style.display = 'flex';
    errorEl.style.display = 'none';
    if (btn) btn.disabled = true;

    try {
        const imgUrl = `${API_BASE}/api/config/get-snapshot?t=${Date.now()}`;
        await new Promise((resolve, reject) => {
            fabric.Image.fromURL(imgUrl, img => {
                if (!img || img.width === 0) { reject(new Error('Invalid image')); return; }
                originalImgW = img.width;
                originalImgH = img.height;

                // Resize canvas to match image aspect ratio based on wrapper width
                const wrapper = document.getElementById('canvasWrapper');
                const newW = wrapper.clientWidth;
                const newH = Math.round(newW * originalImgH / originalImgW);
                fabricCanvas.setWidth(newW);
                fabricCanvas.setHeight(newH);

                img.scaleX = newW / img.width;
                img.scaleY = newH / img.height;
                img.selectable = false;
                img.evented = false;
                fabricCanvas.setBackgroundImage(img, () => {
                    fabricCanvas.renderAll();
                    resolve();
                });
            });
        });

        loadingEl.style.display = 'none';
        metaEl.style.display = 'block';
        const now = new Date();
        document.getElementById('snapshotTime').textContent =
            `Cập nhật lúc: ${now.toLocaleTimeString('vi-VN')} — ${now.toLocaleDateString('vi-VN')}`;

        // Vẽ polygon riêng — lỗi vẽ polygon không được phép đè lớp phủ lỗi camera
        try {
            drawAllPolygons();
        } catch (polyErr) {
            console.error('Lỗi khi vẽ polygon:', polyErr);
        }
    } catch (e) {
        console.error('Lỗi khi tải ảnh snapshot:', e);
        loadingEl.style.display = 'none';
        errorEl.style.display = 'flex';
        document.getElementById('canvasErrorMsg').textContent = 'Không thể kết nối đến camera. Kiểm tra RTSP URL.';
    } finally {
        if (btn) btn.disabled = false;
    }
}

// =====================================================
// POLYGON DRAWING & MANAGEMENT
// =====================================================
function drawAllPolygons() {
    // Remove existing polygons
    fabricCanvas.getObjects('polygon').forEach(p => fabricCanvas.remove(p));
    (globalConfig.zones ?? []).forEach((_, idx) => addPolygonToCanvas(idx));
    fabricCanvas.renderAll();
    renderAreaList();
}

function addPolygonToCanvas(idx) {
    const area = globalConfig.zones[idx];
    if (!area) return null;
    const color = AREA_COLORS[idx % AREA_COLORS.length];
    const points = area.points.map(pt => imgToCanvas(pt[0], pt[1]));

    const poly = new fabric.Polygon(points, {
        fill: color.fill,
        stroke: color.stroke,
        strokeWidth: 2,
        selectable: true,
        objectCaching: false,
        perPixelTargetFind: false,
        areaIndex: idx,
        cornerStyle: 'circle',
        cornerColor: color.stroke,
        cornerSize: 8,
        transparentCorners: false,
    });

    fabricCanvas.add(poly);
    return poly;
}

function syncPolygonToConfig(polygon) {
    const idx = polygon.areaIndex;
    if (idx === undefined || !globalConfig.zones?.[idx]) return;
    const absPoints = getAbsolutePoints(polygon);
    globalConfig.zones[idx].points = absPoints.map(p => canvasToImg(p.x, p.y));
    updateYAMLPreview();
    renderAreaList();
}

function onPolygonModified(e) {
    const obj = e.target;
    if (obj && obj.areaIndex !== undefined) syncPolygonToConfig(obj);
}

function onSelectionChanged(e) {
    const obj = e.selected?.[0];
    if (obj && obj.areaIndex !== undefined) {
        selectedAreaIdx = obj.areaIndex;
        renderAreaList();
        populateAreaForm(obj.areaIndex);
        document.getElementById('btnVertexEdit').disabled = false;
    }
}

function onSelectionCleared() {
    if (isVertexEditMode) disableVertexEdit();
    selectedAreaIdx = null;
    renderAreaList();
    document.getElementById('areaForm').style.display = 'none';
    document.getElementById('btnVertexEdit').disabled = true;
    document.getElementById('btnVertexEdit').classList.remove('active');
}

// =====================================================
// VERTEX EDITING (Fabric.js official approach)
// =====================================================
function getObjectSizeWithStroke(object) {
    const stroke = new fabric.Point(
        object.strokeUniform ? 1 / object.scaleX : 1,
        object.strokeUniform ? 1 / object.scaleY : 1
    ).multiply(object.strokeWidth);
    return new fabric.Point(object.width + stroke.x, object.height + stroke.y);
}

function polygonPositionHandler(dim, finalMatrix, fabricObject) {
    const x = fabricObject.points[this.pointIndex].x - fabricObject.pathOffset.x;
    const y = fabricObject.points[this.pointIndex].y - fabricObject.pathOffset.y;
    return fabric.util.transformPoint(
        { x, y },
        fabric.util.multiplyTransformMatrices(
            fabricObject.canvas.viewportTransform,
            fabricObject.calcTransformMatrix()
        )
    );
}

function actionHandler(eventData, transform, x, y) {
    const polygon = transform.target;
    const currentControl = polygon.controls[polygon.__corner];
    const mouseLocalPosition = polygon.toLocalPoint(new fabric.Point(x, y), 'center', 'center');
    const polygonBaseSize = getObjectSizeWithStroke(polygon);
    const size = polygon._getTransformedDimensions(0, 0);
    polygon.points[currentControl.pointIndex] = {
        x: mouseLocalPosition.x * polygonBaseSize.x / size.x + polygon.pathOffset.x,
        y: mouseLocalPosition.y * polygonBaseSize.y / size.y + polygon.pathOffset.y
    };
    return true;
}

function anchorWrapper(anchorIndex, fn) {
    return function (eventData, transform, x, y) {
        const fabricObject = transform.target;
        const absolutePoint = fabric.util.transformPoint(
            {
                x: fabricObject.points[anchorIndex].x - fabricObject.pathOffset.x,
                y: fabricObject.points[anchorIndex].y - fabricObject.pathOffset.y
            },
            fabricObject.calcTransformMatrix()
        );
        const actionPerformed = fn(eventData, transform, x, y);
        fabricObject._setPositionDimensions({});
        const polygonBaseSize = getObjectSizeWithStroke(fabricObject);
        const newX = (fabricObject.points[anchorIndex].x - fabricObject.pathOffset.x) / polygonBaseSize.x;
        const newY = (fabricObject.points[anchorIndex].y - fabricObject.pathOffset.y) / polygonBaseSize.y;
        fabricObject.setPositionByOrigin(absolutePoint, newX + 0.5, newY + 0.5);
        return actionPerformed;
    };
}

function enableVertexEdit(polygon) {
    isVertexEditMode = true;
    polygon.edit = true;
    polygon.objectCaching = false;
    polygon.hasBorders = false;
    const lastControl = polygon.points.length - 1;
    polygon.controls = polygon.points.reduce((acc, point, index) => {
        acc['p' + index] = new fabric.Control({
            positionHandler: polygonPositionHandler,
            actionHandler: anchorWrapper(index > 0 ? index - 1 : lastControl, actionHandler),
            actionName: 'modifyPolygon',
            pointIndex: index,
            cursorStyle: 'crosshair',
        });
        return acc;
    }, {});
    fabricCanvas.requestRenderAll();
    document.getElementById('btnVertexEdit').classList.add('active');
    document.getElementById('btnVertexEdit').title = 'Thoát sửa đỉnh (Esc)';
}

function disableVertexEdit() {
    isVertexEditMode = false;
    const poly = fabricCanvas.getActiveObject();
    if (poly && poly.areaIndex !== undefined) {
        poly.edit = false;
        poly.hasBorders = true;
        poly.controls = fabric.Object.prototype.controls;
        syncPolygonToConfig(poly);
    }
    fabricCanvas.requestRenderAll();
    document.getElementById('btnVertexEdit').classList.remove('active');
    document.getElementById('btnVertexEdit').title = 'Sửa đỉnh';
}

function toggleVertexEdit() {
    if (isVertexEditMode) { disableVertexEdit(); return; }
    const poly = fabricCanvas.getActiveObject();
    if (poly && poly.areaIndex !== undefined) enableVertexEdit(poly);
}

// =====================================================
// DRAWING NEW POLYGON
// =====================================================
function startDrawing() {
    if (!fabricCanvas.backgroundImage) {
        showToast('Vui lòng tải ảnh camera trước khi vẽ', 'error'); return;
    }
    if (isDrawingMode) return;
    isDrawingMode = true;
    fabricCanvas.discardActiveObject();
    fabricCanvas.selection = false;
    fabricCanvas.defaultCursor = 'crosshair';
    tempPoints = []; tempCircles = []; lastClickMs = 0;

    document.getElementById('drawingHint').style.display = 'block';
    document.getElementById('btnAddArea').style.display = 'none';
    document.getElementById('btnCancelDraw').style.display = 'inline-flex';
    document.getElementById('btnVertexEdit').disabled = true;
}

function cancelDrawing() {
    tempCircles.forEach(c => fabricCanvas.remove(c));
    if (previewLine) { fabricCanvas.remove(previewLine); previewLine = null; }
    tempPoints = []; tempCircles = [];
    exitDrawingMode();
}

function exitDrawingMode() {
    isDrawingMode = false;
    fabricCanvas.selection = true;
    fabricCanvas.defaultCursor = 'default';
    document.getElementById('drawingHint').style.display = 'none';
    document.getElementById('btnAddArea').style.display = 'inline-flex';
    document.getElementById('btnCancelDraw').style.display = 'none';
}

function addTempPoint(x, y) {
    tempPoints.push({ x, y });
    const color = AREA_COLORS[(globalConfig.zones?.length ?? 0) % AREA_COLORS.length];
    const circle = new fabric.Circle({
        left: x - 5, top: y - 5, radius: 5,
        fill: color.stroke, stroke: '#fff', strokeWidth: 1.5,
        selectable: false, evented: false, originX: 'left', originY: 'top',
    });
    fabricCanvas.add(circle);
    tempCircles.push(circle);
    fabricCanvas.renderAll();
}

function finishDrawing() {
    if (tempPoints.length < 3) {
        showToast('Cần ít nhất 3 đỉnh để tạo đa giác', 'error'); return;
    }
    // Clean up temp objects
    tempCircles.forEach(c => fabricCanvas.remove(c));
    if (previewLine) { fabricCanvas.remove(previewLine); previewLine = null; }

    // Create new area
    const newIdx = (globalConfig.zones ?? []).length;
    if (!globalConfig.zones) globalConfig.zones = [];
    globalConfig.zones.push({
        name: 'area_' + (newIdx + 1),
        goal_pose: { x: 0, y: 0, theta: 90 },
        points: tempPoints.map(p => canvasToImg(p.x, p.y))
    });

    tempPoints = []; tempCircles = [];
    exitDrawingMode();

    addPolygonToCanvas(newIdx);
    fabricCanvas.renderAll();
    renderAreaList();
    updateYAMLPreview();

    // Auto-select new polygon
    const polys = fabricCanvas.getObjects('polygon');
    const newPoly = polys.find(p => p.areaIndex === newIdx);
    if (newPoly) { fabricCanvas.setActiveObject(newPoly); fabricCanvas.renderAll(); }

    showToast('Đã thêm vùng mới — nhập tên và nhấn Áp dụng', 'success');
}

function onMouseDown(opt) {
    if (!isDrawingMode) return;
    const now = Date.now();
    const pt = fabricCanvas.getPointer(opt.e);

    if (now - lastClickMs < 350) {
        // Double-click detected — remove last point added by second click and finish
        if (tempCircles.length > 0) {
            fabricCanvas.remove(tempCircles.pop());
            tempPoints.pop();
        }
        if (previewLine) { fabricCanvas.remove(previewLine); previewLine = null; }
        finishDrawing();
        lastClickMs = 0;
    } else {
        addTempPoint(pt.x, pt.y);
        lastClickMs = now;
    }
}

function onMouseMove(opt) {
    if (!isDrawingMode || tempPoints.length === 0) return;
    const pt = fabricCanvas.getPointer(opt.e);
    const last = tempPoints[tempPoints.length - 1];
    if (previewLine) fabricCanvas.remove(previewLine);
    previewLine = new fabric.Line([last.x, last.y, pt.x, pt.y], {
        stroke: '#3b7df8', strokeWidth: 1.5, strokeDashArray: [5, 4],
        selectable: false, evented: false,
    });
    fabricCanvas.add(previewLine);
    fabricCanvas.renderAll();
}

// =====================================================
// AREA LIST & FORM
// =====================================================
function renderAreaList() {
    const list = document.getElementById('areaList');
    const empty = document.getElementById('areaEmpty');
    const badge = document.getElementById('areaCountBadge');
    const areas = globalConfig.zones ?? [];

    badge.textContent = areas.length;

    if (areas.length === 0) {
        list.innerHTML = '';
        empty.style.display = 'flex';
        return;
    }
    empty.style.display = 'none';
    list.innerHTML = areas.map((area, idx) => {
        const color = AREA_COLORS[idx % AREA_COLORS.length];
        const sel = selectedAreaIdx === idx ? 'selected' : '';
        return `<div class="area-list-item ${sel}" onclick="selectAreaByIdx(${idx})">
            <span class="area-color-dot" style="background:${color.stroke}"></span>
            <span class="area-name">${area.name || 'Vùng ' + (idx + 1)}</span>
            <span class="area-pts-count">${area.points.length} đỉnh</span>
        </div>`;
    }).join('');
}

function selectAreaByIdx(idx) {
    selectedAreaIdx = idx;
    const polys = fabricCanvas.getObjects('polygon');
    const poly = polys.find(p => p.areaIndex === idx);
    if (poly) { fabricCanvas.setActiveObject(poly); fabricCanvas.renderAll(); }
    populateAreaForm(idx);
    renderAreaList();
    document.getElementById('btnVertexEdit').disabled = false;
}

function populateAreaForm(idx) {
    const area = globalConfig.zones?.[idx];
    if (!area) return;
    document.getElementById('areaForm').style.display = 'flex';
    document.getElementById('areaName').value = area.name ?? '';
    document.getElementById('areaSlam_x').value = area.goal_pose?.x ?? 0;
    document.getElementById('areaSlam_y').value = area.goal_pose?.y ?? 0;
    document.getElementById('areaSlam_theta').value = area.goal_pose?.theta ?? 90;

    // Luôn reset switch về OFF khi chọn vùng mới
    disconnectSlamWs();
    const toggle = document.getElementById('slamRealtimeToggle');
    if (toggle) toggle.checked = false;
    setSlamInputsReadonly(false);
    document.getElementById('realtimeWsStatus').style.display = 'none';
}

function applyAreaProperties() {
    if (selectedAreaIdx === null) return;
    const area = globalConfig.zones?.[selectedAreaIdx];
    if (!area) return;
    area.name = document.getElementById('areaName').value.trim() || area.name;
    area.goal_pose = {
        x: parseFloat(document.getElementById('areaSlam_x').value) || 0,
        y: parseFloat(document.getElementById('areaSlam_y').value) || 0,
        theta: parseFloat(document.getElementById('areaSlam_theta').value) || 90,
    };
    updateYAMLPreview();
    renderAreaList();
    showToast('Đã cập nhật thông tin vùng', 'success');
}

function deleteSelectedArea() {
    if (selectedAreaIdx === null) return;
    globalConfig.zones.splice(selectedAreaIdx, 1);

    // Rebuild all polygons (re-index)
    fabricCanvas.getObjects('polygon').forEach(p => fabricCanvas.remove(p));
    (globalConfig.zones ?? []).forEach((_, i) => addPolygonToCanvas(i));
    fabricCanvas.discardActiveObject();
    fabricCanvas.renderAll();

    selectedAreaIdx = null;
    document.getElementById('areaForm').style.display = 'none';
    document.getElementById('btnVertexEdit').disabled = true;
    renderAreaList();
    updateYAMLPreview();
    showToast('Đã xóa vùng', 'info');
}

// =====================================================
// SECTION 3 — YAML PREVIEW & SAVE
// =====================================================
function updateYAMLPreview() {
    const preview = document.getElementById('yamlPreview');
    if (!preview) return;
    const config = buildConfigFromUI();
    const yamlStr = jsonToYaml(config);
    preview.innerHTML = syntaxHighlightYAML(yamlStr);
}

/** Chuyển đổi object JS thành chuỗi YAML đơn giản */
function jsonToYaml(obj, indent = 0) {
    const pad = '  '.repeat(indent);
    let lines = [];
    for (const [key, value] of Object.entries(obj)) {
        if (value === null || value === undefined) {
            lines.push(`${pad}${key}: null`);
        } else if (Array.isArray(value)) {
            if (value.length === 0) {
                lines.push(`${pad}${key}: []`);
            } else {
                lines.push(`${pad}${key}:`);
                value.forEach(item => {
                    if (Array.isArray(item)) {
                        // Inline array cho points: - [x, y]
                        lines.push(`${pad}- [${item.join(', ')}]`);
                    } else if (typeof item === 'object' && item !== null) {
                        const entries = Object.entries(item);
                        // First key trên cùng dòng với -
                        entries.forEach((entry, i) => {
                            const [k, v] = entry;
                            const prefix = i === 0 ? `${pad}- ` : `${pad}  `;
                            if (typeof v === 'object' && v !== null && !Array.isArray(v)) {
                                lines.push(`${prefix}${k}:`);
                                lines.push(jsonToYaml(v, indent + 2));
                            } else if (Array.isArray(v)) {
                                lines.push(`${prefix}${k}:`);
                                v.forEach(pt => {
                                    if (Array.isArray(pt)) lines.push(`${pad}    - [${pt.join(', ')}]`);
                                    else lines.push(`${pad}    - ${pt}`);
                                });
                            } else {
                                lines.push(`${prefix}${k}: ${formatYamlValue(v)}`);
                            }
                        });
                    } else {
                        lines.push(`${pad}- ${formatYamlValue(item)}`);
                    }
                });
            }
        } else if (typeof value === 'object') {
            lines.push(`${pad}${key}:`);
            lines.push(jsonToYaml(value, indent + 1));
        } else {
            lines.push(`${pad}${key}: ${formatYamlValue(value)}`);
        }
    }
    return lines.join('\n');
}

function formatYamlValue(v) {
    if (typeof v === 'string') return v;
    if (typeof v === 'boolean') return v ? 'true' : 'false';
    if (typeof v === 'number') return String(v);
    return String(v);
}

function syntaxHighlightYAML(str) {
    return str
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/^(\s*)(- )?([\w_]+)(:)/gm, (m, sp, dash, key, colon) => {
            return `${sp}${dash || ''}<span class="yaml-key">${key}</span><span class="yaml-colon">${colon}</span>`;
        })
        .replace(/:\s+(true|false)$/gm, (m, val) => `: <span class="yaml-bool">${val}</span>`)
        .replace(/:\s+(-?\d+\.?\d*)$/gm, (m, val) => `: <span class="yaml-number">${val}</span>`)
        .replace(/- \[(.*?)\]/g, (m, inner) => `- [<span class="yaml-number">${inner}</span>]`);
}

async function saveConfigToServer() {
    const config = buildConfigFromUI();
    const btn = document.getElementById('btnSave');
    if (btn) { btn.disabled = true; btn.textContent = 'Đang lưu...'; }
    try {
        const res = await fetch(`${API_BASE}/api/config`, {
            method: 'PUT', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(config)
        });
        const data = await res.json();
        if (data.status === 'success') {
            globalConfig = JSON.parse(JSON.stringify(config));
            showToast('✅ Đã lưu cấu hình thành công!', 'success');
        } else {
            showToast('❌ Lỗi: ' + (data.detail ?? 'Không rõ'), 'error');
        }
    } catch {
        showToast('❌ Không thể kết nối server', 'error');
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = `<svg class="btn-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/></svg> Lưu cấu hình`;
        }
    }
}

// =====================================================
// REALTIME SLAM — WebSocket
// =====================================================

/**
 * Gọi khi người dùng bật/tắt switch "Tọa độ Realtime".
 * @param {boolean} enabled
 */
function onSlamRealtimeToggle(enabled) {
    if (enabled) {
        slamRealtimeOn = true;
        connectSlamWs();
        setSlamInputsReadonly(true);
    } else {
        slamRealtimeOn = false;
        disconnectSlamWs();
        setSlamInputsReadonly(false);
        document.getElementById('realtimeWsStatus').style.display = 'none';
    }
}

/** Kết nối WebSocket /ws/robot và lắng nghe tọa độ SLAM */
function connectSlamWs() {
    // Đóng kết nối cũ nếu có (im lặng, không reset cờ)
    if (slamWs) {
        slamWs.onclose = null;
        slamWs.close();
        slamWs = null;
    }

    const wsUrl = `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}/ws/uart`;
    const statusBar = document.getElementById('realtimeWsStatus');
    const dot = document.getElementById('wsStatusDot');
    const txt = document.getElementById('wsStatusText');

    statusBar.style.display = 'flex';
    dot.className = 'ws-dot connecting';
    txt.textContent = 'Đang kết nối...';

    try {
        slamWs = new WebSocket(wsUrl);
    } catch (e) {
        dot.className = 'ws-dot error';
        txt.textContent = 'Không thể tạo WebSocket';
        return;
    }

    slamWs.onopen = () => {
        dot.className = 'ws-dot connected';
        txt.textContent = 'Đã kết nối — chờ dữ liệu...';
    };

    slamWs.onmessage = (event) => {
        if (!slamRealtimeOn) return;
        try {
            const data = JSON.parse(event.data);
            const x     = data.x     !== undefined ? data.x     : (data.slam_x     !== undefined ? data.slam_x     : null);
            const y     = data.y     !== undefined ? data.y     : (data.slam_y     !== undefined ? data.slam_y     : null);
            const theta = data.theta !== undefined ? data.theta : (data.slam_theta !== undefined ? data.slam_theta : null);

            if (x !== null) document.getElementById('areaSlam_x').value = parseFloat(x).toFixed(4);
            if (y !== null) document.getElementById('areaSlam_y').value = parseFloat(y).toFixed(4);
            if (theta !== null) document.getElementById('areaSlam_theta').value = parseFloat(theta).toFixed(2);

            var xTxt = x !== null ? parseFloat(x).toFixed(2) : '-';
            var yTxt = y !== null ? parseFloat(y).toFixed(2) : '-';
            var tTxt = theta !== null ? parseFloat(theta).toFixed(1) : '-';
            dot.className = 'ws-dot connected';
            txt.textContent = 'x=' + xTxt + '  y=' + yTxt + '  th=' + tTxt + 'deg';
        } catch(e) {
            // ignore parse errors
        }
    };

    slamWs.onerror = () => {
        dot.className = 'ws-dot error';
        txt.textContent = 'Lỗi kết nối WebSocket';
    };

    slamWs.onclose = () => {
        if (!slamRealtimeOn) return;
        dot.className = 'ws-dot error';
        txt.textContent = 'Mất kết nối';
    };
}

/** Ngắt WebSocket hiện tại một cách sạch sẽ */
function disconnectSlamWs() {
    if (slamWs) {
        slamWs.onclose = null; // tránh trigger UI lỗi
        slamWs.close();
        slamWs = null;
    }
}

/**
 * Bật/tắt khả năng chỉnh sửa thủ công cho 3 input SLAM.
 * @param {boolean} readonly - true: readonly (realtime mode), false: cho phép sửa
 */
function setSlamInputsReadonly(readonly) {
    const ids = ['areaSlam_x', 'areaSlam_y', 'areaSlam_theta'];
    ids.forEach(id => {
        const el = document.getElementById(id);
        if (!el) return;
        el.readOnly = readonly;
        el.classList.toggle('slam-readonly', readonly);
    });
    // Nút "Áp dụng" vẫn hoạt động để ghi nhận giá trị đang hiển thị
}

// =====================================================
// TOAST
// =====================================================
function showToast(message, type = 'info') {
    const container = document.getElementById('toastContainer');
    if (!container) return;
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    container.appendChild(toast);
    setTimeout(() => {
        toast.style.transition = 'opacity 0.2s ease, transform 0.2s ease';
        toast.style.opacity = '0';
        toast.style.transform = 'translateY(8px)';
        setTimeout(() => toast.remove(), 220);
    }, 3000);
}

// =====================================================
// AI CONTROL (Start / Stop / Restart)
// =====================================================
async function controlAI(action) {
    const btnStart = document.getElementById('btnStartAI');
    const btnStop = document.getElementById('btnStopAI');
    const btnRestart = document.getElementById('btnRestartAI');
    const allBtns = [btnStart, btnStop, btnRestart];

    // Disable tất cả button khi đang xử lý
    allBtns.forEach(b => { if (b) b.disabled = true; });

    const labels = { start: 'Đang khởi động...', stop: 'Đang dừng...', restart: 'Đang khởi động lại...' };
    const activeBtn = action === 'start' ? btnStart : action === 'stop' ? btnStop : btnRestart;
    const originalHTML = activeBtn ? activeBtn.innerHTML : '';
    if (activeBtn) activeBtn.textContent = labels[action] || '...';

    try {
        const res = await fetch(`${API_BASE}/api/detector/${action}`, { method: 'POST' });
        const data = await res.json();

        if (res.status === 409) {
            showToast('⏳ ' + (data.detail || 'Đang xử lý lệnh khác'), 'info');
        } else if (data.status === 'success') {
            showToast('✅ ' + data.message, 'success');
        } else if (data.status === 'info') {
            showToast('ℹ️ ' + data.message, 'info');
        } else {
            showToast('⚠️ ' + data.message, 'error');
        }
    } catch {
        showToast('❌ Không thể kết nối server', 'error');
    } finally {
        // Khôi phục button
        if (activeBtn) activeBtn.innerHTML = originalHTML;
        allBtns.forEach(b => { if (b) b.disabled = false; });
        // Cập nhật AI status ngay lập tức
        updateAIStatus();
    }
}