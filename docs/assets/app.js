import {
  centerDistances, defaultDesign, GEAR_NAMES, gearEnvelope, gearRatio, GEOMETRY_ROWS,
  makeGears, meshPhases, PROFILE_FIELDS, RAD, readGearCsv, readProfileValues,
  readSearchValues, readSystemValues, readTeeth, SYSTEM_FIELDS, TEETH_KEYS,
} from "./gear-model.js";
import {buildPlot, drawingPng, drawingSvg, PLOT_COLORS} from "./gear-plot.js";

const $ = (id) => document.getElementById(id);
const defaults = defaultDesign();
let design = defaults, gears = makeGears(defaults);
let mode = "system", view = "layout", role = 0;
let profileDrafts = defaults.profiles.map((profile) => ({...profile}));
let boards = [], plotRoles = [], rotation = null;
let searchWorker = null, candidates = [], selectedCandidate = null;
let cadWorker = null, cadRequest = null;

const SEARCH_FIELDS = [
  ["M", "模數", "mm"], ["max_diameter", "最大齒輪外廓", "mm"],
  ["min_ratio", "最低齒比 z"], ["min_teeth", "最小齒數", "齒"], ["n", "行星輪組數", "組"],
];
const VIEW_LABELS = {
  layout: ["行星齒輪系節圓配置", "兩級行星輪共用中心，沿行星架等角分布。"],
  assembly: ["齒輪系組合", "分別查看第一層外嚙合與第二層內嚙合。"],
  overlay: ["齒輪系全組合", "將兩層齒形投影到同一平面。"],
  results: ["組合搜尋結果", "候選組合依齒比、外廓由小到大排列。"],
};
const MODE_VIEWS = {system: ["layout", "assembly", "overlay"], single: ["single", "details"], search: ["results"]};
const modeTabs = [...document.querySelectorAll("[data-mode]")];
const viewTabs = [...document.querySelectorAll("[data-view]")];

function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text != null) node.textContent = text;
  if (className) node.className = className;
  return node;
}

function fillFields(container, fields, {prefix, symbols = false} = {}) {
  const inputs = {};
  const nodes = fields.map(([key, label, unit]) => {
    const field = element("div", null, "field");
    const id = `${prefix}-${key}`;
    const fieldLabel = element("label", label, "field-label");
    fieldLabel.htmlFor = id;
    if (symbols) fieldLabel.append(element("code", key));
    if (unit) fieldLabel.append(element("span", " (" + unit + ")", "sr-only"));
    const shell = element("div", null, "input-shell");
    const input = element("input");
    input.id = id;
    input.type = "text";
    input.inputMode = ["Ts", "Tp1", "Tp2", "Tr", "n", "teeth", "min_teeth"].includes(key) ? "numeric" : "decimal";
    input.autocomplete = "off";
    input.spellcheck = false;
    shell.append(input);
    if (unit) {
      input.classList.add("with-unit");
      const suffix = element("span", unit, "field-unit");
      suffix.setAttribute("aria-hidden", "true");
      shell.append(suffix);
    }
    field.append(fieldLabel, shell);
    inputs[key] = input;
    return field;
  });
  container.replaceChildren(...nodes);
  return inputs;
}

function valuesOf(inputs) {
  return Object.fromEntries(Object.entries(inputs).map(([key, field]) => [key, field.value]));
}

function setValues(inputs, values) {
  for (const [key, field] of Object.entries(inputs)) field.value = values[key] ?? "";
}

const systemInputs = fillFields($("system-fields"), SYSTEM_FIELDS, {prefix: "system", symbols: true});
const profileInputs = fillFields($("profile-fields"), [["teeth", "齒數", "齒"], ...PROFILE_FIELDS], {prefix: "profile"});
const searchInputs = fillFields($("search-fields"), SEARCH_FIELDS, {prefix: "search"});
setValues(systemInputs, defaults);
setValues(searchInputs, {M: defaults.M, max_diameter: Math.ceil(gearEnvelope(gears)), min_ratio: 8, min_teeth: 20, n: defaults.n});

function status(message, error = false) {
  $("design-status").textContent = message;
  $("design-status").classList.toggle("error", error);
}

function selectTab(button, selected) {
  button.setAttribute("aria-selected", String(selected));
  button.tabIndex = selected ? 0 : -1;
}

function wireTabs(tabs, select) {
  for (const button of tabs) {
    button.addEventListener("click", () => select(button));
    button.addEventListener("keydown", (event) => {
      const visible = tabs.filter((tab) => !tab.hidden);
      const index = visible.indexOf(button);
      let next;
      if (event.key === "ArrowRight") next = visible[(index + 1) % visible.length];
      else if (event.key === "ArrowLeft") next = visible[(index - 1 + visible.length) % visible.length];
      else if (event.key === "Home") next = visible[0];
      else if (event.key === "End") next = visible.at(-1);
      else return;
      event.preventDefault();
      select(next);
      next.focus();
    });
  }
}

function changeMode(next, initial = MODE_VIEWS[next][0]) {
  mode = next;
  for (const tab of modeTabs) {
    const selected = tab.dataset.mode === next;
    selectTab(tab, selected);
    $(tab.getAttribute("aria-controls")).hidden = !selected;
  }
  for (const tab of viewTabs) tab.hidden = !MODE_VIEWS[next].includes(tab.dataset.view);
  if (next === "single") updateProfileInputs();
  changeView(initial);
}

function changeView(next) {
  view = next;
  for (const tab of viewTabs) selectTab(tab, tab.dataset.view === next);
  $("view-panel").setAttribute("aria-labelledby", "tab-" + next);
  renderView();
}

wireTabs(modeTabs, (button) => {
  if (button.dataset.mode !== mode) changeMode(button.dataset.mode);
});
wireTabs(viewTabs, (button) => {
  if (button.dataset.view !== view) changeView(button.dataset.view);
});

function renderSummary() {
  $("metric-module").textContent = String(design.M);
  $("metric-planets").textContent = design.n;
  $("metric-ratio").textContent = gearRatio(design).toFixed(3);
  $("metric-diameter").textContent = gearEnvelope(gears).toFixed(2);
  $("single-module").textContent = `${design.M} mm`;
  const [external, internal] = centerDistances(design);
  $("center-distances").textContent = `外嚙合 ${external.toFixed(3)} ／ 內嚙合 ${internal.toFixed(3)} mm`;
}

function updateProfileInputs() {
  setValues(profileInputs, {...profileDrafts[role], teeth: systemInputs[TEETH_KEYS[role]].value});
  profileInputs.bore_diameter.disabled = role === 3;
  profileInputs.bore_diameter.placeholder = role === 3 ? "—" : String(design.axle);
  $("bore-hint").hidden = role === 3;
}

function commitDesign(next, message = "已套用參數。") {
  const calculated = makeGears(next);
  const searchChanged = next.axle !== design.axle || next.profiles !== design.profiles;
  design = next;
  gears = calculated;
  if (searchChanged) clearSearch();
  renderSummary();
  renderView();
  status(message);
}

function showError(error) {
  status(error.message || "操作未完成，請再試一次。", true);
}

$("system-form").addEventListener("input", () => status("參數已修改。按「更新圖形」或 Enter 套用。"));
$("system-form").addEventListener("submit", (event) => {
  event.preventDefault();
  try {
    commitDesign({...readSystemValues(valuesOf(systemInputs)), profiles: design.profiles});
  } catch (error) {
    showError(new Error(error.message + " 仍顯示上次套用的結果。"));
  }
});

$("reset-design").addEventListener("click", () => {
  setValues(systemInputs, defaults);
  profileDrafts = defaults.profiles.map((profile) => ({...profile}));
  commitDesign(defaults, "已還原預設參數。");
});

$("import-csv").addEventListener("click", () => $("csv-file").click());
$("csv-file").addEventListener("change", async (event) => {
  const [file] = event.target.files;
  event.target.value = "";
  if (!file) return;
  try {
    if (file.size > 1_000_000) throw new Error("參數 CSV 檔案須小於 1 MB。");
    const values = readGearCsv(await file.text());
    commitDesign({...values, profiles: design.profiles}, `已匯入 ${file.name}。`);
    setValues(systemInputs, values);
    if (mode === "single") updateProfileInputs();
  } catch (error) {
    showError(error);
  }
});

$("gear-role").addEventListener("change", (event) => {
  role = Number(event.target.value);
  updateProfileInputs();
  renderView();
});

$("profile-form").addEventListener("input", (event) => {
  const {teeth, ...draft} = valuesOf(profileInputs);
  if (event.target === profileInputs.teeth) systemInputs[TEETH_KEYS[role]].value = teeth;
  profileDrafts[role] = draft;
  status("齒形已修改。按「套用到齒輪系」或 Enter 更新。");
});

$("profile-form").addEventListener("submit", (event) => {
  event.preventDefault();
  try {
    const values = valuesOf(profileInputs);
    const teeth = readTeeth(values.teeth);
    const profile = readProfileValues(values, role === 3);
    const profiles = design.profiles.map((item, index) => index === role ? profile : item);
    commitDesign({...design, [TEETH_KEYS[role]]: teeth, profiles});
    profileDrafts[role] = profile;
    systemInputs[TEETH_KEYS[role]].value = teeth;
    updateProfileInputs();
  } catch (error) {
    showError(error);
  }
});

function descriptionList(container, rows) {
  container.replaceChildren(...rows.map(([label, value]) => {
    const pair = element("div");
    pair.append(element("dt", label), element("dd", value));
    return pair;
  }));
}

function notice(message = "", error = false) {
  $("plot-notice").hidden = !message;
  $("plot-notice").textContent = message;
  $("plot-notice").classList.toggle("error", error);
}

function renderDetails(gear) {
  const rows = [
    ["齒數", gear.teeth, "齒"], ["壓力角", gear.settings.pressure_angle, "°"],
    ["軸孔直徑", gear.internal ? "—" : gear.bore.toFixed(6), gear.internal ? "—" : "mm"],
    ...GEOMETRY_ROWS.map(([key, label, unit]) => [label, gear.geometry[key].toFixed(6), unit || "—"]),
  ];
  $("details-body").replaceChildren(...rows.map(([label, value, unit]) => {
    const row = element("tr");
    const header = element("th", label);
    header.scope = "row";
    row.append(header, element("td", value), element("td", unit));
    return row;
  }));
}

function renderView() {
  stopRotation();
  boards.forEach((board) => board.dispose());
  boards = [];
  plotRoles = [];
  const gear = gears[role];
  const labels = VIEW_LABELS[view] ?? (view === "single"
    ? [`${gear.name}（${gear.teeth} 齒）`, "查看漸開線輪廓、節圓及軸孔。"]
    : [`${gear.name}｜詳細參數`, "依目前已套用的齒數、模數與齒形設定計算。"]);
  $("view-title").textContent = labels[0];
  $("view-description").textContent = labels[1];
  const isPlot = view !== "details" && view !== "results";
  $("plot-toolbar").hidden = !isPlot;
  $("plot-content").hidden = !isPlot;
  $("details-content").hidden = view !== "details";
  $("results-content").hidden = view !== "results";
  notice();
  if (view === "details") renderDetails(gear);
  if (!isPlot) return;
  const grid = $("plot-grid");
  grid.replaceChildren();
  $("single-stats").hidden = true;
  $("rotate-gear").hidden = true;
  $("phase-info").hidden = true;
  try {
    const plot = buildPlot(view, design, gears, role);
    boards = plot.boards;
    plotRoles = plot.roles;
    grid.classList.toggle("split", boards.length > 1);
    for (const board of boards) {
      const figure = element("figure", null, "plot-board");
      if (boards.length > 1) figure.append(element("figcaption", board.title));
      figure.append(board.root);
      grid.append(figure);
      board.observe();
    }
    $("plot-legend").replaceChildren(...plotRoles.map((index) => {
      const label = view === "single" ? gear.name + "（虛線為節圓）" : GEAR_NAMES[index];
      const item = element("li");
      const swatch = element("span", null, view === "layout" && index === 2 ? "legend-swatch dashed" : "legend-swatch");
      swatch.style.setProperty("--gear-color", PLOT_COLORS[index]);
      item.append(swatch, label);
      return item;
    }));
    if (plot.warnings.length) notice(plot.warnings.join("\n"));
    if (view === "single") {
      const g = gear.geometry;
      descriptionList($("single-stats"), [
        ["節圓", `Ø ${g.pitch_diameter.toFixed(3)} mm`], ["齒頂圓", `Ø ${g.tip_diameter.toFixed(3)} mm`],
        ["齒根圓", `Ø ${g.root_diameter.toFixed(3)} mm`], ["節圓齒厚", `${g.tooth_thickness.toFixed(3)} mm`],
        ["節圓齒槽", `${g.tooth_space.toFixed(3)} mm`], ["齒根參考圓角", `R ${g.fillet_radius.toFixed(3)} mm`],
      ]);
      $("single-stats").hidden = false;
      $("rotate-gear").hidden = false;
    }
    if (view === "assembly" || view === "overlay") {
      const [external, internal] = centerDistances(design);
      const {phases} = meshPhases(design, gears);
      descriptionList($("phase-values"), [
        ["外嚙合中心距", `${external.toFixed(6)} mm`], ["內嚙合中心距", `${internal.toFixed(6)} mm`],
        ...phases.map((phase, index) => [GEAR_NAMES[index] + "相位", `${(phase / RAD).toFixed(6)}°`]),
      ]);
      $("phase-info").hidden = false;
    }
  } catch (error) {
    notice(error.message, true);
    $("plot-content").hidden = true;
    $("plot-toolbar").hidden = true;
  }
}

function stopRotation() {
  if (rotation === null) return;
  cancelAnimationFrame(rotation);
  rotation = null;
  for (const board of boards) board.rotate(0);
  $("rotate-gear").setAttribute("aria-pressed", "false");
  $("rotate-gear").querySelector("span").textContent = "旋轉預覽";
}

$("rotate-gear").addEventListener("click", () => {
  if (rotation !== null) {
    stopRotation();
    return;
  }
  const [board] = boards;
  if (!board) return;
  $("rotate-gear").setAttribute("aria-pressed", "true");
  $("rotate-gear").querySelector("span").textContent = "停止旋轉";
  const start = performance.now();
  const frame = (now) => {
    board.rotate(((now - start) * 0.08) % 360);
    rotation = requestAnimationFrame(frame);
  };
  rotation = requestAnimationFrame(frame);
});

$("zoom-in").addEventListener("click", () => boards.forEach((board) => board.setZoom(1.25)));
$("zoom-out").addEventListener("click", () => boards.forEach((board) => board.setZoom(0.8)));
$("zoom-reset").addEventListener("click", () => boards.forEach((board) => board.reset()));

function download(blob, name) {
  const url = URL.createObjectURL(blob);
  const link = element("a");
  link.href = url;
  link.download = name;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 30_000);
}

async function downloadDrawing(drawing, name, format) {
  const blob = format === "SVG" ? new Blob([drawing.content], {type: "image/svg+xml;charset=utf-8"}) : await drawingPng(drawing);
  download(blob, name);
  status("已匯出 " + name);
}

$("save-plot").addEventListener("click", async () => {
  if (!boards.length) return;
  const button = $("save-plot");
  button.disabled = true;
  try {
    const title = view === "single" ? `${gears[role].name}_${gears[role].teeth}T` : VIEW_LABELS[view][0];
    await downloadDrawing(drawingSvg(boards, plotRoles), title + ".png", "PNG");
  } catch (error) {
    showError(error);
  } finally {
    button.disabled = false;
  }
});

function clearSearch(message = "", error = false) {
  searchWorker?.terminate();
  searchWorker = null;
  candidates = [];
  selectedCandidate = null;
  $("run-search").disabled = false;
  $("apply-candidate").disabled = true;
  $("results-body").replaceChildren();
  $("result-table").hidden = true;
  $("search-empty").hidden = false;
  $("search-status").textContent = message;
  $("search-status").classList.toggle("error", error);
}

function showCandidates(result) {
  candidates = result.candidates;
  if (!result.total) {
    $("search-status").textContent = "找不到符合條件的組合。可提高外廓上限、降低齒比門檻或減少行星輪組數。";
    return;
  }
  const rows = candidates.map(({design: d, ratio, diameter, maxPlanets}, index) => {
    const row = element("tr");
    const radio = element("input");
    radio.type = "radio";
    radio.name = "candidate";
    radio.setAttribute("aria-label", `選取第 ${index + 1} 組，齒數 ${d.Ts}、${d.Tp1}、${d.Tp2}、${d.Tr}`);
    function select() {
      if (selectedCandidate !== null) rows[selectedCandidate].classList.remove("is-selected");
      selectedCandidate = index;
      row.classList.add("is-selected");
      $("apply-candidate").disabled = false;
    }
    radio.addEventListener("change", select);
    row.addEventListener("click", (event) => {
      if (event.target !== radio) {
        radio.checked = true;
        radio.focus({preventScroll: true});
        select();
      }
    });
    const check = element("td");
    check.append(radio);
    row.append(check, ...[d.Ts, d.Tp1, d.Tp2, d.Tr, ratio.toFixed(3), diameter.toFixed(2), maxPlanets]
      .map((value) => element("td", value)));
    return row;
  });
  $("results-body").replaceChildren(...rows);
  $("search-empty").hidden = true;
  $("result-table").hidden = false;
  $("result-table").scrollTop = 0;
  const shown = result.total > candidates.length ? `，顯示前 ${candidates.length} 組` : "";
  $("search-status").textContent = `找到 ${result.total.toLocaleString("zh-TW")} 組${shown}。選取一列後按「產生齒輪系」。`;
}

$("search-form").addEventListener("input", () => clearSearch());
$("search-form").addEventListener("submit", (event) => {
  event.preventDefault();
  clearSearch();
  try {
    const criteria = readSearchValues(valuesOf(searchInputs));
    const worker = new Worker(new URL("./search-worker.js", import.meta.url), {type: "module"});
    searchWorker = worker;
    $("search-status").textContent = "搜尋中…";
    $("run-search").disabled = true;
    worker.onmessage = ({data}) => {
      if (searchWorker !== worker) return;
      clearSearch(data.error, Boolean(data.error));
      if (data.result) showCandidates(data.result);
    };
    worker.onerror = () => {
      if (searchWorker === worker) clearSearch("無法執行搜尋，請重新整理頁面後再試。", true);
    };
    worker.postMessage({design, criteria});
  } catch (error) {
    clearSearch(error.message, true);
  }
});

$("apply-candidate").addEventListener("click", () => {
  if (selectedCandidate === null) return;
  const next = {...candidates[selectedCandidate].design, profiles: design.profiles};
  try {
    commitDesign(next, "已套用搜尋結果。");
    setValues(systemInputs, next);
    changeMode("system", "assembly");
    $("tab-assembly").focus({preventScroll: true});
  } catch (error) {
    showError(error);
  }
});

const dialog = $("cad-dialog");
let cadInputs;
function cadError(message) {
  $("cad-error").textContent = message;
  $("cad-error").hidden = !message;
}

function finishCad() {
  cadWorker?.terminate();
  cadWorker = null;
  $("export-gear").disabled = false;
  $("download-cad").disabled = false;
  $("download-cad").lastChild.textContent = " 下載";
}

function exportCad(request, values = {}) {
  const fromDialog = dialog.open;
  function report(error) {
    finishCad();
    if (fromDialog) cadError(error);
    else status(error, true);
  }
  try {
    const worker = new Worker(new URL("./cad-worker.js", import.meta.url), {type: "module"});
    cadWorker = worker;
    $("export-gear").disabled = true;
    $("download-cad").disabled = true;
    $("download-cad").lastChild.textContent = " 產生中…";
    cadError("");
    worker.onmessage = ({data}) => {
      if (cadWorker !== worker) return;
      if (data.error) {
        report(data.error);
        return;
      }
      finishCad();
      if (fromDialog) dialog.close();
      download(new Blob([data.content], {type: "application/octet-stream"}), request.name);
      status("已匯出 " + request.name);
    };
    worker.onerror = () => {
      if (cadWorker === worker) report("無法產生 CAD 檔案，請重新整理頁面後再試。");
    };
    worker.postMessage({...request, ...values});
  } catch (error) {
    report(error.message);
  }
}

$("export-gear").addEventListener("click", async () => {
  stopRotation();
  const gear = gears[role];
  const format = $("gear-format").value;
  const name = `${gear.name}_${gear.teeth}T.${format.toLowerCase()}`;
  if (format === "PNG" || format === "SVG") {
    $("export-gear").disabled = true;
    try {
      const plot = view === "single" && boards.length ? {boards, roles: plotRoles}
        : buildPlot("single", design, gears, role);
      await downloadDrawing(drawingSvg(plot.boards, plot.roles), name, format);
    } catch (error) {
      showError(error);
    } finally {
      $("export-gear").disabled = false;
    }
    return;
  }
  cadRequest = {gear, format, name};
  if (!gear.internal && format === "DXF") {
    exportCad(cadRequest);
    return;
  }
  $("cad-title").textContent = `匯出 ${format}｜${gear.name}`;
  $("cad-description").textContent = gear.internal
    ? `外徑須大於齒根圓直徑 ${Number(gear.geometry.root_diameter.toPrecision(10))} mm。`
    : "設定齒輪沿軸向拉伸的厚度。";
  const fields = [];
  if (gear.internal) fields.push(["outerDiameter", `${gear.name}外徑`, "mm"]);
  if (format === "STEP") fields.push(["thickness", "齒輪厚度", "mm"]);
  cadInputs = fillFields($("cad-fields"), fields, {prefix: "cad"});
  setValues(cadInputs, {outerDiameter: Number((gear.geometry.root_diameter + 2 * design.M).toPrecision(12)), thickness: 5});
  cadError("");
  dialog.showModal();
  Object.values(cadInputs)[0].select();
});

$("cad-form").addEventListener("submit", (event) => {
  event.preventDefault();
  if (cadRequest && !cadWorker) exportCad(cadRequest, valuesOf(cadInputs));
});
$("cancel-export").addEventListener("click", () => dialog.close());
dialog.addEventListener("close", () => {
  cadRequest = null;
  finishCad();
});

renderSummary();
updateProfileInputs();
clearSearch();
changeMode("system");
status("已載入預設參數。");
