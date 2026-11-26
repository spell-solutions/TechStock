(() => {
    const form = document.getElementById("busca-inventario");
    const input = document.getElementById("busca-inventario-input");
    if (!form || !input) {
        return;
    }

    const categories = Array.from(
        document.querySelectorAll("[data-categoria-inventario]")
    );
    const emptyMessage = document.querySelector("[data-inventario-vazio]");
    const clearLink = form.querySelector("[data-limpar-busca]");
    const normalize = value =>
        value
            .normalize("NFD")
            .replace(/[\u0300-\u036f]/g, "")
            .toLocaleLowerCase("pt-BR");

    function filterProducts() {
        const query = normalize(input.value.trim());
        let visibleCount = 0;

        categories.forEach(category => {
            const rows = Array.from(
                category.querySelectorAll("[data-produto-inventario]")
            );
            let categoryCount = 0;

            rows.forEach(row => {
                const matches =
                    !query || normalize(row.dataset.busca || "").includes(query);
                row.hidden = !matches;
                if (matches) {
                    categoryCount += 1;
                }
            });

            visibleCount += categoryCount;
            category.hidden = Boolean(query) && categoryCount === 0;
            category.open = Boolean(query) && categoryCount > 0;

            const count = category.querySelector("[data-contagem-categoria]");
            count.textContent = `${categoryCount} ${
                categoryCount === 1 ? "produto" : "produtos"
            }`;
        });

        if (emptyMessage) {
            emptyMessage.hidden = visibleCount > 0;
            emptyMessage.textContent = query
                ? "Nenhum produto corresponde à pesquisa."
                : "Nenhum produto encontrado.";
        }
    }

    input.addEventListener("input", filterProducts);
    form.addEventListener("submit", event => {
        event.preventDefault();
        filterProducts();
    });
    clearLink?.addEventListener("click", event => {
        event.preventDefault();
        input.value = "";
        filterProducts();
        input.focus();
    });

    filterProducts();
})();
