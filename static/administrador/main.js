document.addEventListener("DOMContentLoaded", () => {
  const searchInput = document.querySelector("#search-input");
  const productCards = [...document.querySelectorAll(".catalog-item")];
  const filterButtons = [...document.querySelectorAll(".category-pill")];
  const emptyMessage = document.querySelector("#no-product-results");
  let activeBrand = "all";

  const normalize = (value) =>
    value.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().trim();

  const filterProducts = () => {
    const query = normalize(searchInput?.value ?? "");
    let visibleCount = 0;

    productCards.forEach((card) => {
      const matchesSearch = normalize(card.dataset.search ?? "").includes(query);
      const matchesBrand =
        activeBrand === "all" || normalize(card.dataset.brand ?? "") === activeBrand;
      const isVisible = matchesSearch && matchesBrand;
      card.hidden = !isVisible;
      if (isVisible) visibleCount += 1;
    });

    if (emptyMessage) {
      emptyMessage.hidden = productCards.length === 0 || visibleCount > 0;
    }
  };

  searchInput?.addEventListener("input", filterProducts);
  filterButtons.forEach((button) => {
    button.addEventListener("click", () => {
      activeBrand = normalize(button.dataset.filter ?? "all");
      filterButtons.forEach((item) => {
        item.classList.remove("bg-primary-container", "text-on-primary");
        item.classList.add("bg-surface-container-lowest", "text-on-surface-variant");
      });
      button.classList.remove("bg-surface-container-lowest", "text-on-surface-variant");
      button.classList.add("bg-primary-container", "text-on-primary");
      filterProducts();
    });
  });
});
