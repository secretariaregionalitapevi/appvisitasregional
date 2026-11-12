
(() => {
  const municipality = document.querySelector('#gem-city');
  const common = document.querySelector('#gem-common');
  if (!municipality || !common) return;

  function updateCommonOptions() {
    const map = window.gemCommonsByMunicipality || {};
    const selectedMunicipalities = [...municipality.selectedOptions].map((option) => option.value);
    const available = selectedMunicipalities.length
      ? selectedMunicipalities.flatMap((value) => map[value] || [])
      : window.gemAllCommons || [];
    const selectedCommons = new Set([...common.selectedOptions].map((option) => option.value));
    common.replaceChildren(...[...new Set(available)].sort().map((value) => {
      const option = new Option(value, value);
      option.selected = selectedCommons.has(value);
      return option;
    }));
    common.nextElementSibling?._sync?.();
  }

  municipality.addEventListener('change', updateCommonOptions, true);
  window.addEventListener('gem-common-options-ready', updateCommonOptions);
  if (window.gemCommonsByMunicipality) updateCommonOptions();
})();
