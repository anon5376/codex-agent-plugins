(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const app = $("app");
  const form = $("mission-form");
  const status = $("form-status");
  const reviewButton = $("review-button");
  const reviewSection = $("review-section");
  const promptOutput = $("prompt-output");
  const warningList = $("warning-list");
  const saveButton = $("save-button");
  const copyButton = $("copy-button");
  const downloadButton = $("download-button");
  const savedState = $("saved-state");
  const savedList = $("saved-list");

  const state = {
    config: null,
    reviewMission: null,
    prompt: "",
    warnings: [],
    savedId: null,
    dirty: false,
    suppressDirty: false,
    revision: 0,
    previewRequestId: 0,
    saveInFlight: false,
    listInFlight: false
  };

  const errorIds = {
    title: "title-error",
    objective: "objective-error",
    project_path: "project-path-error",
    work_types: "work-types-error",
    deliverables: "deliverables-error",
    success_criteria: "success-criteria-error",
    constraints: "constraints-error",
    context_files: "context-files-error",
    max_astra: "max-astra-error",
    max_luna: "max-luna-error",
    budget_mode: "budget-mode-error",
    budget_value: "budget-value-error",
    pro_enabled: "pro-enabled-error",
    pro_messages: "pro-messages-error",
    pro_project: "pro-project-error",
    external_mode: "external-mode-error",
    external_scope: "external-scope-error",
    private_boundary: "private-boundary-error"
  };

  const fieldIds = {
    title: "title",
    objective: "objective",
    project_path: "project_path",
    deliverables: "deliverables",
    success_criteria: "success_criteria",
    constraints: "constraints",
    context_files: "context_files",
    max_astra: "max_astra",
    max_luna: "max_luna",
    budget_mode: "budget_mode",
    budget_value: "budget_value",
    pro_enabled: "pro_enabled",
    pro_messages: "pro_messages",
    pro_project: "pro_project",
    external_mode: "external_mode",
    external_scope: "external_scope",
    private_boundary: "private_boundary"
  };

  const fieldDetails = {
    deliverables: "outcomes-details",
    success_criteria: "outcomes-details",
    constraints: "outcomes-details",
    context_files: "outcomes-details",
    max_astra: "limits-details",
    max_luna: "limits-details",
    budget_mode: "limits-details",
    budget_value: "limits-details",
    pro_enabled: "pro-details",
    pro_messages: "pro-details",
    pro_project: "pro-details",
    external_mode: "authority-details",
    external_scope: "authority-details",
    private_boundary: "authority-details"
  };

  function hasOwn(object, key) {
    return Object.prototype.hasOwnProperty.call(object, key);
  }

  function setHidden(element, hidden) {
    if (element) {
      element.hidden = hidden;
    }
  }

  function setAppState(value) {
    app.dataset.state = value;
  }

  function setStatus(message, kind) {
    status.textContent = message;
    status.dataset.state = kind || "ready";
  }

  function setSavedStatus(message) {
    savedState.textContent = message;
  }

  function setValue(id, value) {
    const element = $(id);
    if (!element) {
      return;
    }
    element.value = value === null || value === undefined ? "" : String(value);
  }

  function getDefault(key) {
    const defaults = state.config && state.config.defaults;
    return defaults && hasOwn(defaults, key) ? defaults[key] : undefined;
  }

  function modelFor(key) {
    const models = state.config && state.config.models;
    if (Array.isArray(models)) {
      return models.find((entry) => {
        if (!entry || typeof entry !== "object") {
          return false;
        }
        return entry.role === key || entry.id === key || entry.name === key;
      });
    }
    if (models && typeof models === "object") {
      if (hasOwn(models, key)) {
        return models[key];
      }
      const match = Object.keys(models).find((name) => name.toLowerCase() === key.toLowerCase());
      return match ? models[match] : undefined;
    }
    return undefined;
  }

  function modelText(value) {
    if (typeof value === "string") {
      return value;
    }
    if (!value || typeof value !== "object") {
      return "Configured by local backend";
    }
    const name = value.model || value.name || value.id || value.value;
    const effort = value.effort || value.reasoning_effort || value.reasoning;
    const surface = value.surface || value.channel;
    if (name && surface) {
      return String(name) + " · " + String(surface);
    }
    if (name && effort) {
      return String(name) + " · " + String(effort);
    }
    if (name) {
      return String(name);
    }
    if (effort) {
      return String(effort);
    }
    return "Configured by local backend";
  }

  function displayType(value) {
    return String(value)
      .replace(/[_-]+/g, " ")
      .replace(/\b\w/g, (letter) => letter.toUpperCase());
  }

  function slug(value, index) {
    const result = String(value).toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
    return (result || "type") + "-" + index;
  }

  function renderWorkTypes() {
    const container = $("work-types");
    container.replaceChildren();
    const workTypes = Array.isArray(state.config.work_types) ? state.config.work_types : [];
    const selected = Array.isArray(getDefault("work_types")) ? getDefault("work_types") : [];

    workTypes.forEach((workType, index) => {
      const label = document.createElement("label");
      label.className = "check-option";

      const input = document.createElement("input");
      input.type = "checkbox";
      input.name = "work_types";
      input.value = String(workType);
      input.id = "work-type-" + slug(workType, index);
      input.checked = selected.includes(workType);

      const text = document.createElement("span");
      text.textContent = displayType(workType);

      label.htmlFor = input.id;
      label.append(input, text);
      container.append(label);
    });
  }

  function renderModelProfile() {
    const profile = $("model-profile");
    profile.replaceChildren();
    const rows = [
      ["Astra", "astra", "Planning director"],
      ["Sol", "sol", "Execution manager"],
      ["Luna", "luna", "Worker pool"]
    ];

    rows.forEach(([label, key, description]) => {
      const row = document.createElement("div");
      row.className = "model-row";
      const term = document.createElement("dt");
      term.textContent = label + " · " + description;
      const definition = document.createElement("dd");
      definition.textContent = modelText(modelFor(key));
      row.append(term, definition);
      profile.append(row);
    });
    $("pro-model-note").textContent = "Configured model: " + modelText(modelFor("pro")) + ".";
  }

  function initializeForm() {
    const defaults = state.config.defaults || {};
    setValue("title", defaults.title);
    setValue("objective", defaults.objective);
    setValue("project_path", defaults.project_path);
    setValue("deliverables", defaults.deliverables);
    setValue("success_criteria", defaults.success_criteria);
    setValue("constraints", defaults.constraints);
    setValue("context_files", Array.isArray(defaults.context_files) ? defaults.context_files.join("\n") : defaults.context_files);
    setValue("max_astra", defaults.max_astra);
    setValue("max_luna", defaults.max_luna);
    setValue("budget_mode", defaults.budget_mode);
    setValue("budget_value", defaults.budget_value);
    $("pro_enabled").checked = Boolean(defaults.pro_enabled);
    setValue("pro_messages", defaults.pro_messages);
    setValue("pro_project", hasOwn(defaults, "pro_project") ? defaults.pro_project : state.config.default_project);
    setValue("external_mode", defaults.external_mode);
    setValue("external_scope", defaults.external_scope);
    setValue("private_boundary", defaults.private_boundary);

    updateBudgetField();
    updateProFields();
    updateExternalFields();
  }

  function clearErrors() {
    Object.keys(errorIds).forEach((key) => {
      const error = $(errorIds[key]);
      if (error) {
        error.textContent = "";
      }
      const field = fieldIds[key] ? $(fieldIds[key]) : null;
      if (field) {
        const owner = field.closest(".field") || field.closest("fieldset");
        if (owner) {
          owner.classList.remove("has-error");
        }
      }
    });
    const workTypes = $("work-types");
    if (workTypes) {
      workTypes.closest("fieldset").classList.remove("has-error");
    }
  }

  function setFieldError(field, message) {
    const detailsId = fieldDetails[field];
    if (detailsId && $(detailsId)) {
      $(detailsId).open = true;
    }
    const error = $(errorIds[field]);
    if (error) {
      error.textContent = message;
    }
    const control = fieldIds[field] ? $(fieldIds[field]) : null;
    if (field === "work_types") {
      $("work-types").closest("fieldset").classList.add("has-error");
    } else if (control) {
      const owner = control.closest(".field");
      if (owner) {
        owner.classList.add("has-error");
      }
    }
  }

  function applyFieldErrors(fields) {
    if (!fields || typeof fields !== "object") {
      return;
    }
    Object.keys(fields).forEach((field) => {
      const message = fields[field];
      const normalizedField = field.startsWith("context_files[") ? "context_files" : field;
      if (hasOwn(errorIds, normalizedField)) {
        setFieldError(normalizedField, String(message));
      }
    });
  }

  function focusFirstError(errors) {
    const first = Object.keys(errors)[0];
    if (first && $(fieldIds[first])) {
      $(fieldIds[first]).focus();
    } else if (first === "work_types") {
      const checkbox = document.querySelector('input[name="work_types"]');
      if (checkbox) {
        checkbox.focus();
      }
    }
  }

  function readNumber(id) {
    const raw = $(id).value.trim();
    return raw === "" ? null : Number(raw);
  }

  function collectMission() {
    const contextText = $("context_files").value;
    const contextFiles = contextText
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean);
    const budgetMode = $("budget_mode").value;
    const budgetValue = budgetMode === "manual" ? null : readNumber("budget_value");

    return {
      title: $("title").value.trim(),
      objective: $("objective").value.trim(),
      project_path: $("project_path").value.trim(),
      work_types: Array.from(document.querySelectorAll('input[name="work_types"]:checked')).map((input) => input.value),
      deliverables: $("deliverables").value.trim(),
      success_criteria: $("success_criteria").value.trim(),
      constraints: $("constraints").value.trim(),
      context_files: contextFiles,
      max_astra: readNumber("max_astra"),
      max_luna: readNumber("max_luna"),
      budget_mode: budgetMode,
      budget_value: budgetValue,
      pro_enabled: $("pro_enabled").checked,
      pro_messages: readNumber("pro_messages"),
      pro_project: $("pro_project").value.trim(),
      external_mode: $("external_mode").value,
      external_scope: $("external_scope").value.trim(),
      private_boundary: $("private_boundary").value.trim()
    };
  }

  function isInteger(value) {
    return Number.isInteger(value);
  }

  function validateMission(mission) {
    const errors = {};
    const lengths = {
      title: 120,
      objective: 16000,
      deliverables: 8000,
      success_criteria: 8000,
      constraints: 8000,
      external_scope: 8000,
      private_boundary: 8000,
      pro_project: 120
    };

    if (!mission.objective) {
      errors.objective = "Objective is required.";
    }
    if (!mission.project_path) {
      errors.project_path = "Project path is required.";
    } else if (!mission.project_path.startsWith("/")) {
      errors.project_path = "Use an existing absolute directory path.";
    }
    if (!Array.isArray(mission.work_types) || mission.work_types.length === 0) {
      errors.work_types = "Choose at least one work type.";
    } else if (mission.work_types.some((value) => !state.config.work_types.includes(value))) {
      errors.work_types = "Choose work types supplied by the local configuration.";
    }
    if (mission.context_files.length > 30) {
      errors.context_files = "Use no more than 30 context-file paths.";
    } else if (mission.context_files.some((path) => !path.startsWith("/"))) {
      errors.context_files = "Every context-file path must be absolute.";
    }

    Object.keys(lengths).forEach((field) => {
      if (mission[field].length > lengths[field]) {
        errors[field] = "Keep this field within " + lengths[field].toLocaleString() + " characters.";
      }
    });

    if (!isInteger(mission.max_astra) || mission.max_astra < 1 || mission.max_astra > 4) {
      errors.max_astra = "Use a whole number from 1 to 4.";
    }
    if (!isInteger(mission.max_luna) || mission.max_luna < 1 || mission.max_luna > 64) {
      errors.max_luna = "Use a whole number from 1 to 64.";
    }
    if (!["hours", "tokens", "manual"].includes(mission.budget_mode)) {
      errors.budget_mode = "Choose hours, tokens, or manual.";
    } else if (mission.budget_mode === "manual") {
      if (mission.budget_value !== null) {
        errors.budget_value = "Manual mode leaves the budget value blank.";
      }
    } else if (!isInteger(mission.budget_value) || mission.budget_value < 1) {
      errors.budget_value = "Use a positive whole number.";
    } else if (mission.budget_mode === "hours" && mission.budget_value > 168) {
      errors.budget_value = "Hours must be 168 or less.";
    } else if (mission.budget_mode === "tokens" && mission.budget_value > 100000000) {
      errors.budget_value = "Tokens must be 100,000,000 or less.";
    }
    if (!isInteger(mission.pro_messages) || mission.pro_messages < 0 || mission.pro_messages > 100) {
      errors.pro_messages = "Use a whole number from 0 to 100.";
    } else if (mission.pro_enabled && mission.pro_messages < 1) {
      errors.pro_messages = "Enable at least one message when Pro Web is enabled.";
    }
    if (!["prepare", "scoped"].includes(mission.external_mode)) {
      errors.external_mode = "Choose prepare-only or scoped permission.";
    } else if (mission.external_mode === "scoped" && !mission.external_scope) {
      errors.external_scope = "Describe the scoped authority before choosing scoped permission.";
    }
    return errors;
  }

  function clearReviewState(hideReview) {
    state.reviewMission = null;
    state.prompt = "";
    state.warnings = [];
    state.savedId = null;
    state.dirty = false;
    promptOutput.textContent = "";
    warningList.replaceChildren();
    setHidden(warningList, true);
    if (hideReview) {
      setHidden(reviewSection, true);
    }
    updateActions();
  }

  function displayWarnings(warnings) {
    warningList.replaceChildren();
    const list = Array.isArray(warnings) ? warnings : [];
    list.forEach((warning) => {
      const item = document.createElement("li");
      item.textContent = typeof warning === "string" ? warning : String(warning && warning.message ? warning.message : warning);
      warningList.append(item);
    });
    setHidden(warningList, list.length === 0);
  }

  function displayReview(prompt, warnings) {
    promptOutput.textContent = prompt;
    displayWarnings(warnings);
    setHidden(reviewSection, false);
    updateActions();
  }

  function updateBudgetField() {
    const manual = $("budget_mode").value === "manual";
    const input = $("budget_value");
    input.disabled = manual;
    input.required = !manual;
    input.setAttribute("aria-disabled", String(manual));
    if (manual) {
      input.value = "";
    }
  }

  function updateProFields() {
    const enabled = $("pro_enabled").checked;
    const messages = $("pro_messages");
    messages.disabled = !enabled;
    messages.required = enabled;
    messages.setAttribute("aria-disabled", String(!enabled));
  }

  function updateExternalFields() {
    const scoped = $("external_mode").value === "scoped";
    const scope = $("external_scope");
    scope.disabled = !scoped;
    scope.required = scoped;
    scope.setAttribute("aria-disabled", String(!scoped));
  }

  function updateActions() {
    const hasPrompt = Boolean(state.prompt) && !state.dirty;
    saveButton.disabled = !hasPrompt || state.saveInFlight || Boolean(state.savedId);
    copyButton.disabled = !hasPrompt;
    downloadButton.disabled = !hasPrompt;
  }

  async function parseResponse(response) {
    const text = await response.text();
    if (!text) {
      return {};
    }
    try {
      return JSON.parse(text);
    } catch (error) {
      return { error: "The local backend returned an unreadable response." };
    }
  }

  async function getJson(path) {
    let response;
    let payload;
    try {
      response = await fetch(path, {
        method: "GET",
        headers: { Accept: "application/json" },
        cache: "no-store"
      });
      payload = await parseResponse(response);
    } catch (error) {
      const networkError = new Error("Could not reach the local operator.");
      networkError.network = true;
      throw networkError;
    }
    if (!response.ok) {
      const apiError = new Error(typeof payload.error === "string" ? payload.error : "The local backend rejected the request.");
      apiError.status = response.status;
      apiError.payload = payload;
      throw apiError;
    }
    return payload;
  }

  async function postJson(path, body) {
    let response;
    let payload;
    try {
      response = await fetch(path, {
        method: "POST",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
          "X-Operator-Token": state.config.csrf_token
        },
        body: JSON.stringify(body)
      });
      payload = await parseResponse(response);
    } catch (error) {
      const networkError = new Error("Could not reach the local operator.");
      networkError.network = true;
      throw networkError;
    }
    if (!response.ok) {
      const apiError = new Error(typeof payload.error === "string" ? payload.error : "The local backend rejected the request.");
      apiError.status = response.status;
      apiError.payload = payload;
      throw apiError;
    }
    return payload;
  }

  function showOperationError(error, fallback) {
    clearErrors();
    if (error && error.payload) {
      applyFieldErrors(error.payload.fields);
    }
    const message = error && error.message ? error.message : fallback;
    setStatus(message, "error");
    setAppState("error");
  }

  function markDirty() {
    if (state.suppressDirty) {
      return;
    }
    state.revision += 1;
    if (state.prompt || state.savedId || reviewButton.disabled) {
      clearReviewState(true);
      state.dirty = true;
      setStatus("Mission changed. Review the prompt again before saving.", "ready");
      setAppState("editing");
    }
  }

  function setMissionFields(mission) {
    const source = mission && typeof mission === "object" ? mission : {};
    state.suppressDirty = true;
    setValue("title", source.title);
    setValue("objective", source.objective);
    setValue("project_path", source.project_path);
    setValue("deliverables", source.deliverables);
    setValue("success_criteria", source.success_criteria);
    setValue("constraints", source.constraints);
    setValue("context_files", Array.isArray(source.context_files) ? source.context_files.join("\n") : source.context_files);
    setValue("max_astra", source.max_astra);
    setValue("max_luna", source.max_luna);
    setValue("budget_mode", source.budget_mode);
    setValue("budget_value", source.budget_value);
    $("pro_enabled").checked = Boolean(source.pro_enabled);
    setValue("pro_messages", source.pro_messages);
    setValue("pro_project", source.pro_project);
    setValue("external_mode", source.external_mode);
    setValue("external_scope", source.external_scope);
    setValue("private_boundary", source.private_boundary);
    const selectedTypes = Array.isArray(source.work_types) ? source.work_types : [];
    document.querySelectorAll('input[name="work_types"]').forEach((input) => {
      input.checked = selectedTypes.includes(input.value);
    });
    updateBudgetField();
    updateProFields();
    updateExternalFields();
    clearErrors();
    state.suppressDirty = false;
  }

  async function previewMission() {
    const requestId = ++state.previewRequestId;
    const requestRevision = ++state.revision;
    clearErrors();
    clearReviewState(true);
    const mission = collectMission();
    const errors = validateMission(mission);
    if (Object.keys(errors).length > 0) {
      Object.keys(errors).forEach((field) => setFieldError(field, errors[field]));
      state.prompt = "";
      state.reviewMission = null;
      state.savedId = null;
      setHidden(reviewSection, true);
      updateActions();
      setStatus("Fix the highlighted fields before reviewing the prompt.", "invalid");
      setAppState("invalid");
      if (state.previewRequestId === requestId) {
        reviewButton.disabled = false;
      }
      focusFirstError(errors);
      return;
    }

    reviewButton.disabled = true;
    setStatus("Generating the prompt from the local backend…", "ready");
    try {
      const payload = await postJson("/api/preview", mission);
      if (!payload || typeof payload.prompt !== "string" || !payload.prompt) {
        throw new Error("The local backend returned no generated prompt.");
      }
      if (state.revision !== requestRevision) {
        return;
      }
      state.reviewMission = payload.mission && typeof payload.mission === "object" ? payload.mission : mission;
      state.prompt = payload.prompt;
      state.warnings = Array.isArray(payload.warnings) ? payload.warnings : [];
      state.savedId = null;
      state.dirty = false;
      displayReview(state.prompt, state.warnings);
      setStatus("Prompt ready. Review it before saving.", "ready");
      setAppState("review");
      reviewSection.scrollIntoView({ block: "start", behavior: "smooth" });
    } catch (error) {
      if (state.revision === requestRevision) {
        showOperationError(error, "The prompt could not be generated.");
      }
    } finally {
      if (state.previewRequestId === requestId) {
        reviewButton.disabled = false;
      }
      updateActions();
    }
  }

  async function saveMission() {
    if (!state.prompt || state.dirty || state.saveInFlight) {
      setStatus("Review the current mission before saving.", "invalid");
      return;
    }
    const requestRevision = ++state.revision;
    state.saveInFlight = true;
    updateActions();
    setStatus("Saving this mission locally…", "ready");
    try {
      const payload = await postJson("/api/missions", state.reviewMission || collectMission());
      if (!payload || payload.id === undefined || payload.id === null) {
        throw new Error("The local backend returned no saved mission ID.");
      }
      if (state.revision !== requestRevision) {
        await loadSavedMissions();
        return;
      }
      state.savedId = String(payload.id);
      state.reviewMission = payload.mission && typeof payload.mission === "object" ? payload.mission : state.reviewMission;
      state.prompt = typeof payload.prompt === "string" && payload.prompt ? payload.prompt : state.prompt;
      state.dirty = false;
      displayReview(state.prompt, payload.warnings || state.warnings);
      setStatus("Mission saved. The prompt is ready to copy.", "saved");
      setAppState("saved");
      await loadSavedMissions();
    } catch (error) {
      if (state.revision === requestRevision) {
        showOperationError(error, "The mission could not be saved.");
      }
    } finally {
      state.saveInFlight = false;
      updateActions();
    }
  }

  async function copyPrompt() {
    if (!state.prompt || state.dirty) {
      return;
    }
    let copied = false;
    if (navigator.clipboard && typeof navigator.clipboard.writeText === "function") {
      try {
        await navigator.clipboard.writeText(state.prompt);
        copied = true;
      } catch (error) {
        copied = false;
      }
    }
    if (!copied) {
      const fallback = document.createElement("textarea");
      fallback.value = state.prompt;
      fallback.setAttribute("readonly", "readonly");
      fallback.style.position = "fixed";
      fallback.style.left = "-9999px";
      document.body.append(fallback);
      fallback.focus();
      fallback.select();
      try {
        copied = document.execCommand("copy");
      } catch (error) {
        copied = false;
      }
      fallback.remove();
    }
    if (copied) {
      setStatus("Prompt copied to the clipboard.", "saved");
    } else {
      setStatus("Copy was unavailable. Focus the prompt and use your keyboard copy shortcut.", "error");
      promptOutput.focus();
    }
  }

  function downloadPrompt() {
    if (!state.prompt || state.dirty) {
      return;
    }
    const blob = new Blob([state.prompt], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "mission-prompt.txt";
    anchor.textContent = "Download prompt";
    document.body.append(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
    setStatus("Prompt download started.", "saved");
  }

  function formatDate(value) {
    if (!value) {
      return "Saved record";
    }
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
      return "Saved record";
    }
    return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(date);
  }

  function actionButton(label, action, id) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "button button-secondary";
    button.dataset.action = action;
    button.dataset.id = id;
    button.textContent = label;
    return button;
  }

  function renderSavedMissions(missions) {
    savedList.replaceChildren();
    if (!missions.length) {
      setSavedStatus("No saved missions yet.");
      return;
    }
    setSavedStatus(missions.length + (missions.length === 1 ? " saved mission." : " saved missions."));
    missions.forEach((record) => {
      if (!record || record.id === undefined || record.id === null) {
        return;
      }
      const id = String(record.id);
      const item = document.createElement("li");
      item.className = "saved-item";
      const title = document.createElement("p");
      title.className = "saved-item-title";
      title.textContent = record.title || "Untitled mission";
      const meta = document.createElement("p");
      meta.className = "saved-item-meta";
      meta.textContent = formatDate(record.created_at) + " · " + (record.status || "prepared");
      const actions = document.createElement("div");
      actions.className = "saved-item-actions";
      actions.append(
        actionButton("Open", "open", id),
        actionButton("Reuse", "reuse", id),
        actionButton("Prompt", "prompt", id)
      );
      item.append(title, meta, actions);
      savedList.append(item);
    });
  }

  async function loadSavedMissions() {
    if (state.listInFlight) {
      return;
    }
    state.listInFlight = true;
    setSavedStatus("Loading saved missions…");
    try {
      const payload = await getJson("/api/missions");
      const missions = payload && Array.isArray(payload.missions) ? payload.missions : [];
      renderSavedMissions(missions);
    } catch (error) {
      savedList.replaceChildren();
      setSavedStatus(error && error.message ? error.message : "Saved missions could not be loaded.");
    } finally {
      state.listInFlight = false;
    }
  }

  async function openSavedMission(id, mode) {
    const requestRevision = ++state.revision;
    setSavedStatus("Opening saved mission…");
    try {
      const record = await getJson("/api/missions/" + encodeURIComponent(id));
      if (state.revision !== requestRevision) {
        return;
      }
      const mission = record && record.mission && typeof record.mission === "object" ? record.mission : record;
      setMissionFields(mission);

      if (mode === "reuse") {
        clearReviewState(true);
        setStatus("Saved mission reused in the editor. Review the prompt before saving.", "ready");
        setAppState("editing");
        $("objective").focus();
        return;
      }

      const prompt = record && typeof record.prompt === "string" ? record.prompt : "";
      state.reviewMission = mission;
      state.prompt = prompt;
      state.warnings = Array.isArray(record && record.warnings) ? record.warnings : [];
      state.savedId = String(record && record.id !== undefined ? record.id : id);
      state.dirty = false;
      if (state.prompt) {
        displayReview(state.prompt, state.warnings);
        setStatus("Saved mission opened. Review its prompt or edit the mission.", "saved");
        setAppState("saved");
        if (mode === "prompt") {
          promptOutput.focus();
        } else {
          reviewSection.scrollIntoView({ block: "start", behavior: "smooth" });
        }
      } else {
        clearReviewState(true);
        setStatus("Saved mission has no prompt to show. Review it to generate a new prompt.", "error");
        setAppState("error");
      }
    } catch (error) {
      if (state.revision === requestRevision) {
        setSavedStatus(error && error.message ? error.message : "Saved mission could not be opened.");
        showOperationError(error, "Saved mission could not be opened.");
      }
    } finally {
      if (!state.listInFlight) {
        loadSavedMissions();
      }
    }
  }

  function validateConfig(config) {
    if (!config || typeof config !== "object") {
      throw new Error("The local backend returned no configuration.");
    }
    if (typeof config.csrf_token !== "string" || !config.csrf_token) {
      throw new Error("The local backend returned an incomplete configuration.");
    }
    if (!Array.isArray(config.work_types) || config.work_types.length === 0) {
      throw new Error("The local backend returned no work types.");
    }
    if (!config.defaults || typeof config.defaults !== "object") {
      throw new Error("The local backend returned no mission defaults.");
    }
  }

  async function loadConfig() {
    setAppState("loading");
    try {
      const config = await getJson("/api/config");
      validateConfig(config);
      state.config = config;
      renderWorkTypes();
      renderModelProfile();
      initializeForm();
      setHidden($("boot-state"), true);
      setHidden($("backend-error"), true);
      setHidden(form, false);
      setStatus("Configuration loaded. Describe the work you want prepared.", "ready");
      updateActions();
      await loadSavedMissions();
    } catch (error) {
      setHidden($("boot-state"), true);
      setHidden(form, true);
      setHidden($("backend-error"), false);
      $("backend-error-message").textContent = error && error.message ? error.message : "Check the local server and reload this page.";
      setAppState("backend-error");
    }
  }

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    previewMission();
  });
  form.addEventListener("input", markDirty);
  form.addEventListener("change", (event) => {
    if (event.target.id === "budget_mode") {
      updateBudgetField();
    }
    if (event.target.id === "pro_enabled") {
      updateProFields();
    }
    if (event.target.id === "external_mode") {
      updateExternalFields();
    }
    markDirty();
  });
  $("edit-button").addEventListener("click", () => {
    state.revision += 1;
    clearReviewState(true);
    state.dirty = true;
    setStatus("Editing mission. Review the prompt again before saving.", "ready");
    setAppState("editing");
    $("objective").focus();
  });
  saveButton.addEventListener("click", saveMission);
  copyButton.addEventListener("click", copyPrompt);
  downloadButton.addEventListener("click", downloadPrompt);
  savedList.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-action]");
    if (!button || !button.dataset.id) {
      return;
    }
    openSavedMission(button.dataset.id, button.dataset.action);
  });

  loadConfig();
})();
