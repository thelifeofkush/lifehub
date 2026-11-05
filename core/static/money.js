(() => {
  const search = document.querySelector('#transaction-search');
  const rows = [...document.querySelectorAll('.transaction-row')];
  search?.addEventListener('input', () => {
    const query = search.value.trim().toLocaleLowerCase();
    let visible = 0;
    for (const row of rows) {
      row.hidden = !row.dataset.search.toLocaleLowerCase().includes(query);
      if (!row.hidden) visible++;
    }
    document.querySelector('#search-empty').hidden = visible > 0 || rows.length === 0;
    document.querySelector('.transaction-count').textContent = `${visible} transaction${visible === 1 ? '' : 's'}`;
  });
})();
