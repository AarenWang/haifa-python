const data = window.LUA_VM_DEMO_DATA;

const els = {
  demoSelect: document.querySelector("#demoSelect"),
  modeSelect: document.querySelector("#modeSelect"),
  demoSummary: document.querySelector("#demoSummary"),
  focusTags: document.querySelector("#focusTags"),
  sourceView: document.querySelector("#sourceView"),
  instructionHeading: document.querySelector("#instructionHeading"),
  instructionView: document.querySelector("#instructionView"),
  stateHeading: document.querySelector("#stateHeading"),
  stepLabel: document.querySelector("#stepLabel"),
  statusPill: document.querySelector("#statusPill"),
  pcLabel: document.querySelector("#pcLabel"),
  registerView: document.querySelector("#registerView"),
  callStackView: document.querySelector("#callStackView"),
  upvalueView: document.querySelector("#upvalueView"),
  outputView: document.querySelector("#outputView"),
  nzcvView: document.querySelector("#nzcvView"),
  memoryView: document.querySelector("#memoryView"),
  instructionTitle: document.querySelector("#instructionTitle"),
  opcodeExplanation: document.querySelector("#opcodeExplanation"),
  changeView: document.querySelector("#changeView"),
  resetBtn: document.querySelector("#resetBtn"),
  prevBtn: document.querySelector("#prevBtn"),
  stepBtn: document.querySelector("#stepBtn"),
  runBtn: document.querySelector("#runBtn"),
  speedSlider: document.querySelector("#speedSlider"),
  speedLabel: document.querySelector("#speedLabel"),
};

let demoIndex = 0;
let mode = "bytecode";
let stepIndex = 0;
let runTimer = null;

function currentDemo() {
  return data.demos[demoIndex];
}

function currentTrace() {
  const demo = currentDemo();
  return demo.views?.[mode] || demo;
}

function currentStep() {
  return currentTrace().steps[stepIndex];
}

function init() {
  data.demos.forEach((demo, index) => {
    const option = document.createElement("option");
    option.value = String(index);
    option.textContent = demo.title;
    els.demoSelect.appendChild(option);
  });

  els.demoSelect.addEventListener("change", () => {
    stopRun();
    demoIndex = Number(els.demoSelect.value);
    stepIndex = 0;
    render();
  });
  els.modeSelect.addEventListener("change", () => {
    stopRun();
    mode = els.modeSelect.value;
    stepIndex = 0;
    render();
  });
  els.resetBtn.addEventListener("click", () => {
    stopRun();
    stepIndex = 0;
    render();
  });
  els.prevBtn.addEventListener("click", () => {
    stopRun();
    stepIndex = Math.max(0, stepIndex - 1);
    render();
  });
  els.stepBtn.addEventListener("click", () => {
    stopRun();
    stepForward();
  });
  els.runBtn.addEventListener("click", () => {
    if (runTimer) {
      stopRun();
    } else {
      startRun();
    }
  });
  els.speedSlider.addEventListener("input", () => {
    els.speedLabel.textContent = `${els.speedSlider.value} ms`;
    if (runTimer) {
      stopRun();
      startRun();
    }
  });

  els.speedLabel.textContent = `${els.speedSlider.value} ms`;
  render();
}

function startRun() {
  const trace = currentTrace();
  if (stepIndex >= trace.steps.length - 1) {
    stepIndex = 0;
  }
  els.runBtn.textContent = "Pause";
  els.runBtn.classList.add("primary");
  runTimer = window.setInterval(() => {
    if (!stepForward()) {
      stopRun();
    }
  }, Number(els.speedSlider.value));
}

function stopRun() {
  if (runTimer) {
    window.clearInterval(runTimer);
    runTimer = null;
  }
  els.runBtn.textContent = "Run";
  els.runBtn.classList.remove("primary");
}

function stepForward() {
  const trace = currentTrace();
  if (stepIndex >= trace.steps.length - 1) {
    render();
    return false;
  }
  stepIndex += 1;
  render();
  return stepIndex < trace.steps.length - 1;
}

function render() {
  const demo = currentDemo();
  const trace = currentTrace();
  const step = currentStep();
  els.demoSelect.value = String(demoIndex);
  els.modeSelect.value = mode;
  els.demoSummary.textContent = `${demo.summary} ${trace.summary || ""}`;
  els.instructionHeading.textContent = trace.title || "Bytecode";
  els.stateHeading.textContent = `${trace.title || "VM"} State`;
  els.focusTags.replaceChildren(
    ...demo.focus.map((tag) => {
      const span = document.createElement("span");
      span.className = "tag";
      span.textContent = tag;
      return span;
    }),
  );
  renderSource(demo, step);
  renderInstructions(trace, step);
  renderState(trace, step);
  renderExplanation(trace, step);
  updateControls(trace, step);
}

function renderSource(demo, step) {
  const activeLine = step.currentSourceLine;
  const rows = demo.source.split(/\r?\n/).map((line, index) => {
    const item = document.createElement("li");
    const lineNo = index + 1;
    item.dataset.line = String(lineNo).padStart(2, "0");
    item.textContent = line || " ";
    if (lineNo === activeLine) {
      item.classList.add("current");
    }
    return item;
  });
  els.sourceView.replaceChildren(...rows);
  const active = els.sourceView.querySelector(".current");
  if (active) {
    active.scrollIntoView({ block: "nearest" });
  }
}

function renderInstructions(trace, step) {
  const rows = trace.instructions.map((inst) => {
    const row = document.createElement("div");
    row.className = "instruction-row";
    if (inst.pc === step.pc) {
      row.classList.add("current");
    }
    if (inst.pc === step.previousPc) {
      row.classList.add("previous");
    }
    row.innerHTML = `
      <span class="pc">${String(inst.pc).padStart(3, "0")}</span>
      <span class="opcode">${escapeHtml(displayOpcode(inst))}</span>
      <span class="args">${escapeHtml(formatArgs(inst.args))}</span>
    `;
    return row;
  });
  els.instructionView.replaceChildren(...rows);
  const active = els.instructionView.querySelector(".current");
  if (active) {
    active.scrollIntoView({ block: "nearest" });
  }
}

function renderState(trace, step) {
  els.stepLabel.textContent = `Step ${step.step} of ${trace.steps.length - 1}`;
  els.pcLabel.textContent = `PC ${step.pc}${step.previousPc !== null ? `, last PC ${step.previousPc}` : ""}`;
  els.statusPill.textContent = step.status;
  els.statusPill.className = `status-pill ${step.status === "halted" ? "halted" : ""} ${
    step.status === "error" ? "error" : ""
  }`;

  const registers = step.registers.map((entry) => {
    const row = document.createElement("div");
    row.className = `register-row ${entry.changed ? "changed" : ""}`;
    row.innerHTML = `
      <span class="register-name">${escapeHtml(entry.name)}</span>
      <span class="register-value">${escapeHtml(formatValue(entry.value))}</span>
    `;
    return row;
  });
  els.registerView.replaceChildren(...registers);
  renderMiniList(
    els.callStackView,
    step.callStack.map(formatFrame),
    "<empty>",
  );
  renderMiniList(els.upvalueView, step.upvalues.map(formatValue), "<empty>");
  renderMiniList(els.outputView, step.output.map(formatValue), "<empty>");
  renderNzcV(step, mode);
  renderMemory(trace, step.memorySections || {});
}

function renderNzcV(step, mode) {
  if (mode !== "armv9") {
    const empty = document.createElement("div");
    empty.className = "mini-item";
    empty.textContent = "<not applicable for bytecode VM>";
    els.nzcvView.replaceChildren(empty);
    return;
  }
  const row = step.registers.find((entry) => entry.name === "NZCV");
  if (!row || row.value === undefined) {
    const empty = document.createElement("div");
    empty.className = "mini-item";
    empty.textContent = "<no NZCV flags>";
    els.nzcvView.replaceChildren(empty);
    return;
  }
  const flags = row.value;
  const flagEntries = [];
  for (const name of ["N", "Z", "C", "V"]) {
    const item = document.createElement("div");
    item.className = "mini-item nzcv-flag";
    const on = flags && (flags[name] === true || flags[name] === "true" || flags[name] === 1);
    item.textContent = `${name} = ${on ? "1" : "0"}`;
    item.classList.toggle("on", on);
    flagEntries.push(item);
  }
  els.nzcvView.replaceChildren(...flagEntries);
}

function renderMemory(trace, sections) {
  const visibleSections = { ...sections };
  if (trace.stackSlots && Object.keys(trace.stackSlots).length) {
    visibleSections.stack_slots = trace.stackSlots;
  }
  const names = Object.keys(visibleSections).filter((name) => hasSectionContent(visibleSections[name]));
  if (!names.length) {
    const empty = document.createElement("div");
    empty.className = "mini-item";
    empty.textContent = "<empty>";
    els.memoryView.replaceChildren(empty);
    return;
  }

  els.memoryView.replaceChildren(
    ...names.map((name) => {
      const section = document.createElement("section");
      section.className = "memory-section";
      const title = document.createElement("div");
      title.className = "memory-title";
      title.textContent = name;
      const body = document.createElement("div");
      body.className = "memory-body";
      body.textContent = formatMemorySection(visibleSections[name]);
      section.replaceChildren(title, body);
      return section;
    }),
  );
}

function hasSectionContent(value) {
  if (value === null || value === undefined) {
    return false;
  }
  if (Array.isArray(value)) {
    return value.length > 0;
  }
  if (typeof value === "object" && Array.isArray(value.entries)) {
    return value.entries.length > 0;
  }
  if (typeof value === "object") {
    return Object.keys(value).length > 0;
  }
  return true;
}

function formatMemorySection(value) {
  if (value && typeof value === "object" && Array.isArray(value.entries)) {
    if (!value.entries.length) {
      return `<empty stack, ${value.length || 0} slots>`;
    }
    return value.entries
      .map((entry) => `[${entry.index}] = ${formatValue(entry.value)}`)
      .join("\n");
  }
  if (Array.isArray(value)) {
    return value.map((item, index) => `[${index}] = ${formatValue(item)}`).join("\n");
  }
  if (value && typeof value === "object") {
    return Object.entries(value)
      .map(([key, item]) => `${key}: ${formatValue(item)}`)
      .join("\n");
  }
  return formatValue(value);
}

function renderMiniList(container, values, emptyText) {
  if (!values.length) {
    const empty = document.createElement("div");
    empty.className = "mini-item";
    empty.textContent = emptyText;
    container.replaceChildren(empty);
    return;
  }
  container.replaceChildren(
    ...values.map((value) => {
      const item = document.createElement("div");
      item.className = "mini-item";
      item.textContent = value;
      return item;
    }),
  );
}

function renderExplanation(trace, step) {
  const previous = step.previousOpcode
    ? `Executed ${step.previousOpcode}`
    : "Ready before the first instruction";
  const current = step.currentInstruction
    ? `next: ${displayOpcode(step.currentInstruction)} @ pc=${step.currentInstruction.pc}`
    : "program halted";
  els.instructionTitle.textContent = `${previous}; ${current}`;

  const opcode = step.previousOpcode || step.currentInstruction?.opcode;
  const explanation =
    data.opcodeExplanations[opcode] ||
    "This instruction is part of the VM execution model. Watch highlighted registers, stack slots, and heap objects to see its effect.";
  const changeText = step.changedRegisters.length
    ? ` Changed registers: ${step.changedRegisters.join(", ")}.`
    : " No register changed in this snapshot.";
  const sourceOpcode = step.currentInstruction?.debug?.sourceOpcode
    ? ` Lowered from ${step.currentInstruction.debug.sourceOpcode}.`
    : "";
  els.opcodeExplanation.textContent = explanation + changeText + sourceOpcode;

  const chips = [];
  chips.push(chip(trace.kind || mode, false));
  if (step.previousOpcode) {
    chips.push(chip(`opcode ${step.previousOpcode}`, true));
  }
  chips.push(chip(`return ${formatValue(step.returnValue)}`, false));
  if (step.lastReturn.length) {
    chips.push(chip(`last return ${step.lastReturn.map(formatValue).join(", ")}`, false));
  }
  for (const name of step.changedRegisters) {
    chips.push(chip(name, true));
  }
  if (step.error) {
    chips.push(chip(`error ${step.error}`, true));
  }
  els.changeView.replaceChildren(...chips);
}

function chip(text, changed) {
  const span = document.createElement("span");
  span.className = `change-chip ${changed ? "changed" : ""}`;
  span.textContent = text;
  return span;
}

function updateControls(trace, step) {
  els.prevBtn.disabled = stepIndex === 0;
  els.stepBtn.disabled = stepIndex >= trace.steps.length - 1 || step.status === "error";
}

function displayOpcode(inst) {
  if (inst.text) {
    return inst.text.split(/\s+/)[0];
  }
  return inst.opcode;
}

function formatArgs(args) {
  return args.map(formatValue).join(", ");
}

function formatFrame(frame) {
  if (typeof frame === "string") {
    return frame;
  }
  if (frame && typeof frame === "object") {
    if (frame.label) {
      return `${frame.label} return=${frame.return_pc} fp=${frame.caller_fp} sp=${frame.caller_sp}`;
    }
    if (frame.function) {
      return `${frame.function} @ pc=${frame.pc} (${frame.line}:${frame.column})`;
    }
    if (frame.return_pc !== undefined) {
      return `return=${frame.return_pc}`;
    }
  }
  return formatValue(frame);
}

function formatValue(value) {
  if (value === null) {
    return "nil";
  }
  if (value === undefined) {
    return "<missing>";
  }
  if (typeof value === "string") {
    return JSON.stringify(value);
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  if (Array.isArray(value)) {
    return `[${value.map(formatValue).join(", ")}]`;
  }
  if (typeof value !== "object") {
    return String(value);
  }
  if (value.kind === "cell") {
    return `cell(${formatValue(value.value)})`;
  }
  if (value.kind === "closure" || value.type === "closure") {
    const name = value.debugName || value.label;
    const upvalues = value.upvalues?.length ? ` upvalues=${value.upvalues.map(formatValue).join(", ")}` : "";
    return `<closure ${name}${upvalues}>`;
  }
  if (value.kind === "table") {
    const array = value.array?.map(formatValue).join(", ") || "";
    const map = value.map?.map((entry) => `${formatValue(entry.key)}=${formatValue(entry.value)}`).join(", ") || "";
    const body = [array, map].filter(Boolean).join("; ");
    return `{${body}}`;
  }
  if (value.type === "cell") {
    return `cell(${formatValue(value.value)})`;
  }
  if (value.type === "multi_return") {
    return `<multi ${value.values?.map(formatValue).join(", ") || ""}>`;
  }
  if (value.kind === "builtin") {
    return `<builtin ${value.name}>`;
  }
  if (value.kind === "ref") {
    return "<ref>";
  }
  if (value.repr) {
    return value.repr;
  }
  if (value.kind === "dict") {
    return `{${value.items.map((entry) => `${formatValue(entry.key)}=${formatValue(entry.value)}`).join(", ")}}`;
  }
  return `{${Object.entries(value)
    .map(([key, item]) => `${key}=${formatValue(item)}`)
    .join(", ")}}`;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

init();
