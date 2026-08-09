/* ============================================================
   États de sortie — design & paramètres partagés
   Réutilise la logique de la facture : nom/slogan/adresse/tél/
   email/RCCM de l'entreprise, design (moderne/classique/minimal)
   et couleur principale définis dans les paramètres.
   ============================================================ */

function escHtmlEtats(t) {
    if (t === null || t === undefined) return '';
    return String(t).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

async function chargerParamsEntreprise() {
    try {
        const r = await fetch('/api/settings');
        const d = await r.json();
        return (d && d.parametres) ? d.parametres : {};
    } catch (e) {
        return {};
    }
}

function genererEnTeteEtat(entreprise, titreDocument, opts) {
    opts = opts || {};
    const design = entreprise.facture_design || 'moderne';
    const nomEnt = (entreprise.nom_entreprise || '').trim() || 'MotoStockIA';
    const slogan = (entreprise.slogan || '').trim();
    const adresse = (entreprise.adresse || '').trim();
    const rccm = (entreprise.rccm || '').trim();
    const tel = (entreprise.telephone || '').trim();
    const email = (entreprise.email || '').trim();

    const showEnt = entreprise.facture_afficher_entreprise !== 'false';
    const showSlogan = entreprise.facture_afficher_slogan !== 'false';
    const showAdresse = entreprise.facture_afficher_adresse !== 'false';
    const showTel = entreprise.facture_afficher_telephone !== 'false';
    const showEmail = entreprise.facture_afficher_email !== 'false';
    const showRccm = entreprise.facture_afficher_rccm !== 'false';

    const coordonnees = [];
    if (showAdresse && adresse) coordonnees.push(escHtmlEtats(adresse));
    if (showRccm && rccm) coordonnees.push('RCCM: ' + escHtmlEtats(rccm));
    if (showTel && tel) coordonnees.push('Tél: ' + escHtmlEtats(tel));
    if (showEmail && email) coordonnees.push(escHtmlEtats(email));

    const now = new Date();
    const dateStr = now.toLocaleDateString('fr-FR', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' });
    const heureStr = now.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' });

    const metaLignes = [];
    if (opts.metaExtra && opts.metaExtra.length) {
        opts.metaExtra.forEach(function (ligne) { metaLignes.push(escHtmlEtats(ligne)); });
    }
    metaLignes.push(dateStr + ' — ' + heureStr);

    let html = '<div class="etat-header etat-' + design + '">';
    html += '<div class="etat-header-left">';
    if (showEnt) {
        html += '<div class="etat-brand">' + escHtmlEtats(nomEnt) + '</div>';
        if (showSlogan && slogan) html += '<div class="etat-slogan">' + escHtmlEtats(slogan) + '</div>';
        if (coordonnees.length) html += '<div class="etat-coord">' + coordonnees.join('<span class="etat-sep"> | </span>') + '</div>';
    } else {
        html += '<div class="etat-coord">' + (coordonnees.join('<span class="etat-sep"> | </span>')) + '</div>';
    }
    html += '</div>';
    html += '<div class="etat-header-right">';
    html += '<div class="etat-title">' + escHtmlEtats(titreDocument) + '</div>';
    if (opts.reference) html += '<div class="etat-subtitle">' + escHtmlEtats(opts.reference) + '</div>';
    html += '<div class="etat-meta">' + metaLignes.join('<br>') + '</div>';
    html += '</div></div>';
    return html;
}

async function injecterEnTeteEtat(elementId, titreDocument, opts) {
    const entreprise = await chargerParamsEntreprise();
    const el = document.getElementById(elementId);
    if (el) {
        el.innerHTML = '<style>' + cssEtats(entreprise) + '</style>' + genererEnTeteEtat(entreprise, titreDocument, opts);
    }
    return entreprise;
}

function cssEtats(entreprise) {
    const design = entreprise.facture_design || 'moderne';
    const couleur = entreprise.couleur_principale || '#1e3a8a';
    let css = '';
    css += '.etat-header { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; padding-bottom: 14px; margin-bottom: 22px; }';
    css += '.etat-brand { font-size: 1.5rem; font-weight: 900; letter-spacing: -0.5px; }';
    css += '.etat-slogan { font-size: 0.8rem; color: #475569; font-style: italic; }';
    css += '.etat-coord { font-size: 0.78rem; color: #475569; margin-top: 4px; max-width: 460px; }';
    css += '.etat-sep { margin: 0 4px; opacity: 0.6; }';
    css += '.etat-header-right { text-align: right; }';
    css += '.etat-title { font-size: 1.15rem; font-weight: 900; letter-spacing: 1px; text-transform: uppercase; }';
    css += '.etat-subtitle { font-size: 0.85rem; color: #334155; font-weight: 700; }';
    css += '.etat-meta { font-size: 0.76rem; color: #64748b; }';

    if (design === 'classique') {
        css += '.etat-header { text-align: center; border: 2px double #1f2937; padding: 18px 16px; flex-direction: column; }';
        css += '.etat-header-left, .etat-header-right { width: 100%; text-align: center; }';
        css += '.etat-brand { font-size: 1.6rem; letter-spacing: 2px; color: #1f2937; }';
        css += '.etat-title { font-size: 1.3rem; letter-spacing: 4px; margin-top: 8px; border-top: 1px solid #1f2937; padding-top: 6px; color: ' + couleur + '; }';
    } else if (design === 'minimal') {
        css += '.etat-header { border-bottom: 1px solid #e5e7eb; }';
        css += '.etat-brand { letter-spacing: 3px; text-transform: uppercase; color: #111827; }';
        css += '.etat-title { font-weight: 300; letter-spacing: 2px; color: ' + couleur + '; }';
    } else {
        css += '.etat-header { border-bottom: 3px solid ' + couleur + '; }';
        css += '.etat-brand { color: #0f172a; }';
        css += '.etat-title { color: ' + couleur + '; }';
    }

    css += '.etat-table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }';
    css += '.etat-table th { padding: 9px 10px; text-align: left; font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.5px; border-bottom: 2px solid ' + couleur + '; color: #334155; }';
    css += '.etat-table .num { text-align: right; }';
    css += '.etat-table td { padding: 8px 10px; border-bottom: 1px solid #e2e8f0; vertical-align: middle; }';
    css += '.etat-table tr:nth-child(even) { background: #f8fafc; }';
    css += '.etat-table .gras { font-weight: 700; }';
    css += '.etat-badge { display: inline-block; padding: 3px 10px; border-radius: 20px; font-weight: 700; font-size: 0.68rem; }';
    css += '.etat-badge.disponible { background: #d1fae5; color: #065f46; }';
    css += '.etat-badge.faible { background: #fef3c7; color: #92400e; }';
    css += '.etat-badge.epuise { background: #fee2e2; color: #991b1b; }';
    css += '.etat-note { font-size: 0.72rem; color: #94a3b8; margin-top: 16px; text-align: center; }';
    css += '.etat-footer { margin-top: 36px; padding-top: 14px; border-top: 1px solid #e2e8f0; text-align: center; color: #94a3b8; font-size: 0.72rem; }';
    css += '.etat-box { margin-top: 26px; padding: 20px; background: #f8fafc; border-left: 4px solid ' + couleur + '; border-radius: 8px; }';
    css += '.etat-box h4 { margin: 0 0 14px; color: #1e293b; font-size: 0.9rem; text-transform: uppercase; letter-spacing: 0.5px; }';
    css += '.etat-row { display: flex; justify-content: space-between; padding: 7px 0; border-bottom: 1px solid #e2e8f0; font-size: 0.85rem; }';
    css += '.etat-row:last-child { border-bottom: none; }';
    css += '.etat-row .gras { font-weight: 700; }';
    css += '.etat-total { background: ' + couleur + '; color: #fff; padding: 14px 18px; border-radius: 8px; font-weight: 700; font-size: 1rem; margin-top: 14px; }';
    return css;
}

function ouvrirDocumentImpression(titreDocument, corpsHtml, entreprise) {
    const design = (entreprise && entreprise.facture_design) || 'moderne';
    const printWindow = window.open('', '_blank');
    if (!printWindow) {
        alert('Veuillez autoriser les fenêtres pop-up pour imprimer le document.');
        return;
    }
    const html = '<!DOCTYPE html><html><head><meta charset="UTF-8">'
        + '<title>' + escHtmlEtats(titreDocument) + '</title>'
        + '<style>'
        + '* { box-sizing: border-box; }'
        + 'body { margin: 0; padding: 24px; background: #f1f5f9; font-family: "Segoe UI", system-ui, -apple-system, sans-serif; color: #0f172a; }'
        + '.etat-sheet { background: #fff; max-width: 1100px; margin: 0 auto; padding: 36px 34px; border-radius: 6px; box-shadow: 0 2px 10px rgba(15,23,42,0.06); }'
        + cssEtats(entreprise)
        + '@media print { body { background: #fff; padding: 0; } .etat-sheet { box-shadow: none; border-radius: 0; padding: 22px 10px; max-width: 100%; } .etat-header, .etat-total { -webkit-print-color-adjust: exact; print-color-adjust: exact; } }'
        + '</style></head><body><div class="etat-sheet etat-' + design + '">'
        + corpsHtml
        + '</div>'
        + '<script>window.onload = function(){ window.print(); };<\/script>'
        + '</body></html>';
    printWindow.document.write(html);
    printWindow.document.close();
}

async function imprimerPageAvecEnTete(titreDocument) {
    const entreprise = await chargerParamsEntreprise();
    let el = document.getElementById('etatPrintHeader');
    if (!el) {
        el = document.createElement('div');
        el.id = 'etatPrintHeader';
        const cible = document.querySelector('.page-content') || document.querySelector('main') || document.body;
        cible.insertBefore(el, cible.firstChild);
    }
    el.innerHTML = '<style>'
        + '#etatPrintHeader { display: none; }'
        + '@media print { #etatPrintHeader { display: block !important; } .etat-header { -webkit-print-color-adjust: exact; print-color-adjust: exact; } }'
        + cssEtats(entreprise)
        + '</style>'
        + genererEnTeteEtat(entreprise, titreDocument);
    window.print();
}
