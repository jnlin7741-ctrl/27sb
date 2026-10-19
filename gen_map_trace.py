# -*- coding: utf-8 -*-
# 描取六板块轮廓 + 三个黑色沦陷斑：最近色分类 → 掩膜装饰 → 连通域过滤 → 形态学 → 轮廓简化
# 输出 map_paths.js（内联用）+ gen_map_debug.png（描边叠加）+ gen_map_fill.png（填充预览）
import numpy as np, cv2, json
from PIL import Image

im = np.array(Image.open('images/map_ref.webp').convert('RGB')).astype(np.int32)
H, W, _ = im.shape
print('size', W, H)

def sample(x, y, k=3):
    blk = im[y-k:y+k, x-k:x+k].reshape(-1, 3)
    return np.median(blk, axis=0)

CLASSES = ['blue', 'red', 'gold', 'purple', 'olive', 'grey']
probes  = {'blue':(200,240), 'red':(420,190), 'gold':(150,370),
           'purple':(400,320), 'olive':(292,392)}
pal = {k: sample(*p, 4) for k, p in probes.items()}
# 土测院灰区基色：框内低饱和中亮度像素中值
gx0, gy0, gx1, gy1 = 398, 422, 463, 476
gpx = im[gy0:gy1, gx0:gx1].reshape(-1, 3)
gsp = gpx.max(1) - gpx.min(1)
glu = gpx @ np.array([3, 6, 1]) / 10
sel = gpx[(gsp < 25) & (glu > 55) & (glu < 95)]
pal['grey'] = np.median(sel, axis=0) if len(sel) > 50 else np.array([80, 78, 76])
for k in CLASSES:
    print(k, [int(v) for v in pal[k]])

bg = sample(15, 15, 4)
# navy：北部暗蓝过渡带（避免并入蓝区）
refs = {**{k: pal[k] for k in CLASSES}, 'bg': bg, 'navy': np.array([48, 64, 84])}
keys = list(refs.keys())
stack = np.stack([np.abs(im-refs[k]).sum(2) for k in keys], axis=0)
idx = stack.argmin(axis=0)
mind = stack.min(axis=0)
labels = np.full((H, W), -1, np.int32)
for i, k in enumerate(keys):
    if k in CLASSES:
        labels[(idx == i) & (mind < (78 if k == 'grey' else 72))] = CLASSES.index(k)
# 顶部暗带防串色：真灰区在 y≥380，其上的灰类像素一律清除
labels[:140, :][labels[:140, :] == 5] = -1

# 掩膜：百分比小牌 / 左侧图例 / 标题带 / 指北针 / 左下角罗盘盾徽
MASKS = [(4,60,68,112),      # 电气院41.4%小牌
         (316,60,394,114),   # 机电院24.1%小牌
         (60,260,116,312),   # 南昌13.8%小牌
         (450,286,512,332),  # 信院10.3%小牌
         (450,412,512,468),  # 土测院3.4%小牌
         (238,464,308,510),  # 法学院6.9%小牌
         (0,200,42,440),     # 左侧图例条
         (0,0,512,58),       # 标题+拼音带
         (460,36,512,114),   # 指北针罗盘
         (0,452,72,512)]     # 左下角罗盘+盾徽
for x0, y0, x1, y1 in MASKS:
    labels[y0:y1, x0:x1] = -1

# 缝隙填充：未分类像素若 8px 内邻接 ≥2 个板块，划归最近板块（保证接壤、共享边界）
dts = np.stack([cv2.distanceTransform((labels != i).astype(np.uint8), cv2.DIST_L2, 3)
                for i in range(6)], axis=0)
order = np.argsort(dts, axis=0)               # 每像素：按到各板块距离排序的类索引
d_sorted = np.take_along_axis(dts, order, axis=0)
nearest = order[0]
second_d = d_sorted[1]
assign = (labels == -1) & (second_d <= 8)
for i in range(6):
    labels[assign & (nearest == i)] = i
print('seam pixels assigned:', int(assign.sum()))

def filter_comps(m, min_area):
    n, lab, stats, _ = cv2.connectedComponentsWithStats(m, 8)
    keep = np.zeros_like(m)
    for i in range(1, n):
        if stats[i, cv2.CC_STAT_AREA] >= min_area:
            keep[lab == i] = 1
    return keep

def trace(m, min_area, eps_k=0.005, dilate=2):
    m = filter_comps(m, min_area)
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((7,7),np.uint8), iterations=2)
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN,  np.ones((5,5),np.uint8), iterations=1)
    if dilate:
        m = cv2.dilate(m, np.ones((9,9),np.uint8), iterations=2)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(m, 8)
    if n <= 1:
        return None, 0
    i = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    m = (lab == i).astype(np.uint8)
    cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    c = max(cnts, key=cv2.contourArea)
    ap = cv2.approxPolyDP(c, eps_k*cv2.arcLength(c, True), True).reshape(-1, 2)
    return ap.tolist(), cv2.contourArea(c)

paths, areas = {}, {}
vis = np.array(Image.open('images/map_ref.webp').convert('RGB'))
for i, k in enumerate(CLASSES):
    ap, area = trace((labels == i).astype(np.uint8), 3000)
    if ap is None:
        print(k, 'EMPTY'); continue
    paths[k] = ap; areas[k] = area
    print(k, 'pts=%d area=%.0f' % (len(ap), area))
    cv2.polylines(vis, [np.array(ap, np.int32)], True, (255,255,255), 2)

# 黑斑（沦陷区）：三块暗斑，按放大裁剪图人工读数硬编码
PATCHES = [
    [(58,133),(90,128),(112,140),(138,150),(160,147),(180,165),(183,200),(163,222),(116,221),(86,229),(66,221),(51,206),(44,179),(48,154)],
    [(402,120),(428,114),(452,118),(462,132),(470,148),(472,168),(460,185),(435,192),(415,186),(400,170),(396,150),(398,132)],
    [(108,424),(132,417),(152,427),(170,423),(186,434),(198,444),(206,458),(200,472),(182,482),(160,486),(138,480),(118,468),(104,448),(103,432)],
]
paths['blk'] = []
for ap in PATCHES:
    m = np.zeros((H, W), np.uint8)
    cv2.fillPoly(m, [np.array(ap, np.int32)], 1)
    m = cv2.dilate(m, np.ones((17,17),np.uint8), iterations=1)   # 外扩约8px，贴住板块缺口
    cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    c = max(cnts, key=cv2.contourArea)
    e = cv2.approxPolyDP(c, 0.008*cv2.arcLength(c, True), True).reshape(-1, 2)
    paths['blk'].append(e.tolist())
    cv2.polylines(vis, [e], True, (0,255,0), 2)
print('patches expanded:', len(paths['blk']))

Image.fromarray(vis).save('gen_map_debug.png')

# 底垫块（六板块 + 三黑斑并集外扩）：垫在所有板块之下，填满板块间空隙，外露边缘即金边
union = np.zeros((H, W), np.uint8)
for k in CLASSES:
    if k in paths:
        cv2.fillPoly(union, [np.array(paths[k], np.int32)], 1)
for ap in paths['blk']:
    cv2.fillPoly(union, [np.array(ap, np.int32)], 1)
union = cv2.morphologyEx(union, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8), iterations=1)
union = cv2.dilate(union, np.ones((13, 13), np.uint8), iterations=1)   # 外扩约6px
cnts, _ = cv2.findContours(union, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
c = max(cnts, key=cv2.contourArea)
ap = cv2.approxPolyDP(c, 0.0015 * cv2.arcLength(c, True), True).reshape(-1, 2)
paths['outline'] = ap.tolist()
print('outline pts=%d area=%.0f' % (len(ap), cv2.contourArea(c)))
cv2.polylines(vis, [ap], True, (0, 215, 255), 2)
Image.fromarray(vis).save('gen_map_debug.png')

# 填充预览（模拟最终效果）
cv2.setRNGSeed(7)
prev = np.full((H, W, 3), (40, 37, 33), np.uint8)
hexc = {'blue':(36,84,121), 'red':(105,48,45), 'gold':(192,165,107),
        'purple':(78,55,95), 'olive':(92,93,58), 'grey':(68,66,64)}
# 模拟实际绘制：暗金底垫块垫底（填满空隙、外露边缘即金边），板块压其上
cv2.polylines(prev, [np.array(paths['outline'], np.int32)], True, (70,110,130), 12)  # 晕圈
cv2.fillPoly(prev, [np.array(paths['outline'], np.int32)], (94,147,171))             # 暗金底垫块
for k in CLASSES:
    if k in paths:
        cv2.fillPoly(prev, [np.array(paths[k], np.int32)], hexc[k])
        cv2.polylines(prev, [np.array(paths[k], np.int32)], True, (210,205,195), 1)
for ap in paths['blk']:
    cv2.fillPoly(prev, [np.array(ap, np.int32)], (12,12,13))
    cv2.polylines(prev, [np.array(ap, np.int32)], True, (60,58,55), 3)
Image.fromarray(prev).save('gen_map_fill.png')

# 输出 map_paths.js
def d(pts):
    return 'M' + 'L'.join('%d,%d' % (p[0], p[1]) for p in pts) + 'Z'
js = '/* 由 gen_map_trace.py 从参考图描摹生成，勿手改 */\nconst TRACE={\n'
js += ',\n'.join('%s:"%s"' % (k, d(paths[k])) for k in CLASSES if k in paths)
js += ',\nblk:[%s]' % ','.join('"%s"' % d(ap) for ap in paths['blk'])
js += ',\noutline:"%s"\n};\n' % d(paths['outline'])
with open('map_paths.js', 'w', encoding='utf-8') as f:
    f.write(js)
print('saved map_paths.js / gen_map_debug.png / gen_map_fill.png')
