const ABILITIES = ["STR", "DEX", "CON", "INT", "WIS", "CHA"];

let llmTouched = false;
let equipmentState = { option_groups: [] };

function getById(id) {
  return document.getElementById(id);
}

function withSign(value) {
  return value >= 0 ? `+${value}` : `${value}`;
}

function clearNode(node) {
  node.textContent = "";
}

function fillList(node, values, emptyText = "Нет") {
  clearNode(node);
  const normalized = values && values.length ? values : [emptyText];
  for (const value of normalized) {
    const li = document.createElement("li");
    li.textContent = value;
    node.appendChild(li);
  }
}

async function fetchJsonWithTimeout(url, options = {}, timeoutMs = 20000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { ...options, signal: controller.signal });
  } finally {
    clearTimeout(timer);
  }
}

function showError(message) {
  getById("error-text").textContent = message;
  getById("error-card").hidden = false;
}

function hideError() {
  getById("error-card").hidden = true;
  getById("error-text").textContent = "";
}

function setLoading(isLoading) {
  getById("loading").hidden = !isLoading;
  getById("generate-button").disabled = isLoading;
}

function renderSheet(data) {
  getById("result-card").hidden = false;
  getById("summary-text").textContent =
    `Класс: ${data.class_index}, уровень: ${data.level}, ` +
    `бонус мастерства: ${withSign(data.derived.prof_bonus)}`;

  const body = getById("ability-body");
  clearNode(body);
  for (const ability of ABILITIES) {
    const tr = document.createElement("tr");
    const score = data.ability_scores?.[ability] ?? "-";
    const mod = data.modifiers?.[ability];

    const abilityCell = document.createElement("td");
    abilityCell.textContent = ability;
    tr.appendChild(abilityCell);

    const scoreCell = document.createElement("td");
    scoreCell.textContent = `${score}`;
    tr.appendChild(scoreCell);

    const modCell = document.createElement("td");
    modCell.textContent = typeof mod === "number" ? withSign(mod) : "-";
    tr.appendChild(modCell);

    body.appendChild(tr);
  }

  fillList(getById("skills-list"), data.proficiencies?.skills || []);

  const equipmentItems = (data.equipment?.items || []).map(
    (item) => `${item.name} x${item.quantity}`
  );
  fillList(getById("equipment-list"), equipmentItems);
  fillList(getById("choices-list"), data.equipment?.choices_explained || []);

  const derivedItems = [
    `Бонус мастерства: ${data.derived.prof_bonus}`,
    `HP: ${data.derived.hp}`,
    `AC: ${data.derived.ac}`,
    `Формула HP: ${data.derived.hp_explanation}`,
    `Формула AC: ${data.derived.ac_explanation}`,
  ];
  fillList(getById("derived-list"), derivedItems);

  const asiSection = getById("asi-section");
  if (data.asi_history && data.asi_history.length > 0) {
    const lines = data.asi_history.map((entry) => {
      const applied = Object.entries(entry.applied || {})
        .map(([stat, value]) => `${stat} ${value > 0 ? `+${value}` : value}`)
        .join(", ");
      return `Уровень ${entry.level}: ${applied}${entry.reason ? ` (${entry.reason})` : ""}`;
    });
    fillList(getById("asi-list"), lines);
    asiSection.hidden = false;
  } else {
    asiSection.hidden = true;
    clearNode(getById("asi-list"));
  }

  const backstorySection = getById("backstory-section");
  if (data.backstory) {
    getById("backstory-text").textContent = data.backstory;
    backstorySection.hidden = false;
  } else {
    backstorySection.hidden = true;
    getById("backstory-text").textContent = "";
  }

  fillList(getById("decisions-list"), data.decisions || []);
  getById("raw-json").textContent = JSON.stringify(data, null, 2);
}

function defaultBaseUrlForBackend(backend) {
  return backend === "ollama" ? "http://localhost:11434" : "http://localhost:8001";
}

function setupLlmControls() {
  const useLlm = getById("use-llm");
  const backend = getById("llm-backend");
  const baseUrl = getById("llm-base-url");
  const model = getById("llm-model");
  const timeout = getById("llm-timeout");

  const touch = () => {
    llmTouched = true;
  };
  useLlm.addEventListener("change", touch);
  backend.addEventListener("change", () => {
    touch();
    if (!baseUrl.value.trim()) {
      baseUrl.placeholder = defaultBaseUrlForBackend(backend.value);
    }
  });
  baseUrl.addEventListener("input", touch);
  model.addEventListener("input", touch);
  timeout.addEventListener("input", touch);

  baseUrl.placeholder = defaultBaseUrlForBackend(backend.value);
}

function renderEquipmentReference(payload) {
  equipmentState = payload || { option_groups: [] };

  const selector = getById("equipment-selector");
  const fixedList = getById("fixed-equipment-list");
  const groupsRoot = getById("equipment-options-groups");
  clearNode(fixedList);
  clearNode(groupsRoot);

  const fixedItems = payload.starting_equipment || [];
  const fixedValues = fixedItems.map((item) => `${item.name} x${item.quantity}`);
  fillList(fixedList, fixedValues, "Нет фиксированного снаряжения");

  const groups = payload.option_groups || [];
  if (!groups.length) {
    selector.hidden = false;
    const info = document.createElement("p");
    info.className = "muted";
    info.textContent = "Для этого класса нет дополнительных вариантов снаряжения.";
    groupsRoot.appendChild(info);
    return;
  }

  groups.forEach((group) => {
    const block = document.createElement("fieldset");
    block.className = "equip-group";
    block.dataset.groupId = group.group_id;
    block.dataset.choose = `${group.choose}`;

    const legend = document.createElement("legend");
    const title = group.description ? group.description : `Блок ${group.group_id}`;
    legend.textContent = `${title}: выберите ${group.choose}`;
    block.appendChild(legend);

    const inputType = group.choose === 1 ? "radio" : "checkbox";
    const options = group.options || [];

    options.forEach((option, index) => {
      const row = document.createElement("label");
      row.className = "equip-option";
      const input = document.createElement("input");
      input.type = inputType;
      input.name = group.group_id;
      input.value = option.option_id;
      if (index < group.choose) {
        input.checked = true;
      }
      row.appendChild(input);

      const text = document.createElement("span");
      text.textContent = option.label;
      row.appendChild(text);
      block.appendChild(row);
    });

    if (inputType === "checkbox") {
      block.addEventListener("change", () => {
        const checked = Array.from(block.querySelectorAll('input[type="checkbox"]:checked'));
        const choose = Number(block.dataset.choose || "0");
        if (checked.length > choose) {
          checked[checked.length - 1].checked = false;
        }
      });
    }

    groupsRoot.appendChild(block);
  });

  selector.hidden = false;
}

function collectSelectedEquipmentChoices() {
  const groups = equipmentState.option_groups || [];
  if (!groups.length) {
    return null;
  }

  const selected = [];
  for (const group of groups) {
    const inputs = Array.from(
      document.querySelectorAll(`#equipment-options-groups input[name="${group.group_id}"]:checked`)
    );
    const choose = Number(group.choose || 0);
    if (inputs.length !== choose) {
      throw new Error(`Для блока снаряжения "${group.description || group.group_id}" выберите ${choose}`);
    }
    for (const input of inputs) {
      selected.push(input.value);
    }
  }
  return selected;
}

async function loadClasses() {
  const select = getById("class-index");
  select.innerHTML = '<option value="">Загрузка классов...</option>';

  try {
    const response = await fetchJsonWithTimeout("/reference/classes", {}, 15000);
    if (!response.ok) {
      throw new Error(`Не удалось загрузить классы: HTTP ${response.status}`);
    }
    const payload = await response.json();
    if (!Array.isArray(payload)) {
      throw new Error("Некорректный формат ответа со списком классов");
    }

    select.innerHTML = '<option value="">Выберите класс...</option>';
    payload.forEach((entry) => {
      const option = document.createElement("option");
      option.value = entry.index;
      option.textContent = entry.name;
      select.appendChild(option);
    });
  } catch (error) {
    select.innerHTML = '<option value="">Классы недоступны</option>';
    select.disabled = true;
    showError(error instanceof Error ? error.message : "Неизвестная ошибка загрузки классов");
  }
}

async function loadEquipmentOptions(classIndex) {
  if (!classIndex) {
    getById("equipment-selector").hidden = true;
    equipmentState = { option_groups: [] };
    return;
  }
  try {
    const response = await fetchJsonWithTimeout(
      `/reference/class/${encodeURIComponent(classIndex)}/equipment-options`,
      {},
      15000
    );
    if (!response.ok) {
      throw new Error(`Не удалось загрузить снаряжение: HTTP ${response.status}`);
    }
    const payload = await response.json();
    renderEquipmentReference(payload);
  } catch (error) {
    equipmentState = { option_groups: [] };
    getById("equipment-selector").hidden = true;
    showError(error instanceof Error ? error.message : "Ошибка загрузки снаряжения");
  }
}

function setupClassChangeHandler() {
  const classSelect = getById("class-index");
  classSelect.addEventListener("change", async () => {
    hideError();
    await loadEquipmentOptions(classSelect.value);
  });
}

function setupCopyJson() {
  const button = getById("copy-json");
  const status = getById("copy-status");
  button.addEventListener("click", async () => {
    status.textContent = "";
    try {
      await navigator.clipboard.writeText(getById("raw-json").textContent || "");
      status.textContent = "Скопировано";
    } catch (_error) {
      status.textContent = "Не удалось скопировать";
    }
  });
}

function buildPayloadFromForm() {
  const payload = {
    level: Number(getById("level").value),
    class_index: getById("class-index").value,
  };

  const role = getById("role").value.trim();
  const description = getById("description").value.trim();
  if (role) {
    payload.role = role;
  }
  if (description) {
    payload.description = description;
  }

  const selectedEquipmentChoices = collectSelectedEquipmentChoices();
  if (selectedEquipmentChoices && selectedEquipmentChoices.length > 0) {
    payload.selected_equipment_choices = selectedEquipmentChoices;
  }

  const useLlm = getById("use-llm").checked;
  const backend = getById("llm-backend").value;
  const baseUrl = getById("llm-base-url").value.trim();
  const model = getById("llm-model").value.trim();
  const timeoutRaw = getById("llm-timeout").value.trim();
  const timeoutNum = timeoutRaw ? Number(timeoutRaw) : null;

  const llmConfig = {};
  if (llmTouched) {
    payload.use_llm = useLlm;
    llmConfig.enabled = useLlm;
    llmConfig.backend = backend;
    if (baseUrl) {
      llmConfig.base_url = baseUrl;
    }
    if (model) {
      llmConfig.model = model;
    }
    if (timeoutNum && Number.isFinite(timeoutNum) && timeoutNum > 0) {
      llmConfig.timeout_seconds = timeoutNum;
    }
  } else {
    if (model || baseUrl || timeoutRaw) {
      llmConfig.backend = backend;
      if (baseUrl) {
        llmConfig.base_url = baseUrl;
      }
      if (model) {
        llmConfig.model = model;
      }
      if (timeoutNum && Number.isFinite(timeoutNum) && timeoutNum > 0) {
        llmConfig.timeout_seconds = timeoutNum;
      }
    }
  }

  if (Object.keys(llmConfig).length > 0) {
    payload.llm_config = llmConfig;
  }
  return payload;
}

function setupFormSubmit() {
  const form = getById("generate-form");
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    hideError();
    setLoading(true);
    getById("result-card").hidden = true;

    try {
      const payload = buildPayloadFromForm();
      const response = await fetchJsonWithTimeout(
        "/generate",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        },
        30000
      );

      if (!response.ok) {
        let detail = `HTTP ${response.status}`;
        try {
          const errorData = await response.json();
          if (errorData && errorData.detail) {
            detail = `${detail}: ${errorData.detail}`;
          }
        } catch (_error) {
          const text = await response.text();
          if (text) {
            detail = `${detail}: ${text}`;
          }
        }
        throw new Error(detail);
      }

      let data;
      try {
        data = await response.json();
      } catch (_error) {
        throw new Error("Не удалось разобрать JSON из ответа /generate");
      }
      renderSheet(data);
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") {
        showError("Превышено время ожидания запроса");
      } else {
        showError(error instanceof Error ? error.message : "Неизвестная ошибка");
      }
    } finally {
      setLoading(false);
    }
  });
}

window.addEventListener("DOMContentLoaded", async () => {
  setupLlmControls();
  setupClassChangeHandler();
  setupCopyJson();
  setupFormSubmit();
  await loadClasses();
});
