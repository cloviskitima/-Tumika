/* =========================================================================
   Graphique de marche - moteur de dessin sur canvas, 100% local.

   Aucune bibliotheque externe : le graphique est dessine a la main sur un
   canvas, comme sur les terminaux de marche. Il affiche une serie de
   bougies journalières au format OHLC :

       O  ouverture    H  plus haut
       B  plus bas     C  clôture

   Plus un panneau de volume et un réticule qui suit la souris.

   Usage :
       const g = new GraphiqueMarche(canvas);
       g.setDonnees(candles);
   ========================================================================= */
(function (global) {
    'use strict';

    var PALETTE = {
        hausse: '#16a34a',
        hausseBord: '#15803d',
        baisse: '#dc2626',
        baisseBord: '#b91c1c',
        neutre: '#94a3b8',
        grille: 'rgba(148, 163, 184, 0.16)',
        grilleForte: 'rgba(148, 163, 184, 0.32)',
        axe: '#64748b',
        texte: '#334155',
        texteDoux: '#64748b',
        fondVoile: 'rgba(255, 255, 255, 0.94)',
        reticule: 'rgba(100, 116, 139, 0.6)',
        selec: 'rgba(30, 58, 138, 0.10)'
    };

    /* ---------- utilitaires ---------- */

    function borne(min, max) { return Math.min(min, max); }
    function maxi(a, b) { return Math.max(a, b); }

    /* Choisit une graduation "ronde" (1, 2, 2.5, 5, 10 x 10^n) */
    function pasJoli(cible) {
        if (!isFinite(cible) || cible <= 0) return 1;
        var brut = Math.pow(10, Math.floor(Math.log(cible) / Math.LN10));
        var norm = cible / brut;
        var pas;
        if (norm <= 1) pas = 1;
        else if (norm <= 2) pas = 2;
        else if (norm <= 2.5) pas = 2.5;
        else if (norm <= 5) pas = 5;
        else pas = 10;
        return pas * brut;
    }

    function formatNombre(n) {
        var abs = Math.abs(n);
        if (abs >= 1e9) return (n / 1e9).toFixed(2).replace(/\.?0+$/, '') + ' Md';
        if (abs >= 1e6) return (n / 1e6).toFixed(2).replace(/\.?0+$/, '') + ' M';
        if (abs >= 1e3) return Math.round(n).toLocaleString('fr-FR');
        return String(Math.round(n * 100) / 100);
    }

    function formatJourCourt(iso) {
        var d = new Date(iso + 'T00:00:00');
        if (isNaN(d.getTime())) return iso;
        return d.toLocaleDateString('fr-FR', { day: '2-digit', month: 'short' });
    }

    function formatJourLong(iso) {
        var d = new Date(iso + 'T00:00:00');
        if (isNaN(d.getTime())) return iso;
        return d.toLocaleDateString('fr-FR', {
            weekday: 'long', day: '2-digit', month: 'long', year: 'numeric'
        });
    }

    /* ---------- repli ResizeObserver ----------
       Chart.js a besoin de ResizeObserver. Les navigateurs récents l'ont
       déjà ; sur une très ancienne version, le graphique ne s'afficherait
       pas du tout. Ce repli minimal garantit l'affichage dans tous les cas. */
    if (typeof global.ResizeObserver !== 'function') {
        global.ResizeObserver = function (callback) {
            this._callback = callback;
        };
        global.ResizeObserver.prototype.observe = function (cible) {
            var self = this;
            if (cible && cible.addEventListener) {
                cible.addEventListener('resize', function () {
                    if (self._callback) {
                        self._callback([{ target: cible, contentRect: {} }], self);
                    }
                });
            }
        };
        global.ResizeObserver.prototype.unobserve = function () {};
        global.ResizeObserver.prototype.disconnect = function () {};
    }

    /* =====================  moteur  ===================== */

    function GraphiqueMarche(canvas, options) {
        this.canvas = canvas;
        this.options = options || {};
        this.candles = [];
        this.survol = -1;
        this.progression = 0;
        this.pret = false;
        this._lierEvenements();
        this._redimensionner();
        var self = this;
        global.addEventListener('resize', function () { self._redimensionner(); });
    }

    GraphiqueMarche.prototype._lierEvenements = function () {
        var self = this;

        function positionSouris(evenement) {
            var rect = self.canvas.getBoundingClientRect();
            var clientX = evenement.touches && evenement.touches.length
                ? evenement.touches[0].clientX : evenement.clientX;
            var clientY = evenement.touches && evenement.touches.length
                ? evenement.touches[0].clientY : evenement.clientY;
            return { x: clientX - rect.left, y: clientY - rect.top };
        }

        function surbrillance(evenement) {
            if (!self.pret || !self.geometrie) return;
            var p = positionSouris(evenement);
            var index = self._indexSousPointeur(p.x);
            if (index !== self.survol) {
                self.survol = index;
                self.dessiner();
                if (typeof self.options.surReticule === 'function') {
                    self.options.surReticule(index >= 0 ? self.candles[index] : null, self.candles);
                }
            }
        }

        function sortie() {
            if (self.survol !== -1) {
                self.survol = -1;
                self.dessiner();
                if (typeof self.options.surReticule === 'function') {
                    self.options.surReticule(null, self.candles);
                }
            }
        }

        this.canvas.addEventListener('mousemove', surbrillance);
        this.canvas.addEventListener('mouseleave', sortie);
        this.canvas.addEventListener('touchstart', function (e) { surbrillance(e); }, { passive: true });
        this.canvas.addEventListener('touchmove', function (e) { surbrillance(e); }, { passive: true });
        this.canvas.addEventListener('touchend', sortie);
    };

    /* Dimension nette, quel que soit le zoom de l'écran */
    GraphiqueMarche.prototype._redimensionner = function () {
        var canvas = this.canvas;
        var rect = canvas.getBoundingClientRect();
        var largeur = Math.max(1, Math.round(rect.width || canvas.clientWidth || 600));
        var hauteur = Math.max(1, Math.round(rect.height || canvas.clientHeight || 320));
        var ratio = global.devicePixelRatio || 1;

        canvas.width = Math.round(largeur * ratio);
        canvas.height = Math.round(hauteur * ratio);
        this.largeur = largeur;
        this.hauteur = hauteur;
        this.ratio = ratio;

        var ctx = canvas.getContext('2d');
        if (ctx && ctx.setTransform) ctx.setTransform(ratio, 0, 0, ratio, 0, 0);

        this.dessiner();
    };

    GraphiqueMarche.prototype.setDonnees = function (candles) {
        this.candles = candles || [];
        this.survol = -1;
        this._calculerBornes();
        this._animer();
    };

    GraphiqueMarche.prototype._calculerBornes = function () {
        var c = this.candles;
        var min = Infinity, max = -Infinity, volMax = 0;
        for (var i = 0; i < c.length; i++) {
            var b = c[i];
            if (!b) continue;
            if (b.b < min) min = b.b;
            if (b.h > max) max = b.h;
            if (b.c > max) max = b.c;
            if (b.o > max) max = b.o;
            if (b.v > volMax) volMax = b.v;
        }
        if (!isFinite(min) || !isFinite(max)) { min = 0; max = 1; }
        if (min === max) { min = Math.max(0, min - 1); max = max + 1; }
        var marge = (max - min) * 0.08;
        this.minY = Math.max(0, min - marge);
        this.maxY = max + marge;
        this.volMax = volMax > 0 ? volMax : 1;
    };

    GraphiqueMarche.prototype._animer = function () {
        var self = this;
        this.progression = 0;
        this.pret = false;
        var debut = null;
        var duree = 620;

        function pas(maintenant) {
            if (debut === null) debut = maintenant;
            var t = maintenant - debut;
            var p = Math.min(1, t / duree);
            // adoucissement (ease out cubic)
            self.progression = 1 - Math.pow(1 - p, 3);
            self.dessiner();
            if (p < 1) {
                global.requestAnimationFrame(pas);
            } else {
                self.pret = true;
                self.dessiner();
            }
        }
        if (typeof global.requestAnimationFrame === 'function') {
            global.requestAnimationFrame(pas);
        } else {
            this.progression = 1;
            this.pret = true;
            this.dessiner();
        }
    };

    /* Géométrie : marges, zone prix, zone volume */
    GraphiqueMarche.prototype._calculerGeometrie = function () {
        var margeGauche = 8;
        var margeDroite = 68;
        var margeHaut = 10;
        var margeBas = 26;
        var hauteurVolume = this.candles.length ? Math.min(64, Math.max(38, this.hauteur * 0.20)) : 0;
        var espaceVolumes = hauteurVolume + 8;

        this.geometrie = {
            gauche: margeGauche,
            droite: this.largeur - margeDroite,
            haut: margeHaut,
            bas: this.hauteur - margeBas - espaceVolumes,
            hautVolume: this.hauteur - margeBas - hauteurVolume,
            basVolume: this.hauteur - margeBas,
            largeurTrace: this.largeur - margeDroite - margeGauche
        };
        return this.geometrie;
    };

    GraphiqueMarche.prototype._indexSousPointeur = function (x) {
        var g = this.geometrie;
        if (!g || !this.candles.length) return -1;
        var n = this.candles.length;
        var pasColonne = g.largeurTrace / n;
        if (pasColonne <= 0) return -1;
        var index = Math.floor((x - g.gauche) / pasColonne);
        if (index < 0 || index >= n) return -1;
        return index;
    };

    GraphiqueMarche.prototype._y = function (valeur) {
        var g = this.geometrie;
        var ratio = (valeur - this.minY) / (this.maxY - this.minY);
        return g.bas - ratio * (g.bas - g.haut);
    };

    GraphiqueMarche.prototype._x = function (index) {
        var g = this.geometrie;
        var n = this.candles.length;
        var pasColonne = g.largeurTrace / n;
        return g.gauche + pasColonne * index + pasColonne / 2;
    };

    /* =====================  dessin  ===================== */

    GraphiqueMarche.prototype.dessiner = function () {
        var ctx = this.canvas.getContext('2d');
        if (!ctx) return;

        var L = this.largeur, H = this.hauteur;
        ctx.clearRect(0, 0, L, H);

        var g = this._calculerGeometrie();
        var c = this.candles;
        var i;

        if (!c.length) return;

        /* ---- grille horizontale + échelle des prix ---- */
        var pasY = pasJoli((this.maxY - this.minY) / 5);
        ctx.save();
        ctx.font = '11px system-ui, -apple-system, "Segoe UI", Roboto, sans-serif';
        ctx.textAlign = 'left';
        ctx.textBaseline = 'middle';

        var premiereLigne = true;
        for (var v = Math.ceil(this.minY / pasY) * pasY; v <= this.maxY; v += pasY) {
            var y = this._y(v);
            if (y < g.haut - 1 || y > g.bas + 1) continue;
            ctx.strokeStyle = premiereLigne ? PALETTE.grille : PALETTE.grille;
            ctx.lineWidth = 1;
            ctx.beginPath();
            // demi-pixel pour une ligne nette
            ctx.moveTo(g.gauche, Math.round(y) + 0.5);
            ctx.lineTo(g.droite, Math.round(y) + 0.5);
            ctx.stroke();

            ctx.fillStyle = PALETTE.axe;
            ctx.fillText(formatNombre(v), g.droite + 8, y);
            premiereLigne = false;
        }
        ctx.restore();

        /* ---- grille verticale + dates ---- */
        var nbCols = c.length;
        var pasColonne = g.largeurTrace / nbCols;
        // on n'écrit une date que si la place le permet
        var uneDateSur = Math.max(1, Math.ceil(64 / pasColonne));

        ctx.save();
        ctx.font = '11px system-ui, -apple-system, "Segoe UI", Roboto, sans-serif';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'top';
        for (i = 0; i < nbCols; i += uneDateSur) {
            var x = this._x(i);
            ctx.strokeStyle = PALETTE.grille;
            ctx.beginPath();
            ctx.moveTo(Math.round(x) + 0.5, g.haut);
            ctx.lineTo(Math.round(x) + 0.5, g.bas);
            ctx.stroke();

            ctx.fillStyle = PALETTE.axe;
            ctx.fillText(formatJourCourt(c[i].jour), x, g.basVolume + 6);
        }
        ctx.restore();

        /* ---- zone sélectionnée au survol ---- */
        if (this.survol >= 0 && this.survol < nbCols) {
            ctx.save();
            ctx.fillStyle = PALETTE.selec;
            var xSel = this._x(this.survol);
            ctx.fillRect(xSel - pasColonne / 2, g.haut, pasColonne, g.bas - g.haut);
            ctx.restore();
        }

        /* ---- panneaux de volume ---- */
        var hauteurVol = g.basVolume - g.hautVolume;
        if (hauteurVol > 0) {
            ctx.save();
            ctx.strokeStyle = PALETTE.grilleForte;
            ctx.beginPath();
            ctx.moveTo(g.gauche, Math.round(g.hautVolume) + 0.5);
            ctx.lineTo(g.droite, Math.round(g.hautVolume) + 0.5);
            ctx.stroke();
            ctx.restore();
        }

        /* ---- bougies + volumes ---- */
        var largeurCorps = Math.max(1, Math.min(14, pasColonne * 0.62));
        var demi = largeurCorps / 2;
        var p = this.progression;

        for (i = 0; i < nbCols; i++) {
            var b = c[i];
            if (!b) continue;

            var x = this._x(i);
            var monte = b.c >= b.o;
            var sansActivite = !b.v;
            var couleur = sansActivite ? PALETTE.neutre : (monte ? PALETTE.hausse : PALETTE.baisse);
            var couleurBord = sansActivite ? PALETTE.neutre : (monte ? PALETTE.hausseBord : PALETTE.baisseBord);

            // Apparition : les bougies « poussent » de bas en haut
            var anim = 1;
            if (p < 1) {
                var debutIdx = i / nbCols;
                var avancee = (p - debutIdx * 0.35) / 0.65;
                anim = avancee < 0 ? 0 : (avancee > 1 ? 1 : avancee);
            }

            var yHaut = this._y(b.h);
            var yBas = this._y(b.b);
            var yOuv = this._y(b.o);
            var yClo = this._y(b.c);

            // mèche
            ctx.save();
            ctx.strokeStyle = couleurBord;
            ctx.lineWidth = 1;
            if (sansActivite) ctx.setLineDash([2, 3]);
            var hautMche = yHaut + (yBas - yHaut) * (1 - anim);
            var basMche = yBas;
            ctx.beginPath();
            ctx.moveTo(Math.round(x) + 0.5, hautMche);
            ctx.lineTo(Math.round(x) + 0.5, basMche);
            ctx.stroke();
            ctx.restore();

            if (sansActivite) {
                // jour sans vente : simple tiret au niveau du dernier prix connu
                ctx.save();
                ctx.strokeStyle = PALETTE.neutre;
                ctx.lineWidth = 1;
                var yTiret = (yHaut + yBas) / 2;
                ctx.beginPath();
                ctx.moveTo(x - demi, yTiret);
                ctx.lineTo(x + demi, yTiret);
                ctx.stroke();
                ctx.restore();
            } else {
                // corps
                var hautCorps = borne(yOuv, yClo);
                var basCorps = maxi(yOuv, yClo);
                var hauteur = Math.max(1, (basCorps - hautCorps) * anim);
                var hautAnime = basCorps - hauteur;

                ctx.save();
                if (monte) {
                    // bougie ascendante : corps creux, comme sur les terminaux
                    ctx.strokeStyle = couleur;
                    ctx.lineWidth = 1.4;
                    ctx.strokeRect(Math.round(x - demi) + 0.5, Math.round(hautAnime) + 0.5,
                        Math.round(largeurCorps), Math.round(hauteur));
                } else {
                    ctx.fillStyle = couleur;
                    ctx.fillRect(Math.round(x - demi), Math.round(hautAnime),
                        Math.round(largeurCorps), Math.round(hauteur));
                }
                ctx.restore();
            }

            // volume
            if (hauteurVol > 0 && b.v > 0) {
                var hVol = (b.v / this.volMax) * (hauteurVol - 4) * anim;
                ctx.save();
                ctx.fillStyle = sansActivite ? PALETTE.neutre
                    : (monte ? 'rgba(22, 163, 74, 0.55)' : 'rgba(220, 38, 38, 0.55)');
                ctx.fillRect(Math.round(x - demi), Math.round(g.basVolume - hVol),
                    Math.round(largeurCorps), Math.round(hVol));
                ctx.restore();
            }
        }

        /* ---- réticule ---- */
        if (this.survol >= 0 && this.survol < nbCols) {
            var bx = this._x(this.survol);
            var bb = c[this.survol];

            ctx.save();
            ctx.strokeStyle = PALETTE.reticule;
            ctx.setLineDash([4, 4]);
            ctx.lineWidth = 1;

            ctx.beginPath();
            ctx.moveTo(Math.round(bx) + 0.5, g.haut);
            ctx.lineTo(Math.round(bx) + 0.5, g.bas);
            ctx.stroke();

            var yCurs = this._y(bb.c);
            ctx.beginPath();
            ctx.moveTo(g.gauche, Math.round(yCurs) + 0.5);
            ctx.lineTo(g.droite, Math.round(yCurs) + 0.5);
            ctx.stroke();
            ctx.setLineDash([]);

            /* étiquette de prix sur l'axe de droite */
            var etiquette = formatNombre(bb.c);
            ctx.font = '11px system-ui, -apple-system, "Segoe UI", Roboto, sans-serif';
            var largeurEtiquette = ctx.measureText(etiquette).width + 12;
            ctx.fillStyle = bb.c >= bb.o ? PALETTE.hausse : PALETTE.baisse;
            ctx.beginPath();
            var ry = Math.round(yCurs) - 9;
            if (ctx.roundRect) {
                ctx.roundRect(g.droite + 2, ry, largeurEtiquette, 18, 3);
            } else {
                ctx.rect(g.droite + 2, ry, largeurEtiquette, 18);
            }
            ctx.fill();
            ctx.fillStyle = '#ffffff';
            ctx.textAlign = 'left';
            ctx.textBaseline = 'middle';
            ctx.fillText(etiquette, g.droite + 8, ry + 9);

            /* étiquette de date sous le graphique */
            var etiquetteDate = formatJourCourt(bb.jour);
            ctx.font = '11px system-ui, -apple-system, "Segoe UI", Roboto, sans-serif';
            var largeurDate = ctx.measureText(etiquetteDate).width + 12;
            ctx.fillStyle = '#1e3a8a';
            ctx.beginPath();
            var dy = g.basVolume + 3;
            if (ctx.roundRect) {
                ctx.roundRect(bx - largeurDate / 2, dy, largeurDate, 17, 3);
            } else {
                ctx.rect(bx - largeurDate / 2, dy, largeurDate, 17);
            }
            ctx.fill();
            ctx.fillStyle = '#ffffff';
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            ctx.fillText(etiquetteDate, bx, dy + 8.5);

            ctx.restore();
        }

        /* ---- mention de laperiode en bas a gauche ---- */
        ctx.save();
        ctx.font = '10px system-ui, -apple-system, "Segoe UI", Roboto, sans-serif';
        ctx.fillStyle = PALETTE.texteDoux;
        ctx.textAlign = 'left';
        ctx.textBaseline = 'bottom';
        ctx.fillText('Volume des ventes', g.gauche, g.hautVolume - 3);
        ctx.restore();
    };

    /* ---------- API publique ---------- */
    GraphiqueMarche.prototype.detruire = function () {
        this.canvas = null;
        this.candles = [];
    };

    GraphiqueMarche.formatJourLong = formatJourLong;
    GraphiqueMarche.formatNombre = formatNombre;

    global.GraphiqueMarche = GraphiqueMarche;
})(typeof window !== 'undefined' ? window : this);
