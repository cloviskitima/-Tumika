// Protection anti double-clic : empêche d'envoyer deux fois la même opération
// et affiche un petit chargement uniquement si l'opération prend du temps.
//
// Usage :
//   withSubmissionGuard(bouton, async () => { ... votre fetch ... });
// Le bouton est verrouillé pendant l'opération ; le spinner n'apparaît que
// si l'opération dépasse loadingDelay (400 ms par défaut). Les clics
// supplémentaires sont ignorés tant que l'opération est en cours.
window.withSubmissionGuard = function (btn, run, options) {
    if (!btn) return;
    var opts = Object.assign({ loadingDelay: 400, loadingText: 'Traitement…' }, options || {});
    if (btn.dataset.locked === '1') return;
    var original = btn.innerHTML;
    btn.dataset.locked = '1';
    btn.disabled = true;
    btn.style.opacity = '0.75';
    btn.style.cursor = 'wait';
    var timer = setTimeout(function () {
        if (btn.dataset.locked === '1') {
            btn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true" style="width:1rem;height:1rem;vertical-align:-2px;margin-right:8px;"></span>' + opts.loadingText;
        }
    }, opts.loadingDelay);
    function release() {
        clearTimeout(timer);
        btn.dataset.locked = '0';
        btn.disabled = false;
        btn.style.opacity = '';
        btn.style.cursor = '';
        btn.innerHTML = original;
    }
    Promise.resolve()
        .then(run)
        .then(release)
        .catch(function (err) {
            console.error('withSubmissionGuard:', err);
            release();
        });
};
