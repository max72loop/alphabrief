document.addEventListener('DOMContentLoaded', function() {
    var container = document.getElementById('sections-container');
    if (!container) return;

    var ticker = container.dataset.ticker;

    Sortable.create(container, {
        handle: '.section-handle',
        animation: 200,
        ghostClass: 'section-ghost',
        chosenClass: 'section-chosen',
        onEnd: function() {
            var sections = Array.from(container.children).map(function(el) {
                return el.dataset.section;
            });
            saveLayout(ticker, sections);
        }
    });

    function saveLayout(ticker, sections) {
        fetch('/detail/save-layout', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ticker: ticker, sections: sections })
        });
    }
});
