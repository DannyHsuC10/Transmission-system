import {GEAR_NAMES, meshPhases, planetCenters, profileSegments, RAD, segmentPoint} from "./gear-model.js";

const NS = "http://www.w3.org/2000/svg";
const W = 560, H = 490;
const LEFT = 46, TOP = 15, RIGHT = 15, PLOT_HEIGHT = 431;
const FONT = "system-ui, sans-serif";
export const PLOT_COLORS = ["#255dce", "#bc4435", "#99610a", "#147c68"];
const labelColor = "#4f6073";
const shapeCache = new WeakMap();
let plotCount = 0;

function svg(tag, attrs = {}, content) {
  const node = document.createElementNS(NS, tag);
  for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
  if (content != null) node.textContent = content;
  return node;
}

function xy([x, y]) {
  return `${Number(x.toPrecision(13))} ${Number(y.toPrecision(13))}`;
}

function outline(gear) {
  if (shapeCache.has(gear)) return shapeCache.get(gear);
  const path = [];
  for (const segment of profileSegments(gear)) {
    if (path.length === 0) path.push("M", xy(segmentPoint(segment, 0)));
    if (segment.kind === "arc") {
      path.push("A", segment.radius, segment.radius, "0", segment.a1 - segment.a0 > Math.PI ? 1 : 0,
        "1", xy(segmentPoint(segment, 1)));
    } else {
      const count = segment.kind === "flank" ? 20 : 1;
      path.push("L");
      for (let i = 1; i <= count; i++) path.push(xy(segmentPoint(segment, i / count)));
    }
  }
  path.push("Z");
  const result = path.join(" ");
  shapeCache.set(gear, result);
  return result;
}

function addPitch(model, gear, x, y, dashed = false) {
  const color = PLOT_COLORS[gear.role];
  const circle = svg("circle", {
    cx: x, cy: y, r: gear.geometry.pitch_radius, fill: color, "fill-opacity": 0.033,
    stroke: color, "stroke-width": 1.6, "vector-effect": "non-scaling-stroke",
  });
  if (dashed) circle.setAttribute("stroke-dasharray", "6 3");
  model.append(circle);
}

function addProfiles(model, defs, parts, uid, {fill = false, markerRadius = 0} = {}) {
  const ids = new Map();
  const instances = [];
  for (const {gear, x = 0, y = 0, rotation = 0} of parts) {
    if (!ids.has(gear)) {
      const id = `${uid}-profile-${gear.role}`;
      const color = PLOT_COLORS[gear.role];
      const group = svg("g", {id});
      let d = outline(gear);
      if (gear.bore > 0) {
        const r = gear.bore / 2;
        d += ` M ${r} 0 A ${r} ${r} 0 1 0 ${-r} 0 A ${r} ${r} 0 1 0 ${r} 0 Z`;
      }
      group.append(svg("path", {
        d, stroke: color, "stroke-width": fill ? 1.5 : 1.25,
        fill: fill && !gear.internal ? color : "none", "fill-opacity": 0.09,
        "fill-rule": "evenodd", "stroke-linejoin": "round", "vector-effect": "non-scaling-stroke",
      }));
      if (markerRadius > 0) {
        const {root_radius: root, pitch_radius: pitch} = gear.geometry;
        group.append(svg("circle", {
          cx: (root + (gear.internal ? pitch : gear.bore / 2)) / 2,
          cy: 0, r: Math.min(markerRadius, root * 0.065), fill: color,
        }));
      }
      defs.append(group);
      ids.set(gear, id);
    }
    const center = `translate(${x} ${y})`;
    const phase = rotation / RAD;
    const node = svg("use", {href: "#" + ids.get(gear), transform: `${center} rotate(${phase})`});
    model.append(node);
    instances.push({node, center, phase, role: gear.role});
  }
  return (offsets) => {
    for (const {node, center, phase, role} of instances) {
      node.setAttribute("transform", `${center} rotate(${phase + offsets[role]})`);
    }
  };
}

function niceStep(scale) {
  const target = 53 / scale;
  const unit = 10 ** Math.floor(Math.log10(target));
  const ratio = target / unit;
  return unit * (ratio >= 5 ? 5 : ratio >= 2 ? 2 : 1);
}

function coordinateLabel(value, step) {
  if (step < 0.001 || Math.abs(value) >= 1e6) return value.toExponential(1);
  return String(Number(value.toFixed(Math.max(0, -Math.floor(Math.log10(step))))));
}

function createBoard(title, extent, draw) {
  const uid = `plot-${++plotCount}`;
  const frame = {x: LEFT, y: TOP, w: W - LEFT - RIGHT, h: PLOT_HEIGHT};
  const origin = {x: frame.x + frame.w / 2, y: frame.y + frame.h / 2};
  let plotWidth = W;
  const root = svg("svg", {
    viewBox: `0 0 ${W} ${H}`, width: W, height: H, role: "img",
    "aria-label": title, class: "engineering-plot", tabindex: "0",
  });
  root.append(svg("title", {}, title));
  const defs = svg("defs");
  const clip = svg("clipPath", {id: `${uid}-frame`});
  const rect = {x: frame.x, y: frame.y, width: frame.w, height: frame.h};
  const clipRect = svg("rect", rect);
  clip.append(clipRect);
  defs.append(clip);
  const backdrop = svg("rect", {width: W, height: H, fill: "#f7f9fc"});
  const gridFill = svg("rect", {...rect, fill: "#fbfdff"});
  const gridFrame = svg("rect", {...rect, fill: "none", stroke: "#dce4ed"});
  root.append(defs, backdrop, gridFill);
  const grid = svg("g", {"aria-hidden": "true"});
  const viewport = svg("g", {"clip-path": `url(#${uid}-frame)`});
  const camera = svg("g");
  const model = svg("g");
  camera.append(model);
  viewport.append(camera);
  root.append(grid, viewport, gridFrame);
  const rotateGears = draw(model, defs, uid);
  let zoom = 1, tx = 0, ty = 0, drag = null;

  function render() {
    const scale = zoom * (Math.min(frame.h, frame.w) * 0.44) / extent;
    const x0 = origin.x + tx, y0 = origin.y + ty;
    camera.setAttribute("transform", `translate(${x0} ${y0}) scale(${scale} ${-scale})`);
    root.classList.toggle("is-zoomed", zoom > 1);
    const gridItems = [];
    const step = niceStep(scale);
    const axisText = {"font-family": FONT, "font-size": 11, fill: labelColor};
    for (const horizontal of [false, true]) {
      const a = horizontal ? frame.y : frame.x;
      const b = a + (horizontal ? frame.h : frame.w);
      const zero = horizontal ? y0 : x0;
      const delta = step * scale;
      const first = Math.ceil((a - zero) / delta);
      const last = Math.floor((b - zero) / delta);
      // Indexing by offset caps work even if the origin is far off screen.
      if (Number.isSafeInteger(first) && Number.isSafeInteger(last) && last - first < 90) {
        for (let index = first; index <= last; index++) {
          const pixel = zero + index * delta;
          const stroke = index === 0 ? "#aebcce" : "#e6edf4";
          const coords = horizontal ? {x1: frame.x, x2: frame.x + frame.w, y1: pixel, y2: pixel}
            : {x1: pixel, x2: pixel, y1: frame.y, y2: frame.y + frame.h};
          gridItems.push(svg("line", {...coords, stroke}));
          const mark = horizontal ? {x: frame.x - 5, y: pixel + 3, "text-anchor": "end"}
            : {x: pixel, y: frame.y + frame.h + 16, "text-anchor": "middle"};
          gridItems.push(svg("text", {...axisText, ...mark}, coordinateLabel(index * step * (horizontal ? -1 : 1), step)));
        }
      }
    }
    gridItems.push(
      svg("text", {...axisText, x: frame.x + frame.w, y: H - 9, "text-anchor": "end", "font-weight": 650}, "X (mm)"),
      svg("text", {...axisText, transform: `translate(12 ${origin.y}) rotate(-90)`, "text-anchor": "middle",
        "font-weight": 650}, "Y (mm)"),
    );
    grid.replaceChildren(...gridItems);
  }

  function setZoom(factor, at = origin) {
    const next = Math.min(16, Math.max(0.4, zoom * factor));
    const ratio = next / zoom;
    tx = at.x - origin.x - (at.x - origin.x - tx) * ratio;
    ty = at.y - origin.y - (at.y - origin.y - ty) * ratio;
    zoom = next;
    render();
  }

  function reset() {
    zoom = 1; tx = 0; ty = 0;
    render();
  }

  function local(event) {
    const point = root.createSVGPoint();
    point.x = event.clientX; point.y = event.clientY;
    return point.matrixTransform(root.getScreenCTM().inverse());
  }

  root.addEventListener("wheel", (event) => {
    if (!event.ctrlKey) return;
    event.preventDefault();
    setZoom(event.deltaY < 0 ? 1.17 : 1 / 1.17, local(event));
  }, {passive: false});
  root.addEventListener("pointerdown", (event) => {
    if (event.button !== 0 || (event.pointerType === "touch" && zoom <= 1)) return;
    root.setPointerCapture(event.pointerId);
    drag = local(event);
    root.classList.add("is-dragging");
  });
  root.addEventListener("pointermove", (event) => {
    if (!drag) return;
    const point = local(event);
    tx += point.x - drag.x; ty += point.y - drag.y;
    drag = point;
    render();
  });
  root.addEventListener("lostpointercapture", () => {
    drag = null;
    root.classList.remove("is-dragging");
  });
  root.addEventListener("dblclick", reset);
  root.addEventListener("keydown", (event) => {
    const offsets = {ArrowUp: [0, -25], ArrowDown: [0, 25], ArrowLeft: [-25, 0], ArrowRight: [25, 0]};
    if (offsets[event.key]) {
      tx += offsets[event.key][0]; ty += offsets[event.key][1];
      render();
    } else if (event.key === "Home") reset();
    else if (event.key === "+" || event.key === "=") setZoom(1.25);
    else if (event.key === "-") setZoom(0.8);
    else return;
    event.preventDefault();
  });
  render();
  let observer;
  function observe() {
    observer = new ResizeObserver(([{contentRect: size}]) => {
      if (!size.width || !size.height) return;
      const width = Math.round(H * size.width / size.height);
      if (width === plotWidth || width < 240) return;
      plotWidth = width;
      frame.w = width - LEFT - RIGHT;
      origin.x = frame.x + frame.w / 2;
      root.setAttribute("viewBox", `0 0 ${plotWidth} ${H}`);
      backdrop.setAttribute("width", plotWidth);
      for (const rect of [gridFill, gridFrame, clipRect]) rect.setAttribute("width", frame.w);
      render();
    });
    observer.observe(root);
  }
  return {
    root, title, setZoom, reset, observe, dispose: () => observer?.disconnect(), width: () => plotWidth, rotateGears,
    rotate: (degrees) => model.setAttribute("transform", `rotate(${degrees})`),
  };
}

export function buildPlot(view, design, gears, role) {
  if (view === "single") {
    const gear = gears[role], g = gear.geometry;
    const title = `${GEAR_NAMES[role]}（${gear.teeth} 齒）`;
    const board = createBoard(title, Math.max(g.root_radius, g.tip_radius), (model, defs, uid) => {
      addProfiles(model, defs, [{gear}], uid, {fill: true});
      model.append(svg("circle", {
        r: g.pitch_radius, fill: "none", stroke: PLOT_COLORS[role], "stroke-opacity": 0.5,
        "stroke-dasharray": "5 4", "vector-effect": "non-scaling-stroke",
      }));
    });
    return {boards: [board], roles: [role], warnings: []};
  }

  const centers = planetCenters(design), orbit = Math.hypot(centers[0].x, centers[0].y);
  const [sun, first, second, ring] = gears;
  if (view === "layout") {
    const extent = Math.max(ring.geometry.pitch_radius, orbit + Math.max(first.geometry.pitch_radius, second.geometry.pitch_radius));
    const board = createBoard("行星齒輪系節圓配置圖", extent, (model) => {
      model.append(svg("circle", {
        r: orbit, fill: "none", stroke: "#8e9db1", "stroke-dasharray": "3 5", "vector-effect": "non-scaling-stroke",
      }));
      addPitch(model, ring, 0, 0);
      addPitch(model, sun, 0, 0);
      for (const {x, y} of centers) {
        addPitch(model, first, x, y);
        addPitch(model, second, x, y, true);
        model.append(svg("circle", {cx: x, cy: y, r: extent * 0.009, fill: "#607087"}));
      }
    });
    return {boards: [board], roles: [0, 1, 2, 3], warnings: []};
  }

  const {phases, step, warnings} = meshPhases(design, gears);
  const outer = [{gear: sun, rotation: phases[0]}], inner = [{gear: ring, rotation: phases[3]}];
  for (const [index, {x, y, angle}] of centers.entries()) {
    const rotation = angle + index * step;
    outer.push({gear: first, x, y, rotation: rotation + phases[1]});
    inner.push({gear: second, x, y, rotation: rotation + phases[2]});
  }
  const outerExtent = Math.max(sun.geometry.tip_radius, orbit + first.geometry.tip_radius);
  const innerExtent = Math.max(ring.geometry.root_radius, orbit + second.geometry.tip_radius);
  const extent = Math.max(outerExtent, innerExtent);
  const profileBoard = (title, parts, markerRadius) =>
    createBoard(title, extent, (model, defs, uid) => addProfiles(model, defs, parts, uid, {markerRadius}));
  const boards = view === "overlay"
    ? [profileBoard("全組合（兩層軸向投影）", [...inner, ...outer], extent * 0.013)]
    : [profileBoard("第一層｜太陽輪與第一行星輪", outer),
      profileBoard(`第二層｜第二行星輪與${GEAR_NAMES[3]}`, inner)];
  return {boards, roles: [0, 1, 2, 3], warnings, phases};
}

export function drawingSvg(boards, roles = []) {
  const titleHeight = 33, legendHeight = roles.length ? 31 : 0;
  const width = boards.reduce((sum, board) => sum + board.width(), 0), height = H + titleHeight + legendHeight;
  const drawing = svg("svg", {width, height, viewBox: `0 0 ${width} ${height}`});
  drawing.append(svg("rect", {width, height, fill: "#f7f9fc"}));
  let offset = 0;
  for (const {root, title, width: plotWidth} of boards) {
    const plot = root.cloneNode(true);
    plot.setAttribute("x", offset);
    plot.setAttribute("y", titleHeight);
    plot.setAttribute("width", plotWidth());
    plot.removeAttribute("tabindex");
    drawing.append(svg("text", {
      x: offset + LEFT, y: 23, "font-family": FONT, "font-size": 16,
      "font-weight": 700, fill: "#122338",
    }, title), plot);
    offset += plotWidth();
  }
  const legendStep = Math.min(118, (width - LEFT - RIGHT) / roles.length);
  roles.forEach((role, index) => {
    const x = LEFT + index * legendStep, y = H + titleHeight + 15;
    drawing.append(svg("line", {x1: x, x2: x + 15, y1: y, y2: y, stroke: PLOT_COLORS[role], "stroke-width": 2}),
      svg("text", {x: x + 21, y: y + 4, "font-family": FONT, "font-size": 11, fill: labelColor}, GEAR_NAMES[role]));
  });
  return {content: new XMLSerializer().serializeToString(drawing), width, height};
}

export async function drawingPng(drawing) {
  const url = URL.createObjectURL(new Blob([drawing.content], {type: "image/svg+xml;charset=utf-8"}));
  try {
    const image = new Image();
    image.src = url;
    await image.decode();
    const canvas = document.createElement("canvas");
    canvas.width = drawing.width * 3;
    canvas.height = drawing.height * 3;
    canvas.getContext("2d").drawImage(image, 0, 0, canvas.width, canvas.height);
    return await new Promise((resolve, reject) => canvas.toBlob((blob) => {
      if (blob) resolve(blob);
      else reject(new Error("無法產生 PNG 圖片。"));
    }, "image/png"));
  } finally {
    URL.revokeObjectURL(url);
  }
}
