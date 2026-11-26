(() => {
    const errors = new WeakMap();
    let nextErrorId = 0;

    function fieldName(field) {
        const label = field.labels && field.labels.length
            ? field.labels[0].textContent.trim()
            : field.previousElementSibling &&
              field.previousElementSibling.tagName === "LABEL"
                ? field.previousElementSibling.textContent.trim()
                : "";
        return label ||
            field.getAttribute("aria-label") ||
            field.getAttribute("placeholder") ||
            field.name.replace(/[_-]+/g, " ") ||
            "este campo";
    }

    function isEmpty(field) {
        return field.type === "password"
            ? field.value.length === 0
            : field.value.trim().length === 0;
    }

    function clearFieldError(field) {
        const error = errors.get(field);
        if (error) {
            error.remove();
            errors.delete(field);
            const describedBy = (field.getAttribute("aria-describedby") || "")
                .split(/\s+/)
                .filter(id => id && id !== error.id);
            if (describedBy.length) {
                field.setAttribute("aria-describedby", describedBy.join(" "));
            } else {
                field.removeAttribute("aria-describedby");
            }
        }
        field.setCustomValidity("");
        field.removeAttribute("aria-invalid");
        field.classList.remove("campo-invalido");
    }

    function showFieldError(field, message) {
        let error = errors.get(field);
        if (!error) {
            error = document.createElement("small");
            error.id = `erro-campo-${++nextErrorId}`;
            error.className = "erro-campo";
            error.setAttribute("role", "alert");
            field.insertAdjacentElement("afterend", error);
            errors.set(field, error);
        }

        error.textContent = message;
        field.setCustomValidity(message);
        field.setAttribute("aria-invalid", "true");
        field.classList.add("campo-invalido");
        const describedBy = (field.getAttribute("aria-describedby") || "")
            .split(/\s+/)
            .filter(Boolean);
        if (!describedBy.includes(error.id)) {
            describedBy.push(error.id);
        }
        field.setAttribute("aria-describedby", describedBy.join(" "));
    }

    function validateField(field) {
        clearFieldError(field);
        if (field.required && isEmpty(field)) {
            showFieldError(field, `Preencha o campo ${fieldName(field)}.`);
            return false;
        }
        if (!field.checkValidity()) {
            showFieldError(field, field.validationMessage);
            return false;
        }
        return true;
    }

    function validateFields(fields) {
        let firstInvalid = null;
        for (const field of fields) {
            if (!validateField(field) && !firstInvalid) {
                firstInvalid = field;
            }
        }
        if (firstInvalid) {
            firstInvalid.focus();
            return false;
        }
        return true;
    }

    document.querySelectorAll("form").forEach(form => {
        form.noValidate = true;
        form.addEventListener("submit", event => {
            const fields = Array.from(form.elements).filter(
                field => field.willValidate
            );
            if (!validateFields(fields)) {
                event.preventDefault();
            }
        });
    });

    document.addEventListener("input", event => {
        const field = event.target;
        if (errors.has(field)) {
            validateField(field);
        }
    });

    document.addEventListener("change", event => {
        const field = event.target;
        if (errors.has(field)) {
            validateField(field);
        }
    });

    window.validateRequiredFields = validateFields;
})();
