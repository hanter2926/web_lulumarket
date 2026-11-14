document.addEventListener("DOMContentLoaded", () => {
    const categorySelect = document.getElementById("id_category");
    const subcategorySelect = document.getElementById("id_subcategory");
    const valuesInput = document.getElementById("id_attributes_json");
    const container = document.getElementById("product-attribute-fields");
    if (!categorySelect || !subcategorySelect || !valuesInput || !container) return;

    const readValues = () => {
        try {
            const values = JSON.parse(valuesInput.value || "{}");
            return values && typeof values === "object" && !Array.isArray(values) ? values : {};
        } catch (error) {
            container.textContent = "The saved attribute values are invalid JSON. Correct them before saving.";
            throw error;
        }
    };

    const syncValues = () => {
        const values = {};
        container.querySelectorAll("[data-attribute-key]").forEach((input) => {
            const key = input.dataset.attributeKey;
            if (input.multiple) {
                const selected = Array.from(input.selectedOptions, (option) => option.value);
                if (selected.length) values[key] = selected;
            } else if (input.type === "checkbox") {
                values[key] = input.checked;
            } else if (input.value !== "") {
                if (input.type === "number" && input.step === "1") {
                    values[key] = Number.parseInt(input.value, 10);
                } else {
                    values[key] = input.value;
                }
            }
        });
        valuesInput.value = JSON.stringify(values);
    };

    const addLabel = (definition) => {
        const wrapper = document.createElement("div");
        wrapper.className = "col-md-6";
        const label = document.createElement("label");
        label.className = "form-label";
        label.htmlFor = `product-attribute-${definition.key}`;
        label.textContent = `${definition.label}${definition.required ? " *" : ""}${definition.unit ? ` (${definition.unit})` : ""}`;
        wrapper.appendChild(label);

        let input;
        if (definition.data_type === "dropdown" || definition.data_type === "multi_select" || definition.data_type === "boolean") {
            input = document.createElement("select");
            input.className = "form-select";
            if (definition.data_type === "multi_select") input.multiple = true;
            if (definition.data_type === "boolean") {
                input.add(new Option("Select", ""));
                input.add(new Option("Yes", "true"));
                input.add(new Option("No", "false"));
            } else {
                if (definition.data_type === "dropdown") input.add(new Option("Select", ""));
                definition.options.forEach((value) => input.add(new Option(value, value)));
            }
        } else {
            input = document.createElement("input");
            input.className = "form-control";
            if (definition.data_type === "integer" || definition.data_type === "decimal") {
                input.type = "number";
                input.step = definition.data_type === "integer" ? "1" : "any";
            } else if (definition.data_type === "date") {
                input.type = "date";
            } else {
                input.type = "text";
            }
        }
        input.id = `product-attribute-${definition.key}`;
        input.dataset.attributeKey = definition.key;
        input.required = Boolean(definition.required);
        input.addEventListener("input", syncValues);
        input.addEventListener("change", syncValues);
        wrapper.appendChild(input);
        container.appendChild(wrapper);
        return input;
    };

    const loadAttributes = async () => {
        const values = readValues();
        container.replaceChildren();
        if (!categorySelect.value) {
            valuesInput.value = "{}";
            return;
        }
        const params = new URLSearchParams({ category: categorySelect.value });
        if (subcategorySelect.value) params.set("subcategory", subcategorySelect.value);
        const response = await fetch(`/products/attributes/?${params.toString()}`);
        if (!response.ok) throw new Error("Unable to load category product fields.");
        const payload = await response.json();
        payload.attributes.forEach((definition) => {
            const input = addLabel(definition);
            const value = values[definition.key];
            if (input.multiple && Array.isArray(value)) {
                Array.from(input.options).forEach((option) => {
                    option.selected = value.includes(option.value);
                });
            } else if (definition.data_type === "boolean" && typeof value === "boolean") {
                input.value = String(value);
            } else if (value !== undefined && value !== null) {
                input.value = String(value);
            }
        });
        syncValues();
    };

    const loadSubcategories = async (reset) => {
        const selected = reset ? "" : subcategorySelect.value;
        subcategorySelect.replaceChildren(new Option("Select a subcategory", ""));
        if (!categorySelect.value) {
            valuesInput.value = "{}";
            return;
        }
        const response = await fetch(`/products/subcategories/?category=${encodeURIComponent(categorySelect.value)}`);
        if (!response.ok) throw new Error("Unable to load subcategories.");
        const payload = await response.json();
        (payload.results || payload).forEach((item) => {
            subcategorySelect.add(new Option(item.name, item.id));
        });
        if (selected && Array.from(subcategorySelect.options).some((option) => option.value === selected)) {
            subcategorySelect.value = selected;
        }
        await loadAttributes();
    };

    categorySelect.addEventListener("change", () => {
        loadSubcategories(true).catch((error) => {
            container.textContent = error.message;
        });
    });
    subcategorySelect.addEventListener("change", () => {
        loadAttributes().catch((error) => {
            container.textContent = error.message;
        });
    });
    loadSubcategories(false).catch((error) => {
        container.textContent = error.message;
    });
});
